"""Synthetic demo scenario (fictional company, people and data). Dates are relative to the seeding time.

Usage:  python -m app.seed            seed if the database is empty
        python -m app.seed --reset    delete ALL rows first (local development only)
"""
import sys
from datetime import timedelta

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from . import models as m
from .ai.client import UnconfiguredClient
from .db import Base, SessionLocal
from .logging_setup import get_logger
from .schemas import HandoverGenerate
from .services.common import date_to_due, now, sha256
from .services.handovers import generate_handover
from .services.knowledge import chunk_pages

log = get_logger("seed")
SEED_MODEL = "seed: synthetic demo (no AI call)"

M1_NOTES = """Payment Integration Kickoff. Attendees: Demo Manager, Rahul, Priya, Amit.

Context: we need to accept card and UPI payments through the new payment gateway before the Q4 release.

Authentication: Amit walked through options for authenticating payment API calls. The team agreed to use the existing internal authentication service for payment API authentication. Decision approved by Demo Manager. Reason: it is already security-reviewed and avoids a new vendor contract.

Webhooks: Rahul noted the gateway reports payment status through webhooks. Agreed that all webhook payloads must be signature-verified on the server before updating order status.

Action items:
- Rahul to complete the payment API integration (create order, capture, refund) by end of next sprint.
- Priya to build the checkout interface, including card and UPI forms.
- Rahul to review the authentication workflow between checkout and the internal auth service.
- Rahul to set up payment sandbox credentials this week.

Open question: do refunds above a certain amount need a separate approval flow? Not decided."""

M2_NOTES = """Weekly Payment Integration Review. Attendees: Demo Manager, Rahul, Amit. Priya absent (on leave).

Status:
- Rahul: payment API integration in progress; create-order and capture endpoints are done, refund is pending. Carrying forward.
- Checkout interface (Priya) has not started yet; carried forward to the next review.
- Amit: the authentication workflow review is blocked. The existing authentication service has limitations: no token refresh endpoint and no support for long-lived checkout sessions.

Discussion: Amit proposed migrating payment authentication to Auth0 to get token refresh and MFA out of the box. Rahul raised concerns about migration effort and vendor cost. No decision was made; the team will evaluate Auth0 before the next review. The existing internal authentication service remains the approved approach for now.

Decision: checkout will support card and UPI payments in the first release; wallets are deferred.

Action items:
- Amit to evaluate Auth0 migration effort and cost and present findings at the next review.
- Rahul to write webhook signature verification tests."""

M3_NOTES = """Payment Security Sync. Attendees: Demo Manager, Rahul, Amit.

Rahul: the refund endpoint is now implemented in the sandbox. Remaining work on the payment API is error handling for gateway timeouts.

Card data: agreed that we store only tokenized card references from the gateway; raw card numbers are never stored or logged.

Auth0: Amit's trial shows token refresh works for long checkout sessions. Amit suggested we switch payment API authentication to Auth0 starting next sprint. Demo Manager will confirm only after the cost review; until then the internal authentication service stays.

Action items:
- Amit to share the Auth0 cost estimate by 15 November.
- Someone from the frontend side should add the 3-D Secure challenge screen to checkout.
- Rahul to add retry and timeout handling for gateway calls.

Risk: the gateway sandbox has been unstable this week, which slows testing."""

DESIGN_DOC = """# Payment Gateway Integration — Technical Design (v1)

## Scope
Accept card and UPI payments in the checkout flow through the external payment gateway. Wallet payments are out of scope for the first release.

## Authentication
Payment API calls from checkout are authenticated with the existing internal authentication service. Access tokens are short-lived (15 minutes). The service does not currently offer a refresh endpoint, so checkout sessions longer than 15 minutes require re-authentication.

## Payment flow
1. Checkout creates an order through the payment API.
2. The customer completes payment on the gateway's hosted form.
3. The gateway sends a webhook with the payment status.
4. The server verifies the webhook signature before updating order status. Unverified webhooks are rejected and logged.

## Refunds
Refunds are initiated by support staff through the admin console and processed through the gateway's refund API. Whether large refunds need a second approval is an open question.

## Data handling
Only tokenized card references returned by the gateway are stored. Raw card numbers must never be stored or written to logs.

## Environments
Sandbox credentials are stored in the team secret manager, never in the repository.

## Open items
- Token refresh for long checkout sessions.
- 3-D Secure challenge handling in the checkout interface.
"""

ONBOARDING_NOTES = """Onboarding Portal Planning. Attendees: Demo Manager, Priya.

Decision: the onboarding portal will use Auth0 for customer single sign-on. Approved by Demo Manager.
Budget: the approved onboarding portal budget is USD 12,000 for this quarter.

Action items:
- Priya to configure the Auth0 tenant for the onboarding portal."""

