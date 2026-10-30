"""Handover Copilot: SQL decides which work transfers; AI only narrates; approval is one transaction."""
import json

from sqlalchemy import select, update
from sqlalchemy.orm import Session, selectinload

from ..ai import prompts
from ..ai.client import AIClient, AIError
from ..ai.schemas import BriefItem, HandoverBriefAI
from ..errors import bad_request, conflict, not_found
from ..logging_setup import get_logger
from ..models import (
    UNFINISHED_TASK_STATUSES,
    Decision,
    Document,
    Handover,
    HandoverTask,
    Meeting,
    MeetingTask,
    Task,
    TaskEvent,
)
from ..schemas import HandoverApprove, HandoverGenerate
from .common import get_member, get_project, iso, member_names, now
from .decisions import serialize_decision
from .tasks import add_event, serialize_event, serialize_task

log = get_logger("handovers")


def clean_refs(items: list[BriefItem], allowed: set[str]) -> tuple[list[dict], int]:
    out, dropped = [], 0
    for it in items:
        keep = [r for r in it.refs if r in allowed]
        dropped += len(it.refs) - len(keep)
        out.append({"text": it.text, "refs": keep})
    return out, dropped


def _context(db: Session, project, tasks: list[Task], names: dict[int, str]) -> dict:
    task_ids = [t.id for t in tasks]
    events = list(db.scalars(select(TaskEvent).where(TaskEvent.task_id.in_(task_ids or [-1]))
                             .order_by(TaskEvent.created_at.desc())))
    links = db.execute(select(MeetingTask.task_id, Meeting).join(Meeting, Meeting.id == MeetingTask.meeting_id)
                       .where(MeetingTask.task_id.in_(task_ids or [-1]))).all()
    meeting_map = {m.id: m for _, m in links}
    decisions = list(db.scalars(select(Decision).where(Decision.project_id == project.id,
                                                       Decision.status.in_(("active", "proposed")))
                                .order_by(Decision.approved_at.desc().nulls_last(), Decision.id.desc())))
    documents = list(db.scalars(select(Document).where(Document.project_id == project.id,
                                                       Document.document_status == "current")))
    unassigned = list(db.scalars(select(Task).where(Task.project_id == project.id, Task.owner_id.is_(None),
                                                    Task.status.in_(UNFINISHED_TASK_STATUSES))))
    task_rows = []
    for t in tasks:
        t_events = [e for e in events if e.task_id == t.id]
        blockers = [e.note for e in t_events if e.note and (e.event_type == "blocker_recorded" or (
            e.event_type == "status_changed" and (e.new_value or {}).get("status") == "blocked"))]
        task_rows.append({
            **serialize_task(t, names),
            "meetings": [{"id": m.id, "title": m.title} for tid, m in links if tid == t.id],
            "latest_blocker": blockers[0] if blockers else None,
            "recent_events": [serialize_event(e, names) for e in t_events[:6]],
        })
    return {
        "tasks": task_rows,
        "decisions": [serialize_decision(d, names) for d in decisions[:15]],
        "meetings": [{"id": m.id, "title": m.title, "meeting_at": iso(m.meeting_at)} for m in meeting_map.values()],
        "documents": [{"id": d.id, "title": d.title, "version_number": d.version_number} for d in documents],
        "unassigned_tasks": [{"id": t.id, "title": t.title, "status": t.status} for t in unassigned],
    }


def _records_only_brief(ctx: dict, from_name: str, to_name: str, project_name: str) -> dict:
    tasks = ctx["tasks"]
    blocked = [t for t in tasks if t["status"] == "blocked"]
    return {
        "project_overview": f"{project_name}: {len(tasks)} unfinished task(s) owned by {from_name} are in scope.",
        "current_status": ", ".join(f"{sum(1 for t in tasks if t['status'] == s)} {s.replace('_', ' ')}"
                                    for s in UNFINISHED_TASK_STATUSES),
        "responsibilities": [{"text": f"{t['title']} ({t['status'].replace('_', ' ')}"
                                      + (f", due {t['due_at'][:10]}" if t["due_at"] else ", no deadline") + ")",
                              "refs": [f"task:{t['id']}"]} for t in tasks],
        "outstanding_work_summary": f"{len(tasks)} task(s) would move from {from_name} to {to_name}; "
                                    f"{sum(1 for t in tasks if t['is_overdue'])} overdue, {len(blocked)} blocked.",
        "important_decisions": [{"text": f"{d['code']}: {d['statement']} ({d['status']})",
                                 "refs": [f"decision:{d['id']}"]} for d in ctx["decisions"][:5]],
        "blockers": [{"text": f"{t['title']}: {t['latest_blocker'] or 'blocked (no note recorded)'}",
                      "refs": [f"task:{t['id']}"]} for t in blocked],
        "relevant_documents": [{"text": f"{d['title']} v{d['version_number']}", "refs": [f"document:{d['id']}"]}
                               for d in ctx["documents"]],
        "next_actions": [{"text": f"Confirm status and next step for '{t['title']}' with {from_name}.",
                          "refs": [f"task:{t['id']}"]} for t in tasks[:5]],
    }


