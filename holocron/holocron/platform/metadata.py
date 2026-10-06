from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

_REDACTED = "***"
_SENSITIVE_KEY_PARTS = (
    "api_key",
    "apikey",
    "auth_token",
    "authorization",
    "consumer_id",
    "cookie",
    "credential",
    "password",
    "secret",
    "session",
    "storage_state_path",
    "token",
)


def safe_config_metadata(config: Any) -> dict[str, Any]:
    """Return config metadata suitable for raw manifests and Dagster output."""
    if hasattr(config, "model_dump"):
        payload = config.model_dump(mode="json")
    elif isinstance(config, Mapping):
        payload = dict(config)
    else:
        raise TypeError(f"Unsupported config metadata type: {type(config)!r}")

    redacted = redact_sensitive_metadata(payload)
    if not isinstance(redacted, dict):
        raise TypeError("Redacted config metadata must be a dict")
    return redacted


def redact_sensitive_metadata(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): (
                _REDACTED if _is_sensitive_key(str(key)) else redact_sensitive_metadata(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, tuple):
        return tuple(redact_sensitive_metadata(item) for item in value)
    if isinstance(value, list):
        return [redact_sensitive_metadata(item) for item in value]
    if _is_sequence_but_not_text(value):
        return [redact_sensitive_metadata(item) for item in value]
    return value


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return any(part in normalized for part in _SENSITIVE_KEY_PARTS)


def _is_sequence_but_not_text(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))
