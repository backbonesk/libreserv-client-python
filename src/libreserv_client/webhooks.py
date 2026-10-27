"""Helpers for receiving libreserv webhook callbacks.

The server POSTs a JSON body when a job finishes, signed with your app's
webhook secret (available at ``client.me().webhook_secret``)::

    X-Libreserv-Event: job.finished
    X-Libreserv-Signature: sha256=<hex hmac of the raw body>

Verify and parse in your HTTP handler::

    from libreserv_client import parse_webhook

    event = parse_webhook(
        request.body,                    # raw bytes, before any JSON parsing
        secret=WEBHOOK_SECRET,
        signature_header=request.headers["X-Libreserv-Signature"],
    )
    if event.succeeded:
        ...
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime

from libreserv_client.exceptions import SignatureVerificationError, WebhookPayloadError
from libreserv_client.models import _parse_datetime

SIGNATURE_HEADER = "X-Libreserv-Signature"
EVENT_HEADER = "X-Libreserv-Event"


def verify_signature(secret: str, body: bytes, signature_header: str | None) -> bool:
    """Constant-time check of a webhook's signature against its raw body."""
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    # compare bytes, not str: compare_digest raises TypeError on non-ASCII
    # str input, and the header is attacker-controlled
    provided = (signature_header or "").encode("utf-8", "surrogateescape")
    return hmac.compare_digest(provided, expected.encode())


@dataclass(frozen=True)
class WebhookEvent:
    """The payload of a job-finished webhook."""

    job_id: str
    status: str
    src_filename: str
    target_format: str
    engine: str | None
    out_bytes: int | None
    duration_ms: int | None
    error_code: str | None
    error_msg: str | None
    created_at: datetime | None
    finished_at: datetime | None
    expires_at: datetime | None

    @property
    def succeeded(self) -> bool:
        return self.status == "succeeded"


def parse_webhook(
    body: bytes,
    *,
    secret: str,
    signature_header: str | None,
) -> WebhookEvent:
    """Verify a webhook's signature, then parse its body.

    Verification is not optional: a webhook endpoint is reachable by anyone
    on the network, so an unverified payload must never drive application
    logic. (For custom flows, :func:`verify_signature` is available on its
    own.) Always pass the **raw request bytes** — re-serialized JSON will
    not match the signature.

    Raises:
        SignatureVerificationError: the signature is missing or wrong.
        WebhookPayloadError: the (verified) body is not the expected JSON.
    """
    if not verify_signature(secret, body, signature_header):
        raise SignatureVerificationError("webhook signature missing or invalid")
    try:
        payload = json.loads(body)
        return WebhookEvent(
            job_id=payload["job_id"],
            status=payload["status"],
            src_filename=payload["src_filename"],
            target_format=payload["target_format"],
            engine=payload.get("engine"),
            out_bytes=payload.get("out_bytes"),
            duration_ms=payload.get("duration_ms"),
            error_code=payload.get("error_code"),
            error_msg=payload.get("error_msg"),
            created_at=_parse_datetime(payload.get("created_at")),
            finished_at=_parse_datetime(payload.get("finished_at")),
            expires_at=_parse_datetime(payload.get("expires_at")),
        )
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise WebhookPayloadError(f"malformed webhook payload: {exc}") from exc
