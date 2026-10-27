# libreserv-client

Python client for `libreserv`, the LibreOffice document-conversion service.
Convert documents (docx → pdf, xlsx → csv, pptx → pdf, …) through a libreserv 
server with one call — synchronously or asynchronously.

- Python ≥ 3.9, one dependency ([httpx](https://www.python-httpx.org/))
- Sync **and** async client with identical APIs
- Typed models, a precise exception hierarchy, webhook signature verification

## Installation

```sh
pip install libreserv-client
```

## Quick start

```python
from libreserv_client import LibreservClient

client = LibreservClient(
    "https://convert.example.com",   # your libreserv server
    api_key="lsv_...",               # issued by a libreserv admin, per app
)

# one call: upload, convert, download
client.convert("report.docx", "pdf", output="report.pdf")

# or work with bytes in memory
pdf_bytes = client.convert("report.docx", "pdf")
```

`convert()` uses the server's synchronous endpoint and transparently falls
back to polling when a conversion outlasts the server-side wait — you always
get the finished document back (or a precise exception).

Use the client as a context manager in scripts, or keep one long-lived
instance per process in services (it pools connections):

```python
with LibreservClient(url, api_key=key) as client:
    client.convert("in.xlsx", "csv", output="out.csv")
```

## Async

`AsyncLibreservClient` mirrors the sync client method-for-method:

```python
import asyncio
from libreserv_client import AsyncLibreservClient

async def main():
    async with AsyncLibreservClient("https://convert.example.com", api_key="lsv_...") as client:
        pdf = await client.convert("report.docx", "pdf")

asyncio.run(main())
```

## The job workflow (async jobs, webhooks)

For long conversions or fire-and-forget submission, use the job API:

```python
job = client.submit_job(
    "big-presentation.pptx", "pdf",
    webhook_url="https://myapp.example.com/hooks/libreserv",  # optional
)
print(job.id, job.status)          # -> "…-uuid-…", "queued"

job = client.wait_for_job(job.id)  # polls until terminal
if job.succeeded:
    client.download_result(job.id, output="deck.pdf")
else:
    print(job.error_code, job.error_msg)

client.job_log(job.id)             # full server-side conversion log (str)
client.download_source(job.id)     # the original upload, while retained
client.cancel_job(job.id)          # cancel queued/running jobs
client.list_jobs(status="failed")  # your app's job history
```

Documents can be given as a path, raw `bytes`, an open binary file, or an
explicit `("filename.docx", payload)` pair — the filename determines both
LibreOffice's import format detection and the result's download name.

### Verifying webhooks

When a job with a `webhook_url` finishes, the server POSTs a JSON body signed
with your app's webhook secret (`client.me().webhook_secret`). In your
handler, verify and parse it with the **raw request bytes** — verification is
built into `parse_webhook` and cannot be skipped, since a webhook endpoint is
reachable by anyone on the network:

```python
from libreserv_client import parse_webhook, SignatureVerificationError

def hook(request):
    try:
        event = parse_webhook(
            request.body,
            secret=WEBHOOK_SECRET,
            signature_header=request.headers["X-Libreserv-Signature"],
        )
    except SignatureVerificationError:
        return 403
    if event.succeeded:
        queue_download(event.job_id)
    return 200
```

## Error handling

Everything the library raises derives from `LibreservError`; HTTP errors map
to precise subclasses of `APIError`:

| Exception | When |
|---|---|
| `AuthenticationError` | 401 — bad/revoked key, deactivated app |
| `PermissionDeniedError` | 403 — admin-only endpoint, or your app's source/Referer restrictions rejected the request |
| `NotFoundError` | 404 — unknown job (or another app's job) |
| `ConflictError` | 409 — e.g. downloading a result that isn't ready |
| `GoneError` | 410 — artifacts expired (retention) |
| `FileTooLargeError` | 413 — upload over your app's size limit |
| `InvalidRequestError` | 422 — unsupported target format, bad fields |
| `ConversionFailedError` | the document itself cannot be converted; `.error_code` says why (`load_failed`, `no_filter`, …) |
| `QuotaExceededError` | 429 — jobs/day, jobs/minute, or concurrency quota |
| `ServiceUnavailableError` | 503/507 — queue down or server out of disk |
| `ServerError` | any 5xx |
| `TransportError` | the server could not be reached (DNS, connection, TLS, timeout) — the underlying `httpx` error is its `__cause__` |
| `WaitTimeout` | client-side wait expired; the job keeps running server-side |
| `SignatureVerificationError` | a webhook's signature is missing or wrong |
| `WebhookPayloadError` | a correctly signed webhook body is not the expected JSON |

```python
from libreserv_client import ConversionFailedError, QuotaExceededError

try:
    client.convert("input.docx", "pdf", output="out.pdf")
except ConversionFailedError as error:
    print(f"unconvertible document: {error.error_code} — {error}")
except QuotaExceededError:
    retry_later()
```

## Identify your application

The client sends `libreserv-client-python/<version>` as its User-Agent, and
the server records it per API key for diagnostics. Add your own identifier so
operators can tell your app's traffic apart:

```python
client = LibreservClient(url, api_key=key, app_identifier="invoice-service/2.3")
```

## TLS and private CAs

Certificates are verified against the system CA bundle by default. For a
self-hosted server with an internal CA, pass the bundle (or an
`ssl.SSLContext`) — never disable verification in production:

```python
client = LibreservClient(url, api_key=key, verify="/etc/ssl/corp-ca.pem")
```

## Typing

The package ships a `py.typed` marker and passes `mypy --strict`; all models
are frozen dataclasses, so your type checker sees every field and return type.

## Account helpers

```python
client.me()        # AppInfo: your quotas, restrictions, webhook secret
client.usage(date_from="2026-08-01", date_to="2026-08-31")  # daily rows + totals
client.formats()   # {"pdf": "pdf", "docx": "docx", ...}
```

## Versioning

This library follows [Semantic Versioning](https://semver.org/); see
[CHANGELOG.md](CHANGELOG.md). The current version is available as
`libreserv_client.__version__`.

## Development

```sh
uv sync
uv run pytest
uv run ruff check src tests
uv run mypy --strict src
```

## Contributing

Issues and pull requests are welcome on
[GitHub](https://github.com/backbonesk/libreserv-client-python). Development
happens in our GitLab, which mirrors `master` to GitHub — see
[CONTRIBUTING.md](CONTRIBUTING.md) for how PRs land (squash-merged, with
attribution preserved) and [SECURITY.md](SECURITY.md) for reporting
vulnerabilities privately.

## License

[MIT](LICENSE)
