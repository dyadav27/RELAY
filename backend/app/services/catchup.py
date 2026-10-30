"""Catch-up / re-entry brief: database records are authoritative; AI only summarises them."""
import json
from datetime import UTC, datetime, time

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai import prompts
from ..ai.client import AIClient, AIError
from ..ai.schemas import CatchUpAI
from ..logging_setup import get_logger
from ..models import (
    UNFINISHED_TASK_STATUSES,
    Decision,
    DecisionAlert,
    DecisionRelation,
    Document,
    Meeting,
    Task,
    TaskEvent,
)
from ..schemas import CatchUpRequest
from .common import get_member, get_project, iso, member_names
from .decisions import decision_code
from .handovers import clean_refs

log = get_logger("catchup")


def _records(db: Session, project_id: int, member_id: int, since: datetime, names: dict[int, str]) -> dict:
    meetings = list(db.scalars(select(Meeting).where(Meeting.project_id == project_id, Meeting.meeting_at >= since)
                               .order_by(Meeting.meeting_at)))
    approved = list(db.scalars(select(Decision).where(Decision.project_id == project_id,
                                                      Decision.approved_at >= since).order_by(Decision.approved_at)))
    proposed = list(db.scalars(select(Decision).where(Decision.project_id == project_id, Decision.status == "proposed",
                                                      Decision.created_at >= since)))
    supersessions = db.execute(select(DecisionRelation).join(Decision, Decision.id == DecisionRelation.new_decision_id)
                               .where(Decision.project_id == project_id, DecisionRelation.relationship_type == "supersedes",
                                      DecisionRelation.created_at >= since)).scalars().all()
    created = list(db.scalars(select(Task).where(Task.project_id == project_id, Task.created_at >= since)))
    completed = list(db.scalars(select(Task).where(Task.project_id == project_id, Task.status == "completed",
                                                   Task.completed_at >= since)))
    reassign = db.execute(select(TaskEvent, Task).join(Task, Task.id == TaskEvent.task_id)
                          .where(Task.project_id == project_id, TaskEvent.event_type == "reassigned",
                                 TaskEvent.created_at >= since).order_by(TaskEvent.created_at)).all()
    blocked = list(db.scalars(select(Task).where(Task.project_id == project_id, Task.status == "blocked")))
    docs = list(db.scalars(select(Document).where(Document.project_id == project_id, Document.created_at >= since)))
    mine = list(db.scalars(select(Task).where(Task.project_id == project_id, Task.owner_id == member_id,
                                              Task.status.in_(UNFINISHED_TASK_STATUSES)).order_by(Task.due_at)))
    alerts = db.scalars(select(DecisionAlert).join(Meeting).where(Meeting.project_id == project_id,
                                                                  DecisionAlert.status == "pending")).all()

    def t(x: Task):
        return {"ref": f"task:{x.id}", "title": x.title, "status": x.status, "owner": names.get(x.owner_id),
                "due_at": iso(x.due_at), "outcome": x.outcome}

    return {
        "meetings": [{"ref": f"meeting:{m.id}", "title": m.title, "meeting_at": iso(m.meeting_at),
                      "summary": m.summary} for m in meetings],
        "decisions_approved": [{"ref": f"decision:{d.id}", "code": decision_code(d.id), "statement": d.statement,
                                "status": d.status, "approved_by": names.get(d.approved_by)} for d in approved],
        "decisions_proposed": [{"ref": f"decision:{d.id}", "code": decision_code(d.id), "statement": d.statement}
                               for d in proposed],
        "decisions_superseded": [{"ref": f"decision:{r.previous_decision_id}",
                                  "old": decision_code(r.previous_decision_id),
                                  "new": decision_code(r.new_decision_id), "new_ref": f"decision:{r.new_decision_id}",
                                  "reason": r.reason} for r in supersessions],
        "tasks_created": [t(x) for x in created],
        "tasks_completed": [t(x) for x in completed],
        "ownership_changes": [{"ref": f"task:{task.id}", "title": task.title,
                               "from": (ev.old_value or {}).get("owner_name"), "to": (ev.new_value or {}).get("owner_name"),
                               "at": iso(ev.created_at), "note": ev.note} for ev, task in reassign],
        "blocked_tasks": [t(x) for x in blocked],
        "documents": [{"ref": f"document:{d.id}", "title": d.title, "version_number": d.version_number}
                      for d in docs],
        "your_open_tasks": [t(x) for x in mine],
        "pending_decision_alerts": [{"ref": f"decision:{a.existing_decision_id}", "alert_id": a.id,
                                     "proposed": a.proposed_statement, "classification": a.relationship_type}
                                    for a in alerts],
    }


