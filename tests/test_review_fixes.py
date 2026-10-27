"""Tests for the pre-1.0 review fixes: redirects, transport errors,
non-ASCII webhook signatures."""

from __future__ import annotations

import hashlib
import hmac
import json
import ssl

import httpx
import pytest

from libreserv_client import (
    APIError,
    AppInfo,
    AsyncLibreservClient,
    InvalidRequestError,
    LibreservClient,
    SignatureVerificationError,
    TransportError,
    WebhookPayloadError,
    parse_webhook,
    verify_signature,
)


def test_redirect_is_followed_not_delivered(make_client):
    """A redirecting server (e.g. http:// behind an https proxy) must be
    followed — the redirect page must never come back as the "result"."""
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if len(calls) == 1:
            return httpx.Response(
                307, headers={"Location": str(request.url).replace("8080", "9090")}
            )
        return httpx.Response(200, content=b"%PDF-real-result")

    client = make_client(handler)
    result = client.convert(b"doc-bytes", "pdf")
    assert result == b"%PDF-real-result"
    assert len(calls) == 2


def test_unfollowable_redirect_raises_not_delivers(make_client):
    """A 3xx without Location survives redirect-following; check() must
    raise instead of returning the body as a converted document."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(304, content=b"<html>not a document</html>")

    client = make_client(handler)
    with pytest.raises(APIError):
        client.convert(b"doc-bytes", "pdf")


def test_network_failure_raises_transport_error(make_client):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    client = make_client(handler)
    with pytest.raises(TransportError) as excinfo:
        client.me()
    assert isinstance(excinfo.value.__cause__, httpx.ConnectError)


async def test_async_network_failure_raises_transport_error(make_async_client):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out")

    client = make_async_client(handler)
    with pytest.raises(TransportError):
        await client.me()


def test_non_ascii_signature_header_returns_false():
    """Attacker-controlled header content must yield False, not TypeError."""
    assert verify_signature("secret", b"{}", "sha256=caf\u00e9\u2603") is False
    assert verify_signature("secret", b"{}", None) is False


def test_empty_credentials_fail_fast():
    """An empty api_key/base_url must raise immediately with a clear message,
    not surface as a cryptic httpx protocol error at request time."""
    with pytest.raises(ValueError, match="api_key"):
        LibreservClient("http://testserver", "")
    with pytest.raises(ValueError, match="api_key"):
        AsyncLibreservClient("http://testserver", "  ")
    with pytest.raises(ValueError, match="base_url"):
        LibreservClient("", "lsv_key")


def _signed(secret: str, payload: dict) -> tuple[bytes, str]:
    body = json.dumps(payload).encode()
    return body, "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_parse_webhook_requires_secret_and_verifies():
    """Verification cannot be skipped: no secret -> TypeError at the call
    site; wrong signature -> SignatureVerificationError before any parsing."""
    body, sig = _signed("s3cret", {"job_id": "j1", "status": "succeeded",
                                   "src_filename": "a.docx", "target_format": "pdf"})
    event = parse_webhook(body, secret="s3cret", signature_header=sig)
    assert event.succeeded and event.job_id == "j1"

    with pytest.raises(TypeError):
        parse_webhook(body, signature_header=sig)  # type: ignore[call-arg]
    with pytest.raises(SignatureVerificationError):
        parse_webhook(body, secret="wrong", signature_header=sig)
    with pytest.raises(SignatureVerificationError):
        parse_webhook(body, secret="s3cret", signature_header=None)


def test_malformed_signed_webhook_raises_library_error():
    """A signed-but-malformed body must surface as a LibreservError, not a
    bare KeyError/ValueError, so `except LibreservError` stays exhaustive."""
    for raw in (b"not json", b'{"status": "succeeded"}', b"[1, 2]"):
        sig = "sha256=" + hmac.new(b"s3cret", raw, hashlib.sha256).hexdigest()
        with pytest.raises(WebhookPayloadError):
            parse_webhook(raw, secret="s3cret", signature_header=sig)


def test_webhook_secret_hidden_from_repr():
    """print(client.me()) / logging must never leak the HMAC secret."""
    info = AppInfo.from_dict({
        "id": 1, "name": "demo", "is_admin": False, "is_active": True,
        "created_at": "2026-08-04T14:11:54Z", "webhook_secret": "TOPSECRET",
    })
    assert info.webhook_secret == "TOPSECRET"
    assert "TOPSECRET" not in repr(info)
    assert "TOPSECRET" not in str(info)


def test_verify_option_is_accepted(make_client):
    """TLS verification is configurable: bool, CA-bundle path, SSLContext."""
    for verify in (True, False, ssl.create_default_context()):
        LibreservClient("https://testserver", "lsv_key", verify=verify).close()
    # a MockTransport ignores TLS, but the kwarg must round-trip cleanly
    client = make_client(lambda req: httpx.Response(200, json={"target_formats": {"pdf": "pdf"}}))
    assert client.formats() == {"pdf": "pdf"}


def test_validation_error_detail_list_is_readable(make_client):
    """FastAPI-style 422 bodies carry a list under `detail`; the exception
    message must surface the messages, not a bare 'HTTP 422'."""
    errors = [
        {"loc": ["body", "target_format"], "msg": "unsupported target format",
         "type": "value_error"},
        {"loc": ["body", "file"], "msg": "field required", "type": "missing"},
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"detail": errors})

    client = make_client(handler)
    with pytest.raises(InvalidRequestError) as excinfo:
        client.formats()
    assert "unsupported target format; field required" in str(excinfo.value)
    assert isinstance(excinfo.value.detail, list)
