"""Typed models mirroring the libreserv API objects.

All models are plain frozen dataclasses built from API responses with
``from_dict``; unknown fields sent by newer servers are ignored, so old
clients keep working against upgraded servers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

#: Job statuses that will never change again.
TERMINAL_STATUSES = frozenset({"succeeded", "failed", "canceled", "expired"})


def _parse_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _require_datetime(value: str) -> datetime:
    """For fields the API always sends; keeps the models strictly typed."""
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@dataclass(frozen=True)
class JobEvent:
    """One entry of a job's timeline (created, started, retrying, ...)."""

    at: datetime
    event: str
    detail: str | None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JobEvent:
        return cls(
            at=_require_datetime(data["at"]),
            event=data["event"],
            detail=data.get("detail"),
        )


@dataclass(frozen=True)
class Job:
    """A conversion job as returned by the server."""

    id: str
    app_id: int
    status: str
    attempt: int
    max_attempts: int
    src_filename: str
    src_bytes: int
    out_bytes: int | None
    target_format: str
    filter_options: str | None
    engine: str | None
    error_code: str | None
    error_msg: str | None
    webhook_url: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    expires_at: datetime | None
    duration_ms: int | None
    #: Timeline events; only populated by ``get_job`` (the detail endpoint).
    events: tuple[JobEvent, ...] = field(default=())

    @property
    def is_terminal(self) -> bool:
        """True once the job can no longer change state."""
        return self.status in TERMINAL_STATUSES

    @property
    def succeeded(self) -> bool:
        return self.status == "succeeded"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Job:
        return cls(
            id=str(data["id"]),
            app_id=data["app_id"],
            status=data["status"],
            attempt=data["attempt"],
            max_attempts=data["max_attempts"],
            src_filename=data["src_filename"],
            src_bytes=data["src_bytes"],
            out_bytes=data.get("out_bytes"),
            target_format=data["target_format"],
            filter_options=data.get("filter_options"),
            engine=data.get("engine"),
            error_code=data.get("error_code"),
            error_msg=data.get("error_msg"),
            webhook_url=data.get("webhook_url"),
            created_at=_require_datetime(data["created_at"]),
            started_at=_parse_datetime(data.get("started_at")),
            finished_at=_parse_datetime(data.get("finished_at")),
            expires_at=_parse_datetime(data.get("expires_at")),
            duration_ms=data.get("duration_ms"),
            events=tuple(
                JobEvent.from_dict(event) for event in data.get("events") or ()
            ),
        )


@dataclass(frozen=True)
class AppInfo:
    """The calling app's identity, limits, and restrictions (GET /api/v1/me)."""

    id: int
    name: str
    description: str | None
    is_admin: bool
    is_active: bool
    max_file_mb: int | None
    max_jobs_per_day: int | None
    max_jobs_per_minute: int | None
    max_concurrent: int | None
    allowed_sources: str | None
    allowed_referers: str | None
    created_at: datetime
    #: HMAC secret for verifying webhook callbacks sent for this app's jobs.
    #: Excluded from repr() so printing/logging an AppInfo never leaks it.
    webhook_secret: str | None = field(default=None, repr=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AppInfo:
        return cls(
            id=data["id"],
            name=data["name"],
            description=data.get("description"),
            is_admin=data["is_admin"],
            is_active=data["is_active"],
            max_file_mb=data.get("max_file_mb"),
            max_jobs_per_day=data.get("max_jobs_per_day"),
            max_jobs_per_minute=data.get("max_jobs_per_minute"),
            max_concurrent=data.get("max_concurrent"),
            allowed_sources=data.get("allowed_sources"),
            allowed_referers=data.get("allowed_referers"),
            created_at=_require_datetime(data["created_at"]),
            webhook_secret=data.get("webhook_secret"),
        )


@dataclass(frozen=True)
class UsageRow:
    """One day of usage for one app."""

    app_id: int
    day: date
    jobs_succeeded: int
    jobs_failed: int
    bytes_in: int
    bytes_out: int
    total_duration_ms: int

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UsageRow:
        return cls(
            app_id=data["app_id"],
            day=date.fromisoformat(data["day"]),
            jobs_succeeded=data["jobs_succeeded"],
            jobs_failed=data["jobs_failed"],
            bytes_in=data["bytes_in"],
            bytes_out=data["bytes_out"],
            total_duration_ms=data["total_duration_ms"],
        )


@dataclass(frozen=True)
class UsageTotals:
    jobs_succeeded: int
    jobs_failed: int
    bytes_in: int
    bytes_out: int
    total_duration_ms: int

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UsageTotals:
        return cls(
            jobs_succeeded=data["jobs_succeeded"],
            jobs_failed=data["jobs_failed"],
            bytes_in=data["bytes_in"],
            bytes_out=data["bytes_out"],
            total_duration_ms=data["total_duration_ms"],
        )


@dataclass(frozen=True)
class UsageReport:
    """Daily usage rows plus their grand total."""

    rows: tuple[UsageRow, ...]
    totals: UsageTotals

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UsageReport:
        return cls(
            rows=tuple(UsageRow.from_dict(row) for row in data["rows"]),
            totals=UsageTotals.from_dict(data["totals"]),
        )
