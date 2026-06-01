"""
Pydantic structured-output models for the planner.

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
