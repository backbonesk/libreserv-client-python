from __future__ import annotations

from datetime import timezone

from conftest import job_payload
from libreserv_client import Job


def test_job_from_dict_parses_everything():
    job = Job.from_dict(job_payload())
    assert job.id == "77a704ed-d952-4e76-b53b-b09da8ca837f"
    assert job.succeeded and job.is_terminal
    assert job.created_at.tzinfo == timezone.utc
    assert [event.event for event in job.events] == ["created", "succeeded"]


def test_job_without_events_and_unknown_fields():
    payload = job_payload(status="queued", engine=None, finished_at=None)
    payload.pop("events")
    payload["field_from_a_newer_server"] = 42  # must be ignored
    job = Job.from_dict(payload)
    assert job.status == "queued"
    assert not job.is_terminal
    assert job.events == ()
