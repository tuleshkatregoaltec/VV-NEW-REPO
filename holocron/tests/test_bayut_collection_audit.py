from __future__ import annotations

import hashlib
import json
import sqlite3
from types import SimpleNamespace
from typing import Any

import pytest

from handoff.bayut_standalone import bayut_collection as standalone
from holocron.sources.bayut_listings import full_collection as integrated
from holocron.sources.bayut_listings.extract import _listing_rows


@pytest.fixture(params=[integrated, standalone], ids=["integrated", "standalone"])
def runner(request: Any, tmp_path: Any) -> Any:
    module = request.param
    roots = [
        {
            "name": f"sale_{index}",
            "purpose": "sale",
            "property_type": "apartment",
            "path": f"/for-sale/apartments/dubai/area-{index}/",
        }
        for index in range(4)
    ]
    payload = {
        "roots": roots,
        "max_results_per_shard": 200,
        "request_pause_seconds": 0,
        "request_jitter_seconds": 0,
        "retry_backoff_seconds": 0,
        "max_attempts_per_page": 2,
        "evidence": "none",
    }
    if module is integrated:
        config = module.BayutFullCollectionConfig.model_validate(payload)
        connection = module.open_collection_database(config=config, output_dir=tmp_path)
        module.initialize_roots(connection, config)
    else:
        config = module.CollectionConfig.from_mapping(payload)
        connection = module.open_database(config=config, output_dir=tmp_path, requested_kind="full")
        module.initialize_full_roots(connection, config)
    state = SimpleNamespace(
        module=module, config=config, connection=connection, output=tmp_path, roots=roots
    )
    yield state
    state.connection.close()


def card(identifier: int, text: str = "AED 100,000 1,000 sqft") -> dict[str, str]:
    return {
        "listing_url": f"https://www.bayut.com/property/details-{identifier}.html",
        "title": "Apartment",
        "text": text,
    }


def result(runner: Any, *, cards: tuple = (), **overrides: Any) -> Any:
    values = {
        "requested_url": "https://www.bayut.com/for-sale/apartments/dubai/area-0/",
        "final_url": "https://www.bayut.com/for-sale/apartments/dubai/area-0/",
        "status_code": 200,
        "title": "10 Apartments for Sale",
        "html": "<html></html>",
        "cards": cards,
        "location_anchors": (),
        "outcome": "ok",
        "error": "",
        "latency_ms": 10,
        "network": {"request_count": 1, "request_bytes": 50, "response_bytes": 1000},
        "identity": {},
        "context_id": "test-context",
    }
    values.update(overrides)
    return runner.module.FetchResult(**values)


class Fetcher:
    def __init__(self, *responses: Any) -> None:
        self.responses = iter(responses)
        self.calls: list[tuple[str, int]] = []
        self.invalidations = 0

    def fetch(self, *, search_path: str, page_number: int, observation_id: str) -> Any:
        self.calls.append((search_path, page_number))
        return next(self.responses)

    def invalidate_context(self) -> None:
        self.invalidations += 1


def ready(runner: Any, *, only_first: bool = True, count: int = 10) -> None:
    with runner.connection:
        if only_first:
            runner.connection.execute("DELETE FROM shards WHERE root_name <> 'sale_0'")
        runner.connection.execute("UPDATE shards SET status='ready', reported_count=?", (count,))


def test_ninety_percent_is_not_complete(runner: Any) -> None:
    ready(runner)
    fetcher = Fetcher(result(runner, cards=tuple(card(i) for i in range(9))), result(runner))
    status = runner.module.collect_shards(
        connection=runner.connection, config=runner.config, fetcher=fetcher
    )
    assert status["coverage_status"] == "not_complete"
    assert status["shard_statuses"] == {"count_mismatch": 1}
    assert status["root_coverage"]["sale_0"]["missing_from_reported_count"] == 1


