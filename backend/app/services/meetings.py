from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, selectinload

from ..ai import prompts
from ..ai.client import AIClient, AIError
from ..ai.schemas import MeetingExtraction
from ..errors import bad_request, conflict, not_found
from ..logging_setup import get_logger
from ..models import (
    UNFINISHED_TASK_STATUSES,
    Decision,
    DecisionAlert,
    Document,
    Meeting,
    MeetingParticipant,
    MeetingTask,
    Member,
    Task,
    TaskEvent,
)
from ..schemas import MeetingApprove, MeetingCreate, MeetingUpdate
from . import decisions as decision_svc
from .common import get_member, get_project, iso, member_names, normalize_ws, now, quote_in_source, sha256, \
    token_overlap
from .tasks import associate_with_meeting, create_task, serialize_event, serialize_task

log = get_logger("meetings")


def load_meeting(db: Session, meeting_id: int) -> Meeting:
    m = db.get(Meeting, meeting_id, options=[selectinload(Meeting.participants)])
    if not m:
        raise not_found("Meeting", meeting_id)
    return m


def create_meeting(db: Session, body: MeetingCreate) -> Meeting:
    project = get_project(db, body.project_id)
    if body.created_by is not None:
        get_member(db, project, body.created_by, field="created_by")
    ids = list(dict.fromkeys(body.participant_ids))
    members = list(db.scalars(select(Member).where(Member.id.in_(ids))))
    invalid = sorted(set(ids) - {m.id for m in members if m.workspace_id == project.workspace_id})
    if invalid:
        raise bad_request("invalid_participants", "Some participants are not members of this workspace.",
                          {"invalid_participant_ids": invalid})
    meeting = Meeting(project_id=project.id, title=body.title, record_type=body.record_type,
                      meeting_at=body.meeting_at, agenda=body.agenda, raw_notes=body.raw_notes,
                      source_hash=sha256(body.raw_notes), created_by=body.created_by, extraction_status="pending")
    meeting.participants = [MeetingParticipant(member_id=i) for i in ids]
    db.add(meeting)
    db.commit()
    log.info("meeting_created", extra={"meeting_id": meeting.id, "project_id": project.id,
                                       "participants": len(ids), "notes_chars": len(body.raw_notes)})
    return meeting


def update_meeting(db: Session, meeting_id: int, body: MeetingUpdate) -> Meeting:
    meeting = load_meeting(db, meeting_id)
    project = get_project(db, meeting.project_id)
    if body.actor_id is not None:
        get_member(db, project, body.actor_id, field="actor_id")
    if meeting.extraction_status == "approved" and body.raw_notes is not None:
        raise conflict("meeting_approved", "Notes of an approved meeting are preserved as the original record.")
    if body.title is not None:
        meeting.title = body.title
    if body.agenda is not None:
        meeting.agenda = body.agenda
    if body.raw_notes is not None and body.raw_notes != meeting.raw_notes:
        meeting.raw_notes = body.raw_notes
        meeting.source_hash = sha256(body.raw_notes)  # any existing extraction is now stale
    db.commit()
    return meeting


def _integrity_summary(db: Session, meeting: Meeting) -> dict:
    counts = dict(db.execute(select(DecisionAlert.status, func.count()).where(DecisionAlert.meeting_id == meeting.id)
                             .group_by(DecisionAlert.status)).all())
    pending = counts.get("pending", 0)
    analysis = (meeting.extraction_draft or {}).get("integrity") or {}
    if pending:
        state = "review_required"
    elif analysis.get("status") == "failed":
        state = "analysis_failed"
    elif analysis.get("status") == "analyzed" or any(counts.values()):
        state = "consistent" if not any(counts.get(s, 0) for s in ("confirmed_change", "marked_proposal")) else "resolved"
    else:
        state = "not_analyzed"
    return {"state": state, "pending_alerts": pending, "resolved_alerts": sum(
        counts.get(s, 0) for s in ("confirmed_change", "marked_proposal", "dismissed"))}


