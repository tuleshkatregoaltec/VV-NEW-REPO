"""Shared test fakes for S3 and related helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class FakeS3:
    """In-memory S3 fake covering all methods used across the test suite.

    - `objects`: byte store (JSONL blobs, binary downloads, etc.)
    - `json_objects`: JSON store (checkpoints, manifests written via put_json)
    - `content_types`: tracks the content_type passed to put_bytes
    """

    def __init__(
        self,
        objects: dict[str, bytes] | None = None,
        *,
        public_url_base: str = "https://cdn.example.test",
    ) -> None:
        self.objects: dict[str, bytes] = objects or {}
        self.json_objects: dict[str, Any] = {}
        self.content_types: dict[str, str | None] = {}
        self.public_url_base = public_url_base

    def download_file(self, *, key: str, path: str | Path) -> None:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(self.objects[key])

    def list_keys(self, *, prefix: str) -> list[str]:
        return sorted(key for key in self.objects if key.startswith(prefix))

    def read_text(self, *, key: str, encoding: str = "utf-8") -> str:
        return self.objects[key].decode(encoding)

    def put_bytes(self, *, key: str, payload: bytes, content_type: str | None = None) -> None:
        self.objects[key] = payload
        self.content_types[key] = content_type

    def object_exists(self, *, key: str) -> bool:
        return key in self.objects

    def public_url(self, *, key: str) -> str | None:
        return f"{self.public_url_base.rstrip('/')}/{key}" if self.public_url_base else None

    def get_json(self, *, key: str) -> dict[str, Any] | None:
        return self.json_objects.get(key)

    def put_json(self, *, key: str, payload: dict[str, Any]) -> None:
        self.json_objects[key] = payload


def _jsonl_bytes(rows: list[dict[str, Any]]) -> bytes:
    """Encode rows as compact JSONL bytes. Returns b'' for empty input."""
    if not rows:
        return b""
    return ("\n".join(json.dumps(row, separators=(",", ":")) for row in rows) + "\n").encode(
        "utf-8"
    )