def test_unknown_parent_count_cannot_be_inferred_from_partial_children(runner: Any) -> None:
    with runner.connection:
        runner.connection.execute("DELETE FROM shards WHERE root_name <> 'sale_0'")
    fetcher = Fetcher(
        result(
            runner,
            title="Apartments for Sale",
            location_anchors=({"href": runner.roots[0]["path"] + "tower/", "text": "Tower (50)"},),
        )
    )
    status = runner.module.plan_collection(
        connection=runner.connection, config=runner.config, fetcher=fetcher, max_nodes=1
    )
    assert status["shard_statuses"]["unresolved"] == 1
    assert (
        runner.connection.execute(
            "SELECT stop_reason FROM shards WHERE root_name='sale_0'"
        ).fetchone()[0]
        == "missing_parent_count"
    )


def test_page_budget_bounds_failures_as_well_as_successes(runner: Any) -> None:
    ready(runner, only_first=False)
    fetcher = Fetcher(result(runner, outcome="captcha"), result(runner, outcome="captcha"))
    status = runner.module.collect_shards(
        connection=runner.connection, config=runner.config, fetcher=fetcher, max_pages=1
    )
    assert len(fetcher.calls) == 2  # One scheduled page, with at most two attempts.
    assert status["shard_statuses"] == {"collect_error": 1, "ready": 3}
    assert status["network_response_megabytes"] == 0.002


def test_repeated_failures_leave_remaining_shards_for_resume(runner: Any) -> None:
    ready(runner, only_first=False)
    fetcher = Fetcher(*(result(runner, outcome="http_error") for _ in range(6)))
    status = runner.module.collect_shards(
        connection=runner.connection, config=runner.config, fetcher=fetcher
    )
    assert len(fetcher.calls) == 6
    assert status["shard_statuses"] == {"collect_error": 3, "ready": 1}


def test_listings_and_cursor_roll_back_together_then_resume(runner: Any) -> None:
    ready(runner, count=2)
    runner.connection.execute(
        "CREATE TEMP TRIGGER fail_cursor BEFORE UPDATE OF next_page ON shards "
        "BEGIN SELECT RAISE(ABORT, 'injected checkpoint failure'); END"
    )
    with pytest.raises(sqlite3.IntegrityError, match="injected checkpoint failure"):
        runner.module.collect_shards(
            connection=runner.connection,
            config=runner.config,
            fetcher=Fetcher(result(runner, cards=(card(1),))),
            max_pages=1,
        )
    assert runner.connection.execute("SELECT COUNT(*) FROM listings").fetchone()[0] == 0
    assert runner.connection.execute("SELECT COUNT(*) FROM listing_shards").fetchone()[0] == 0
    assert runner.connection.execute("SELECT next_page FROM shards").fetchone()[0] == 1
    runner.connection.execute("DROP TRIGGER fail_cursor")
    status = runner.module.collect_shards(
        connection=runner.connection,
        config=runner.config,
        fetcher=Fetcher(
            result(runner, cards=(card(1),)), result(runner, cards=(card(2),)), result(runner)
        ),
    )
    assert status["global_unique_listings"] == 2
    assert status["coverage_status"] == "complete"


def test_planner_applies_cadence_to_small_leaves(runner: Any, monkeypatch: Any) -> None:
    pauses = []
    monkeypatch.setattr(runner.module, "_pause", lambda config, seed: pauses.append(seed))
    runner.module.plan_collection(
        connection=runner.connection,
        config=runner.config,
        fetcher=Fetcher(result(runner), result(runner)),
        max_nodes=2,
    )
    assert len(pauses) == 2


def test_bandwidth_export_preserves_request_metrics(runner: Any) -> None:
    ready(runner)
    runner.module.collect_shards(
        connection=runner.connection,
        config=runner.config,
        fetcher=Fetcher(result(runner, cards=(card(1),))),
        max_pages=1,
    )
    summary = runner.module.export_collection(runner.connection, runner.output)
    assert summary["measured_response_bytes_per_listing"] == 1000
    assert summary["projected_response_gb_per_250k_listings"] == 0.25
    assert summary["network_request_megabytes"] == 0.00005
    attempt = json.loads((runner.output / "page_attempts.jsonl").read_text().splitlines()[0])
    assert json.loads(attempt["network_json"])["request_bytes"] == 50


