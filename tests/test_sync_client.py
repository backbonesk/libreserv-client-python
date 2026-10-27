from __future__ import annotations

import httpx
import pytest

from conftest import job_payload, json_response
from libreserv_client import (
    AuthenticationError,
    ConversionFailedError,
    FileTooLargeError,
    NotFoundError,
    PermissionDeniedError,
    QuotaExceededError,
    ServiceUnavailableError,
    WaitTimeout,
    __version__,
)


def test_user_agent_and_auth_headers(make_client):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(request.headers)
        return json_response(200, {"target_formats": {"pdf": "pdf"}})

    with make_client(handler) as client:
        client.formats()
    assert seen["user-agent"].startswith(f"libreserv-client-python/{__version__}")
    assert seen["authorization"] == "Bearer lsv_test_key"


def test_convert_returns_bytes(make_client):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/convert"
        assert b"sample.docx" in request.read()  # multipart carries the filename
        return httpx.Response(200, content=b"%PDF-fake")

    with make_client(handler) as client:
        result = client.convert(("sample.docx", b"doc-bytes"), "pdf")
    assert result == b"%PDF-fake"


def test_convert_writes_output_file(make_client, tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"%PDF-fake")

    destination = tmp_path / "out.pdf"
    with make_client(handler) as client:
        result = client.convert(b"doc", "pdf", output=destination)
    assert result == destination
    assert destination.read_bytes() == b"%PDF-fake"


def test_convert_falls_back_to_polling_on_202(make_client):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == "/api/v1/convert":
            return httpx.Response(
                202,
                json={"job_id": job_payload()["id"], "status": "running"},
                headers={"X-Libreserv-Job": job_payload()["id"]},
            )
        if request.url.path.endswith("/result"):
            return httpx.Response(200, content=b"%PDF-late")
        return json_response(200, job_payload())  # job detail: already succeeded

    with make_client(handler) as client:
        result = client.convert(b"doc", "pdf", poll_interval=0)
    assert result == b"%PDF-late"
    assert calls[0] == "/api/v1/convert"
    assert calls[-1].endswith("/result")


def test_convert_failure_maps_to_conversion_failed(make_client):
    def handler(request: httpx.Request) -> httpx.Response:
        return json_response(
            422,
            {"detail": {"job_id": "j1", "error_code": "no_filter",
                        "error_msg": "no export filter"}},
        )

    with make_client(handler) as client:
        with pytest.raises(ConversionFailedError) as excinfo:
            client.convert(b"doc", "pdf")
    assert excinfo.value.error_code == "no_filter"
    assert excinfo.value.job_id == "j1"


def test_submit_wait_download_roundtrip(make_client, tmp_path):
    state = {"polls": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/v1/jobs" and request.method == "POST":
            return json_response(202, {"job_id": job_payload()["id"], "status": "queued"})
        if path.endswith("/result"):
            return httpx.Response(200, content=b"%PDF-async")
        state["polls"] += 1
        status = "queued" if state["polls"] < 3 else "succeeded"
        return json_response(200, job_payload(status=status))

    with make_client(handler) as client:
        job = client.submit_job(b"doc", "pdf")
        assert job.status == "queued"
        job = client.wait_for_job(job.id, poll_interval=0)
        assert job.succeeded
        out = client.download_result(job.id, output=tmp_path / "x.pdf")
    assert out.read_bytes() == b"%PDF-async"


def test_wait_for_job_times_out(make_client):
    def handler(request: httpx.Request) -> httpx.Response:
        return json_response(200, job_payload(status="running"))

    with make_client(handler) as client:
        with pytest.raises(WaitTimeout):
            client.wait_for_job("j1", timeout=0, poll_interval=0)


@pytest.mark.parametrize(
    ("status_code", "expected"),
    [
        (401, AuthenticationError),
        (403, PermissionDeniedError),
        (404, NotFoundError),
        (413, FileTooLargeError),
        (429, QuotaExceededError),
        (503, ServiceUnavailableError),
    ],
)
def test_error_mapping(make_client, status_code, expected):
    def handler(request: httpx.Request) -> httpx.Response:
        return json_response(status_code, {"detail": "nope"})

    with make_client(handler) as client:
        with pytest.raises(expected) as excinfo:
            client.get_job("j1")
    assert excinfo.value.status_code == status_code
    assert str(excinfo.value) == "nope"


def test_me_and_usage_parsing(make_client):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/me":
            return json_response(200, {
                "id": 2, "name": "demo", "description": None, "is_admin": False,
                "is_active": True, "max_file_mb": 50, "max_jobs_per_day": None,
                "max_jobs_per_minute": None, "max_concurrent": None,
                "allowed_sources": None, "allowed_referers": None,
                "created_at": "2026-08-04T08:00:00Z", "webhook_secret": "s3cr3t",
            })
        return json_response(200, {
            "rows": [{"app_id": 2, "day": "2026-08-04", "jobs_succeeded": 5,
                      "jobs_failed": 1, "bytes_in": 100, "bytes_out": 900,
                      "total_duration_ms": 4000}],
            "totals": {"jobs_succeeded": 5, "jobs_failed": 1, "bytes_in": 100,
                       "bytes_out": 900, "total_duration_ms": 4000},
        })

    with make_client(handler) as client:
        me = client.me()
        report = client.usage(date_from="2026-08-01")
    assert me.name == "demo" and me.webhook_secret == "s3cr3t"
    assert report.totals.jobs_succeeded == 5
    assert report.rows[0].day.isoformat() == "2026-08-04"


def test_upload_from_path_uses_filename(make_client, tmp_path):
    source = tmp_path / "report.docx"
    source.write_bytes(b"doc-from-disk")

    def handler(request: httpx.Request) -> httpx.Response:
        body = request.read()
        assert b'filename="report.docx"' in body
        assert b"doc-from-disk" in body
        return httpx.Response(200, content=b"%PDF")

    with make_client(handler) as client:
        client.convert(source, "pdf")
