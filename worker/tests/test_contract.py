"""
Contract tests — verify job payload and worker_activity row shapes against
the shared Pydantic schemas.
"""
from __future__ import annotations
import pytest
from pydantic import ValidationError

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "shared"))

from schemas.job_payloads import (
    EchoPayload,
    CoordinatorReviewPayload,
    GeneratePlanPayload,
    GenerateReportPayload,
    ResearchSubtopicPayload,
    WorkerActivityRow,
    JOB_PAYLOAD_MODELS,
)


def test_echo_payload_valid():
    p = EchoPayload(message="hello")
    assert p.message == "hello"
    assert p.echo is None
    assert p.progress is None


def test_echo_payload_with_all_fields():
    p = EchoPayload(message="hello", progress="step_1", echo="hello")
    assert p.echo == "hello"


def test_echo_payload_missing_message_raises():
    with pytest.raises(ValidationError):
        EchoPayload()  # type: ignore[call-arg]


def test_worker_activity_row_valid():
    row = WorkerActivityRow(
        subtopic_id="abc",
        project_id="xyz",
        latest_activity="reading example.com",
        sources_stored=3,
        status="running",
    )
    assert row.status == "running"
    assert row.why_nothing_report is None


def test_worker_activity_row_invalid_status():
    with pytest.raises(ValidationError):
        WorkerActivityRow(
            subtopic_id="a",
            project_id="b",
            latest_activity="",
            sources_stored=0,
            status="invalid_status",  # type: ignore[arg-type]
        )


def test_generate_plan_payload_valid():
    p = GeneratePlanPayload(project_id="abc-123")
    assert p.project_id == "abc-123"
    assert p.feedback is None
    assert p.progress is None


def test_generate_plan_payload_with_feedback():
    p = GeneratePlanPayload(project_id="abc-123", feedback="Add more on policy")
    assert p.feedback == "Add more on policy"


def test_generate_plan_payload_missing_project_id_raises():
    with pytest.raises(ValidationError):
        GeneratePlanPayload()  # type: ignore[call-arg]


def test_registry_has_generate_plan():
    assert "generate_plan" in JOB_PAYLOAD_MODELS
    assert JOB_PAYLOAD_MODELS["generate_plan"] is GeneratePlanPayload


def test_registry_has_echo():
    assert "echo" in JOB_PAYLOAD_MODELS


def test_research_subtopic_payload_valid():
    p = ResearchSubtopicPayload(project_id="proj-1", subtopic_id="sub-1")
    assert p.project_id == "proj-1"
    assert p.subtopic_id == "sub-1"
    assert p.checkpoint is None
    assert p.progress is None


def test_research_subtopic_payload_with_checkpoint():
    ckpt = {"processed_urls": ["https://example.com"], "stored_count": 2}
    p = ResearchSubtopicPayload(project_id="p", subtopic_id="s", checkpoint=ckpt)
    assert p.checkpoint == ckpt


def test_research_subtopic_payload_missing_subtopic_id_raises():
    with pytest.raises(ValidationError):
        ResearchSubtopicPayload(project_id="p")  # type: ignore[call-arg]


def test_research_subtopic_payload_missing_project_id_raises():
    with pytest.raises(ValidationError):
        ResearchSubtopicPayload(subtopic_id="s")  # type: ignore[call-arg]


def test_registry_has_research_subtopic():
    assert "research_subtopic" in JOB_PAYLOAD_MODELS
    assert JOB_PAYLOAD_MODELS["research_subtopic"] is ResearchSubtopicPayload


def test_coordinator_review_payload_valid():
    p = CoordinatorReviewPayload(project_id="proj-1", wave=1)
    assert p.project_id == "proj-1"
    assert p.wave == 1
    assert p.progress is None


def test_coordinator_review_payload_wave2():
    p = CoordinatorReviewPayload(project_id="proj-1", wave=2)
    assert p.wave == 2


def test_coordinator_review_payload_missing_wave_raises():
    with pytest.raises(ValidationError):
        CoordinatorReviewPayload(project_id="proj-1")  # type: ignore[call-arg]


def test_coordinator_review_payload_missing_project_id_raises():
    with pytest.raises(ValidationError):
        CoordinatorReviewPayload(wave=1)  # type: ignore[call-arg]


def test_registry_has_coordinator_review():
    assert "coordinator_review" in JOB_PAYLOAD_MODELS
    assert JOB_PAYLOAD_MODELS["coordinator_review"] is CoordinatorReviewPayload


def test_generate_report_payload_curated():
    p = GenerateReportPayload(project_id="proj-1", mode="curated", source_ids=["id-1", "id-2"])
    assert p.project_id == "proj-1"
    assert p.mode == "curated"
    assert p.source_ids == ["id-1", "id-2"]
    assert p.instructions is None
    assert p.progress is None


def test_generate_report_payload_auto():
    p = GenerateReportPayload(project_id="proj-1", mode="auto")
    assert p.mode == "auto"
    assert p.source_ids == []


def test_generate_report_payload_with_instructions():
    p = GenerateReportPayload(project_id="proj-1", mode="curated", instructions="Focus on policy.")
    assert p.instructions == "Focus on policy."


def test_generate_report_payload_missing_project_id_raises():
    with pytest.raises(ValidationError):
        GenerateReportPayload(mode="curated")  # type: ignore[call-arg]


def test_generate_report_payload_missing_mode_raises():
    with pytest.raises(ValidationError):
        GenerateReportPayload(project_id="proj-1")  # type: ignore[call-arg]


def test_generate_report_payload_invalid_mode_raises():
    with pytest.raises(ValidationError):
        GenerateReportPayload(project_id="proj-1", mode="manual")  # type: ignore[arg-type]


def test_registry_has_generate_report():
    assert "generate_report" in JOB_PAYLOAD_MODELS
    assert JOB_PAYLOAD_MODELS["generate_report"] is GenerateReportPayload
