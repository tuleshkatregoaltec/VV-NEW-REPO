from __future__ import annotations

import ast
import json
import sqlite3
import tempfile
import unittest
from collections.abc import Mapping
from pathlib import Path

from bayut_collection import (
    BLOCKED_RESOURCE_TYPES,
    CollectionConfig,
    FetchResult,
    SearchRoot,
    collection_status,
    extract_reported_count,
    initialize_practice_roots,
    normalize_location_links,
    open_database,
    plan_collection,
    run_practice,
    search_url,
    validate_proxy_environment,
    validate_search_page,
)


class FakeFetcher:
    def __init__(self, responses: Mapping[tuple[str, int], list[FetchResult]]) -> None:
        self.responses = {key: list(value) for key, value in responses.items()}
        self.invalidations = 0

    def fetch(self, *, search_path: str, page_number: int, observation_id: str) -> FetchResult:
        self.assert_observation_id(observation_id)
        return self.responses[(search_path, page_number)].pop(0)

    def invalidate_context(self) -> None:
        self.invalidations += 1

    @staticmethod
    def assert_observation_id(observation_id: str) -> None:
        if not observation_id:
            raise AssertionError("missing observation ID")


def result(
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
            "observed_at": "2026-09-01T00:00:00+00:00",
            "ip": "203.0.113.1",
            "country": "AE",
            "asn": "AS64500",
        },
        context_id="context-1",
    )


def card(listing_id: int) -> dict[str, str]:
    return {
        "listing_url": f"https://www.bayut.com/property/details-{listing_id}.html",
        "title": f"Listing {listing_id}",
        "text": f"AED 1,000,000 Area: 1,000 sqft Listing {listing_id}",
    }


def config(*, roots: tuple[SearchRoot, ...], **overrides: object) -> CollectionConfig:
    values: dict[str, object] = {
        "roots": roots,
        "max_results_per_shard": 200,
        "request_pause_seconds": 0,
        "request_jitter_seconds": 0,
        "retry_backoff_seconds": 0,
        "max_attempts_per_page": 2,
        "evidence": "none",
    }
    values.update(overrides)
    parsed = CollectionConfig(**values)  # type: ignore[arg-type]
    parsed.validate()
    return parsed


