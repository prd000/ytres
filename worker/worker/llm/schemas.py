"""
Pydantic structured-output models for the planner and research pipeline.

SourceTier matches the source_tier Postgres enum (including social_media added
in migration 0009). ResearchPlan.subtopics has a 3–8 guardrail matching the PRD
budget constraint.
"""
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field

SourceTier = Literal["academic", "government", "news", "industry", "social_media"]


class PlannedSubtopic(BaseModel):
    title: str
    information_objective: str
    source_tier_preferences: list[SourceTier]


class ResearchPlan(BaseModel):
    subtopics: list[PlannedSubtopic] = Field(min_length=3, max_length=8)


# ── Research pipeline schemas ─────────────────────────────────────────────────

class SearchQuerySet(BaseModel):
    """3–5 search queries generated for a subtopic."""
    queries: list[str] = Field(min_length=3, max_length=5)


class Pass1Item(BaseModel):
    """Classifier verdict for one candidate in the Pass-1 batch filter."""
    index: int
    relevant: bool
    accessible: bool


class Pass1Batch(BaseModel):
    """One batched Flash call classifies all candidate snippets cheaply."""
    items: list[Pass1Item]


class SourceEvaluation(BaseModel):
    """Pass-2 Pro evaluation of a single extracted source.

    All scores are 1–5 integers. Store rule: avg >= 3 and no dimension == 1.
    """
    score_relevance: int = Field(ge=1, le=5)
    score_credibility: int = Field(ge=1, le=5)
    score_uniqueness: int = Field(ge=1, le=5)
    score_actionability: int = Field(ge=1, le=5)
    key_takeaway: str
