from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from holocron.pydantic_helpers import CsvIntTuple, CsvTuple, HolocronModel, NonBlankStr


def test_csv_tuple_accepts_comma_newline_and_sequence_values() -> None:
    adapter = TypeAdapter(CsvTuple)

    assert adapter.validate_python(" alpha, beta\n gamma ,, ") == ("alpha", "beta", "gamma")
    assert adapter.validate_python([" alpha ", "", "beta", None, " gamma "]) == (
        "alpha",
        "beta",
        "gamma",
    )
    assert adapter.validate_python(("one", " two ")) == ("one", "two")


def test_csv_int_tuple_converts_items_and_rejects_invalid_ints() -> None:
    adapter = TypeAdapter(CsvIntTuple)

    assert adapter.validate_python("1, 2\n3,,") == (1, 2, 3)
    assert adapter.validate_python(["4", 5, " 6 "]) == (4, 5, 6)

    with pytest.raises(ValueError):
        adapter.validate_python("1,nope")


def test_non_blank_str_strips_whitespace_and_rejects_blank() -> None:
    adapter = TypeAdapter(NonBlankStr)

    assert adapter.validate_python("  value  ") == "value"
    with pytest.raises(ValidationError):
        adapter.validate_python("   ")


def test_holocron_model_forbids_extra_fields_and_assignment() -> None:
    class Example(HolocronModel):
        name: NonBlankStr

    model = Example(name=" alpha ")

    assert model.name == "alpha"
    with pytest.raises(ValidationError):
        Example.model_validate({"name": "alpha", "unexpected": True})
    with pytest.raises(ValidationError):
        model.name = "beta"  # type: ignore[misc]
