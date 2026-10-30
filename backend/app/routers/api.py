"""REST API. Thin handlers: validation via Pydantic, business rules and transactions live in services."""
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from ..ai.client import AIClient, get_ai_client
from ..config import get_settings
from ..db import get_db
from ..models import Member, Project, Workspace
from ..schemas import (
    AlertResolve,
    AnalyzeRequest,
    CatchUpRequest,
    HandoverApprove,
    HandoverGenerate,
    KnowledgeAsk,
    MeetingApprove,
    MeetingCreate,
    MeetingUpdate,
    TaskCarryForward,
    TaskClose,
    TaskCreate,
    TaskReopen,
    TaskUpdate,
)
from ..services import catchup, dashboard, decisions, handovers, knowledge, meetings, tasks
from ..services.common import get_project, member_names

router = APIRouter(prefix="/api")
DB = Annotated[Session, Depends(get_db)]
AI = Annotated[AIClient, Depends(get_ai_client)]
ProjectQ = Annotated[int, Query(description="Project scope (required for all project data)")]


# ---------------------------------------------------------------- system
@router.get("/health", tags=["system"])
def health(db: DB):
    db.execute(text("SELECT 1"))
    s = get_settings()
    return {"status": "ok", "database": db.get_bind().dialect.name, "ai_configured": s.ai_configured,
            "ai_model": s.gemini_model if s.ai_configured else None}


@router.get("/dashboard", tags=["dashboard"])
def get_dashboard(db: DB, project_id: ProjectQ):
    return dashboard.dashboard(db, project_id)


@router.get("/projects", tags=["workspace"])
def list_projects(db: DB):
    rows = db.execute(select(Project, Workspace).join(Workspace, Workspace.id == Project.workspace_id)
                      .order_by(Project.id)).all()
    return [{"id": p.id, "name": p.name, "description": p.description, "workspace_id": w.id,
             "workspace_name": w.name, "is_demo_data": "(demo)" in w.name.lower()} for p, w in rows]


@router.get("/members", tags=["workspace"])
def list_members(db: DB, project_id: int | None = None):
    stmt = select(Member).order_by(Member.id)
    if project_id is not None:
        stmt = stmt.where(Member.workspace_id == get_project(db, project_id).workspace_id)
    return [{"id": m.id, "workspace_id": m.workspace_id, "name": m.name, "email": m.email, "role": m.role,
             "is_active": m.is_active} for m in db.scalars(stmt)]


@router.get("/search", tags=["knowledge"], summary="Global search across project records")
def global_search(db: DB, project_id: ProjectQ, q: Annotated[str, Query(min_length=2, max_length=200)]):
    return knowledge.search(db, project_id, q, limit=5)


# ---------------------------------------------------------------- meetings
@router.post("/meetings", tags=["meetings"], status_code=status.HTTP_201_CREATED)
def create_meeting(db: DB, body: MeetingCreate):
    m = meetings.create_meeting(db, body)
    return meetings.meeting_detail(db, m.id)


@router.get("/meetings", tags=["meetings"])
def list_meetings(db: DB, project_id: ProjectQ):
    return meetings.list_meetings(db, project_id)


@router.get("/meetings/{meeting_id}", tags=["meetings"])
def get_meeting(db: DB, meeting_id: int):
    return meetings.meeting_detail(db, meeting_id)


@router.patch("/meetings/{meeting_id}", tags=["meetings"])
def update_meeting(db: DB, meeting_id: int, body: MeetingUpdate):
    meetings.update_meeting(db, meeting_id, body)
    return meetings.meeting_detail(db, meeting_id)


@router.post("/meetings/{meeting_id}/extract", tags=["meetings"],
             summary="Run AI extraction (draft only) and decision drift analysis")
def extract_meeting(db: DB, ai: AI, meeting_id: int):
    return meetings.extract_meeting(db, meeting_id, ai)


@router.post("/meetings/{meeting_id}/approve", tags=["meetings"],
             summary="Persist human-reviewed decisions and tasks in one transaction")
def approve_meeting(db: DB, meeting_id: int, body: MeetingApprove):
    result = meetings.approve_meeting(db, meeting_id, body)
    return result | {"meeting": meetings.meeting_detail(db, meeting_id)}


# ---------------------------------------------------------------- tasks
@router.get("/tasks", tags=["tasks"])
def list_tasks(db: DB, project_id: ProjectQ, owner_id: int | None = None, status: str | None = None,
               priority: str | None = None, q: str | None = None, overdue: bool | None = None):
    return tasks.list_tasks(db, project_id, owner_id=owner_id, status=status, priority=priority, q=q, overdue=overdue)


@router.post("/tasks", tags=["tasks"], status_code=status.HTTP_201_CREATED)
def create_task(db: DB, body: TaskCreate):
    task = tasks.create_task_from_request(db, body)
    return tasks.task_detail(db, task.id)


@router.get("/tasks/{task_id}", tags=["tasks"])
def get_task(db: DB, task_id: int):
    return tasks.task_detail(db, task_id)


@router.patch("/tasks/{task_id}", tags=["tasks"], summary="Update a task (requires current version; 409 if stale)")
def update_task(db: DB, task_id: int, body: TaskUpdate):
    tasks.update_task(db, task_id, body)
    return tasks.task_detail(db, task_id)


