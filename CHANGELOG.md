# Changelog

All notable changes to `libreserv-client` are documented here.
Versions follow [Semantic Versioning](https://semver.org/). `master`
carries `X.Y.Z.devN` between releases; a release is a version-bump commit
tagged `vX.Y.Z` and published to PyPI.

## 1.0.2 — unreleased

(nothing yet)

## 1.0.1 — 2026-10-27

### Upgrading from 1.0.0

Three changes can affect existing code:

- **Network errors are now `TransportError`** (a `LibreservError`), no
  longer raw `httpx` exceptions. Code that caught `httpx.ConnectError` /
  `httpx.TimeoutException` directly must catch `TransportError` (or
  `LibreservError`) instead; the original httpx error is available as
  `__cause__`.
- **`parse_webhook` requires `secret`.** Calls that omitted it (and so
  skipped verification) now raise `TypeError`; pass
  `secret=client.me().webhook_secret`.
- **Redirects are followed and any non-2xx raises.** A `base_url` that
  redirected (e.g. `http://` → `https://`) used to return the redirect page
  as the "result"; it now works correctly — or raises `APIError` if the
  redirect cannot be followed.

### Changes

- `parse_webhook` now always verifies the signature — `secret` is required,
  so an unverified payload can never drive application logic by accident.
  A correctly signed but malformed body raises the new
  `WebhookPayloadError` instead of a bare `KeyError`/`ValueError`.
- `AppInfo.webhook_secret` is excluded from the dataclass `repr`, so
  printing or logging an `AppInfo` no longer leaks the HMAC secret.
- New `verify` option on both clients (CA bundle path, `ssl.SSLContext`,
  or bool) for servers behind a private CA.
- The package ships a `py.typed` marker and passes `mypy --strict`;
  model fields the API always sends are now typed as non-optional
  (`created_at`, event `at`), `list_jobs` params and `formats()` are
  precisely typed.
- 422 validation errors from the server (FastAPI-style list `detail`)
  now carry the actual validation messages instead of a bare `HTTP 422`.
- Network failures (DNS, connection refused, TLS, timeouts) now raise
  `TransportError` — a `LibreservError` subclass wrapping the underlying
  `httpx` exception — so `except LibreservError` really catches everything
  the library raises, as documented.
- The clients now follow HTTP redirects, and any non-2xx response raises.
  Previously a misconfigured `base_url` (e.g. `http://` behind an
  https-redirecting proxy) could silently deliver the redirect page as the
  "converted document". httpx drops the Authorization header on
  cross-origin redirects, so the API key does not leak.
- `verify_signature` no longer raises `TypeError` on non-ASCII signature
  headers (attacker-controlled input); it returns `False`.
- An empty `api_key` or `base_url` now raises `ValueError` at construction
  instead of a cryptic httpx protocol error at request time.
- Explicit source-distribution contents (package, tests, and docs only).

## 1.0.0 — 2026-08-04

- Initial release.