class StandaloneCollectionTests(unittest.TestCase):
    def test_bundled_example_configs_validate_after_identity_edit(self) -> None:
        bundle = Path(__file__).parent
        for name, expected_roots in (
            ("bayut_practice.example.json", 2),
            ("bayut_full.example.json", 16),
        ):
            raw = (
                (bundle / name)
                .read_text(encoding="utf-8")
                .replace(
                    "https://REPLACE-WITH-INTERNAL.example/identity",
                    "https://security.example.test/identity",
                )
            )
            parsed = CollectionConfig.from_mapping(json.loads(raw))
            self.assertEqual(len(parsed.roots), expected_roots)

    def test_module_has_no_repository_imports(self) -> None:
        source = Path(__file__).with_name("bayut_collection.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
        imports.extend(
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        )
        self.assertFalse(
            any(name == "holocron" or name.startswith("holocron.") for name in imports)
        )

    def test_media_request_types_are_blocked(self) -> None:
        self.assertEqual(BLOCKED_RESOURCE_TYPES, {"font", "image", "media"})

    def test_page_urls_and_location_partitions(self) -> None:
        self.assertEqual(
            search_url(
                base_url="https://www.bayut.com",
                search_path="/for-sale/apartments/dubai/",
                page_number=2,
            ),
            "https://www.bayut.com/for-sale/apartments/dubai/page-2/",
        )
        links = normalize_location_links(
            current_path="/for-sale/apartments/dubai/",
            anchors=(
                {
                    "href": "/for-sale/apartments/dubai/jvc/",
                    "text": "JVC (10,100)",
                },
                {
                    "href": "/for-sale/apartments/dubai/jvc/district-10/",
                    "text": "Too deep (2,000)",
                },
            ),
        )
        self.assertEqual(
            [(link.path, link.count) for link in links],
            [("/for-sale/apartments/dubai/jvc/", 10_100)],
        )
        self.assertEqual(
            extract_reported_count(title="100,656 Apartments for Rent", html=""),
            100_656,
        )

    def test_proxy_rotation_requires_provider_session_template(self) -> None:
        parsed = config(
            roots=(SearchRoot("sale", "sale", "property", "/for-sale/property/dubai/"),),
            proxy="residential",
            proxy_rotation="context",
            identity_url="https://security.example.test/identity",
        )
        with self.assertRaisesRegex(ValueError, "BAYUT_PROXY_SERVER"):
            validate_proxy_environment(parsed, {})
        with self.assertRaisesRegex(ValueError, "session"):
            validate_proxy_environment(
                parsed,
                {"BAYUT_PROXY_SERVER": "http://proxy.example:8000"},
            )
        validate_proxy_environment(
            parsed,
            {
                "BAYUT_PROXY_SERVER": "http://proxy.example:8000",
                "BAYUT_PROXY_USERNAME": "customer-session-{session}",
                "BAYUT_PROXY_PASSWORD": "secret",
            },
        )

    def test_practice_collects_sale_and_rent_then_exports_checkpoint_state(self) -> None:
        roots = (
            SearchRoot("sale", "sale", "property", "/for-sale/property/dubai/"),
            SearchRoot("rent", "rent", "property", "/to-rent/property/dubai/"),
        )
        parsed = config(roots=roots, practice_pages_per_root=1)
        fetcher = FakeFetcher(
            {
                (roots[0].path, 1): [result(cards=(card(1),))],
                (roots[1].path, 1): [result(cards=(card(2),))],
            }
        )
        with tempfile.TemporaryDirectory() as temporary:
            connection = open_database(
                config=parsed,
                output_dir=temporary,
                requested_kind="practice",
            )
            summary = run_practice(connection=connection, config=parsed, fetcher=fetcher)
            self.assertEqual(summary["coverage_status"], "practice_only")
            self.assertEqual(summary["global_unique_listings"], 2)
            self.assertEqual(summary["purposes"]["sale"]["unique_listings"], 1)
            self.assertEqual(summary["purposes"]["rent"]["unique_listings"], 1)
            connection.close()

    def test_full_planner_splits_a_large_root(self) -> None:
        root = SearchRoot(
            "sale_apartments",
            "sale",
            "apartment",
            "/for-sale/apartments/dubai/",
        )
        parsed = config(roots=(root,))
        fetcher = FakeFetcher(
            {
                (root.path, 1): [
                    result(
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
        with tempfile.TemporaryDirectory() as temporary:
            connection = open_database(
                config=parsed,
                output_dir=temporary,
                requested_kind="full",
            )
            summary = plan_collection(connection=connection, config=parsed, fetcher=fetcher)
            self.assertEqual(summary["shard_statuses"], {"ready": 2, "split": 1})
            self.assertEqual(summary["terminal_reported_listing_sum"], 250)
            self.assertEqual(collection_status(connection)["coverage_status"], "not_complete")
            connection.close()

    def test_practice_rolls_back_listings_when_checkpoint_fails(self) -> None:
        root = SearchRoot("sale", "sale", "property", "/for-sale/property/dubai/")
        parsed = config(roots=(root,), practice_pages_per_root=1)
        with tempfile.TemporaryDirectory() as temporary:
            connection = open_database(
                config=parsed, output_dir=temporary, requested_kind="practice"
            )
            try:
                initialize_practice_roots(connection, parsed)
                connection.execute(
                    "CREATE TEMP TRIGGER fail_cursor BEFORE UPDATE OF next_page ON shards "
                    "BEGIN SELECT RAISE(ABORT, 'injected failure'); END"
                )
                with self.assertRaisesRegex(sqlite3.IntegrityError, "injected failure"):
                    run_practice(
                        connection=connection,
                        config=parsed,
                        fetcher=FakeFetcher({(root.path, 1): [result(cards=(card(1),))]}),
                    )
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM listings").fetchone()[0], 0
                )
                self.assertEqual(
                    connection.execute("SELECT next_page FROM shards").fetchone()[0], 1
                )
            finally:
                connection.close()

    def test_document_mode_rejects_empty_hydration_shell(self) -> None:
        outcome = validate_search_page(
            requested_url="https://www.bayut.com/for-sale/property/dubai/",
            final_url="https://www.bayut.com/for-sale/property/dubai/",
            cards=(),
            body_text="Loading...",
            title="Bayut",
        )
        self.assertEqual(outcome, "unrecognized_page")


if __name__ == "__main__":
    unittest.main()
