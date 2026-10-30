"""Structures the model must return. Anything that fails validation is rejected, never persisted."""
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

Classification = Literal[
    "consistent", "proposal", "potential_conflict", "conditional_change", "revisit", "explicit_replacement"
]


class ExtractedDecision(BaseModel):
    statement: str = Field(min_length=3, max_length=1000)
    evidence: str = Field(min_length=3, description="Verbatim quote from the notes supporting this decision.")


class ExtractedActionItem(BaseModel):
    title: str = Field(min_length=3, max_length=300)
    description: str | None = None
    suggested_owner_name: str | None = Field(None, description="Name exactly as written in the notes, or null.")
    deadline_text: str | None = Field(None, description="Deadline phrase exactly as written in the notes, or null.")
    due_date: date | None = Field(None, description="ISO date only if the notes state an explicit calendar date.")
    evidence: str = Field(min_length=3, description="Verbatim quote from the notes.")


class ExtractedBlocker(BaseModel):
    description: str = Field(min_length=3)
    evidence: str = Field(min_length=3)


class ExtractedQuestion(BaseModel):
    question: str = Field(min_length=3)
    evidence: str | None = None


class MeetingExtraction(BaseModel):
    summary: str = Field(min_length=10, max_length=4000)
    confirmed_decisions: list[ExtractedDecision] = []
    proposed_decisions: list[ExtractedDecision] = []
    action_items: list[ExtractedActionItem] = []
    blockers: list[ExtractedBlocker] = []
    unresolved_questions: list[ExtractedQuestion] = []


class DriftFinding(BaseModel):
    existing_decision_id: int
    new_statement: str = Field(min_length=3)
    classification: Classification
    explanation: str = Field(min_length=3)
    old_evidence: str | None = None
    new_evidence: str | None = None
    affected_task_ids: list[int] = []


class DriftAnalysis(BaseModel):
    findings: list[DriftFinding] = []


class AnswerClaim(BaseModel):
    text: str = Field(min_length=2)
    source_ids: list[str] = Field(min_length=1)


class AnswerConflict(BaseModel):
    description: str
    source_ids: list[str] = []


class KnowledgeAnswer(BaseModel):
    status: Literal["supported", "conflicting", "insufficient_evidence"]
    answer: str
    claims: list[AnswerClaim] = []
    conflicts: list[AnswerConflict] = []
    missing_information: str | None = None


class BriefItem(BaseModel):
    text: str
    refs: list[str] = []


class HandoverBriefAI(BaseModel):
    project_overview: str
    current_status: str
    responsibilities: list[BriefItem] = []
    outstanding_work_summary: str
    important_decisions: list[BriefItem] = []
    blockers: list[BriefItem] = []
    relevant_documents: list[BriefItem] = []
    next_actions: list[BriefItem] = []


class CatchUpAI(BaseModel):
    what_changed: list[BriefItem] = []
    decisions: list[BriefItem] = []
    completed_work: list[BriefItem] = []
    outstanding: list[BriefItem] = []
    ownership_changes: list[BriefItem] = []
    attention_next: list[BriefItem] = []
