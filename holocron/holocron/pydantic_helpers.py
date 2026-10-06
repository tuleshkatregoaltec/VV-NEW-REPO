from __future__ import annotations

from typing import Annotated, Any, TypeAlias, cast

from pydantic import BaseModel, BeforeValidator, ConfigDict, StringConstraints


class HolocronModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


NonBlankStr: TypeAlias = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
]


def _coerce_csv_tuple(value: object) -> object:
    if isinstance(value, str):
        return _clean_csv_items(value.replace("\n", ",").split(","))
    if isinstance(value, (list, tuple)):
        return _clean_csv_items(value)
    return value


def _coerce_csv_int_tuple(value: object) -> object:
    coerced = _coerce_csv_tuple(value)
    if isinstance(coerced, tuple):
        return tuple(int(item) for item in cast(tuple[str, ...], coerced))
    return coerced


def _clean_csv_items(items: Any) -> tuple[str, ...]:
    values: list[str] = []
    for item in items:
        text = "" if item is None else str(item).strip()
        if text:
            values.append(text)
    return tuple(values)


CsvTuple: TypeAlias = Annotated[tuple[str, ...], BeforeValidator(_coerce_csv_tuple)]
CsvIntTuple: TypeAlias = Annotated[tuple[int, ...], BeforeValidator(_coerce_csv_int_tuple)]


__all__ = ["CsvIntTuple", "CsvTuple", "HolocronModel", "NonBlankStr"]
