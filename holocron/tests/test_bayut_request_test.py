from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from typing import Any

import pytest

from handoff.bayut_standalone import bayut_collection as collection
from handoff.bayut_standalone.run_bayut_request_test import LimitedFetcher
from handoff.bayut_standalone.run_bayut_request_test import TestStopped as BudgetStop


@pytest.fixture
def state(tmp_path: Any) -> Any:
    config = collection.CollectionConfig(
        roots=(
            collection.SearchRoot("sale", "sale", "property", "/for-sale/property/dubai/"),
            collection.SearchRoot("rent", "rent", "property", "/to-rent/property/dubai/"),
        ),
        practice_pages_per_root=3,
        max_attempts_per_page=1,
        request_pause_seconds=0,
        request_jitter_seconds=0,
        evidence="none",
    )
    connection = collection.open_database(
        config=config, output_dir=tmp_path, requested_kind="practice"
    )
    yield SimpleNamespace(config=config, connection=connection)
    connection.close()


def response(identifier: int = 1, *, outcome: str = "ok", response_bytes: int = 100) -> Any:
    return collection.FetchResult(
        requested_url="https://www.bayut.com/for-sale/property/dubai/",
        final_url="https://www.bayut.com/for-sale/property/dubai/",
        status_code=200 if outcome == "ok" else 429 if outcome == "rate_limited" else 503,
        title="Properties for Sale",
        html="<html></html>",
        cards=(
            {
                "listing_url": f"https://www.bayut.com/property/details-{identifier}.html",
                "title": f"Listing {identifier}",
                "text": "AED 100,000 1,000 sqft",
            },
        )
        if outcome == "ok"
        else (),
        location_anchors=(),
        outcome=outcome,
        error="",
        latency_ms=1,
        network={"response_bytes": response_bytes, "request_count": 1},
        identity={},
        context_id="test",
    )


class Fetcher:
    def __init__(self, *, duplicate: bool = False, outcome: str = "ok") -> None:
        self.calls: list[tuple[str, int]] = []
        self.duplicate = duplicate
        self.outcome = outcome

    def fetch(self, *, search_path: str, page_number: int, observation_id: str) -> Any:
        self.calls.append((search_path, page_number))
        identifier = 1 if self.duplicate else page_number * 100 + int("for-sale" in search_path)
        return response(identifier, outcome=self.outcome)

    def invalidate_context(self) -> None:
        pass


def test_attempt_limit_counts_canary_and_resumed_attempts(state: Any) -> None:
    first = Fetcher()
    limited = LimitedFetcher(
        first, state.connection, max_attempts=4, max_response_bytes=1000, stop_after=2
    )
    with pytest.raises(BudgetStop, match="stage_limit"):
        collection.run_practice(
            connection=state.connection, config=state.config, fetcher=limited, round_robin=True
        )
    assert len(first.calls) == 2
    second = Fetcher()
    resumed = LimitedFetcher(second, state.connection, max_attempts=4, max_response_bytes=1000)
    with pytest.raises(BudgetStop, match="attempt_budget"):
        collection.run_practice(
            connection=state.connection, config=state.config, fetcher=resumed, round_robin=True
        )
    assert len(second.calls) == 2
    assert collection.collection_status(state.connection)["page_attempts"] == 4


def test_response_budget_stops_before_another_page(state: Any) -> None:
    fetcher = Fetcher()
    limited = LimitedFetcher(fetcher, state.connection, max_attempts=1000, max_response_bytes=150)
    with pytest.raises(BudgetStop, match="measured_response_budget"):
        collection.run_practice(
            connection=state.connection, config=state.config, fetcher=limited, round_robin=True
        )
    assert len(fetcher.calls) == 2  # At most the final page can cross the measured-byte limit.


def test_rate_limit_stops_without_changing_ip_and_trying_another_root(state: Any) -> None:
    fetcher = Fetcher(outcome="rate_limited")
    limited = LimitedFetcher(fetcher, state.connection, max_attempts=1000, max_response_bytes=1000)
    with pytest.raises(BudgetStop, match="rate_limited"):
        collection.run_practice(
            connection=state.connection, config=state.config, fetcher=limited, round_robin=True
        )
    assert len(fetcher.calls) == 1


def test_duplicate_only_pagination_does_not_burn_the_rest_of_the_budget(state: Any) -> None:
    fetcher = Fetcher(duplicate=True)
    result = collection.run_practice(
        connection=state.connection, config=state.config, fetcher=fetcher, round_robin=True
    )
    assert [page for _, page in fetcher.calls] == [1, 1, 2, 2]
    assert result["page_attempts"] == 4
    assert {row[0] for row in state.connection.execute("SELECT stop_reason FROM shards")} == {
        "duplicate_only_page"
    }


def test_explicit_request_test_can_cover_500_pages_per_purpose(state: Any) -> None:
    replace(state.config, practice_pages_per_root=500).validate()
    with pytest.raises(ValueError):
        replace(state.config, practice_pages_per_root=501).validate()
