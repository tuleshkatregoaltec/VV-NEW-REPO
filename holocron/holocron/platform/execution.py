from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from holocron.contracts import RawFile, RawRelease, SourceSpec


def utc_now() -> datetime:
    return datetime.now(UTC)


def new_run_id(now: datetime | None = None) -> str:
    current = now or utc_now()
    return current.strftime("%Y-%m-%dT%H-%M-%SZ")


def build_raw_file(
    *,
    path: str | Path,
    sha256: str,
    size_bytes: int,
    row_count: int | None = None,
    content_type: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> RawFile:
    return RawFile(
        path=str(path),
        sha256=sha256,
        size_bytes=size_bytes,
        row_count=row_count,
        content_type=content_type,
        metadata=metadata or {},
    )


def build_raw_release(
    *,
    source: SourceSpec,
    files: Iterable[RawFile],
    run_id: str | None = None,
    now: datetime | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> RawRelease:
    current = now or utc_now()
    current_run_id = run_id or new_run_id(current)
    extract_date = current.date().isoformat()
    return RawRelease(
        source=source.name,
        run_id=current_run_id,
        extract_date=extract_date,
        created_at=current.isoformat(),
        files=tuple(files),
        metadata=metadata or {},
    )
