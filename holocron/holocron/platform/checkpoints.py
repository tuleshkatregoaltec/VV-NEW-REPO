from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel, ValidationError


class JsonCheckpointStore(Protocol):
    def get_json(self, *, key: str) -> dict[str, Any] | None: ...

    def put_json(self, *, key: str, payload: dict[str, Any]) -> None: ...


CheckpointModelT = TypeVar("CheckpointModelT", bound=BaseModel)


def checkpoint_s3_key(*, source: str, operation: str) -> str:
    return f"state/source={source}/operation={operation}.json"


def read_checkpoint(
    store: JsonCheckpointStore,
    *,
    source: str,
    operation: str,
) -> dict[str, Any] | None:
    checkpoint = store.get_json(key=checkpoint_s3_key(source=source, operation=operation))
    if checkpoint is None:
        return None
    if not isinstance(checkpoint, dict):
        raise TypeError(
            f"Checkpoint for source={source} operation={operation} must be a JSON object"
        )
    return checkpoint


def read_checkpoint_model(
    store: JsonCheckpointStore,
    *,
    source: str,
    operation: str,
    model: type[CheckpointModelT],
) -> CheckpointModelT | None:
    checkpoint = read_checkpoint(store, source=source, operation=operation)
    if checkpoint is None:
        return None
    try:
        return model.model_validate(checkpoint)
    except ValidationError as exc:
        raise ValueError(
            f"Checkpoint for source={source} operation={operation} is invalid: {exc}"
        ) from exc


def write_checkpoint(
    store: JsonCheckpointStore,
    *,
    source: str,
    operation: str,
    payload: Mapping[str, Any],
) -> None:
    store.put_json(
        key=checkpoint_s3_key(source=source, operation=operation),
        payload=dict(payload),
    )