def _to_markdown(brief: dict, h: Handover, names: dict[int, str], project_name: str, generated_by: str) -> str:
    lines = [f"# Handover brief: {names.get(h.from_member_id)} → {names.get(h.to_member_id)}",
             f"Project: {project_name} · Period: {h.start_date} → {h.end_date or 'open'} · Source: {generated_by}", "",
             "## Project overview", brief["project_overview"], "", "## Current status", brief["current_status"], "",
             "## Outstanding work", brief["outstanding_work_summary"], ""]
    for key, title in (("responsibilities", "Responsibilities being transferred"),
                       ("important_decisions", "Important decisions"), ("blockers", "Blockers"),
                       ("relevant_documents", "Relevant documents"), ("next_actions", "Recommended next actions")):
        lines.append(f"## {title}")
        lines += [f"- {i['text']}" + (f" [{', '.join(i['refs'])}]" if i["refs"] else "") for i in brief[key]] or ["- None"]
        lines.append("")
    return "\n".join(lines)


def generate_handover(db: Session, body: HandoverGenerate, ai: AIClient) -> dict:
    project = get_project(db, body.project_id)
    from_m = get_member(db, project, body.from_member_id, field="from_member_id")
    to_m = get_member(db, project, body.to_member_id, field="to_member_id", must_be_active=True)
    if from_m.id == to_m.id:
        raise bad_request("same_member", "Outgoing and incoming members must be different people.")
    if body.end_date and body.end_date < body.start_date:
        raise bad_request("invalid_dates", "End date must be on or after the start date.")
    if body.created_by is not None:
        get_member(db, project, body.created_by, field="created_by")

    # The database, not the model, decides which work is in scope.
    tasks = list(db.scalars(select(Task).where(Task.project_id == project.id, Task.owner_id == from_m.id,
                                               Task.status.in_(UNFINISHED_TASK_STATUSES)).order_by(Task.due_at, Task.id)))
    names = member_names(db, project.workspace_id)
    ctx = _context(db, project, tasks, names)

    h = Handover(project_id=project.id, from_member_id=from_m.id, to_member_id=to_m.id, status="draft",
                 start_date=body.start_date, end_date=body.end_date)
    h.tasks = [HandoverTask(task_id=t.id, previous_owner_id=from_m.id, proposed_owner_id=to_m.id, selected=True)
               for t in tasks]
    db.add(h)
    db.flush()

    allowed = ({f"task:{t['id']}" for t in ctx["tasks"]} | {f"decision:{d['id']}" for d in ctx["decisions"]}
               | {f"meeting:{m['id']}" for m in ctx["meetings"]} | {f"document:{d['id']}" for d in ctx["documents"]})
    ai_status, ai_message, dropped = "generated", None, 0
    try:
        prompt = "\n\n".join([
            f"Project: {project.name}\nOutgoing: {from_m.name} ({from_m.role})\nIncoming: {to_m.name} ({to_m.role})\n"
            f"Handover period: {body.start_date} to {body.end_date or 'open-ended'}",
            prompts.data_block("handover_records", json.dumps(ctx, indent=1, default=str)[:30000]),
        ])
        result = ai.generate_json(task="handover_brief", system=prompts.HANDOVER_SYSTEM, prompt=prompt,
                                  schema=HandoverBriefAI)
        brief = result.model_dump()
        for key in ("responsibilities", "important_decisions", "blockers", "relevant_documents", "next_actions"):
            brief[key], d = clean_refs(getattr(result, key), allowed)
            dropped += d
        source = f"AI draft ({getattr(ai, 'model', 'model')}) from RELAY records"
    except AIError as exc:
        ai_status, ai_message = "unavailable", str(exc)
        brief = _records_only_brief(ctx, from_m.name, to_m.name, project.name)
        source = "RELAY records only (AI unavailable)"
    h.brief_json = {**ctx, "brief": brief, "ai_status": ai_status, "ai_message": ai_message,
                    "dropped_invalid_refs": dropped, "generated_at": iso(now()), "source": source}
    h.brief_text = _to_markdown(brief, h, names, project.name, source)
    db.commit()
    log.info("handover_generated", extra={"handover_id": h.id, "project_id": project.id, "tasks": len(tasks),
                                          "ai_status": ai_status})
    return handover_detail(db, h.id)


