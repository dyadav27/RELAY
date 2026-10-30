from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..errors import bad_request, conflict, not_found
from ..logging_setup import get_logger
from ..models import (
    UNFINISHED_TASK_STATUSES,
    Decision,
    DecisionAlert,
    Meeting,
    MeetingTask,
    Project,
    Task,
    TaskEvent,
)
from ..schemas import TaskClose, TaskCreate, TaskReopen, TaskUpdate
from .common import aware, date_to_due, get_member, get_project, iso, member_names, now

log = get_logger("tasks")


def is_overdue(task: Task) -> bool:
    return task.status in UNFINISHED_TASK_STATUSES and task.due_at is not None and aware(task.due_at) < now()


def serialize_task(task: Task, names: dict[int, str]) -> dict:
    return {
        "id": task.id,
        "project_id": task.project_id,
        "title": task.title,
        "description": task.description,
        "owner_id": task.owner_id,
        "owner_name": names.get(task.owner_id) if task.owner_id else None,
        "origin_meeting_id": task.origin_meeting_id,
        "due_at": iso(task.due_at),
        "deadline_text": task.deadline_text,
        "acceptance_criteria": task.acceptance_criteria,
        "status": task.status,
        "priority": task.priority,
        "outcome": task.outcome,
        "version": task.version,
        "is_overdue": is_overdue(task),
        "created_at": iso(task.created_at),
        "updated_at": iso(task.updated_at),
        "completed_at": iso(task.completed_at),
    }


def serialize_event(ev: TaskEvent, names: dict[int, str]) -> dict:
    return {
        "id": ev.id,
        "task_id": ev.task_id,
        "event_type": ev.event_type,
        "actor_id": ev.actor_id,
        "actor_name": names.get(ev.actor_id) if ev.actor_id else "RELAY",
        "old_value": ev.old_value,
        "new_value": ev.new_value,
        "note": ev.note,
        "meeting_id": ev.meeting_id,
        "created_at": iso(ev.created_at),
    }


def add_event(db: Session, task: Task, event_type: str, actor_id: int | None, *, old=None, new=None, note=None,
              meeting_id=None) -> TaskEvent:
    ev = TaskEvent(task_id=task.id, actor_id=actor_id, event_type=event_type, old_value=old, new_value=new,
                   note=note, meeting_id=meeting_id)
    db.add(ev)
    return ev


def load_task(db: Session, task_id: int, project_id: int | None = None) -> Task:
    task = db.get(Task, task_id)
    if not task or (project_id is not None and task.project_id != project_id):
        raise not_found("Task", task_id)
    return task


def _check_version(task: Task, version: int) -> None:
    if task.version != version:
        raise conflict(
            "version_conflict",
            f"Task {task.id} was modified (current version {task.version}, you sent {version}). Reload and retry.",
            {"current_version": task.version},
        )


def create_task(db: Session, project: Project, *, title: str, description=None, owner_id=None, due_at=None,
                deadline_text=None, priority="medium", acceptance_criteria=None, origin_meeting_id=None,
                actor_id=None, evidence=None) -> Task:
    if owner_id is not None:
        get_member(db, project, owner_id, field="owner_id", must_be_active=True)
    if origin_meeting_id is not None:
        m = db.get(Meeting, origin_meeting_id)
        if not m or m.project_id != project.id:
            raise bad_request("invalid_meeting", f"Meeting {origin_meeting_id} is not part of this project.")
    task = Task(project_id=project.id, title=title.strip(), description=description, owner_id=owner_id,
                due_at=date_to_due(due_at), deadline_text=deadline_text, priority=priority,
                acceptance_criteria=acceptance_criteria, origin_meeting_id=origin_meeting_id, status="open")
    db.add(task)
    db.flush()
    add_event(db, task, "created", actor_id, new={"title": task.title, "owner_id": owner_id, "status": "open"},
              note=f"Evidence: {evidence}" if evidence else None, meeting_id=origin_meeting_id)
    if origin_meeting_id is not None:
        db.add(MeetingTask(meeting_id=origin_meeting_id, task_id=task.id, relationship_type="origin"))
    log.info("task_created", extra={"task_id": task.id, "project_id": project.id, "has_owner": owner_id is not None})
    return task


def create_task_from_request(db: Session, body: TaskCreate) -> Task:
    project = get_project(db, body.project_id)
    if body.actor_id is not None:
        get_member(db, project, body.actor_id, field="actor_id")
    task = create_task(db, project, **body.model_dump(exclude={"project_id"}))
    db.commit()
    return task