def serialize_meeting(db: Session, m: Meeting, names: dict[int, str], *, full: bool = False) -> dict:
    out = {
        "id": m.id,
        "project_id": m.project_id,
        "title": m.title,
        "record_type": m.record_type,
        "meeting_at": iso(m.meeting_at),
        "agenda": m.agenda,
        "summary": m.summary,
        "summary_preview": (m.summary or (m.extraction_draft or {}).get("summary") or "")[:220] or None,
        "extraction_status": m.extraction_status,
        "notes_changed_since_extraction": bool(
            m.extraction_draft and m.extraction_draft.get("source_hash") != m.source_hash),
        "source_hash": m.source_hash,
        "participants": [{"member_id": p.member_id, "name": names.get(p.member_id),
                          "attendance_status": p.attendance_status} for p in m.participants],
        "integrity": _integrity_summary(db, m),
        "created_by": m.created_by,
        "created_at": iso(m.created_at),
        "updated_at": iso(m.updated_at),
    }
    if full:
        out["raw_notes"] = m.raw_notes
        out["extraction_draft"] = m.extraction_draft
    return out


def list_meetings(db: Session, project_id: int) -> list[dict]:
    project = get_project(db, project_id)
    names = member_names(db, project.workspace_id)
    meetings = db.scalars(select(Meeting).options(selectinload(Meeting.participants))
                          .where(Meeting.project_id == project_id).order_by(Meeting.meeting_at.desc()))
    return [serialize_meeting(db, m, names) for m in meetings]


def meeting_detail(db: Session, meeting_id: int) -> dict:
    m = load_meeting(db, meeting_id)
    project = get_project(db, m.project_id)
    names = member_names(db, project.workspace_id)
    links = db.execute(select(MeetingTask, Task).join(Task, Task.id == MeetingTask.task_id)
                       .where(MeetingTask.meeting_id == m.id).order_by(Task.id)).all()
    decisions = db.scalars(select(Decision).where(Decision.meeting_id == m.id).order_by(Decision.id))
    alerts = db.scalars(select(DecisionAlert).where(DecisionAlert.meeting_id == m.id, DecisionAlert.status != "stale")
                        .order_by(DecisionAlert.id))
    task_ids = [t.id for _, t in links]
    events = db.scalars(select(TaskEvent).where(TaskEvent.meeting_id == m.id).order_by(TaskEvent.created_at.desc())
                        .limit(50))
    # Linked documents: current project documents sharing vocabulary with the meeting.
    docs = list(db.scalars(select(Document).where(Document.project_id == m.project_id,
                                                  Document.document_status == "current")))
    basis = m.title + " " + (m.agenda or "") + " " + (m.summary or "")
    scored = sorted(((token_overlap(d.title + " " + d.content_text[:3000], basis), d) for d in docs),
                    key=lambda x: x[0], reverse=True)
    return {
        "meeting": serialize_meeting(db, m, names, full=True),
        "project": {"id": project.id, "name": project.name},
        "tasks": [{**serialize_task(t, names), "relationship_type": link.relationship_type} for link, t in links],
        "decisions": [decision_svc.serialize_decision(d, names) for d in decisions],
        "alerts": [decision_svc.serialize_alert(db, a, names) for a in alerts],
        "related_documents": [{"id": d.id, "title": d.title, "version_number": d.version_number,
                               "relevance": "shared terms"} for s, d in scored if s > 0.02][:5],
        "activity": [serialize_event(e, names) | {"task_title": next((t.title for _, t in links if t.id == e.task_id),
                                                                      None)} for e in events],
        "linked_task_ids": task_ids,
    }


# ---------------------------------------------------------------------------- extraction

def _resolve_owner(name: str | None, notes: str, participants: list[Member]) -> dict:
    if not name or not name.strip():
        return {"owner_id": None, "resolution": "none", "candidates": []}
    if not quote_in_source(name, notes):
        return {"owner_id": None, "resolution": "not_in_notes", "candidates": []}
    needle = normalize_ws(name)
    exact = [p for p in participants if normalize_ws(p.name) == needle]
    if len(exact) == 1:
        return {"owner_id": exact[0].id, "resolution": "matched", "candidates": [exact[0].id]}
    tokens = set(needle.split())
    partial = [p for p in participants if tokens & set(normalize_ws(p.name).split())]
    if len(partial) == 1:
        return {"owner_id": partial[0].id, "resolution": "matched", "candidates": [partial[0].id]}
    if len(partial) > 1:
        return {"owner_id": None, "resolution": "ambiguous", "candidates": [p.id for p in partial]}
    return {"owner_id": None, "resolution": "not_a_participant", "candidates": []}


def _existing_matches(title: str, description: str | None, tasks: list[Task]) -> list[dict]:
    basis = title + " " + (description or "")
    scored = [(max(token_overlap(title, t.title), token_overlap(basis, t.title + " " + (t.description or ""))), t)
              for t in tasks]
    return [{"task_id": t.id, "title": t.title, "status": t.status, "owner_id": t.owner_id, "score": round(s, 2)}
            for s, t in sorted(scored, key=lambda x: x[0], reverse=True) if s >= 0.25][:3]


