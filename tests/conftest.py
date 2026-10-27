from __future__ import annotations

import json

import httpx
import pytest

from libreserv_client import AsyncLibreservClient, LibreservClient

JOB = {
    "id": "77a704ed-d952-4e76-b53b-b09da8ca837f",
    "app_id": 2,
    "status": "succeeded",
    "attempt": 1,
    "max_attempts": 3,
    "src_filename": "sample.docx",
    "src_bytes": 5120,
    "out_bytes": 15099,
    "target_format": "pdf",
    "filter_options": None,
    "engine": "pool",
    "error_code": None,
    "error_msg": None,
    "webhook_url": None,
    "created_at": "2026-08-04T14:11:54.965645Z",
    "started_at": "2026-08-04T14:11:55.101899Z",
    "finished_at": "2026-08-04T14:11:58.112182Z",
    "expires_at": "2026-08-05T14:11:58.112047Z",
    "duration_ms": 3003,
    "events": [
        {"at": "2026-08-04T14:11:54.969532Z", "event": "created", "detail": "by app demo"},
        {"at": "2026-08-04T14:11:58.112182Z", "event": "succeeded", "detail": "3003 ms"},
    ],
}


def job_payload(**overrides) -> dict:
    payload = dict(JOB)
    payload.update(overrides)
    return payload


def json_response(status_code: int, payload) -> httpx.Response:
    return httpx.Response(status_code, content=json.dumps(payload).encode(),
                          headers={"Content-Type": "application/json"})


@pytest.fixture()
def make_client():
    """Build a sync client whose transport is the given handler function."""

    def factory(handler) -> LibreservClient:
        return LibreservClient(
            "http://testserver", "lsv_test_key",
            transport=httpx.MockTransport(handler),
        )

    return factory


@pytest.fixture()
def make_async_client():
    def factory(handler) -> AsyncLibreservClient:
        return AsyncLibreservClient(
            "http://testserver", "lsv_test_key",
            transport=httpx.MockTransport(handler),
        )

    return factory