def test_partition_overlap_cannot_hide_missing_root_listings(runner: Any) -> None:
    ready(runner, count=2)
    root = runner.connection.execute("SELECT * FROM shards").fetchone()
    with runner.connection:
        runner.connection.execute("UPDATE shards SET status='split'")
        for index in range(2):
            runner.connection.execute(
                "INSERT INTO shards(shard_id, root_name, purpose, property_type, path, parent_id, "
                "depth, name, reported_count, status, updated_at) "
                "VALUES(?, 'sale_0', 'sale', 'apartment', ?, ?, 1, ?, 1, 'ready', 'test')",
                (
                    f"child-{index}",
                    root["path"] + f"child-{index}/",
                    root["shard_id"],
                    f"child-{index}",
                ),
            )
    # Both leaves meet their own count, but they return the same listing.
    status = runner.module.collect_shards(
        connection=runner.connection,
        config=runner.config,
        fetcher=Fetcher(
            result(runner, cards=(card(1),)),
            result(runner),
            result(runner, cards=(card(1),)),
            result(runner),
        ),
    )
    assert status["shard_statuses"] == {"complete": 2, "split": 1}
    assert status["coverage_status"] == "not_complete"
    assert status["root_coverage"]["sale_0"]["missing_from_reported_count"] == 1


@pytest.mark.parametrize(
    ("body", "title", "final_path", "expected"),
    [
        ("Loading...", "Bayut", "/page-2/", "unrecognized_page"),
        ("No properties found", "Bayut", "/page-2/", "ok"),
        ("", "0 Apartments for Sale", "/page-2/", "ok"),
        ("Verify you are human", "Security check | Bayut", "/page-2/", "captcha"),
        ("No properties found", "Bayut", "/", "unexpected_redirect"),
    ],
)
def test_unknown_empty_and_redirected_pages_cannot_end_collection(
    runner: Any, body: str, title: str, final_path: str, expected: str
) -> None:
    validate = (
        getattr(runner.module, "validate_search_page", None) or runner.module._validate_search_page
    )
    assert (
        validate(
            requested_url="https://www.bayut.com/page-2/",
            final_url="https://www.bayut.com" + final_path,
            cards=(),
            body_text=body,
            title=title,
        )
        == expected
    )


def test_decimal_prices_and_areas_are_preserved(runner: Any) -> None:
    parse = standalone.listing_rows if runner.module is standalone else _listing_rows
    rows = parse(
        cards=(card(1, "AED 12,500.75 Apartment 1,234.50 sq. ft"),),
        search_path="/to-rent/property/dubai/",
        page=1,
        scraped_at="2026-09-07",
    )
    assert rows[0]["price_aed"] == 12500.75
    assert rows[0]["size_sqft"] == 1234.5


def test_dataimpulse_session_token_and_error_redaction(runner: Any) -> None:
    prefix = "BAYUT" if runner.module is standalone else "BAYUT_FULL"
    env = {
        f"{prefix}_PROXY_USERNAME": "customer__cr.ae;sessid.{session}",
        f"{prefix}_PROXY_PASSWORD": "private-password",
    }
    fetcher = object.__new__(runner.module.BrowserPageFetcher)
    fetcher._env = env
    fetcher._context_id = "trial123"
    message = fetcher._safe_error(
        "proxy http://customer__cr.ae;sessid.trial123:private-password@gw.dataimpulse.com:823 failed"
    )
    assert "private-password" not in message
    assert "customer__cr.ae" not in message
    assert "trial123" not in message


def test_legacy_checkpoint_accepts_default_new_options_and_migrates_metrics(runner: Any) -> None:
    sanitize = (
        getattr(runner.module, "sanitized_config", None) or runner.module.sanitized_full_config
    )
    payload = sanitize(runner.config)
    payload.pop("resource_mode")
    payload.pop("max_consecutive_failed_pages")
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    with runner.connection:
        runner.connection.execute(
            "UPDATE metadata SET value=? WHERE key='config_sha256'", (digest,)
        )
        runner.connection.execute("ALTER TABLE page_attempts DROP COLUMN network_json")
    runner.connection.close()
    if runner.module is integrated:
        connection = integrated.open_collection_database(
            config=runner.config, output_dir=runner.output
        )
    else:
        connection = standalone.open_database(
            config=runner.config, output_dir=runner.output, requested_kind="full"
        )
    runner.connection = connection
    assert "network_json" in {
        row[1] for row in connection.execute("PRAGMA table_info(page_attempts)")
    }
    assert runner.module.collection_status(connection)["page_attempts"] == 0