def build_draft(extraction: MeetingExtraction, meeting: Meeting, participants: list[Member],
                project_tasks: list[Task], model: str) -> dict:
    notes = meeting.raw_notes

    def decision(d, kind):
        return {"statement": d.statement, "evidence": d.evidence, "kind": kind,
                "evidence_verified": quote_in_source(d.evidence, notes)}

    items = []
    for a in extraction.action_items:
        owner = _resolve_owner(a.suggested_owner_name, notes, participants)
        deadline_text = a.deadline_text if quote_in_source(a.deadline_text, notes) else None
        # Never invent dates: keep an ISO date only when the deadline phrase is verifiably in the notes.
        due_date = a.due_date.isoformat() if (a.due_date and deadline_text) else None
        matches = _existing_matches(a.title, a.description, project_tasks)
        suggested = "create"
        if matches and matches[0]["score"] >= 0.45:
            suggested = "carry_forward" if matches[0]["status"] in UNFINISHED_TASK_STATUSES else "link"
        flags = []
        if owner["resolution"] in ("ambiguous", "not_a_participant", "not_in_notes"):
            flags.append(f"owner_{owner['resolution']}")
        if a.deadline_text and not deadline_text:
            flags.append("deadline_not_found_in_notes")
        if not quote_in_source(a.evidence, notes):
            flags.append("evidence_not_found_in_notes")
        items.append({
            "title": a.title, "description": a.description, "suggested_owner_name": a.suggested_owner_name,
            "owner_id": owner["owner_id"], "owner_resolution": owner["resolution"],
            "owner_candidates": owner["candidates"], "deadline_text": deadline_text, "due_date": due_date,
            "evidence": a.evidence, "evidence_verified": "evidence_not_found_in_notes" not in flags,
            "existing_task_matches": matches, "suggested_action": suggested, "review_flags": flags,
        })
    return {
        "summary": extraction.summary,
        "confirmed_decisions": [decision(d, "confirmed") for d in extraction.confirmed_decisions],
        "proposed_decisions": [decision(d, "proposed") for d in extraction.proposed_decisions],
        "action_items": items,
        "blockers": [{"description": b.description, "evidence": b.evidence,
                      "evidence_verified": quote_in_source(b.evidence, notes)} for b in extraction.blockers],
        "unresolved_questions": [q.model_dump() for q in extraction.unresolved_questions],
        "source_hash": meeting.source_hash,
        "model": model,
        "generated_at": iso(now()),
    }


def extract_meeting(db: Session, meeting_id: int, ai: AIClient) -> dict:
    meeting = load_meeting(db, meeting_id)
    if meeting.extraction_status == "approved":
        raise conflict("already_approved", "This meeting's extraction was already approved.")
    project = get_project(db, meeting.project_id)
    participants = [db.get(Member, p.member_id) for p in meeting.participants]
    prompt = "\n\n".join([
        f"Project: {project.name}\nMeeting title: {meeting.title}\nMeeting date: {iso(meeting.meeting_at)}",
        "Participants: " + ", ".join(f"{p.name} ({p.role})" for p in participants),
        prompts.data_block("agenda", meeting.agenda or "(none)"),
        prompts.data_block("meeting_notes", meeting.raw_notes),
    ])
    try:
        extraction = ai.generate_json(task="meeting_extraction", system=prompts.EXTRACTION_SYSTEM, prompt=prompt,
                                      schema=MeetingExtraction)
    except AIError as exc:
        # Notes are untouched; status stays retryable.
        if meeting.extraction_status != "extracted":
            meeting.extraction_status = "failed"
            db.commit()
        log.warning("meeting_extraction_failed", extra={"meeting_id": meeting.id, "error_type": exc.error_type})
        raise
    project_tasks = list(db.scalars(select(Task).where(Task.project_id == project.id)))
    draft = build_draft(extraction, meeting, participants, project_tasks, getattr(ai, "model", "unknown"))
    meeting.extraction_draft = draft
    meeting.extraction_status = "extracted"
    db.commit()
    log.info("meeting_extracted", extra={"meeting_id": meeting.id, "action_items": len(draft["action_items"]),
                                         "confirmed": len(draft["confirmed_decisions"]),
                                         "proposed": len(draft["proposed_decisions"])})
    run_integrity_analysis(db, meeting, ai)
    return meeting_detail(db, meeting.id)


