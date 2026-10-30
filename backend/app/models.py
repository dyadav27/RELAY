from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base, JSONType


def utcnow() -> datetime:
    return datetime.now(UTC)


TASK_STATUSES = ("open", "in_progress", "blocked", "completed", "cancelled")
UNFINISHED_TASK_STATUSES = ("open", "in_progress", "blocked")
TASK_PRIORITIES = ("low", "medium", "high", "critical")
DECISION_STATUSES = ("proposed", "active", "superseded", "rejected")
EXTRACTION_STATUSES = ("pending", "extracted", "approved", "failed")
CLASSIFICATIONS = (
    "consistent",
    "proposal",
    "potential_conflict",
    "conditional_change",
    "revisit",
    "explicit_replacement",
)
ALERT_STATUSES = ("pending", "confirmed_change", "marked_proposal", "dismissed", "stale")
HANDOVER_STATUSES = ("draft", "approved", "cancelled")
MEETING_TASK_RELATIONSHIPS = ("origin", "carried_forward", "linked")


def _in(col: str, values: tuple[str, ...]) -> str:
    return f"{col} IN ({', '.join(repr(v) for v in values)})"


class Workspace(Base):
    __tablename__ = "workspaces"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Member(Base):
    __tablename__ = "members"
    __table_args__ = (UniqueConstraint("workspace_id", "email", name="uq_member_email"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(320))
    role: Mapped[str] = mapped_column(String(120))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Meeting(Base):
    __tablename__ = "meetings"
    __table_args__ = (
        CheckConstraint(_in("extraction_status", EXTRACTION_STATUSES), name="ck_meeting_extraction_status"),
        Index("ix_meetings_project_meeting_at", "project_id", "meeting_at"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    record_type: Mapped[str] = mapped_column(String(40), default="meeting_notes")
    meeting_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    agenda: Mapped[str | None] = mapped_column(Text)
    raw_notes: Mapped[str] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    extraction_draft: Mapped[dict | None] = mapped_column(JSONType)
    extraction_status: Mapped[str] = mapped_column(String(20), default="pending")
    source_hash: Mapped[str] = mapped_column(String(64))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("members.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    participants: Mapped[list["MeetingParticipant"]] = relationship(
        back_populates="meeting", cascade="all, delete-orphan"
    )


class MeetingParticipant(Base):
    __tablename__ = "meeting_participants"
    meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), primary_key=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id", ondelete="CASCADE"), primary_key=True)
    attendance_status: Mapped[str] = mapped_column(String(20), default="attended")

    meeting: Mapped[Meeting] = relationship(back_populates="participants")
    member: Mapped[Member] = relationship()


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint(_in("status", TASK_STATUSES), name="ck_task_status"),
        CheckConstraint(_in("priority", TASK_PRIORITIES), name="ck_task_priority"),
        # Closure integrity enforced by the database, not only the API.
        CheckConstraint(
            "status <> 'completed' OR (outcome IS NOT NULL AND length(trim(outcome)) > 0)",
            name="ck_task_completed_needs_outcome",
        ),
        Index("ix_tasks_project_status", "project_id", "status"),
        Index("ix_tasks_project_owner", "project_id", "owner_id"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("members.id", ondelete="SET NULL"))
    origin_meeting_id: Mapped[int | None] = mapped_column(ForeignKey("meetings.id", ondelete="SET NULL"))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deadline_text: Mapped[str | None] = mapped_column(String(200))
    acceptance_criteria: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="open")
    priority: Mapped[str] = mapped_column(String(20), default="medium")
    outcome: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    owner: Mapped[Member | None] = relationship(foreign_keys=[owner_id])
    origin_meeting: Mapped[Meeting | None] = relationship(foreign_keys=[origin_meeting_id])

    # Optimistic concurrency: every flush issues UPDATE ... WHERE version = <loaded version>.
    __mapper_args__ = {"version_id_col": version}


class MeetingTask(Base):
    __tablename__ = "meeting_tasks"
    __table_args__ = (
        UniqueConstraint("meeting_id", "task_id", name="uq_meeting_task"),
        CheckConstraint(_in("relationship_type", MEETING_TASK_RELATIONSHIPS), name="ck_meeting_task_rel"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), index=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    relationship_type: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TaskEvent(Base):
    __tablename__ = "task_events"
    __table_args__ = (Index("ix_task_events_task_created", "task_id", "created_at"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("members.id", ondelete="SET NULL"))
    event_type: Mapped[str] = mapped_column(String(40))
    old_value: Mapped[dict | None] = mapped_column(JSONType)
    new_value: Mapped[dict | None] = mapped_column(JSONType)
    note: Mapped[str | None] = mapped_column(Text)
    meeting_id: Mapped[int | None] = mapped_column(ForeignKey("meetings.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    actor: Mapped[Member | None] = relationship()


class Decision(Base):
    __tablename__ = "decisions"
    __table_args__ = (
        CheckConstraint(_in("status", DECISION_STATUSES), name="ck_decision_status"),
        CheckConstraint(
            "status <> 'active' OR (approved_by IS NOT NULL AND approved_at IS NOT NULL)",
            name="ck_active_decision_is_approved",
        ),
        Index("ix_decisions_project_status", "project_id", "status"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    meeting_id: Mapped[int | None] = mapped_column(ForeignKey("meetings.id", ondelete="SET NULL"))
    statement: Mapped[str] = mapped_column(Text)
    evidence: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="proposed")
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("members.id", ondelete="SET NULL"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    effective_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    approver: Mapped[Member | None] = relationship(foreign_keys=[approved_by])
    meeting: Mapped[Meeting | None] = relationship()


class DecisionRelation(Base):
    __tablename__ = "decision_relations"
    __table_args__ = (UniqueConstraint("previous_decision_id", "new_decision_id", name="uq_decision_relation"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    previous_decision_id: Mapped[int] = mapped_column(ForeignKey("decisions.id", ondelete="CASCADE"), index=True)
    new_decision_id: Mapped[int] = mapped_column(ForeignKey("decisions.id", ondelete="CASCADE"), index=True)
    relationship_type: Mapped[str] = mapped_column(String(30))
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DecisionAlert(Base):
    __tablename__ = "decision_alerts"
    __table_args__ = (
        CheckConstraint(_in("relationship_type", CLASSIFICATIONS), name="ck_alert_classification"),
        CheckConstraint(_in("status", ALERT_STATUSES), name="ck_alert_status"),
        Index("ix_decision_alerts_meeting_status", "meeting_id", "status"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"))
    existing_decision_id: Mapped[int] = mapped_column(ForeignKey("decisions.id", ondelete="CASCADE"), index=True)
    proposed_statement: Mapped[str] = mapped_column(Text)
    relationship_type: Mapped[str] = mapped_column(String(30))
    explanation: Mapped[str] = mapped_column(Text)
    old_evidence: Mapped[str | None] = mapped_column(Text)
    new_evidence: Mapped[str | None] = mapped_column(Text)
    affected_task_ids: Mapped[list | None] = mapped_column(JSONType)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    resolved_by: Mapped[int | None] = mapped_column(ForeignKey("members.id", ondelete="SET NULL"))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    meeting: Mapped[Meeting] = relationship()
    existing_decision: Mapped[Decision] = relationship()


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("project_id", "title", "version_number", name="uq_document_version"),
        CheckConstraint("document_status IN ('current', 'superseded')", name="ck_document_status"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    source_filename: Mapped[str] = mapped_column(String(300))
    content_text: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    version_number: Mapped[int] = mapped_column(Integer, default=1)
    document_status: Mapped[str] = mapped_column(String(20), default="current")
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("members.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"
    __table_args__ = (UniqueConstraint("document_id", "chunk_index", name="uq_chunk_index"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    page_number: Mapped[int | None] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    document: Mapped[Document] = relationship()


class AnswerRun(Base):
    """Audit record of a knowledge question, the answer status and the sources cited."""

    __tablename__ = "answer_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    asked_by: Mapped[int | None] = mapped_column(ForeignKey("members.id", ondelete="SET NULL"))
    question: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30))
    answer_json: Mapped[dict | None] = mapped_column(JSONType)
    source_ids: Mapped[list | None] = mapped_column(JSONType)
    model: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Handover(Base):
    __tablename__ = "handovers"
    __table_args__ = (
        CheckConstraint(_in("status", HANDOVER_STATUSES), name="ck_handover_status"),
        CheckConstraint("from_member_id <> to_member_id", name="ck_handover_distinct_members"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    from_member_id: Mapped[int] = mapped_column(ForeignKey("members.id"))
    to_member_id: Mapped[int] = mapped_column(ForeignKey("members.id"))
    status: Mapped[str] = mapped_column(String(20), default="draft")
    start_date: Mapped[datetime] = mapped_column(Date)
    end_date: Mapped[datetime | None] = mapped_column(Date)
    brief_text: Mapped[str | None] = mapped_column(Text)
    brief_json: Mapped[dict | None] = mapped_column(JSONType)
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("members.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    from_member: Mapped[Member] = relationship(foreign_keys=[from_member_id])
    to_member: Mapped[Member] = relationship(foreign_keys=[to_member_id])
    tasks: Mapped[list["HandoverTask"]] = relationship(back_populates="handover", cascade="all, delete-orphan")


class HandoverTask(Base):
    __tablename__ = "handover_tasks"
    handover_id: Mapped[int] = mapped_column(ForeignKey("handovers.id", ondelete="CASCADE"), primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True)
    previous_owner_id: Mapped[int | None] = mapped_column(ForeignKey("members.id", ondelete="SET NULL"))
    proposed_owner_id: Mapped[int | None] = mapped_column(ForeignKey("members.id", ondelete="SET NULL"))
    selected: Mapped[bool] = mapped_column(Boolean, default=True)
    transferred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    handover: Mapped[Handover] = relationship(back_populates="tasks")
    task: Mapped[Task] = relationship()
