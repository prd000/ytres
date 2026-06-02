"""
Pydantic structured-output models for the planner and research pipeline.

SourceTier matches the source_tier Postgres enum (including social_media added
in migration 0009). ResearchPlan.subtopics has a 3–8 guardrail matching the PRD
budget constraint.
"""
from __future__ import annotations
from typing import Any, Literal
from pydantic import BaseModel, Field, field_validator

SourceTier = Literal["academic", "government", "news", "industry", "social_media"]


class PlannedSubtopic(BaseModel):
    title: str
    information_objective: str
    source_tier_preferences: list[SourceTier]


class ResearchPlan(BaseModel):
    subtopics: list[PlannedSubtopic] = Field(min_length=3, max_length=8)


# ── Research pipeline schemas ─────────────────────────────────────────────────

class SearchQuerySet(BaseModel):
    """3–5 search queries generated for a subtopic.

    The model is prompted with source-tier preferences and intermittently returns
    each query as an object (e.g. ``{"query": "...", "source_type": "news"}``)
    instead of a bare string. The validator below normalises either shape down to
    a plain query string so a richer-than-asked-for response doesn't fail the job.
    """
    queries: list[str] = Field(min_length=3, max_length=5)

    @field_validator("queries", mode="before")
    @classmethod
    def _coerce_query_items(cls, value: Any) -> Any:
        if not isinstance(value, list):
            return value

        def _to_query_str(item: Any) -> Any:
            if isinstance(item, str):
                return item
            if isinstance(item, dict):
                # Accept the common "query"/"q"/"text"/"search_query" object shapes;
                # fall back to the first string value so we never silently drop a query.
                for key in ("query", "q", "text", "search_query"):
                    if isinstance(item.get(key), str):
                        return item[key]
                for v in item.values():
                    if isinstance(v, str):
                        return v
            return item  # leave anything unexpected for Pydantic to reject

        return [_to_query_str(item) for item in value]


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


class CoverageReview(BaseModel):
    """Coordinator's coverage assessment after a research wave.

    Reuses PlannedSubtopic for gap_subtopics so the subtopic INSERT path is identical.
    On wave 1: is_complete=False + gap_subtopics triggers one gap-fill round.
    On wave 2: gap_subtopics is structurally ignored — project always completes.
    """
    is_complete: bool
    summary: str
    gap_subtopics: list[PlannedSubtopic] = Field(default_factory=list, max_length=3)


# ── Report generation schemas ─────────────────────────────────────────────────

class AutoDraftSelection(BaseModel):
    """Auto-draft mode: LLM picks the top sources to include (<=25)."""
    selected_source_ids: list[str]


class ReportDraft(BaseModel):
    """Report synthesis output.

    markdown: full report with inline citations as markdown links to source URLs
              and a References section at the end.
    source_ids_used: which source IDs were actually cited (stored as source_refs).
    """
    markdown: str
    source_ids_used: list[str]


# ── RAG chat schemas ──────────────────────────────────────────────────────────

class ChatAnswer(BaseModel):
    """Structured output for the chat_respond handler.

    answer_markdown: answer synthesized from provided source chunks, with inline
                     markdown citation links [Title](URL).
    cited_source_ids: subset of the source IDs provided in context (hallucinated
                      IDs outside this set are dropped before the DB INSERT).
    confidence: how well the provided corpus answers the question.
    """
    answer_markdown: str
    cited_source_ids: list[str]
    confidence: Literal["high", "medium", "low"]