def update_task(db: Session, task_id: int, body: TaskUpdate) -> Task:
    task = load_task(db, task_id)
    project = get_project(db, task.project_id)
    actor = body.actor_id
    if actor is not None:
        get_member(db, project, actor, field="actor_id")
    _check_version(task, body.version)
    fields = body.model_fields_set
    names = member_names(db, project.workspace_id)
    changed = False

    simple_old, simple_new = {}, {}
    for f in ("title", "description", "priority", "deadline_text", "acceptance_criteria"):
        if f in fields and getattr(body, f) != getattr(task, f):
            if f in ("title", "priority") and getattr(body, f) is None:
                raise bad_request("invalid_field", f"{f} cannot be empty.")
            simple_old[f], simple_new[f] = getattr(task, f), getattr(body, f)
            setattr(task, f, getattr(body, f))
    if simple_new:
        add_event(db, task, "updated", actor, old=simple_old, new=simple_new, note=body.note)
        changed = True

    if "owner_id" in fields and body.owner_id != task.owner_id:
        if body.owner_id is not None:
            get_member(db, project, body.owner_id, field="owner_id", must_be_active=True)
        old = {"owner_id": task.owner_id, "owner_name": names.get(task.owner_id)}
        task.owner_id = body.owner_id
        add_event(db, task, "reassigned", actor, old=old,
                  new={"owner_id": body.owner_id, "owner_name": names.get(body.owner_id)}, note=body.note)
        log.info("task_reassigned", extra={"task_id": task.id, "from_owner": old["owner_id"], "to_owner": body.owner_id,
                                           "actor_id": actor})
        changed = True

    if "due_at" in fields:
        new_due = date_to_due(body.due_at)
        if iso(new_due) != iso(task.due_at):
            add_event(db, task, "deadline_changed", actor, old={"due_at": iso(task.due_at)},
                      new={"due_at": iso(new_due)}, note=body.note)
            task.due_at = new_due
            changed = True

    if body.status is not None and body.status != task.status:
        if task.status not in UNFINISHED_TASK_STATUSES:
            raise conflict("task_closed", f"Task is {task.status}. Use the reopen action with a reason first.")
        if body.status == "blocked" and not body.blocker_note:
            raise bad_request("blocker_note_required", "Describe the blocker when marking a task as blocked.")
        add_event(db, task, "status_changed", actor, old={"status": task.status}, new={"status": body.status},
                  note=body.blocker_note or body.note)
        task.status = body.status
        changed = True
    elif body.blocker_note:
        add_event(db, task, "blocker_recorded", actor, note=body.blocker_note)
        changed = True

    if not changed and body.note:
        add_event(db, task, "comment", actor, note=body.note)
        changed = True
    if not changed:
        raise bad_request("no_changes", "The request did not change anything.")
    task.updated_at = now()  # forces a versioned UPDATE even when only events were added
    db.commit()
    return task


def close_task(db: Session, task_id: int, body: TaskClose) -> Task:
    task = load_task(db, task_id)
    project = get_project(db, task.project_id)
    if body.actor_id is not None:
        get_member(db, project, body.actor_id, field="actor_id")
    _check_version(task, body.version)
    if task.status not in UNFINISHED_TASK_STATUSES:
        raise conflict("task_already_closed", f"Task is already {task.status}.")
    if not body.outcome.strip():
        raise bad_request("outcome_required", "A task cannot be closed without an outcome.")
    old = {"status": task.status}
    task.status = body.resolution
    task.outcome = body.outcome
    task.completed_at = now() if body.resolution == "completed" else None
    add_event(db, task, body.resolution, body.actor_id, old=old,
              new={"status": body.resolution, "outcome": body.outcome})
    db.commit()
    log.info("task_closed", extra={"task_id": task.id, "resolution": body.resolution, "actor_id": body.actor_id})
    return task


def reopen_task(db: Session, task_id: int, body: TaskReopen) -> Task:
    task = load_task(db, task_id)
    project = get_project(db, task.project_id)
    if body.actor_id is not None:
        get_member(db, project, body.actor_id, field="actor_id")
    _check_version(task, body.version)
    if task.status in UNFINISHED_TASK_STATUSES:
        raise conflict("task_not_closed", "Only completed or cancelled tasks can be reopened.")
    add_event(db, task, "reopened", body.actor_id, old={"status": task.status, "outcome": task.outcome},
              new={"status": "open"}, note=body.reason)
    task.status, task.outcome, task.completed_at = "open", None, None
    db.commit()
    log.info("task_reopened", extra={"task_id": task.id, "actor_id": body.actor_id})
    return task


