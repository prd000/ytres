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

from schemas.job_payloads import EchoPayload, WorkerActivityRow


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
