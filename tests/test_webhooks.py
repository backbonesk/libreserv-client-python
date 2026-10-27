from __future__ import annotations

import hashlib
import hmac
import json

import pytest

from libreserv_client import SignatureVerificationError, parse_webhook, verify_signature

PAYLOAD = {
    "job_id": "815105c5-4199-4ab1-a281-834761f4d05b",
    "status": "succeeded",
    "src_filename": "sample.docx",
    "target_format": "pdf",
    "engine": "pool",
    "out_bytes": 15099,
    "duration_ms": 194,
    "error_code": None,
    "error_msg": None,
    "created_at": "2026-08-04T19:35:24.897364+00:00",
    "finished_at": "2026-08-04T19:35:25.484787+00:00",
    "expires_at": "2026-08-05T19:35:25.484790+00:00",
}


def _signed(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_verify_signature_roundtrip():
    body = json.dumps(PAYLOAD).encode()
    header = _signed("secret", body)
    assert verify_signature("secret", body, header)
    assert not verify_signature("secret", body + b" ", header)  # body must be raw
    assert not verify_signature("other", body, header)
    assert not verify_signature("secret", body, None)


def test_parse_webhook_with_verification():
    body = json.dumps(PAYLOAD).encode()
    event = parse_webhook(body, secret="secret", signature_header=_signed("secret", body))
    assert event.succeeded
    assert event.job_id == PAYLOAD["job_id"]
    assert event.finished_at.year == 2026


def test_parse_webhook_rejects_bad_signature():
    body = json.dumps(PAYLOAD).encode()
    with pytest.raises(SignatureVerificationError):
        parse_webhook(body, secret="secret", signature_header="sha256=deadbeef")
    with pytest.raises(SignatureVerificationError):
        parse_webhook(body, secret="secret", signature_header=None)


def test_parse_webhook_cannot_skip_verification():
    """There is no unverified mode: omitting the secret is a call-site error."""
    body = json.dumps(PAYLOAD).encode()
    with pytest.raises(TypeError):
        parse_webhook(body)  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        parse_webhook(body, signature_header=_signed("secret", body))  # type: ignore[call-arg]