def associate_with_meeting(db: Session, task: Task, meeting: Meeting, relationship_type: str,
                           actor_id: int | None, note: str | None = None) -> MeetingTask:
    """Attach an existing task to a meeting without duplicating it. Raises 409 on duplicate association."""
    if meeting.project_id != task.project_id:
        raise bad_request("cross_project", "Tasks can only be linked to meetings of the same project.")
    if relationship_type == "carried_forward" and task.status not in UNFINISHED_TASK_STATUSES:
        raise conflict("task_closed", f"Task {task.id} is {task.status}; it will not be reopened automatically. "
                                      "Reopen it explicitly with a reason before carrying it forward.")
    exists = db.scalar(select(MeetingTask).where(MeetingTask.meeting_id == meeting.id, MeetingTask.task_id == task.id))
    if exists:
        raise conflict("duplicate_association", f"Task {task.id} is already associated with meeting {meeting.id}.")
    link = MeetingTask(meeting_id=meeting.id, task_id=task.id, relationship_type=relationship_type)
    db.add(link)
    event = "carry_forward" if relationship_type == "carried_forward" else "linked_to_meeting"
    add_event(db, task, event, actor_id, new={"meeting_id": meeting.id, "meeting_title": meeting.title,
                                              "status": task.status, "owner_id": task.owner_id},
              note=note, meeting_id=meeting.id)
    if relationship_type == "carried_forward":
        log.info("task_carried_forward", extra={"task_id": task.id, "meeting_id": meeting.id, "actor_id": actor_id})
    return link


def carry_forward(db: Session, task_id: int, meeting_id: int, actor_id: int | None, note: str | None) -> Task:
    task = load_task(db, task_id)
    project = get_project(db, task.project_id)
    if actor_id is not None:
        get_member(db, project, actor_id, field="actor_id")
    meeting = db.get(Meeting, meeting_id)
    if not meeting or meeting.project_id != task.project_id:
        raise bad_request("invalid_meeting", f"Meeting {meeting_id} is not part of this task's project.")
    associate_with_meeting(db, task, meeting, "carried_forward", actor_id, note)
    db.commit()
    return task


def list_tasks(db: Session, project_id: int, *, owner_id=None, status=None, priority=None, q=None,
               overdue: bool | None = None) -> list[dict]:
    project = get_project(db, project_id)
    stmt = select(Task).where(Task.project_id == project_id)
    if owner_id is not None:  # owner_id=0 means "unassigned"
        stmt = stmt.where(Task.owner_id == owner_id) if owner_id else stmt.where(Task.owner_id.is_(None))
    if status:
        stmt = stmt.where(Task.status.in_(status.split(",")))
    if priority:
        stmt = stmt.where(Task.priority.in_(priority.split(",")))
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Task.title.ilike(like), Task.description.ilike(like)))
    names = member_names(db, project.workspace_id)
    tasks = [serialize_task(t, names) for t in db.scalars(stmt.order_by(Task.id))]
    if overdue is not None:
        tasks = [t for t in tasks if t["is_overdue"] == overdue]
    order = {"blocked": 0, "in_progress": 1, "open": 2, "completed": 3, "cancelled": 4}
    tasks.sort(key=lambda t: (order[t["status"]], t["due_at"] or "9999"))
    return tasks


def task_detail(db: Session, task_id: int) -> dict:
    task = load_task(db, task_id)
    project = get_project(db, task.project_id)
    names = member_names(db, project.workspace_id)
    links = db.execute(
        select(MeetingTask, Meeting).join(Meeting, Meeting.id == MeetingTask.meeting_id)
        .where(MeetingTask.task_id == task.id).order_by(Meeting.meeting_at)
    ).all()
    meeting_ids = [m.id for _, m in links]
    decisions = list(db.scalars(select(Decision).where(Decision.project_id == task.project_id,
                                                       Decision.meeting_id.in_(meeting_ids or [-1]))))
    flagged = [a for a in db.scalars(select(DecisionAlert).join(Meeting).where(Meeting.project_id == task.project_id))
               if task.id in (a.affected_task_ids or [])]
    flagged_decision_ids = {a.existing_decision_id for a in flagged}
    for d in db.scalars(select(Decision).where(Decision.id.in_(flagged_decision_ids or [-1]))):
        if d not in decisions:
            decisions.append(d)
    from .decisions import serialize_alert, serialize_decision  # local import avoids a cycle

    events = db.scalars(select(TaskEvent).where(TaskEvent.task_id == task.id).order_by(TaskEvent.created_at,
                                                                                       TaskEvent.id))
    return {
        "task": serialize_task(task, names),
        "project": {"id": project.id, "name": project.name},
        "meetings": [{"id": m.id, "title": m.title, "meeting_at": iso(m.meeting_at),
                      "relationship_type": link.relationship_type, "linked_at": iso(link.created_at)}
                     for link, m in links],
        "decisions": [serialize_decision(d, names) for d in decisions],
        "decision_alerts": [serialize_alert(db, a, names) for a in flagged],
        "events": [serialize_event(e, names) for e in events],
    }


def task_history(db: Session, task_id: int) -> list[dict]:
    task = load_task(db, task_id)
    project = get_project(db, task.project_id)
    names = member_names(db, project.workspace_id)
    events = db.scalars(select(TaskEvent).where(TaskEvent.task_id == task.id).order_by(TaskEvent.created_at,
                                                                                       TaskEvent.id))
    return [serialize_event(e, names) for e in events]
