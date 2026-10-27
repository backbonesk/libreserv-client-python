"""Exception hierarchy for libreserv-client.

Every error raised by this library derives from :class:`LibreservError`, so a
single ``except LibreservError`` catches them all. HTTP-level failures raise
the :class:`APIError` subclass matching the server's status code.
"""

from __future__ import annotations

import httpx


class LibreservError(Exception):
    """Base class for every error raised by this library."""


class TransportError(LibreservError):
    """The server could not be reached or did not answer in time.

    Wraps the underlying network failure (DNS, connection refused, TLS,
    read/write timeout); the original ``httpx`` exception is available as
    ``__cause__``. Retrying is usually reasonable.
    """


class WaitTimeout(LibreservError):
    """A job did not reach a terminal state within the allotted time.

    The job keeps running on the server — this is purely a client-side limit.
    """

    def __init__(self, job_id: str, timeout: float):
        super().__init__(f"job {job_id} still not finished after {timeout:.0f}s")
        self.job_id = job_id
        self.timeout = timeout


class SignatureVerificationError(LibreservError):
    """A webhook body did not match its X-Libreserv-Signature header."""


class WebhookPayloadError(LibreservError):
    """A correctly signed webhook body was not the expected JSON document."""


class APIError(LibreservError):
    """The server answered with an HTTP error status."""

    def __init__(self, message: str, *, status_code: int | None = None, detail: object = None):
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail


class AuthenticationError(APIError):
    """401 — missing, malformed, revoked, or unknown API key, or the app is deactivated."""


class PermissionDeniedError(APIError):
    """403 — admin endpoint without an admin key, or an app restriction
    (allowed sources / Referers) rejected the request."""


class NotFoundError(APIError):
    """404 — no such resource (or a job owned by another app)."""


class ConflictError(APIError):
    """409 — the resource is in a conflicting state (e.g. job not cancelable)."""


class GoneError(APIError):
    """410 — the artifacts existed but expired or were deleted."""


class FileTooLargeError(APIError):
    """413 — the upload exceeds the app's file-size limit."""


class InvalidRequestError(APIError):
    """422 — validation failed (unsupported target format, malformed fields)."""


class ConversionFailedError(APIError):
    """The document could not be converted (fatal — retrying will not help).

    ``error_code`` carries the server's machine-readable reason, e.g.
    ``load_failed`` or ``no_filter``; see the server's API documentation.
    """

    def __init__(
        self,
        message: str,
        *,
        job_id: str | None = None,
        error_code: str | None = None,
        status_code: int | None = None,
        detail: object = None,
    ):
        super().__init__(message, status_code=status_code, detail=detail)
        self.job_id = job_id
        self.error_code = error_code


class QuotaExceededError(APIError):
    """429 — the app's jobs/day, jobs/minute, or concurrency quota is exhausted."""


class ServiceUnavailableError(APIError):
    """503/507 — the queue is unreachable or the server is out of disk space."""


class ServerError(APIError):
    """Any 5xx server-side failure."""


_STATUS_MAP = {
    401: AuthenticationError,
    403: PermissionDeniedError,
    404: NotFoundError,
    409: ConflictError,
    410: GoneError,
    413: FileTooLargeError,
    422: InvalidRequestError,
    429: QuotaExceededError,
    503: ServiceUnavailableError,
    507: ServiceUnavailableError,
}


def error_from_response(response: httpx.Response) -> APIError:
    """Map an HTTP error response to the matching exception instance."""
    try:
        detail = response.json().get("detail")
    except Exception:  # noqa: BLE001 - non-JSON error bodies
        detail = response.text or None

    # a failed conversion on POST /convert carries a structured detail object
    if response.status_code == 422 and isinstance(detail, dict) and "error_code" in detail:
        return ConversionFailedError(
            str(detail.get("error_msg") or "conversion failed"),
            job_id=detail.get("job_id"),
            error_code=detail.get("error_code"),
            status_code=response.status_code,
            detail=detail,
        )

    if isinstance(detail, str):
        message = detail
    elif isinstance(detail, list):
        # FastAPI validation errors: [{"loc": [...], "msg": "...", ...}, ...]
        message = "; ".join(
            str(item.get("msg", item)) if isinstance(item, dict) else str(item)
            for item in detail
        ) or f"HTTP {response.status_code}"
    else:
        message = f"HTTP {response.status_code}"
    error_cls = _STATUS_MAP.get(response.status_code)
    if error_cls is None:
        error_cls = ServerError if response.status_code >= 500 else APIError
    return error_cls(message, status_code=response.status_code, detail=detail)
