"""Pydantic schemas. The LLM brief schema is strict: unknown fields are rejected."""
from __future__ import annotations
from enum import Enum
from typing import List
from pydantic import BaseModel, ConfigDict, Field


class Action(str, Enum):
    APPROVE = "APPROVE"
    DECLINE = "DECLINE"
    REQUEST_INFORMATION = "REQUEST_INFORMATION"
    REFER = "REFER"
    ESCALATE = "ESCALATE"


FINAL_ACTIONS = {Action.APPROVE, Action.DECLINE}


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class KnownFact(Strict):
    fact: str
    evidence_ids: List[str] = Field(min_length=1)
    quote: str


class Conflict(Strict):
    description: str
    evidence_ids: List[str] = Field(min_length=1)
    verification_required: bool


class MissingItem(Strict):
    field: str
    reason: str


class NextStep(Strict):
    action: Action
    reason: str


class LLMBrief(Strict):
    """What the LLM is allowed to produce. Completeness is NOT here: app logic computes it."""
    submission_id: str
    known: List[KnownFact] = []
    conflicts: List[Conflict] = []
    missing: List[MissingItem] = []
    next_steps: List[NextStep] = []
    human_review_required: bool = True
