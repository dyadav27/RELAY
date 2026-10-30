"""Decision Integrity Engine: ledger, drift detection against approved decisions, human-reviewed supersession."""
import json

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..ai import prompts
from ..ai.client import AIClient
from ..ai.schemas import DriftAnalysis
from ..errors import conflict, not_found
from ..logging_setup import get_logger
from ..models import (
    UNFINISHED_TASK_STATUSES,
    Decision,
    DecisionAlert,
    DecisionRelation,
    Meeting,
    Task,
)
from ..schemas import AlertResolve
from .common import get_member, get_project, iso, member_names, now, quote_in_source, token_overlap
from .tasks import add_event

log = get_logger("decisions")


def decision_code(decision_id: int) -> str:
    return f"DEC-{decision_id:04d}"


def serialize_decision(d: Decision, names: dict[int, str], lineage: dict | None = None) -> dict:
    out = {
        "id": d.id,
        "code": decision_code(d.id),
        "project_id": d.project_id,
        "meeting_id": d.meeting_id,
        "meeting_title": d.meeting.title if d.meeting else None,
        "statement": d.statement,
        "evidence": d.evidence,
        "status": d.status,
        "approved_by": d.approved_by,
        "approved_by_name": names.get(d.approved_by) if d.approved_by else None,
        "approved_at": iso(d.approved_at),
        "effective_from": iso(d.effective_from),
        "effective_until": iso(d.effective_until),
        "created_at": iso(d.created_at),
    }
    if lineage is not None:
        out["lineage"] = lineage
    return out


def _lineage(db: Session, decision_ids: list[int]) -> dict[int, dict]:
    result = {i: {"supersedes": [], "superseded_by": [], "proposed_changes": [], "proposes_change_to": []}
              for i in decision_ids}
    rels = db.scalars(select(DecisionRelation).where(
        DecisionRelation.previous_decision_id.in_(decision_ids or [-1])
        | DecisionRelation.new_decision_id.in_(decision_ids or [-1])))
    for r in rels:
        entry = {"relation_id": r.id, "reason": r.reason, "created_at": iso(r.created_at)}
        if r.relationship_type == "supersedes":
            if r.new_decision_id in result:
                result[r.new_decision_id]["supersedes"].append({**entry, "decision_id": r.previous_decision_id})
            if r.previous_decision_id in result:
                result[r.previous_decision_id]["superseded_by"].append({**entry, "decision_id": r.new_decision_id})
        else:
            if r.new_decision_id in result:
                result[r.new_decision_id]["proposes_change_to"].append({**entry, "decision_id": r.previous_decision_id})
            if r.previous_decision_id in result:
                result[r.previous_decision_id]["proposed_changes"].append({**entry, "decision_id": r.new_decision_id})
    return result


def list_decisions(db: Session, project_id: int, status: str | None = None) -> list[dict]:
    project = get_project(db, project_id)
    stmt = select(Decision).where(Decision.project_id == project_id)
    if status:
        stmt = stmt.where(Decision.status.in_(status.split(",")))
    decisions = list(db.scalars(stmt.order_by(Decision.created_at.desc(), Decision.id.desc())))
    names = member_names(db, project.workspace_id)
    lineage = _lineage(db, [d.id for d in decisions])
    return [serialize_decision(d, names, lineage[d.id]) for d in decisions]


def serialize_alert(db: Session, a: DecisionAlert, names: dict[int, str]) -> dict:
    task_ids = a.affected_task_ids or []
    tasks = list(db.scalars(select(Task).where(Task.id.in_(task_ids or [-1])))) if task_ids else []
    return {
        "id": a.id,
        "code": f"ALERT-{a.id:04d}",
        "meeting": {"id": a.meeting.id, "title": a.meeting.title, "meeting_at": iso(a.meeting.meeting_at)},
        "existing_decision": serialize_decision(a.existing_decision, names),
        "proposed_statement": a.proposed_statement,
        "classification": a.relationship_type,
        "explanation": a.explanation,
        "old_evidence": a.old_evidence,
        "new_evidence": a.new_evidence,
        "affected_tasks": [{"id": t.id, "title": t.title, "status": t.status,
                            "owner_name": names.get(t.owner_id) if t.owner_id else None} for t in tasks],
        "status": a.status,
        "resolved_by_name": names.get(a.resolved_by) if a.resolved_by else None,
        "resolved_at": iso(a.resolved_at),
        "resolution_note": a.resolution_note,
        "created_at": iso(a.created_at),
    }


