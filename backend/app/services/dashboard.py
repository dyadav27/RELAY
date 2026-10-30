from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..models import UNFINISHED_TASK_STATUSES, Decision, Handover, Meeting, Task, TaskEvent, Workspace
from .common import aware, get_project, iso, member_names, now
from .decisions import list_alerts, serialize_decision
from .handovers import handover_detail
from .meetings import serialize_meeting
from .tasks import is_overdue, serialize_event


def dashboard(db: Session, project_id: int) -> dict:
    project = get_project(db, project_id)
    workspace = db.get(Workspace, project.workspace_id)
    names = member_names(db, project.workspace_id)
    tasks = list(db.scalars(select(Task).where(Task.project_id == project_id)))
    unfinished = [t for t in tasks if t.status in UNFINISHED_TASK_STATUSES]
    week_ago = now() - timedelta(days=7)
    alerts = list_alerts(db, project_id, "pending")

    meetings = db.scalars(select(Meeting).options(selectinload(Meeting.participants))
                          .where(Meeting.project_id == project_id).order_by(Meeting.meeting_at.desc()).limit(5))
    recent_meetings = []
    for m in meetings:
        row = serialize_meeting(db, m, names)
        key = db.scalar(select(Decision).where(Decision.meeting_id == m.id).order_by(Decision.id).limit(1))
        row["key_decision"] = {"code": f"DEC-{key.id:04d}", "statement": key.statement, "status": key.status} if key else None
        recent_meetings.append(row)

    decisions = db.scalars(select(Decision).where(Decision.project_id == project_id, Decision.approved_at.is_not(None))
                           .order_by(Decision.approved_at.desc()).limit(5))
    handover_id = db.scalar(select(Handover.id).where(Handover.project_id == project_id)
                            .order_by(Handover.created_at.desc()).limit(1))
    events = db.execute(select(TaskEvent, Task.title).join(Task, Task.id == TaskEvent.task_id)
                        .where(Task.project_id == project_id).order_by(TaskEvent.created_at.desc(), TaskEvent.id.desc())
                        .limit(8)).all()
    meeting_count = db.scalar(select(func.count()).select_from(Meeting).where(Meeting.project_id == project_id))
    return {
        "project": {"id": project.id, "name": project.name, "description": project.description},
        "workspace": {"id": workspace.id, "name": workspace.name},
        "is_demo_data": "(demo)" in workspace.name.lower(),
        "generated_at": iso(now()),
        "metrics": {
            "open_tasks": len(unfinished),
            "in_progress": sum(t.status == "in_progress" for t in unfinished),
            "blocked": sum(t.status == "blocked" for t in unfinished),
            "unassigned": sum(t.owner_id is None for t in unfinished),
            "overdue": sum(is_overdue(t) for t in unfinished),
            "completed_last_7d": sum(1 for t in tasks if t.status == "completed" and t.completed_at
                                     and aware(t.completed_at) >= week_ago),
            "completed_total": sum(t.status == "completed" for t in tasks),
            "pending_decision_alerts": len(alerts),
            "meetings": meeting_count,
        },
        "pending_alerts": alerts,
        "recent_meetings": recent_meetings,
        "recent_decisions": [serialize_decision(d, names) for d in decisions],
        "latest_handover": handover_detail(db, handover_id) if handover_id else None,
        "activity": [serialize_event(e, names) | {"task_title": title} for e, title in events],
    }