ONBOARDING_DOC = """# Customer Onboarding Portal — Requirements

Customers sign in with Auth0 single sign-on. The approved budget for the onboarding portal is USD 12,000 for this quarter.
The portal collects company details, verifies email addresses and provisions a starter workspace."""


def _ev(db, task, etype, actor, when, old=None, new=None, note=None, meeting=None):
    db.add(m.TaskEvent(task_id=task.id, actor_id=actor.id if actor else None, event_type=etype, old_value=old,
                       new_value=new, note=note, meeting_id=meeting.id if meeting else None, created_at=when))


def _meeting(db, project, title, when, notes, participants, creator, status="approved", summary=None, draft=None,
             absent=()):
    mt = m.Meeting(project_id=project.id, title=title, meeting_at=when, raw_notes=notes, source_hash=sha256(notes),
                   extraction_status=status, summary=summary, created_by=creator.id, created_at=when, updated_at=when,
                   record_type="meeting_notes")
    if draft is not None:
        draft.setdefault("source_hash", mt.source_hash)
        draft.setdefault("model", SEED_MODEL)
        draft.setdefault("generated_at", when.isoformat())
    mt.extraction_draft = draft
    mt.participants = [m.MeetingParticipant(member_id=p.id, attendance_status="absent" if p in absent else "attended")
                       for p in participants]
    db.add(mt)
    db.flush()
    return mt


def _task(db, project, title, owner, origin, created, *, status="open", priority="medium", due=None,
          deadline_text=None, description=None, acceptance=None, outcome=None, completed_at=None, creator=None):
    t = m.Task(project_id=project.id, title=title, description=description, owner_id=owner.id if owner else None,
               origin_meeting_id=origin.id, due_at=due, deadline_text=deadline_text, acceptance_criteria=acceptance,
               status=status, priority=priority, outcome=outcome, completed_at=completed_at, created_at=created,
               updated_at=created)
    db.add(t)
    db.flush()
    db.add(m.MeetingTask(meeting_id=origin.id, task_id=t.id, relationship_type="origin", created_at=created))
    _ev(db, t, "created", creator, created, new={"title": title, "owner_id": t.owner_id, "status": "open"},
        meeting=origin)
    return t


def _doc(db, project, title, filename, body, uploader, when):
    d = m.Document(project_id=project.id, title=title, source_filename=filename, content_text=body,
                   content_hash=sha256(body), version_number=1, document_status="current", uploaded_by=uploader.id,
                   created_at=when)
    db.add(d)
    db.flush()
    for i, (page, piece) in enumerate(chunk_pages([(None, body)])):
        db.add(m.KnowledgeChunk(document_id=d.id, chunk_index=i, content=piece, page_number=page,
                                content_hash=sha256(piece), created_at=when))
    return d