def _records_brief(r: dict) -> dict:
    def items(rows, fmt):
        return [{"text": fmt(x), "refs": [x["ref"]]} for x in rows]

    return {
        "what_changed": items(r["meetings"], lambda m: f"Meeting held: {m['title']} ({m['meeting_at'][:10]})")
        + items(r["documents"], lambda d: f"Document added: {d['title']} v{d['version_number']}"),
        "decisions": items(r["decisions_approved"], lambda d: f"{d['code']} {d['status']}: {d['statement']}")
        + [{"text": f"{s['old']} superseded by {s['new']}", "refs": [s["ref"], s["new_ref"]]}
           for s in r["decisions_superseded"]]
        + items(r["decisions_proposed"], lambda d: f"{d['code']} proposed (not approved): {d['statement']}"),
        "completed_work": items(r["tasks_completed"], lambda x: f"Completed: {x['title']} — {x['outcome']}"),
        "outstanding": items(r["blocked_tasks"], lambda x: f"Blocked: {x['title']} ({x['owner'] or 'unassigned'})")
        + items([x for x in r["tasks_created"] if x["status"] in UNFINISHED_TASK_STATUSES],
                lambda x: f"New task: {x['title']} ({x['owner'] or 'unassigned'})"),
        "ownership_changes": items(r["ownership_changes"], lambda x: f"{x['title']}: {x['from'] or 'unassigned'} → "
                                                                      f"{x['to'] or 'unassigned'}"),
        "attention_next": items(r["your_open_tasks"], lambda x: f"Your task: {x['title']} ({x['status']}"
                                                                + (f", due {x['due_at'][:10]})" if x["due_at"] else ")"))
        + items(r["pending_decision_alerts"], lambda a: f"Decision review pending: {a['proposed']}"),
    }


def catch_up(db: Session, body: CatchUpRequest, ai: AIClient) -> dict:
    project = get_project(db, body.project_id)
    member = get_member(db, project, body.member_id, field="member_id")
    names = member_names(db, project.workspace_id)
    since = datetime.combine(body.since, time.min, tzinfo=UTC)
    records = _records(db, project.id, member.id, since, names)
    allowed = {x["ref"] for rows in records.values() for x in rows} | {
        x["new_ref"] for x in records["decisions_superseded"]}

    ai_status, ai_message, dropped = "generated", None, 0
    try:
        prompt = "\n\n".join([
            f"Project: {project.name}\nReader: {member.name} ({member.role})\nAbsent since: {body.since}",
            prompts.data_block("changes_since", json.dumps(records, indent=1, default=str)[:30000]),
        ])
        result = ai.generate_json(task="catch_up_brief", system=prompts.CATCHUP_SYSTEM, prompt=prompt, schema=CatchUpAI)
        brief = {}
        for key in CatchUpAI.model_fields:
            brief[key], d = clean_refs(getattr(result, key), allowed)
            dropped += d
    except AIError as exc:
        ai_status, ai_message = "unavailable", str(exc)
        brief = _records_brief(records)
    log.info("catch_up_generated", extra={"project_id": project.id, "member_id": member.id, "ai_status": ai_status})
    return {"project": {"id": project.id, "name": project.name}, "member": {"id": member.id, "name": member.name},
            "since": body.since.isoformat(), "records": records, "brief": brief, "ai_status": ai_status,
            "ai_message": ai_message, "dropped_invalid_refs": dropped,
            "source": "AI summary of RELAY records" if ai_status == "generated" else "RELAY records only (AI unavailable)"}