def handover_detail(db: Session, handover_id: int) -> dict:
    h = db.get(Handover, handover_id, options=[selectinload(Handover.tasks)])
    if not h:
        raise not_found("Handover", handover_id)
    project = get_project(db, h.project_id)
    names = member_names(db, project.workspace_id)
    tasks = {t.id: t for t in db.scalars(select(Task).where(Task.id.in_([ht.task_id for ht in h.tasks] or [-1])))}
    return {
        "id": h.id, "project_id": h.project_id, "project_name": project.name, "status": h.status,
        "from_member": {"id": h.from_member_id, "name": names.get(h.from_member_id)},
        "to_member": {"id": h.to_member_id, "name": names.get(h.to_member_id)},
        "start_date": iso(h.start_date), "end_date": iso(h.end_date), "created_at": iso(h.created_at),
        "approved_at": iso(h.approved_at), "approved_by_name": names.get(h.approved_by) if h.approved_by else None,
        "brief_text": h.brief_text, "brief_json": h.brief_json,
        "tasks": [{"task": serialize_task(tasks[ht.task_id], names), "selected": ht.selected,
                   "previous_owner_id": ht.previous_owner_id, "proposed_owner_id": ht.proposed_owner_id,
                   "transferred_at": iso(ht.transferred_at)} for ht in h.tasks if ht.task_id in tasks],
    }


def list_handovers(db: Session, project_id: int) -> list[dict]:
    get_project(db, project_id)
    ids = db.scalars(select(Handover.id).where(Handover.project_id == project_id).order_by(Handover.created_at.desc()))
    return [handover_detail(db, i) for i in ids]


def approve_handover(db: Session, handover_id: int, body: HandoverApprove) -> dict:
    h = db.get(Handover, handover_id, options=[selectinload(Handover.tasks)])
    if not h:
        raise not_found("Handover", handover_id)
    project = get_project(db, h.project_id)
    approver = get_member(db, project, body.approved_by, field="approved_by", must_be_active=True)
    get_member(db, project, h.to_member_id, field="incoming member", must_be_active=True)
    if h.status != "draft":
        raise conflict("handover_not_draft", f"Handover is already {h.status}.")
    if body.selections is not None:
        by_task = {ht.task_id: ht for ht in h.tasks}
        unknown = [s.task_id for s in body.selections if s.task_id not in by_task]
        if unknown:
            raise bad_request("unknown_tasks", "Selections reference tasks outside this handover.", {"task_ids": unknown})

    claimed = db.execute(update(Handover).where(Handover.id == h.id, Handover.status == "draft")
                         .values(status="approved", approved_at=now(), approved_by=approver.id))
    if claimed.rowcount != 1:
        db.rollback()
        raise conflict("handover_not_draft", "Handover was already approved.")
    transferred = []
    try:
        if body.selections is not None:
            for s in body.selections:
                next(ht for ht in h.tasks if ht.task_id == s.task_id).selected = s.selected
        names = member_names(db, project.workspace_id)
        for ht in h.tasks:
            if not ht.selected:
                continue
            task = db.get(Task, ht.task_id)
            if task.project_id != h.project_id or task.status not in UNFINISHED_TASK_STATUSES:
                raise conflict("task_not_transferable", f"Task {task.id} is {task.status}; completed or cancelled "
                                                        "tasks are not transferred. Nothing was changed.",
                               {"task_id": task.id})
            if task.owner_id != h.from_member_id:
                raise conflict("owner_changed", f"Task {task.id} is no longer owned by "
                                                f"{names.get(h.from_member_id)}. Nothing was changed.",
                               {"task_id": task.id})
            add_event(db, task, "reassigned", approver.id,
                      old={"owner_id": task.owner_id, "owner_name": names.get(task.owner_id)},
                      new={"owner_id": h.to_member_id, "owner_name": names.get(h.to_member_id)},
                      note=f"Transferred by approved handover #{h.id}")
            task.owner_id = h.to_member_id  # deadlines intentionally untouched
            ht.transferred_at = now()
            transferred.append(task.id)
        db.commit()
    except Exception:
        db.rollback()
        log.warning("handover_approval_rolled_back", extra={"handover_id": h.id})
        raise
    log.info("handover_approved", extra={"handover_id": h.id, "approved_by": approver.id,
                                         "transferred": len(transferred)})
    return handover_detail(db, h.id) | {"transferred_task_ids": transferred}

