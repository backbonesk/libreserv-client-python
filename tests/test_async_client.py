from __future__ import annotations

import httpx
import pytest

from conftest import job_payload, json_response
from libreserv_client import AuthenticationError, __version__


async def test_async_convert_and_headers(make_async_client):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(request.headers)
        return httpx.Response(200, content=b"%PDF-async")

    async with make_async_client(handler) as client:
        result = await client.convert(b"doc", "pdf")
    assert result == b"%PDF-async"
    assert seen["user-agent"].startswith(f"libreserv-client-python/{__version__}")


async def test_async_submit_wait_download(make_async_client, tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/v1/jobs" and request.method == "POST":
            return json_response(202, {"job_id": job_payload()["id"], "status": "queued"})
        if path.endswith("/result"):
            return httpx.Response(200, content=b"%PDF-x")
        return json_response(200, job_payload())

    async with make_async_client(handler) as client:
        job = await client.submit_job(b"doc", "pdf")
        job = await client.wait_for_job(job.id, poll_interval=0)
        assert job.succeeded
        out = await client.download_result(job.id, output=tmp_path / "a.pdf")
    assert out.read_bytes() == b"%PDF-x"


async def test_async_error_mapping(make_async_client):
    def handler(request: httpx.Request) -> httpx.Response:
        return json_response(401, {"detail": "invalid or missing API key"})

    async with make_async_client(handler) as client:
        with pytest.raises(AuthenticationError):
            await client.me()