def run_integrity_analysis(db: Session, meeting: Meeting, ai: AIClient) -> dict:
    try:
        result = decision_svc.analyze_meeting(db, meeting, ai)
    except AIError as exc:
        db.rollback()
        result = {"status": "failed", "error_type": exc.error_type, "message": str(exc), "analyzed_at": iso(now())}
        log.warning("decision_analysis_failed", extra={"meeting_id": meeting.id, "error_type": exc.error_type})
    draft = dict(meeting.extraction_draft or {})
    draft["integrity"] = result
    meeting.extraction_draft = draft
    db.commit()
    return result


# ---------------------------------------------------------------------------- approval

def approve_meeting(db: Session, meeting_id: int, body: MeetingApprove) -> dict:
    meeting = load_meeting(db, meeting_id)
    project = get_project(db, meeting.project_id)
    approver = get_member(db, project, body.approved_by, field="approved_by", must_be_active=True)
    if meeting.extraction_status == "approved":
        raise conflict("already_approved", "This meeting's extraction was already approved.")
    if meeting.extraction_status != "extracted" or not meeting.extraction_draft:
        raise conflict("extraction_required", "Run extraction before approving.")
    current_hash = sha256(meeting.raw_notes)
    if not (current_hash == meeting.source_hash == meeting.extraction_draft.get("source_hash") == body.source_hash):
        raise conflict("source_changed", "The meeting notes changed after extraction. Re-run extraction and review again.")

    seen_existing: set[int] = set()
    for i, item in enumerate(body.action_items):
        if item.action in ("link", "carry_forward"):
            if item.existing_task_id is None:
                raise bad_request("existing_task_required", f"Action item {i + 1}: choose an existing task.")
            if item.existing_task_id in seen_existing:
                raise bad_request("duplicate_task_reference", f"Task {item.existing_task_id} is referenced twice.")
            seen_existing.add(item.existing_task_id)
            t = db.get(Task, item.existing_task_id)
            if not t or t.project_id != project.id:
                raise bad_request("invalid_task", f"Task {item.existing_task_id} is not part of this project.")
        elif item.action == "create":
            if not item.title or len(item.title.strip()) < 3:
                raise bad_request("title_required", f"Action item {i + 1}: a title is required.")
            if item.owner_id is not None:
                get_member(db, project, item.owner_id, field="owner_id", must_be_active=True)

    # Atomic state transition: a concurrent or repeated approval matches zero rows.
    claimed = db.execute(update(Meeting).where(Meeting.id == meeting.id, Meeting.extraction_status == "extracted",
                                               Meeting.source_hash == body.source_hash)
                         .values(extraction_status="approved", summary=body.summary, updated_at=now()))
    if claimed.rowcount != 1:
        db.rollback()
        raise conflict("already_approved", "This meeting was approved by another request.")

    created = {"decisions": [], "tasks_created": [], "tasks_linked": [], "tasks_carried_forward": [], "excluded": 0}
    try:
        ts = now()
        for d in body.decisions:
            if not d.include:
                continue
            dec = Decision(project_id=project.id, meeting_id=meeting.id, statement=d.statement, evidence=d.evidence,
                           status=d.status, approved_by=approver.id if d.status == "active" else None,
                           approved_at=ts if d.status == "active" else None,
                           effective_from=ts if d.status == "active" else None)
            db.add(dec)
            db.flush()
            created["decisions"].append(dec.id)
        for item in body.action_items:
            if item.action == "exclude":
                created["excluded"] += 1
            elif item.action == "create":
                task = create_task(db, project, title=item.title, description=item.description,
                                   owner_id=item.owner_id, due_at=item.due_at, deadline_text=item.deadline_text,
                                   priority=item.priority, acceptance_criteria=item.acceptance_criteria,
                                   origin_meeting_id=meeting.id, actor_id=approver.id, evidence=item.evidence)
                created["tasks_created"].append(task.id)
            else:
                task = db.get(Task, item.existing_task_id)
                rel = "carried_forward" if item.action == "carry_forward" else "linked"
                associate_with_meeting(db, task, meeting, rel, approver.id, note=item.evidence)
                created["tasks_carried_forward" if rel == "carried_forward" else "tasks_linked"].append(task.id)
        db.commit()
    except Exception:
        db.rollback()
        log.warning("meeting_approval_rolled_back", extra={"meeting_id": meeting.id})
        raise
    log.info("meeting_approved", extra={"meeting_id": meeting.id, "approved_by": approver.id,
                                        **{k: (len(v) if isinstance(v, list) else v) for k, v in created.items()}})
    return {"meeting_id": meeting.id, "created": created}