def list_alerts(db: Session, project_id: int, status: str | None = "pending") -> list[dict]:
    project = get_project(db, project_id)
    stmt = select(DecisionAlert).join(Meeting, Meeting.id == DecisionAlert.meeting_id).where(
        Meeting.project_id == project_id)
    if status:
        stmt = stmt.where(DecisionAlert.status.in_(status.split(",")))
    names = member_names(db, project.workspace_id)
    return [serialize_alert(db, a, names) for a in db.scalars(stmt.order_by(DecisionAlert.created_at.desc()))]


def analyze_meeting(db: Session, meeting: Meeting, ai: AIClient) -> dict:
    """Compare a meeting's discussion with historical active decisions of the SAME project and record alerts.

    Never changes existing decisions; only creates pending alerts for human review.
    """
    project = get_project(db, meeting.project_id)
    draft = meeting.extraction_draft or {}
    candidates = [{"statement": d["statement"], "kind": kind, "evidence": d.get("evidence")}
                  for kind in ("confirmed_decisions", "proposed_decisions") for d in draft.get(kind, [])]

    history = list(db.scalars(select(Decision).where(
        Decision.project_id == project.id, Decision.status == "active",
        (Decision.meeting_id != meeting.id) | Decision.meeting_id.is_(None))))
    corpus = meeting.raw_notes + " " + " ".join(c["statement"] for c in candidates)
    history.sort(key=lambda d: token_overlap(d.statement + " " + (d.evidence or ""), corpus), reverse=True)
    history = history[:25]

    result = {"status": "analyzed", "analyzed_at": iso(now()), "alert_ids": [], "consistent": [],
              "historical_decisions_checked": len(history)}
    # Re-analysis replaces earlier unresolved alerts for this meeting (kept for audit as "stale").
    db.execute(update(DecisionAlert).where(DecisionAlert.meeting_id == meeting.id,
                                           DecisionAlert.status == "pending").values(status="stale"))
    if not history:
        result["note"] = "No approved decisions exist in this project yet; nothing to compare."
        return result

    tasks = list(db.scalars(select(Task).where(Task.project_id == project.id,
                                               Task.status.in_(UNFINISHED_TASK_STATUSES)).limit(60)))
    hist_payload = [{"existing_decision_id": d.id, "statement": d.statement, "evidence": d.evidence,
                     "approved_at": iso(d.approved_at)} for d in history]
    task_payload = [{"task_id": t.id, "title": t.title, "status": t.status} for t in tasks]
    prompt = "\n\n".join([
        f"Project: {project.name}\nMeeting: {meeting.title} ({iso(meeting.meeting_at)})",
        prompts.data_block("historical_active_decisions", json.dumps(hist_payload, indent=1)),
        prompts.data_block("candidate_statements_from_new_meeting", json.dumps(candidates, indent=1)),
        prompts.data_block("new_meeting_notes", meeting.raw_notes[:15000]),
        prompts.data_block("open_tasks", json.dumps(task_payload, indent=1)),
    ])
    analysis = ai.generate_json(task="decision_drift", system=prompts.DRIFT_SYSTEM, prompt=prompt,
                                schema=DriftAnalysis)

    by_id = {d.id: d for d in history}
    valid_task_ids = {t.id for t in tasks}
    dropped = 0
    for f in analysis.findings:
        decision = by_id.get(f.existing_decision_id)
        if decision is None:  # model referenced a decision it was not given (or from another project)
            dropped += 1
            continue
        if f.classification == "consistent":
            result["consistent"].append({"existing_decision_id": decision.id, "statement": f.new_statement})
            continue
        new_ev = f.new_evidence if quote_in_source(f.new_evidence, meeting.raw_notes) else None
        explanation = f.explanation
        if f.new_evidence and not new_ev:
            explanation += " (The model's quote could not be matched to the notes; review the original notes.)"
        alert = DecisionAlert(
            meeting_id=meeting.id, existing_decision_id=decision.id, proposed_statement=f.new_statement,
            relationship_type=f.classification, explanation=explanation,
            old_evidence=decision.evidence or decision.statement,  # authoritative stored evidence
            new_evidence=new_ev,
            affected_task_ids=[t for t in dict.fromkeys(f.affected_task_ids) if t in valid_task_ids],
        )
        db.add(alert)
        db.flush()
        result["alert_ids"].append(alert.id)
    result["dropped_invalid_references"] = dropped
    log.info("decision_analysis", extra={"meeting_id": meeting.id, "project_id": project.id,
                                         "alerts": len(result["alert_ids"]), "dropped_references": dropped})
    return result