@router.post("/tasks/{task_id}/carry-forward", tags=["tasks"])
def carry_forward(db: DB, task_id: int, body: TaskCarryForward):
    tasks.carry_forward(db, task_id, body.meeting_id, body.actor_id, body.note)
    return tasks.task_detail(db, task_id)


@router.post("/tasks/{task_id}/close", tags=["tasks"], summary="Complete or cancel; an outcome is mandatory")
def close_task(db: DB, task_id: int, body: TaskClose):
    tasks.close_task(db, task_id, body)
    return tasks.task_detail(db, task_id)


@router.post("/tasks/{task_id}/reopen", tags=["tasks"], summary="Explicit reopen with a recorded reason")
def reopen_task(db: DB, task_id: int, body: TaskReopen):
    tasks.reopen_task(db, task_id, body)
    return tasks.task_detail(db, task_id)


@router.get("/tasks/{task_id}/history", tags=["tasks"])
def task_history(db: DB, task_id: int):
    return tasks.task_history(db, task_id)


# ---------------------------------------------------------------- decisions
@router.get("/decisions", tags=["decisions"])
def list_decisions(db: DB, project_id: ProjectQ, status: str | None = None):
    return decisions.list_decisions(db, project_id, status)


@router.get("/decision-alerts", tags=["decisions"])
def list_alerts(db: DB, project_id: ProjectQ, status: str | None = "pending"):
    return decisions.list_alerts(db, project_id, status or None)


@router.post("/decisions/analyze", tags=["decisions"], summary="Re-run decision drift analysis for a meeting")
def analyze(db: DB, ai: AI, body: AnalyzeRequest):
    meeting = meetings.load_meeting(db, body.meeting_id)
    result = meetings.run_integrity_analysis(db, meeting, ai)
    return {"meeting_id": meeting.id, "integrity": result,
            "alerts": decisions.list_alerts(db, meeting.project_id, "pending")}


@router.post("/decision-alerts/{alert_id}/resolve", tags=["decisions"],
             summary="Human review: confirm change (supersede), mark as proposal, or dismiss")
def resolve_alert(db: DB, alert_id: int, body: AlertResolve):
    return decisions.resolve_alert(db, alert_id, body)


# ---------------------------------------------------------------- knowledge
@router.post("/knowledge/documents", tags=["knowledge"], status_code=status.HTTP_201_CREATED)
async def upload_document(db: DB, project_id: Annotated[int, Form()], file: Annotated[UploadFile, File()],
                          title: Annotated[str | None, Form()] = None,
                          uploaded_by: Annotated[int | None, Form()] = None):
    limit = get_settings().max_upload_bytes
    data = await file.read(limit + 1)
    doc = knowledge.ingest_document(db, project_id=project_id, filename=file.filename or "upload", data=data,
                                    title=title, uploaded_by=uploaded_by)
    names = member_names(db, get_project(db, project_id).workspace_id)
    return knowledge.serialize_document(doc, names)


@router.get("/knowledge/documents", tags=["knowledge"])
def list_documents(db: DB, project_id: ProjectQ):
    return knowledge.list_documents(db, project_id)


@router.get("/knowledge/documents/{document_id}", tags=["knowledge"])
def get_document(db: DB, document_id: int):
    from ..models import Document, KnowledgeChunk
    from ..services.common import ensure_found

    doc = ensure_found(db.get(Document, document_id), "Document", document_id)
    names = member_names(db, get_project(db, doc.project_id).workspace_id)
    chunks = db.scalar(select(func.count()).select_from(KnowledgeChunk).where(KnowledgeChunk.document_id == doc.id))
    return knowledge.serialize_document(doc, names, chunks) | {"content_text": doc.content_text}


@router.get("/knowledge/search", tags=["knowledge"])
def search(db: DB, project_id: ProjectQ, q: Annotated[str, Query(min_length=2, max_length=300)]):
    return knowledge.search(db, project_id, q)


@router.post("/knowledge/ask", tags=["knowledge"], summary="Proof-carrying answer with validated source references")
def ask(db: DB, ai: AI, body: KnowledgeAsk):
    return knowledge.ask(db, body.project_id, body.question, ai, body.actor_id)


# ---------------------------------------------------------------- handovers & catch-up
@router.post("/handovers/generate", tags=["handovers"], status_code=status.HTTP_201_CREATED)
def generate_handover(db: DB, ai: AI, body: HandoverGenerate):
    return handovers.generate_handover(db, body, ai)


@router.get("/handovers", tags=["handovers"])
def list_handovers(db: DB, project_id: ProjectQ):
    return handovers.list_handovers(db, project_id)


@router.get("/handovers/{handover_id}", tags=["handovers"])
def get_handover(db: DB, handover_id: int):
    return handovers.handover_detail(db, handover_id)


@router.post("/handovers/{handover_id}/approve", tags=["handovers"],
             summary="Transfer selected tasks atomically (all or nothing)")
def approve_handover(db: DB, handover_id: int, body: HandoverApprove):
    return handovers.approve_handover(db, handover_id, body)


@router.post("/catch-up", tags=["handovers"], summary="Re-entry brief of changes since a date")
def catch_up(db: DB, ai: AI, body: CatchUpRequest):
    return catchup.catch_up(db, body, ai)
