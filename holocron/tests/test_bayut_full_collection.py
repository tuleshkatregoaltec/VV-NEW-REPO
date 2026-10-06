from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from pathlib import Path
import pytest
from pydantic import ValidationError

from holocron.sources.bayut_listings.full_collection import (
    BAYUT_RESIDENTIAL_ROOTS,
    BayutFullCollectionConfig,
    BayutFullRoot,
    FetchResult,
    collect_shards,
    export_collection,
    extract_reported_count,
    full_search_url,
    initialize_roots,
    normalize_location_links,
    open_collection_database,
    plan_collection,
    validate_full_proxy_environment,
)


class FakeFetcher:
    def __init__(self, responses: Mapping[tuple[str, int], list[FetchResult]]) -> None:
        self.responses = {key: list(values) for key, values in responses.items()}
        self.invalidations = 0

    def fetch(self, *, search_path: str, page_number: int, observation_id: str) -> FetchResult:
        assert observation_id
        return self.responses[(search_path, page_number)].pop(0)

    def invalidate_context(self) -> None:
        self.invalidations += 1


def _config(**overrides: object) -> BayutFullCollectionConfig:
    payload: dict[str, object] = {
        "roots": [
            {
                "name": "sale_apartments",
                "purpose": "sale",
                "property_type": "apartment",
                "path": "/for-sale/apartments/dubai/",
            }
        ],
        "max_results_per_shard": 200,
        "request_pause_seconds": 0,
        "request_jitter_seconds": 0,
        "max_attempts_per_page": 2,
        "retry_backoff_seconds": 0,
        "evidence": "none",
    }
    payload.update(overrides)
    return BayutFullCollectionConfig.model_validate(payload)


def _result(
    *,
    title: str = "",
    cards: tuple[dict[str, str], ...] = (),
    anchors: tuple[dict[str, str], ...] = (),
    outcome: str = "ok",
) -> FetchResult:
    return FetchResult(
        requested_url="https://www.bayut.com/requested/",
        final_url="https://www.bayut.com/final/",
        status_code=200,
        title=title,
        html="<html></html>",
        cards=cards,
        location_anchors=anchors,
        outcome=outcome,
        error="",
        latency_ms=10,
        network={"request_count": 5, "response_bytes": 1_000},
        identity={
            "sample_id": "sample-1",
            "observed_at": "2026-08-29T00:00:00+00:00",
            "ip": "203.0.113.1",
            "country": "AE",
            "asn": "AS64500",
        },
        context_id="context-1",
    )


def _card(listing_id: int) -> dict[str, str]:
    return {
        "listing_url": f"https://www.bayut.com/property/details-{listing_id}.html",
        "title": f"Listing {listing_id}",
        "text": f"AED 1,000,000 Area: 1,000 sqft Listing {listing_id}",
    }


def test_default_roots_cover_sale_and_rent_residential_types() -> None:
    assert len([root for root in BAYUT_RESIDENTIAL_ROOTS if root.purpose == "sale"]) == 9
    assert len([root for root in BAYUT_RESIDENTIAL_ROOTS if root.purpose == "rent"]) == 7
    assert len({root.path for root in BAYUT_RESIDENTIAL_ROOTS}) == 16


def test_full_search_url_uses_canonical_path_cursor_and_preserves_query() -> None:
    assert (
        full_search_url(
            base_url="https://www.bayut.com",
            search_path="/for-sale/apartments/dubai/",
            page_number=1,
        )
        == "https://www.bayut.com/for-sale/apartments/dubai/"
    )
    assert (
        full_search_url(
            base_url="https://www.bayut.com",
            search_path="/for-sale/apartments/dubai/?sort=date_desc",
            page_number=12,
        )
        == "https://www.bayut.com/for-sale/apartments/dubai/page-12/?sort=date_desc"
    )


def test_location_link_normalization_keeps_only_counted_direct_children() -> None:
    links = normalize_location_links(
        current_path="/for-sale/apartments/dubai/",
        anchors=[
            {
                "href": "https://www.bayut.com/for-sale/apartments/dubai/jvc/",
                "text": "JVC (10,100)",
            },
            {
                "href": "/for-sale/apartments/dubai/jvc/district-10/",
                "text": "Too deep (2,000)",
            },
            {
                "href": "/for-sale/apartments/dubai/page-2/",
                "text": "Next (2)",
            },
            {"href": "/for-sale/villas/dubai/jvc/", "text": "Wrong prefix (50)"},
            {"href": "/for-sale/apartments/dubai/arjan/", "text": "Arjan"},
        ],
    )
    assert [(link.path, link.name, link.count) for link in links] == [
        ("/for-sale/apartments/dubai/jvc/", "JVC", 10_100)
    ]


def test_reported_count_prefers_page_one_title() -> None:
    assert (
        extract_reported_count(
            title="100,656 Apartments for Rent in Dubai", html='{"totalProperties": 99}'
        )
        == 100_656
    )
    assert extract_reported_count(title="Apartments", html='{"totalResults":2450}') == 2_450


