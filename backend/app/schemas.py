"""Request bodies for the REST API (responses are documented via serializers in services)."""
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

Priority = Literal["low", "medium", "high", "critical"]


class _Body(BaseModel):
    model_config = {"extra": "forbid"}


def _strip(v):
    return v.strip() if isinstance(v, str) else v


class MeetingCreate(_Body):
    project_id: int
    title: str = Field(min_length=3, max_length=300)
    meeting_at: datetime
    agenda: str | None = Field(None, max_length=5000)
    raw_notes: str = Field(min_length=20, max_length=100_000)
    participant_ids: list[int] = Field(min_length=1)
    record_type: Literal["meeting_notes", "transcript"] = "meeting_notes"
    created_by: int | None = None

    _s = field_validator("title", "raw_notes", "agenda", mode="before")(_strip)


class MeetingUpdate(_Body):
    title: str | None = Field(None, min_length=3, max_length=300)
    agenda: str | None = None
    raw_notes: str | None = Field(None, min_length=20, max_length=100_000)
    actor_id: int | None = None


class ApproveDecision(_Body):
    statement: str = Field(min_length=3, max_length=1000)
    evidence: str | None = None
    status: Literal["active", "proposed"]
    include: bool = True


class ApproveActionItem(_Body):
    action: Literal["create", "link", "carry_forward", "exclude"]
    existing_task_id: int | None = None
    title: str | None = Field(None, max_length=300)
    description: str | None = None
    owner_id: int | None = None
    due_at: date | None = None
    deadline_text: str | None = Field(None, max_length=200)
    priority: Priority = "medium"
    acceptance_criteria: str | None = None
    evidence: str | None = None


class MeetingApprove(_Body):
    source_hash: str = Field(min_length=64, max_length=64)
    approved_by: int
    summary: str = Field(min_length=10, max_length=4000)
    decisions: list[ApproveDecision] = []
    action_items: list[ApproveActionItem] = []


class TaskCreate(_Body):
    project_id: int
    title: str = Field(min_length=3, max_length=300)
    description: str | None = None
    owner_id: int | None = None
    due_at: date | None = None
    deadline_text: str | None = Field(None, max_length=200)
    priority: Priority = "medium"
    acceptance_criteria: str | None = None
    origin_meeting_id: int | None = None
    actor_id: int | None = None


class TaskUpdate(_Body):
    version: int
    actor_id: int | None = None
    title: str | None = Field(None, min_length=3, max_length=300)
    description: str | None = None
    owner_id: int | None = None
    due_at: date | None = None
    deadline_text: str | None = Field(None, max_length=200)
    priority: Priority | None = None
    status: Literal["open", "in_progress", "blocked"] | None = None
    blocker_note: str | None = Field(None, max_length=2000)
    acceptance_criteria: str | None = None
    note: str | None = Field(None, max_length=2000)


class TaskCarryForward(_Body):
    meeting_id: int
    actor_id: int | None = None
    note: str | None = Field(None, max_length=2000)


class TaskClose(_Body):
    version: int
    outcome: str = Field(min_length=3, max_length=4000)
    resolution: Literal["completed", "cancelled"] = "completed"
    actor_id: int | None = None

    _s = field_validator("outcome", mode="before")(_strip)


class TaskReopen(_Body):
    version: int
    reason: str = Field(min_length=3, max_length=2000)
    actor_id: int | None = None

    _s = field_validator("reason", mode="before")(_strip)


class AnalyzeRequest(_Body):
    meeting_id: int


class AlertResolve(_Body):
    action: Literal["confirm_change", "mark_proposal", "dismiss"]
    actor_id: int
    statement: str | None = Field(None, min_length=3, max_length=1000)
    note: str | None = Field(None, max_length=2000)


class KnowledgeAsk(_Body):
    project_id: int
    question: str = Field(min_length=3, max_length=1000)
    actor_id: int | None = None


class HandoverGenerate(_Body):
    project_id: int
    from_member_id: int
    to_member_id: int
    start_date: date
    end_date: date | None = None
    created_by: int | None = None


class HandoverSelection(_Body):
    task_id: int
    selected: bool


class HandoverApprove(_Body):
    approved_by: int
    selections: list[HandoverSelection] | None = None


class CatchUpRequest(_Body):
    project_id: int
    member_id: int
    since: date
