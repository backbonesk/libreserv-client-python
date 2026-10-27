"""Python client for libreserv, the LibreOffice document-conversion service.

Quick start::

    from libreserv_client import LibreservClient

    with LibreservClient("https://convert.example.com", api_key="lsv_...") as client:
        client.convert("report.docx", "pdf", output="report.pdf")
"""

from libreserv_client._version import __version__
from libreserv_client.async_client import AsyncLibreservClient
from libreserv_client.exceptions import (
    APIError,
    AuthenticationError,
    ConflictError,
    ConversionFailedError,
    FileTooLargeError,
    GoneError,
    InvalidRequestError,
    LibreservError,
    NotFoundError,
    PermissionDeniedError,
    QuotaExceededError,
    ServerError,
    ServiceUnavailableError,
    SignatureVerificationError,
    TransportError,
    WaitTimeout,
    WebhookPayloadError,
)
from libreserv_client.models import (
    TERMINAL_STATUSES,
    AppInfo,
    Job,
    JobEvent,
    UsageReport,
    UsageRow,
    UsageTotals,
)
from libreserv_client.sync_client import LibreservClient
from libreserv_client.webhooks import WebhookEvent, parse_webhook, verify_signature

__all__ = [
    "__version__",
    "LibreservClient",
    "AsyncLibreservClient",
    # models
    "Job",
    "JobEvent",
    "AppInfo",
    "UsageReport",
    "UsageRow",
    "UsageTotals",
    "TERMINAL_STATUSES",
    # webhooks
    "WebhookEvent",
    "parse_webhook",
    "verify_signature",
    # exceptions
    "LibreservError",
    "APIError",
    "AuthenticationError",
    "PermissionDeniedError",
    "NotFoundError",
    "ConflictError",
    "GoneError",
    "FileTooLargeError",
    "InvalidRequestError",
    "ConversionFailedError",
    "QuotaExceededError",
    "ServiceUnavailableError",
    "ServerError",
    "SignatureVerificationError",
    "WebhookPayloadError",
    "TransportError",
    "WaitTimeout",
]