def resolve_alert(db: Session, alert_id: int, body: AlertResolve) -> dict:
    alert = db.get(DecisionAlert, alert_id)
    if not alert:
        raise not_found("Decision alert", alert_id)
    meeting = alert.meeting
    project = get_project(db, meeting.project_id)
    actor = get_member(db, project, body.actor_id, field="actor_id", must_be_active=True)
    status_for = {"confirm_change": "confirmed_change", "mark_proposal": "marked_proposal", "dismiss": "dismissed"}

    # Atomic claim: only one reviewer can resolve a pending alert.
    claimed = db.execute(update(DecisionAlert).where(DecisionAlert.id == alert.id, DecisionAlert.status == "pending")
                         .values(status=status_for[body.action], resolved_by=actor.id, resolved_at=now(),
                                 resolution_note=body.note))
    if claimed.rowcount != 1:
        db.rollback()
        raise conflict("alert_already_resolved", f"Alert {alert_id} has already been resolved.")

    old = alert.existing_decision
    statement = body.statement or alert.proposed_statement
    new_decision = None
    flagged_tasks: list[int] = []
    try:
        if body.action in ("confirm_change", "mark_proposal") and old.status != "active":
            raise conflict("decision_not_active", f"{decision_code(old.id)} is no longer active ({old.status}).")
        if body.action == "confirm_change":
            ts = now()
            new_decision = Decision(project_id=project.id, meeting_id=meeting.id, statement=statement,
                                    evidence=alert.new_evidence, status="active", approved_by=actor.id,
                                    approved_at=ts, effective_from=ts)
            db.add(new_decision)
            db.flush()
            old.status, old.effective_until = "superseded", ts
            db.add(DecisionRelation(previous_decision_id=old.id, new_decision_id=new_decision.id,
                                    relationship_type="supersedes", reason=body.note or alert.explanation))
            for task in db.scalars(select(Task).where(Task.id.in_(alert.affected_task_ids or [-1]),
                                                      Task.project_id == project.id,
                                                      Task.status.in_(UNFINISHED_TASK_STATUSES))):
                add_event(db, task, "decision_review", actor.id, meeting_id=meeting.id,
                          old={"decision_id": old.id}, new={"decision_id": new_decision.id},
                          note=f"{decision_code(old.id)} was superseded by {decision_code(new_decision.id)}. "
                               "Review whether this task is still valid.")
                flagged_tasks.append(task.id)
            log.info("decision_superseded", extra={"old_decision_id": old.id, "new_decision_id": new_decision.id,
                                                   "actor_id": actor.id, "flagged_tasks": len(flagged_tasks)})
        elif body.action == "mark_proposal":
            new_decision = Decision(project_id=project.id, meeting_id=meeting.id, statement=statement,
                                    evidence=alert.new_evidence, status="proposed")
            db.add(new_decision)
            db.flush()
            db.add(DecisionRelation(previous_decision_id=old.id, new_decision_id=new_decision.id,
                                    relationship_type="proposed_change", reason=body.note or alert.explanation))
        db.commit()
    except Exception:
        db.rollback()
        raise
    log.info("decision_alert_resolved", extra={"alert_id": alert.id, "action": body.action, "actor_id": actor.id})
    names = member_names(db, project.workspace_id)
    db.refresh(alert)
    return {
        "alert": serialize_alert(db, alert, names),
        "new_decision": serialize_decision(new_decision, names) if new_decision else None,
        "tasks_flagged_for_review": flagged_tasks,
    }
