"""Internals shared by the sync and async clients."""

from __future__ import annotations

import os
import pathlib
from collections.abc import Iterator
from contextlib import contextmanager
from typing import IO, Any, Union

import httpx

from libreserv_client._version import __version__
from libreserv_client.exceptions import TransportError, error_from_response

#: Anything the upload helpers accept as a document source: a filesystem path,
#: raw bytes, an open binary file object, or an explicit (filename, payload)
#: pair when the filename cannot be derived.
FileSource = Union[str, "os.PathLike[str]", bytes, IO[bytes], tuple[str, Any]]

DEFAULT_TIMEOUT = 30.0
DEFAULT_WAIT_TIMEOUT = 600.0
DEFAULT_POLL_INTERVAL = 1.0
CONNECT_TIMEOUT = 10.0


def build_user_agent(app_identifier: str | None = None) -> str:
    """User-Agent sent with every request; the server records it per API key.

    Pass ``app_identifier`` (e.g. ``"invoice-service/2.3"``) to make your
    application identifiable in the server's diagnostics.
    """
    base = f"libreserv-client-python/{__version__} python-httpx/{httpx.__version__}"
    return f"{base} {app_identifier}" if app_identifier else base


def build_timeout(total: float) -> httpx.Timeout:
    return httpx.Timeout(total, connect=CONNECT_TIMEOUT)


@contextmanager
def open_source(
    source: FileSource, filename: str | None = None
) -> Iterator[tuple[str, Any]]:
    """Yield an ``(upload_name, payload)`` pair for httpx, closing what we open.

    The upload name matters: the server preserves it and derives the result's
    download filename from it.
    """
    if isinstance(source, tuple):
        name, payload = source
        yield (filename or name, payload)
        return
    if isinstance(source, bytes):
        yield (filename or "upload", source)
        return
    if isinstance(source, (str, os.PathLike)):
        path = pathlib.Path(source)
        with path.open("rb") as handle:
            yield (filename or path.name, handle)
        return
    # an already-open binary file object
    inferred = getattr(source, "name", None)
    if filename is None and isinstance(inferred, str):
        filename = pathlib.Path(inferred).name
    yield (filename or "upload", source)


def form_data(
    target_format: str,
    filter_options: str | None = None,
    webhook_url: str | None = None,
) -> dict[str, str]:
    data = {"target_format": target_format}
    if filter_options is not None:
        data["filter_options"] = filter_options
    if webhook_url is not None:
        data["webhook_url"] = webhook_url
    return data


def check(response: httpx.Response) -> httpx.Response:
    """Return the response, or raise the matching APIError subclass.

    Anything that is not a 2xx raises — including stray 3xx responses that
    survive redirect following (e.g. a misconfigured ``base_url``), which
    must never be delivered as a "converted document".
    """
    if not response.is_success:
        raise error_from_response(response)
    return response


class ErrorMappingClient(httpx.Client):
    """httpx.Client whose network failures raise :class:`TransportError`.

    ``send()`` is the single choke point for both regular and streamed
    requests, so every call site gets the translation for free.
    """

    def send(self, *args: Any, **kwargs: Any) -> httpx.Response:
        try:
            return super().send(*args, **kwargs)
        except httpx.TransportError as exc:
            raise TransportError(str(exc) or exc.__class__.__name__) from exc


class ErrorMappingAsyncClient(httpx.AsyncClient):
    """httpx.AsyncClient counterpart of :class:`ErrorMappingClient`."""

    async def send(self, *args: Any, **kwargs: Any) -> httpx.Response:
        try:
            return await super().send(*args, **kwargs)
        except httpx.TransportError as exc:
            raise TransportError(str(exc) or exc.__class__.__name__) from exc


def deliver(
    content: bytes, output: str | os.PathLike[str] | None
) -> bytes | pathlib.Path:
    """Return raw bytes, or write them to ``output`` and return its Path."""
    if output is None:
        return content
    path = pathlib.Path(output)
    path.write_bytes(content)
    return path
