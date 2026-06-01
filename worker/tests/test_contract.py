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

from schemas.job_payloads import EchoPayload, GeneratePlanPayload, ResearchSubtopicPayload, WorkerActivityRow, JOB_PAYLOAD_MODELS


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