def test_residential_rotation_requires_session_template_and_identity() -> None:
    with pytest.raises(ValidationError, match="identity_url is required"):
        _config(proxy="residential", proxy_rotation="context")
    config = _config(
        proxy="residential",
        proxy_rotation="context",
        identity_url="https://security.example.test/identity",
    )
    with pytest.raises(ValueError, match="BAYUT_FULL_PROXY_SERVER"):
        validate_full_proxy_environment(config, {})
    with pytest.raises(ValueError, match=r"requires \{session\}"):
        validate_full_proxy_environment(
            config,
            {"BAYUT_FULL_PROXY_SERVER": "http://proxy.example:8000"},
        )
    validate_full_proxy_environment(
        config,
        {
            "BAYUT_FULL_PROXY_SERVER": "http://proxy.example:8000",
            "BAYUT_FULL_PROXY_USERNAME": "customer-session-{session}",
            "BAYUT_FULL_PROXY_PASSWORD": "secret",
        },
    )


def test_planner_splits_large_root_into_count_bounded_location_shards(tmp_path: Path) -> None:
    config = _config()
    connection = open_collection_database(config=config, output_dir=tmp_path)
    fetcher = FakeFetcher(
        {
            ("/for-sale/apartments/dubai/", 1): [
                _result(
                    title="250 Apartments for Sale in Dubai",
                    anchors=(
                        {
                            "href": "/for-sale/apartments/dubai/arjan/",
                            "text": "Arjan (125)",
                        },
                        {
                            "href": "/for-sale/apartments/dubai/jvc/",
                            "text": "JVC (125)",
                        },
                    ),
                )
            ]
        }
    )

    status = plan_collection(connection=connection, config=config, fetcher=fetcher)

    assert status["shard_statuses"] == {"ready": 2, "split": 1}
    assert status["terminal_reported_listing_sum"] == 250
    paths = [
        row["path"]
        for row in connection.execute("SELECT path FROM shards WHERE status='ready' ORDER BY path")
    ]
    assert paths == [
        "/for-sale/apartments/dubai/arjan/",
        "/for-sale/apartments/dubai/jvc/",
    ]
    connection.close()


def test_collection_retries_context_and_resumes_with_global_dedup(tmp_path: Path) -> None:
    config = _config(minimum_observed_count_coverage=0.5)
    connection = open_collection_database(config=config, output_dir=tmp_path)
    initialize_roots(connection, config)
    root = connection.execute("SELECT * FROM shards").fetchone()
    assert root is not None
    with connection:
        connection.execute(
            "UPDATE shards SET status='ready', reported_count=3 WHERE shard_id=?",
            (root["shard_id"],),
        )
    fetcher = FakeFetcher(
        {
            (root["path"], 1): [
                _result(outcome="captcha"),
                _result(cards=(_card(1), _card(2))),
            ],
            (root["path"], 2): [_result(cards=(_card(1), _card(2)))],
        }
    )

    first = collect_shards(
        connection=connection,
        config=config,
        fetcher=fetcher,
        max_pages=1,
    )
    assert first["global_unique_listings"] == 2
    assert first["remaining_collectable_shards"] == 1
    assert fetcher.invalidations == 1

    final = collect_shards(connection=connection, config=config, fetcher=fetcher)
    assert final["coverage_status"] == "not_complete"
    assert final["global_unique_listings"] == 2
    assert final["shard_statuses"] == {"complete_with_tolerance": 1}
    assert final["page_attempts"] == 3

    exported = export_collection(connection, tmp_path)
    assert exported["global_unique_listings"] == 2
    listings = [json.loads(line) for line in (tmp_path / "listings.jsonl").read_text().splitlines()]
    assert [row["listing_id"] for row in listings] == ["1", "2"]
    connection.close()


def test_collection_marks_an_early_natural_end_as_count_mismatch(tmp_path: Path) -> None:
    config = _config()
    connection = open_collection_database(config=config, output_dir=tmp_path)
    initialize_roots(connection, config)
    root = connection.execute("SELECT * FROM shards").fetchone()
    assert root is not None
    with connection:
        connection.execute(
            "UPDATE shards SET status='ready', reported_count=100 WHERE shard_id=?",
            (root["shard_id"],),
        )
    fetcher = FakeFetcher(
        {
            (root["path"], 1): [_result(cards=(_card(1),))],
            (root["path"], 2): [_result(cards=())],
        }
    )

    status = collect_shards(connection=connection, config=config, fetcher=fetcher)

    assert status["coverage_status"] == "not_complete"
    assert status["shard_statuses"] == {"count_mismatch": 1}
    connection.close()


def test_existing_database_rejects_a_different_config(tmp_path: Path) -> None:
    connection = open_collection_database(config=_config(), output_dir=tmp_path)
    connection.close()
    with pytest.raises(ValueError, match="different config"):
        open_collection_database(
            config=_config(
                roots=(
                    BayutFullRoot(
                        name="rent_villas",
                        purpose="rent",
                        property_type="villa",
                        path="/to-rent/villas/dubai/",
                    ),
                )
            ),
            output_dir=tmp_path,
        )


def test_database_uses_foreign_keys(tmp_path: Path) -> None:
    connection = open_collection_database(config=_config(), output_dir=tmp_path)
    assert isinstance(connection, sqlite3.Connection)
    assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    connection.close()
