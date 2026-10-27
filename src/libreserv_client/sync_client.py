"""The synchronous libreserv client."""

from __future__ import annotations

import os
import pathlib
import ssl
import time
from typing import Union

import httpx

from libreserv_client._base import (
    DEFAULT_POLL_INTERVAL,
    DEFAULT_TIMEOUT,
    DEFAULT_WAIT_TIMEOUT,
    ErrorMappingClient,
    FileSource,
    build_timeout,
    build_user_agent,
    check,
    deliver,
    form_data,
    open_source,
)
from libreserv_client.exceptions import ConversionFailedError, WaitTimeout, error_from_response
from libreserv_client.models import AppInfo, Job, UsageReport

OutputPath = Union[str, "os.PathLike[str]"]


class LibreservClient:
    """Synchronous client for a libreserv server.

    Args:
        base_url: Root URL of the server, e.g. ``https://convert.example.com``.
        api_key: An app API key (``lsv_...``), issued by a libreserv admin.
        timeout: Default timeout in seconds for regular API calls.
        app_identifier: Optional token appended to the User-Agent header
            (e.g. ``"invoice-service/2.3"``); the server records it per key,
            which makes client-side issues much easier to diagnose.
        verify: TLS verification, as in httpx — ``True`` (default, system
            CA bundle), a path to a CA bundle for a private CA, or an
            ``ssl.SSLContext``. ``False`` disables verification (never in
            production).
        transport: Custom ``httpx`` transport, used by the test-suite.

    Use it as a context manager (or call :meth:`close` when done)::

        with LibreservClient("https://convert.example.com", api_key="lsv_...") as client:
            client.convert("report.docx", "pdf", output="report.pdf")
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        app_identifier: str | None = None,
        verify: bool | str | ssl.SSLContext = True,
        transport: httpx.BaseTransport | None = None,
    ):
        if not base_url or not base_url.strip():
            raise ValueError("base_url must be a non-empty URL")
        if not api_key or not api_key.strip():
            # fail fast: an empty key would otherwise surface deep inside
            # httpx as a cryptic "Illegal header value b'Bearer '"
            raise ValueError("api_key must be non-empty")
        self._http = ErrorMappingClient(
            base_url=base_url.rstrip("/"),
            timeout=build_timeout(timeout),
            headers={
                "Authorization": f"Bearer {api_key}",
                "User-Agent": build_user_agent(app_identifier),
            },
            # a misconfigured scheme (http:// behind an https-redirecting
            # proxy) must not surface redirect pages as results; httpx drops
            # the Authorization header on cross-origin redirects
            follow_redirects=True,
            verify=verify,
            transport=transport,
        )

    def __enter__(self) -> LibreservClient:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    # -- conversion ------------------------------------------------------

    def convert(
        self,
        source: FileSource,
        target_format: str,
        *,
        filter_options: str | None = None,
        output: OutputPath | None = None,
        timeout: float = DEFAULT_WAIT_TIMEOUT,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
    ) -> bytes | pathlib.Path:
        """Convert a document and return the result in a single call.

        Uses the server's synchronous endpoint; if the server's own wait
        limit expires first, this transparently falls back to polling the
        job until done, so the call behaves the same for long conversions.

        Args:
            source: Path, bytes, open binary file, or ``(filename, payload)``.
            target_format: e.g. ``"pdf"`` — see :meth:`formats`.
            filter_options: Optional LibreOffice export filter options.
            output: If given, the result is written there and its
                :class:`~pathlib.Path` is returned; otherwise raw ``bytes``.
            timeout: Overall seconds to wait for the conversion.
            poll_interval: Seconds between polls in the fallback path.

        Raises:
            ConversionFailedError: The document cannot be converted.
            WaitTimeout: Still running after ``timeout`` (job keeps running).
        """
        with open_source(source) as file_tuple:
            response = self._http.post(
                "/api/v1/convert",
                files={"file": file_tuple},
                data=form_data(target_format, filter_options),
                timeout=build_timeout(timeout + 30.0),
            )
        if response.status_code == 202:
            job_id = response.headers.get("x-libreserv-job") or response.json()["job_id"]
            job = self.wait_for_job(job_id, timeout=timeout, poll_interval=poll_interval)
            return self._finish_conversion(job, output)
        check(response)
        return deliver(response.content, output)

    def _finish_conversion(
        self, job: Job, output: OutputPath | None
    ) -> bytes | pathlib.Path:
        if not job.succeeded:
            raise ConversionFailedError(
                job.error_msg or f"job ended as {job.status}",
                job_id=job.id,
                error_code=job.error_code,
            )
        return self.download_result(job.id, output=output)

    # -- job lifecycle ---------------------------------------------------

    def submit_job(
        self,
        source: FileSource,
        target_format: str,
        *,
        filter_options: str | None = None,
        webhook_url: str | None = None,
    ) -> Job:
        """Submit a job and return immediately (async flow).

        Follow up with :meth:`wait_for_job` / :meth:`get_job` and
        :meth:`download_result`, or receive a webhook if ``webhook_url``
        is given (see :mod:`libreserv_client.webhooks` for verification).
        """
        with open_source(source) as file_tuple:
            response = check(
                self._http.post(
                    "/api/v1/jobs",
                    files={"file": file_tuple},
                    data=form_data(target_format, filter_options, webhook_url),
                )
            )
        return self.get_job(response.json()["job_id"])

    def get_job(self, job_id: str) -> Job:
        """Fetch a job's current state, including its event timeline."""
        response = check(self._http.get(f"/api/v1/jobs/{job_id}"))
        return Job.from_dict(response.json())

    def list_jobs(
        self, *, status: str | None = None, limit: int = 50, offset: int = 0
    ) -> list[Job]:
        """List this app's jobs, newest first."""
        params: dict[str, str | int] = {"limit": limit, "offset": offset}
        if status is not None:
            params["status"] = status
        response = check(self._http.get("/api/v1/jobs", params=params))
        return [Job.from_dict(item) for item in response.json()]

    def wait_for_job(
        self,
        job_id: str,
        *,
        timeout: float = DEFAULT_WAIT_TIMEOUT,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
    ) -> Job:
        """Poll until the job is terminal and return it (whatever the outcome).

        Raises:
            WaitTimeout: Not terminal after ``timeout`` seconds.
        """
        deadline = time.monotonic() + timeout
        while True:
            job = self.get_job(job_id)
            if job.is_terminal:
                return job
            if time.monotonic() >= deadline:
                raise WaitTimeout(str(job_id), timeout)
            time.sleep(poll_interval)

    def cancel_job(self, job_id: str) -> Job:
        """Cancel a queued/running job (or delete a finished job's files)."""
        response = check(self._http.delete(f"/api/v1/jobs/{job_id}"))
        return Job.from_dict(response.json())

    # -- downloads -------------------------------------------------------

    def download_result(
        self, job_id: str, *, output: OutputPath | None = None
    ) -> bytes | pathlib.Path:
        """Download the converted document of a succeeded job."""
        return self._download(f"/api/v1/jobs/{job_id}/result", output)

    def download_source(
        self, job_id: str, *, output: OutputPath | None = None
    ) -> bytes | pathlib.Path:
        """Download the originally uploaded document (while retained)."""
        return self._download(f"/api/v1/jobs/{job_id}/source", output)

    def job_log(self, job_id: str) -> str:
        """The job's plain-text log (engine used, errors, retries)."""
        response = check(self._http.get(f"/api/v1/jobs/{job_id}/log"))
        return response.text

    def _download(
        self, url: str, output: OutputPath | None
    ) -> bytes | pathlib.Path:
        with self._http.stream("GET", url) as response:
            if not response.is_success:
                response.read()
                raise error_from_response(response)
            if output is None:
                return b"".join(response.iter_bytes())
            path = pathlib.Path(output)
            with path.open("wb") as handle:
                for chunk in response.iter_bytes():
                    handle.write(chunk)
            return path

    # -- account ---------------------------------------------------------

    def me(self) -> AppInfo:
        """This app's identity, quotas, restrictions, and webhook secret."""
        response = check(self._http.get("/api/v1/me"))
        return AppInfo.from_dict(response.json())

    def usage(
        self, *, date_from: str | None = None, date_to: str | None = None
    ) -> UsageReport:
        """This app's usage report (dates as ``YYYY-MM-DD``, inclusive)."""
        params = {}
        if date_from is not None:
            params["from"] = date_from
        if date_to is not None:
            params["to"] = date_to
        response = check(self._http.get("/api/v1/me/usage", params=params))
        return UsageReport.from_dict(response.json())

    def formats(self) -> dict[str, str]:
        """Supported target formats, mapped to their file extensions."""
        response = check(self._http.get("/api/v1/formats"))
        return {str(k): str(v) for k, v in response.json()["target_formats"].items()}