def seed(db: Session) -> None:
    t0 = now()

    def ago(days, hours=0):
        return t0 - timedelta(days=days, hours=hours)

    ws = m.Workspace(name="Northwind Labs (Demo)")
    db.add(ws)
    db.flush()
    mgr = m.Member(workspace_id=ws.id, name="Demo Manager", email="manager@northwind.example", role="Project Manager")
    rahul = m.Member(workspace_id=ws.id, name="Rahul", email="rahul@northwind.example", role="Backend Developer")
    priya = m.Member(workspace_id=ws.id, name="Priya", email="priya@northwind.example", role="Frontend Developer")
    amit = m.Member(workspace_id=ws.id, name="Amit", email="amit@northwind.example", role="Backend Developer")
    db.add_all([mgr, rahul, priya, amit])
    pay = m.Project(workspace_id=ws.id, name="Payment Gateway Integration",
                    description="Card and UPI payments through an external gateway for the Q4 release.")
    onb = m.Project(workspace_id=ws.id, name="Customer Onboarding Portal",
                    description="Self-service onboarding for new business customers.")
    db.add_all([pay, onb])
    db.flush()
    everyone = [mgr, rahul, priya, amit]

    # ---- Meeting 1: kickoff
    d1_ev = "The team agreed to use the existing internal authentication service for payment API authentication."
    d2_ev = "Agreed that all webhook payloads must be signature-verified on the server before updating order status."
    m1 = _meeting(db, pay, "Payment Integration Kickoff", ago(21), M1_NOTES, everyone, mgr,
                  summary="Kickoff for card and UPI payments. Approved the internal authentication service for payment "
                          "API authentication and mandatory webhook signature verification. Four action items assigned.",
                  draft={"summary": "Kickoff for card and UPI payments.",
                         "confirmed_decisions": [{"statement": "Use the existing internal authentication service for "
                                                               "payment API authentication.", "evidence": d1_ev,
                                                  "kind": "confirmed", "evidence_verified": True}],
                         "proposed_decisions": [], "action_items": [], "blockers": [],
                         "unresolved_questions": [{"question": "Do refunds above a certain amount need a separate "
                                                               "approval flow?", "evidence": "Not decided."}],
                         "integrity": {"status": "analyzed", "alert_ids": [], "consistent": [],
                                       "note": "No approved decisions existed yet."}})
    dec1 = m.Decision(project_id=pay.id, meeting_id=m1.id, status="active", approved_by=mgr.id, approved_at=ago(21),
                      effective_from=ago(21), created_at=ago(21), evidence=d1_ev,
                      statement="Use the existing internal authentication service for payment API authentication.")
    dec2 = m.Decision(project_id=pay.id, meeting_id=m1.id, status="active", approved_by=mgr.id, approved_at=ago(21),
                      effective_from=ago(21), created_at=ago(21), evidence=d2_ev,
                      statement="All payment webhook payloads must be signature-verified on the server before order "
                                "status is updated.")
    db.add_all([dec1, dec2])

    t1 = _task(db, pay, "Complete payment API integration", rahul, m1, ago(21), priority="high",
               description="Create order, capture and refund endpoints against the gateway.",
               deadline_text="by end of next sprint", due=date_to_due((t0 + timedelta(days=6)).date()),
               acceptance="Create, capture and refund pass end-to-end tests in the sandbox.", creator=mgr)
    t2 = _task(db, pay, "Build checkout interface", priya, m1, ago(21), priority="high",
               description="Checkout UI with card and UPI forms.", due=date_to_due((t0 - timedelta(days=1)).date()),
               deadline_text="set by manager after kickoff", creator=mgr)
    t3 = _task(db, pay, "Review authentication workflow", rahul, m1, ago(21),
               description="Review token flow between checkout and the internal authentication service.",
               due=date_to_due((t0 + timedelta(days=3)).date()), deadline_text="set by manager after kickoff",
               creator=mgr)
    t4 = _task(db, pay, "Set up payment sandbox credentials", rahul, m1, ago(21), deadline_text="this week",
               creator=mgr)

    _ev(db, t3, "reassigned", mgr, ago(20), old={"owner_id": rahul.id, "owner_name": "Rahul"},
        new={"owner_id": amit.id, "owner_name": "Amit"}, note="Amit has more context on the internal auth service.")
    t3.owner_id = amit.id
    _ev(db, t1, "status_changed", rahul, ago(18), old={"status": "open"}, new={"status": "in_progress"})
    t1.status = "in_progress"
    _ev(db, t4, "completed", rahul, ago(16), old={"status": "open"}, new={"status": "completed"})
    t4.status, t4.completed_at = "completed", ago(16)
    t4.outcome = "Sandbox merchant account configured; keys stored in the team secret manager, not in the repository."
    _ev(db, t3, "status_changed", amit, ago(15), old={"status": "open"}, new={"status": "in_progress"})
    _ev(db, t3, "status_changed", amit, ago(5), old={"status": "in_progress"}, new={"status": "blocked"},
        note="Internal auth service has no token refresh endpoint; long checkout sessions fail. Waiting on platform team.")
    t3.status = "blocked"

    # ---- Meeting 2: weekly review (Auth0 proposal, NOT approved)
    d3_ev = "Decision: checkout will support card and UPI payments in the first release; wallets are deferred."
    new_ev = "Amit proposed migrating payment authentication to Auth0 to get token refresh and MFA out of the box."
    m2 = _meeting(db, pay, "Weekly Payment Integration Review", ago(4), M2_NOTES, everyone, mgr, absent=(priya,),
                  summary="Payment API partly done and carried forward; checkout UI not started and carried forward; "
                          "auth review blocked by internal auth service limitations. Auth0 migration was proposed but "
                          "not approved. Card and UPI confirmed for first release.",
                  draft={"summary": "Weekly review.", "confirmed_decisions": [
                      {"statement": "Checkout will support card and UPI payments in the first release; wallets are "
                                    "deferred.", "evidence": d3_ev, "kind": "confirmed", "evidence_verified": True}],
                         "proposed_decisions": [{"statement": "Migrate payment authentication to Auth0.",
                                                 "evidence": new_ev, "kind": "proposed", "evidence_verified": True}],
                         "action_items": [], "unresolved_questions": [],
                         "blockers": [{"description": "Internal auth service lacks token refresh and long sessions.",
                                       "evidence": "no token refresh endpoint and no support for long-lived checkout "
                                                   "sessions", "evidence_verified": True}]})
    dec3 = m.Decision(project_id=pay.id, meeting_id=m2.id, status="active", approved_by=mgr.id, approved_at=ago(4),
                      effective_from=ago(4), created_at=ago(4), evidence=d3_ev,
                      statement="Checkout will support card and UPI payments in the first release; wallets are deferred.")
    db.add(dec3)
    for task, note in ((t1, "Create-order and capture done; refund pending."),
                       (t2, "Checkout UI not started; Priya on leave.")):
        db.add(m.MeetingTask(meeting_id=m2.id, task_id=task.id, relationship_type="carried_forward", created_at=ago(4)))
        _ev(db, task, "carry_forward", mgr, ago(4), new={"meeting_id": m2.id, "meeting_title": m2.title,
                                                         "status": task.status, "owner_id": task.owner_id},
            note=note, meeting=m2)
    db.add(m.MeetingTask(meeting_id=m2.id, task_id=t3.id, relationship_type="linked", created_at=ago(4)))
    _ev(db, t3, "linked_to_meeting", mgr, ago(4), new={"meeting_id": m2.id, "meeting_title": m2.title}, meeting=m2)
    t5 = _task(db, pay, "Evaluate Auth0 migration effort and cost", amit, m2, ago(4), priority="medium",
               deadline_text="before the next review", creator=mgr,
               description="Proposal only: estimate effort and vendor cost; no migration is approved.")
    t6 = _task(db, pay, "Write webhook signature verification tests", rahul, m2, ago(4), creator=mgr)
    db.flush()
    alert = m.DecisionAlert(
        meeting_id=m2.id, existing_decision_id=dec1.id, relationship_type="proposal", status="pending",
        proposed_statement="Migrate payment API authentication from the internal authentication service to Auth0.",
        explanation="The weekly review discussed replacing the approved internal authentication service with Auth0 "
                    "because of missing token refresh. The notes state no decision was made, so this is a proposal "
                    "that would change an active decision if approved.",
        old_evidence=d1_ev, new_evidence=new_ev, affected_task_ids=[t1.id, t3.id, t5.id], created_at=ago(4))
    db.add(alert)
    db.flush()
    m2.extraction_draft = {**m2.extraction_draft, "integrity": {"status": "analyzed", "alert_ids": [alert.id],
                                                                "consistent": [], "historical_decisions_checked": 2}}

    # ---- Meeting 3: logged but not yet extracted (try the live AI workflow on it)
    _meeting(db, pay, "Payment Security Sync", ago(1), M3_NOTES, [mgr, rahul, amit], mgr, status="pending")

    _doc(db, pay, "Payment Gateway Technical Design", "payment-gateway-design.md", DESIGN_DOC, mgr, ago(19))

    # ---- Second project, used to demonstrate project isolation
    om = _meeting(db, onb, "Onboarding Portal Planning", ago(10), ONBOARDING_NOTES, [mgr, priya], mgr,
                  summary="Auth0 SSO approved for the onboarding portal; budget USD 12,000.")
    db.add(m.Decision(project_id=onb.id, meeting_id=om.id, status="active", approved_by=mgr.id, approved_at=ago(10),
                      effective_from=ago(10), created_at=ago(10),
                      statement="The onboarding portal will use Auth0 for customer single sign-on.",
                      evidence="the onboarding portal will use Auth0 for customer single sign-on"))
    _task(db, onb, "Configure Auth0 tenant for onboarding portal", priya, om, ago(10), creator=mgr)
    _doc(db, onb, "Onboarding Portal Requirements", "onboarding-requirements.md", ONBOARDING_DOC, mgr, ago(10))
    db.commit()

    # ---- Draft handover: Rahul goes on leave; built by the real handover service (records-only brief, no AI call)
    generate_handover(db, HandoverGenerate(project_id=pay.id, from_member_id=rahul.id, to_member_id=amit.id,
                                           start_date=(t0 + timedelta(days=2)).date(),
                                           end_date=(t0 + timedelta(days=16)).date(), created_by=mgr.id),
                      UnconfiguredClient())
    log.info("demo_seeded", extra={"workspace_id": ws.id, "projects": 2})


def reset(db: Session) -> None:
    if db.get_bind().dialect.name == "postgresql":
        names = ", ".join(t.name for t in Base.metadata.sorted_tables)
        db.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
    else:
        for table in reversed(Base.metadata.sorted_tables):
            db.execute(table.delete())
    db.commit()


def seed_if_empty(db: Session) -> bool:
    if db.scalar(select(func.count()).select_from(m.Workspace)):
        return False
    seed(db)
    return True


if __name__ == "__main__":
    from .config import get_settings
    from .logging_setup import configure_logging

    configure_logging(get_settings().log_file_path)
    with SessionLocal() as session:
        if "--reset" in sys.argv:
            reset(session)
        print("seeded" if seed_if_empty(session) else "database already has data; nothing seeded")
