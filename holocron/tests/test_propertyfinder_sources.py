from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from holocron.contracts import RawRelease
from holocron.platform.checkpoints import checkpoint_s3_key
from holocron.sources import PF_LISTINGS_SOURCE, PF_LOCATIONS_SOURCE, registry
from holocron.sources.pf_listings.extract import extract_release as extract_listings_release
from holocron.sources.pf_listings.extract import PropertyFinderBrowserListingsClient
from holocron.sources.pf_listings.media_assets import (
    MediaDownload,
    PropertyFinderListingMediaHydrationConfig,
    hydrate_pf_listing_media_assets,
)
from holocron.sources.pf_listings.orchestration import (
    resolve_listings_config,
    write_listings_checkpoint,
)
from holocron.sources.pf_listings.source import PropertyFinderListingsConfig
from holocron.sources.pf_locations.extract import extract_release as extract_locations_release
from holocron.sources.pf_locations.source import PropertyFinderLocationsConfig
from tests.fakes import FakeS3, _jsonl_bytes


class FakePropertyFinderLocationsApi:
    def __init__(self) -> None:
        self.location_calls: list[tuple[int, int, str]] = []
        self.filter_calls: list[tuple[int, str]] = []

    def fetch_locations(self, *, page: int, limit: int, locale: str) -> dict[str, Any]:
        self.location_calls.append((page, limit, locale))
        return {
            "data": {
                "attributes": [
                    {
                        "id": 1,
                        "name": "Dubai",
                        "path": "1",
                        "path_name": "",
                        "level": 0,
                        "location_type": "CITY",
                        "coordinates": {"lat": 25.2, "lon": 55.3},
                    },
                    {
                        "id": 14,
                        "name": "Al Furjan",
                        "path": "1.14",
                        "path_name": "Dubai",
                        "level": 1,
                        "location_type": "COMMUNITY",
                        "coordinates": {"lat": 25.0, "lon": 55.1},
                    },
                    {
                        "id": 900,
                        "name": "Abu Dhabi Marina",
                        "path": "2.900",
                        "path_name": "Abu Dhabi",
                        "level": 1,
                        "location_type": "COMMUNITY",
                    },
                ],
                "meta": {"total_count": 3, "total_pages": 1},
            }
        }

    def fetch_filter_settings(self, *, category: int, locale: str) -> dict[str, Any]:
        self.filter_calls.append((category, locale))
        return _filter_settings(property_types=(("1", "Apartment"), ("5", "Land")))


class FakePropertyFinderListingsClient:
    def __init__(self) -> None:
        self.search_calls: list[dict[str, str]] = []
        self.detail_calls: list[str] = []

    def fetch_filter_settings(self, *, category: int, locale: str) -> dict[str, Any]:
        assert category == 1
        assert locale == "en"
        return _filter_settings(property_types=(("1", "Apartment"), ("5", "Land")))

    def fetch_locations(self, *, page: int, limit: int, locale: str) -> dict[str, Any]:
        assert page == 1
        assert limit == 500
        assert locale == "en"
        return _locations_payload(
            [
                {"id": 1, "name": "Dubai", "path": "1", "level": 0, "location_type": "CITY"},
                {
                    "id": 14,
                    "name": "Al Furjan",
                    "path": "1.14",
                    "level": 1,
                    "location_type": "COMMUNITY",
                },
                {
                    "id": 250,
                    "name": "Example Tower",
                    "path": "1.14.250",
                    "level": 2,
                    "location_type": "TOWER",
                },
            ]
        )

    def fetch_search_page(self, *, params) -> dict[str, Any]:
        query = dict(params)
        self.search_calls.append(query)
        property_type_id = query.get("t")
        if property_type_id is None:
            return _search_payload(total_count=5, page_count=1, listings=[])
        if property_type_id == "1":
            return _search_payload(
                total_count=1,
                page_count=1,
                listings=[
                    _listing_wrapper(
                        listing_id="apt-1",
                        property_type="Apartment",
                        location_tree=[
                            {"id": 1, "name": "Dubai", "type": "CITY"},
                            {"id": 14, "name": "Al Furjan", "type": "COMMUNITY"},
                            {"id": 250, "name": "Example Tower", "type": "TOWER"},
                        ],
                        details_path="/en/plp/buy/apartment-for-sale-dubai-example-apt-1.html",
                    )
                ],
            )
        if property_type_id == "5":
            return _search_payload(
                total_count=1,
                page_count=1,
                listings=[
                    _listing_wrapper(
                        listing_id="land-1",
                        property_type="Land",
                        location_tree=[
                            {"id": 1, "name": "Dubai", "type": "CITY"},
                            {"id": 14, "name": "Al Furjan", "type": "COMMUNITY"},
                        ],
                        details_path="/en/plp/buy/land-for-sale-dubai-example-land-1.html",
                    )
                ],
            )
        raise AssertionError(f"Unexpected property type: {property_type_id}")

    def fetch_detail(self, *, details_path: str) -> dict[str, Any]:
        self.detail_calls.append(details_path)
        return {
            "pageProps": {
                "propertyResult": {
                    "property": {
                        "id": "apt-1",
                        "listing_id": "apt-1",
                        "images": {
                            "property": [
                                {
                                    "full": "https://static.shared.propertyfinder.ae/listings/apt-1/full.jpg",
                                    "medium": (
                                        "https://static.shared.propertyfinder.ae/listings/"
                                        "apt-1/medium.jpg"
                                    ),
                                }
                            ],
                            "tower": ["https://graph-images.propertyfinder.ae/towers/example.jpg"],
                        },
                        "floor_plans": [
                            {
                                "url": (
                                    "https://static.shared.propertyfinder.ae/listings/"
                                    "apt-1/floorplan.jpg"
                                )
                            }
                        ],
                    }
                }
            }
        }


class FakePropertyFinderLocationSplitListingsClient:
    def fetch_filter_settings(self, *, category: int, locale: str) -> dict[str, Any]:
        assert category == 1
        assert locale == "en"
        return _filter_settings(property_types=(("1", "Apartment"),))

    def fetch_locations(self, *, page: int, limit: int, locale: str) -> dict[str, Any]:
        assert page == 1
        assert limit == 500
        assert locale == "en"
        return _locations_payload(
            [
                {"id": 1, "name": "Dubai", "path": "1", "level": 0, "location_type": "CITY"},
                {
                    "id": 14,
                    "name": "Al Furjan",
                    "path": "1.14",
                    "level": 1,
                    "location_type": "COMMUNITY",
                },
                {
                    "id": 15,
                    "name": "Dubai Marina",
                    "path": "1.15",
                    "level": 1,
                    "location_type": "COMMUNITY",
                },
            ]
        )

    def fetch_search_page(self, *, params) -> dict[str, Any]:
        query = dict(params)
        if query.get("t") is None:
            return _search_payload(total_count=5, page_count=1, listings=[])
        if query.get("l") == "1":
            return _search_payload(total_count=5, page_count=1, listings=[])
        return _search_payload(
            total_count=1,
            page_count=1,
            listings=[
                _listing_wrapper(
                    listing_id=f"apt-{query['l']}",
                    property_type="Apartment",
                    location_tree=[
                        {"id": 1, "name": "Dubai", "type": "CITY"},
                        {"id": int(query["l"]), "name": "Community", "type": "COMMUNITY"},
                    ],
                    details_path=f"/en/plp/buy/apartment-for-sale-dubai-{query['l']}.html",
                )
            ],
        )

    def fetch_detail(self, *, details_path: str) -> dict[str, Any]:
        raise AssertionError("details should not be fetched")


class FakePropertyFinderSearchErrorListingsClient:
    def fetch_filter_settings(self, *, category: int, locale: str) -> dict[str, Any]:
        assert category == 1
        assert locale == "en"
        return _filter_settings(property_types=(("1", "Apartment"),))

    def fetch_locations(self, *, page: int, limit: int, locale: str) -> dict[str, Any]:
        assert page == 1
        assert limit == 500
        assert locale == "en"
        return _locations_payload(
            [{"id": 1, "name": "Dubai", "path": "1", "level": 0, "location_type": "CITY"}]
        )

    def fetch_search_page(self, *, params) -> dict[str, Any]:
        query = dict(params)
        if query.get("page") == "2":
            raise RuntimeError("Property Finder fetch returned non-JSON after retries")
        if query.get("t") is None:
            return _search_payload(total_count=2_000, page_count=1, listings=[])
        return _search_payload(
            total_count=31,
            page_count=2,
            listings=[
                _listing_wrapper(
                    listing_id="apt-with-page-error",
                    property_type="Apartment",
                    location_tree=[{"id": 1, "name": "Dubai", "type": "CITY"}],
                    details_path="/en/plp/buy/apartment-for-sale-dubai-page-error.html",
                )
            ],
        )

    def fetch_detail(self, *, details_path: str) -> dict[str, Any]:
        raise AssertionError("details should not be fetched")


class FakePropertyFinderChunkListingsClient:
    def __init__(self) -> None:
        self.search_calls: list[dict[str, str]] = []
        self.detail_calls: list[str] = []

    def fetch_filter_settings(self, *, category: int, locale: str) -> dict[str, Any]:
        raise AssertionError("filter settings should not be fetched")

    def fetch_locations(self, *, page: int, limit: int, locale: str) -> dict[str, Any]:
        raise AssertionError("locations should not be fetched")

    def fetch_search_page(self, *, params: Sequence[tuple[str, str]]) -> dict[str, Any]:
        query = dict(params)
        self.search_calls.append(query)
        page = int(query["page"])
        listing_id = f"chunk-{query['l']}-{page}"
        return _search_payload(
            total_count=2 if query["l"] == "14" else 1,
            page_count=2 if query["l"] == "14" else 1,
            listings=[
                _listing_wrapper(
                    listing_id=listing_id,
                    property_type="Apartment",
                    location_tree=[
                        {"id": 1, "name": "Dubai", "type": "CITY"},
                        {"id": int(query["l"]), "name": "Community", "type": "COMMUNITY"},
                    ],
                    details_path=f"/en/plp/buy/apartment-for-sale-dubai-{listing_id}.html",
                )
            ],
        )

    def fetch_detail(self, *, details_path: str) -> dict[str, Any]:
        self.detail_calls.append(details_path)
        return {
            "pageProps": {
                "propertyResult": {
                    "property": {
                        "listing_id": details_path.rsplit("-", 1)[-1].replace(".html", ""),
                        "images": {"property": []},
                    }
                }
            }
        }


class FakePropertyFinderLatestDeltaClient:
    def __init__(
        self,
        *,
        pages: dict[int, list[dict[str, Any]]],
        detail_failures: set[str] | None = None,
    ) -> None:
        self.pages = pages
        self.detail_failures = detail_failures or set()
        self.search_calls: list[dict[str, str]] = []
        self.detail_calls: list[str] = []

    def fetch_filter_settings(self, *, category: int, locale: str) -> dict[str, Any]:
        return _filter_settings(property_types=(("1", "Apartment"),))

    def fetch_locations(self, *, page: int, limit: int, locale: str) -> dict[str, Any]:
        return _locations_payload([])

    def fetch_search_page(self, *, params) -> dict[str, Any]:
        query = dict(params)
        self.search_calls.append(query)
        page = int(query["page"])
        listings = self.pages.get(page, [])
        return _search_payload(total_count=len(listings), page_count=1, listings=listings)

    def fetch_detail(self, *, details_path: str) -> dict[str, Any]:
        self.detail_calls.append(details_path)
        if details_path in self.detail_failures:
            raise RuntimeError(f"detail failed: {details_path}")
        return {
            "pageProps": {
                "propertyResult": {
                    "property": {
                        "listing_id": details_path.rsplit("-", 1)[-1].replace(".html", ""),
                        "images": {"property": []},
                    }
                }
            }
        }


class FakeMediaDownloader:
    def __init__(self, downloads: dict[str, bytes]) -> None:
        self.downloads = downloads
        self.calls: list[str] = []

    def download_media(self, url: str, *, max_bytes: int) -> MediaDownload:
        self.calls.append(url)
        payload = self.downloads[url]
        assert len(payload) <= max_bytes
        return MediaDownload(content=payload, content_type="image/jpeg", final_url=url)


def test_propertyfinder_sources_are_registered() -> None:
    assert registry.get("pf_locations") is PF_LOCATIONS_SOURCE
    assert registry.get("pf_listings") is PF_LISTINGS_SOURCE


def test_pf_listings_browser_client_uses_html_search_route() -> None:
    client = object.__new__(PropertyFinderBrowserListingsClient)
    client._base_url = "https://www.propertyfinder.ae"
    client._config = PropertyFinderListingsConfig(locale="en")

    assert client._search_url(
        params=(("c", "2"), ("l", "1"), ("page", "3"), ("ob", "nd"))
    ) == "https://www.propertyfinder.ae/en/search?c=2&l=1&page=3&ob=nd"


def test_pf_locations_extract_writes_dubai_hierarchy_and_filter_context(tmp_path: Path) -> None:
    api_client = FakePropertyFinderLocationsApi()

    release = extract_locations_release(
        tmp_path,
        config=PropertyFinderLocationsConfig(categories=(1,), max_location_pages=1),
        now=datetime(2026, 5, 4, 12, 0, tzinfo=UTC),
        api_client=api_client,
    )

    files_by_name = {Path(raw_file.path).name: raw_file for raw_file in release.files}
    assert release.source == "pf_locations"
    assert files_by_name["pf_locations_pages.jsonl"].row_count == 1
    assert files_by_name["pf_locations.jsonl"].row_count == 2
    assert files_by_name["pf_filter_settings.jsonl"].row_count == 1
    assert api_client.location_calls == [(1, 500, "en")]
    assert api_client.filter_calls == [(1, "en")]

    location_rows = _read_jsonl(Path(files_by_name["pf_locations.jsonl"].path))
    assert {row["location_id"] for row in location_rows} == {"1", "14"}
    assert {tuple(row["path_ids"]) for row in location_rows} == {("1",), ("1", "14")}

    filter_rows = _read_jsonl(Path(files_by_name["pf_filter_settings.jsonl"].path))
    assert {"value": "5", "label": "Land"} in filter_rows[0]["property_type_choices"]


def test_pf_listings_extract_partitions_by_property_type_and_keeps_land(
    tmp_path: Path,
) -> None:
    listing_client = FakePropertyFinderListingsClient()

    release = extract_listings_release(
        tmp_path,
        config=PropertyFinderListingsConfig(
            categories=(1,),
            max_results_per_query=2,
            max_planned_queries=5,
            max_search_pages_per_run=5,
            fetch_details=True,
            max_details_per_run=1,
        ),
        now=datetime(2026, 5, 4, 12, 0, tzinfo=UTC),
        listing_client=listing_client,
    )

    files_by_name = {Path(raw_file.path).name: raw_file for raw_file in release.files}
    assert release.source == "pf_listings"
    assert files_by_name["pf_listing_query_plan.jsonl"].row_count == 3
    assert files_by_name["pf_listing_properties.jsonl"].row_count == 2
    assert files_by_name["pf_listing_details.jsonl"].row_count == 1

    plan_rows = _read_jsonl(Path(files_by_name["pf_listing_query_plan.jsonl"].path))
    assert plan_rows[0]["status"] == "split"
    assert plan_rows[0]["split_reason"] == "property_type"
    assert {row["query"]["property_type_id"] for row in plan_rows[1:]} == {1, 5}

    property_rows = _read_jsonl(Path(files_by_name["pf_listing_properties.jsonl"].path))
    rows_by_listing_id = {row["listing_id"]: row for row in property_rows}
    assert set(rows_by_listing_id) == {"apt-1", "land-1"}
    assert rows_by_listing_id["land-1"]["raw_property"]["type"] == "Land"
    assert rows_by_listing_id["apt-1"]["listing_location_ids"] == ["1", "14", "250"]
    assert rows_by_listing_id["apt-1"]["community_location_id"] == "14"
    assert rows_by_listing_id["apt-1"]["building_location_id"] == "250"
    assert listing_client.detail_calls == [
        "/en/plp/buy/apartment-for-sale-dubai-example-apt-1.html"
    ]


def test_pf_listings_extract_uses_location_hierarchy_for_broad_queries(
    tmp_path: Path,
) -> None:
    listing_client = FakePropertyFinderLocationSplitListingsClient()

    release = extract_listings_release(
        tmp_path,
        config=PropertyFinderListingsConfig(
            categories=(1,),
            max_results_per_query=2,
            max_planned_queries=4,
            max_search_pages_per_run=5,
            fetch_details=False,
        ),
        now=datetime(2026, 5, 4, 12, 0, tzinfo=UTC),
        listing_client=listing_client,
    )

    files_by_name = {Path(raw_file.path).name: raw_file for raw_file in release.files}
    assert files_by_name["pf_listing_location_partitions.jsonl"].row_count == 3
    assert files_by_name["pf_listing_query_plan.jsonl"].row_count == 4
    assert files_by_name["pf_listing_properties.jsonl"].row_count == 2

    plan_rows = _read_jsonl(Path(files_by_name["pf_listing_query_plan.jsonl"].path))
    assert [row["split_reason"] for row in plan_rows[:2]] == ["property_type", "location"]
    assert {row["query"]["location_id"] for row in plan_rows[2:]} == {"14", "15"}


def test_pf_listings_extract_records_search_page_errors_and_continues(tmp_path: Path) -> None:
    listing_client = FakePropertyFinderSearchErrorListingsClient()

    release = extract_listings_release(
        tmp_path,
        config=PropertyFinderListingsConfig(
            categories=(1,),
            max_planned_queries=5,
            max_search_pages_per_run=5,
            fetch_details=False,
        ),
        now=datetime(2026, 5, 4, 12, 0, tzinfo=UTC),
        listing_client=listing_client,
    )

    files_by_name = {Path(raw_file.path).name: raw_file for raw_file in release.files}
    assert files_by_name["pf_listing_properties.jsonl"].row_count == 1
    assert files_by_name["pf_listing_search_pages.jsonl"].row_count == 2

    search_page_rows = _read_jsonl(Path(files_by_name["pf_listing_search_pages.jsonl"].path))
    assert [row["status"] for row in search_page_rows] == ["ok", "search_error"]
    assert search_page_rows[1]["page"] == 2
    assert "non-JSON" in search_page_rows[1]["error"]


def test_pf_listings_plan_mode_writes_durable_plan_only(tmp_path: Path) -> None:
    listing_client = FakePropertyFinderListingsClient()

    release = extract_listings_release(
        tmp_path,
        config=PropertyFinderListingsConfig(
            mode="plan",
            categories=(1,),
            max_results_per_query=2,
            max_planned_queries=5,
            fetch_details=False,
        ),
        now=datetime(2026, 5, 4, 12, 0, tzinfo=UTC),
        listing_client=listing_client,
    )

    files_by_name = {Path(raw_file.path).name: raw_file for raw_file in release.files}
    assert set(files_by_name) == {
        "pf_listing_filter_settings.jsonl",
        "pf_listing_location_partitions.jsonl",
        "pf_listing_plan_state.jsonl",
        "pf_listing_query_plan.jsonl",
    }
    assert release.metadata["stage"] == "plan"
    assert release.metadata["terminal_query_count"] == 2
    plan_state_rows = _read_jsonl(Path(files_by_name["pf_listing_plan_state.jsonl"].path))
    assert plan_state_rows[0]["completed"] is True
    assert plan_state_rows[0]["queue_count"] == 0


def test_pf_listings_plan_mode_resumes_from_plan_state(tmp_path: Path) -> None:
    s3 = FakeS3()
    first_manifest_key = _put_pf_plan_manifest(
        s3,
        run_id="plan-1",
        terminal_queries=[],
        plan_state={
            "completed": False,
            "queue": [
                {
                    "category_id": 1,
                    "location_id": "1",
                    "property_type_id": 1,
                    "depth": 1,
                }
            ],
            "queue_count": 1,
            "assessed_count": 1,
            "terminal_count": 0,
            "split_count": 1,
            "fetch_error_count": 0,
            "skipped_count": 0,
        },
    )
    listing_client = FakePropertyFinderListingsClient()

    release = extract_listings_release(
        tmp_path,
        config=PropertyFinderListingsConfig(
            mode="plan",
            categories=(1,),
            max_results_per_query=2,
            max_planned_queries=5,
            max_plan_queries_per_run=1,
            plan_state_manifest_s3_key=first_manifest_key,
            plan_manifest_s3_keys=(first_manifest_key,),
            fetch_details=False,
        ),
        now=datetime(2026, 5, 4, 12, 0, tzinfo=UTC),
        listing_client=listing_client,
        state_store=s3,
    )

    files_by_name = {Path(raw_file.path).name: raw_file for raw_file in release.files}
    assert set(files_by_name) == {
        "pf_listing_plan_state.jsonl",
        "pf_listing_query_plan.jsonl",
    }
    plan_rows = _read_jsonl(Path(files_by_name["pf_listing_query_plan.jsonl"].path))
    state_rows = _read_jsonl(Path(files_by_name["pf_listing_plan_state.jsonl"].path))

    assert release.metadata["stage"] == "plan"
    assert release.metadata["previous_plan_manifest_s3_keys"] == [first_manifest_key]
    assert release.metadata["planned_query_count"] == 2
    assert release.metadata["terminal_query_count_in_run"] == 1
    assert plan_rows[0]["query"]["property_type_id"] == 1
    assert plan_rows[0]["assessed_index"] == 2
    assert state_rows[0]["completed"] is True
    assert state_rows[0]["queue_count"] == 0


def test_pf_listings_search_mode_resumes_from_plan_manifest(tmp_path: Path) -> None:
    s3 = FakeS3()
    plan_manifest_key = _put_pf_plan_manifest(
        s3,
        run_id="plan-1",
        terminal_queries=[
            {"category_id": 1, "location_id": "14", "property_type_id": 1},
            {"category_id": 1, "location_id": "15", "property_type_id": 1},
        ],
    )
    listing_client = FakePropertyFinderChunkListingsClient()

    release = extract_listings_release(
        tmp_path,
        config=PropertyFinderListingsConfig(
            mode="search",
            categories=(1,),
            plan_manifest_s3_key=plan_manifest_key,
            search_query_cursor=0,
            search_page_cursor=2,
            max_search_pages_per_run=1,
            fetch_details=False,
        ),
        now=datetime(2026, 5, 4, 12, 0, tzinfo=UTC),
        listing_client=listing_client,
        state_store=s3,
    )

    files_by_name = {Path(raw_file.path).name: raw_file for raw_file in release.files}
    search_rows = _read_jsonl(Path(files_by_name["pf_listing_search_pages.jsonl"].path))
    property_rows = _read_jsonl(Path(files_by_name["pf_listing_properties.jsonl"].path))

    assert release.metadata["stage"] == "search"
    assert release.metadata["next_query_index"] == 1
    assert release.metadata["next_page"] == 1
    assert release.metadata["search_completed_result_set"] is False
    assert search_rows[0]["query_index"] == 0
    assert search_rows[0]["page"] == 2
    assert property_rows[0]["listing_id"] == "chunk-14-2"


def test_pf_listings_detail_mode_resumes_through_property_manifests(tmp_path: Path) -> None:
    s3 = FakeS3()
    _put_pf_manifest(
        s3,
        run_id="search-1",
        details=[],
        properties=[
            {
                "listing_id": "apt-1",
                "property_key": "listing_id:apt-1",
                "details_path": "/en/plp/buy/apartment-for-sale-dubai-apt-1.html",
                "category_id": 1,
                "location_id": "14",
            },
            {
                "listing_id": "apt-2",
                "property_key": "listing_id:apt-2",
                "details_path": "/en/plp/buy/apartment-for-sale-dubai-apt-2.html",
                "category_id": 1,
                "location_id": "14",
            },
        ],
    )
    listing_client = FakePropertyFinderChunkListingsClient()

    release = extract_listings_release(
        tmp_path,
        config=PropertyFinderListingsConfig(
            mode="details",
            categories=(1,),
            detail_manifest_cursor=0,
            detail_row_cursor=1,
            max_details_per_run=1,
        ),
        now=datetime(2026, 5, 4, 12, 0, tzinfo=UTC),
        listing_client=listing_client,
        state_store=s3,
    )

    detail_rows = _read_jsonl(Path(release.files[0].path))
    assert release.metadata["stage"] == "details"
    assert release.metadata["next_manifest_index"] == 1
    assert release.metadata["next_row_index"] == 0
    assert release.metadata["detail_completed_result_set"] is True
    assert detail_rows[0]["listing_id"] == "apt-2"
    assert detail_rows[0]["source_manifest_index"] == 0
    assert detail_rows[0]["source_row_index"] == 1


def test_pf_listings_detail_mode_skips_malformed_property_rows(tmp_path: Path) -> None:
    s3 = FakeS3()
    _, _, properties_key = _put_pf_manifest(
        s3,
        run_id="search-1",
        details=[],
        properties=[],
    )
    valid_rows = [
        {
            "listing_id": "apt-1",
            "property_key": "listing_id:apt-1",
            "details_path": "/en/plp/buy/apartment-for-sale-dubai-apt-1.html",
            "category_id": 1,
            "location_id": "14",
        },
        {
            "listing_id": "apt-2",
            "property_key": "listing_id:apt-2",
            "details_path": "/en/plp/buy/apartment-for-sale-dubai-apt-2.html",
            "category_id": 1,
            "location_id": "14",
        },
    ]
    s3.objects[properties_key] = (
        json.dumps(valid_rows[0], separators=(",", ":")).encode("utf-8")
        + b'\n{"listing_id":"broken"\n'
        + json.dumps(valid_rows[1], separators=(",", ":")).encode("utf-8")
        + b"\n"
    )
    listing_client = FakePropertyFinderChunkListingsClient()

    release = extract_listings_release(
        tmp_path,
        config=PropertyFinderListingsConfig(
            mode="details",
            categories=(1,),
            max_details_per_run=10,
        ),
        now=datetime(2026, 5, 4, 12, 0, tzinfo=UTC),
        listing_client=listing_client,
        state_store=s3,
    )

    detail_rows = _read_jsonl(Path(release.files[0].path))
    assert release.metadata["stage"] == "details"
    assert release.metadata["source_property_invalid_row_count"] == 1
    assert [row["listing_id"] for row in detail_rows] == ["apt-1", "apt-2"]


def test_pf_listings_search_checkpoint_resolves_plan_and_cursor() -> None:
    s3 = FakeS3()
    s3.json_objects[checkpoint_s3_key(source="pf_listings", operation="plan_snapshot")] = {
        "last_manifest_s3_key": "raw/source=pf_listings/manifests/plan-2.json",
        "plan_manifest_s3_keys": [
            "raw/source=pf_listings/manifests/plan-1.json",
            "raw/source=pf_listings/manifests/plan-2.json",
        ],
        "completed": True,
    }
    s3.json_objects[checkpoint_s3_key(source="pf_listings", operation="search_chunk")] = {
        "plan_manifest_s3_keys": [
            "raw/source=pf_listings/manifests/plan-1.json",
            "raw/source=pf_listings/manifests/plan-2.json",
        ],
        "plan_manifest_s3_key": "raw/source=pf_listings/manifests/plan-2.json",
        "next_query_index": 12,
        "next_page": 3,
        "completed": False,
    }

    config = resolve_listings_config(
        source_config={"mode": "search"},
        object_storage_client=s3,
    )

    assert config["plan_manifest_s3_key"] == "raw/source=pf_listings/manifests/plan-2.json"
    assert config["plan_manifest_s3_keys"] == [
        "raw/source=pf_listings/manifests/plan-1.json",
        "raw/source=pf_listings/manifests/plan-2.json",
    ]
    assert config["search_query_cursor"] == 12
    assert config["search_page_cursor"] == 3


def test_pf_listings_checkpoint_write_records_stage_specific_cursor() -> None:
    s3 = FakeS3()

    write_listings_checkpoint(
        raw_release=_raw_pf_release(
            run_id="search-1",
            metadata={
                "stage": "search",
                "plan_manifest_s3_key": "raw/source=pf_listings/manifests/plan-1.json",
                "plan_manifest_s3_keys": ["raw/source=pf_listings/manifests/plan-1.json"],
                "search_completed_result_set": False,
                "next_query_index": 4,
                "next_page": 9,
                "search_page_count": 100,
                "property_row_count": 2000,
                "search_error_count": 1,
            },
        ),
        manifest_key="raw/source=pf_listings/manifests/search-1.json",
        object_storage_client=s3,
    )

    checkpoint = s3.json_objects[checkpoint_s3_key(source="pf_listings", operation="search_chunk")]
    assert checkpoint["completed"] is False
    assert checkpoint["next_query_index"] == 4
    assert checkpoint["next_page"] == 9
    assert checkpoint["last_manifest_s3_key"] == "raw/source=pf_listings/manifests/search-1.json"
    assert checkpoint["plan_manifest_s3_keys"] == ["raw/source=pf_listings/manifests/plan-1.json"]


def test_pf_listings_latest_delta_bootstrap_fetches_search_only(tmp_path: Path) -> None:
    listing = _listing_wrapper(
        listing_id="apt-1",
        property_type="Apartment",
        location_tree=[{"id": 1, "name": "Dubai", "type": "CITY"}],
        details_path="/en/plp/buy/apartment-for-sale-dubai-example-apt-1.html",
    )
    listing["property"]["last_refreshed_at"] = "2026-05-02T10:00:00+00:00"
    listing_client = FakePropertyFinderLatestDeltaClient(pages={1: [listing]})
    s3 = FakeS3()

    release = extract_listings_release(
        tmp_path,
        config=PropertyFinderListingsConfig(
            mode="latest_delta",
            categories=(1,),
            location_ids=("1",),
            max_pages_per_query=1,
            max_search_pages_per_run=1,
            latest_delta_bootstrap_details=False,
        ),
        now=datetime(2026, 5, 4, 12, 0, tzinfo=UTC),
        listing_client=listing_client,
        state_store=s3,
    )

    property_rows = _read_jsonl(tmp_path / "pf_listing_properties.jsonl")
    state_update = release.metadata["_state_updates"][0]
    state = json.loads(Path(state_update["path"]).read_text(encoding="utf-8"))

    assert listing_client.detail_calls == []
    assert release.metadata["stage"] == "latest_delta"
    assert release.metadata["state_was_empty"] is True
    assert property_rows[0]["delta_reason"] == "new"
    assert property_rows[0]["selected_for_detail"] is False
    assert "listing_id:apt-1" in state["listings"]


def test_pf_listings_latest_delta_fetches_details_only_for_new_or_changed(
    tmp_path: Path,
) -> None:
    unchanged = _listing_wrapper(
        listing_id="apt-1",
        property_type="Apartment",
        location_tree=[{"id": 1, "name": "Dubai", "type": "CITY"}],
        details_path="/en/plp/buy/apartment-for-sale-dubai-example-apt-1.html",
    )
    changed = _listing_wrapper(
        listing_id="apt-2",
        property_type="Apartment",
        location_tree=[{"id": 1, "name": "Dubai", "type": "CITY"}],
        details_path="/en/plp/buy/apartment-for-sale-dubai-example-apt-2.html",
    )
    s3 = FakeS3()
    s3.json_objects[PropertyFinderListingsConfig().latest_delta_state_key] = {
        "version": 1,
        "listings": {
            "listing_id:apt-1": {"property_fingerprint": _fingerprint(unchanged["property"])},
            "listing_id:apt-2": {"property_fingerprint": "old"},
        },
    }
    listing_client = FakePropertyFinderLatestDeltaClient(
        pages={
            1: [
                unchanged,
                changed,
                _listing_wrapper(
                    listing_id="apt-3",
                    property_type="Apartment",
                    location_tree=[{"id": 1, "name": "Dubai", "type": "CITY"}],
                    details_path="/en/plp/buy/apartment-for-sale-dubai-example-apt-3.html",
                ),
            ]
        }
    )

    release = extract_listings_release(
        tmp_path,
        config=PropertyFinderListingsConfig(
            mode="latest_delta",
            categories=(1,),
            location_ids=("1",),
            max_pages_per_query=1,
            max_search_pages_per_run=1,
            fetch_details=True,
        ),
        now=datetime(2026, 5, 4, 12, 0, tzinfo=UTC),
        listing_client=listing_client,
        state_store=s3,
    )

    property_rows = _read_jsonl(tmp_path / "pf_listing_properties.jsonl")

    assert listing_client.detail_calls == [
        "/en/plp/buy/apartment-for-sale-dubai-example-apt-2.html",
        "/en/plp/buy/apartment-for-sale-dubai-example-apt-3.html",
    ]
    assert {row["listing_id"]: row["delta_reason"] for row in property_rows} == {
        "apt-1": "unchanged",
        "apt-2": "changed",
        "apt-3": "new",
    }
    assert release.metadata["delta_reason_counts"] == {
        "unchanged": 1,
        "changed": 1,
        "new": 1,
    }


def test_pf_listings_latest_delta_detail_errors_remain_retryable(tmp_path: Path) -> None:
    existing = _listing_wrapper(
        listing_id="apt-1",
        property_type="Apartment",
        location_tree=[{"id": 1, "name": "Dubai", "type": "CITY"}],
        details_path="/en/plp/buy/apartment-for-sale-dubai-example-apt-1.html",
    )
    failed = _listing_wrapper(
        listing_id="apt-2",
        property_type="Apartment",
        location_tree=[{"id": 1, "name": "Dubai", "type": "CITY"}],
        details_path="/en/plp/buy/apartment-for-sale-dubai-example-apt-2.html",
    )
    failed_path = "/en/plp/buy/apartment-for-sale-dubai-example-apt-2.html"
    s3 = FakeS3()
    s3.json_objects[PropertyFinderListingsConfig().latest_delta_state_key] = {
        "version": 1,
        "listings": {
            "listing_id:apt-1": {
                "property_fingerprint": _fingerprint(existing["property"]),
                "last_detail_scraped_at": "2026-05-01T00:00:00+00:00",
            },
        },
    }
    failing_client = FakePropertyFinderLatestDeltaClient(
        pages={1: [failed, existing]},
        detail_failures={failed_path},
    )

    first_release = extract_listings_release(
        tmp_path / "first",
        config=PropertyFinderListingsConfig(
            mode="latest_delta",
            categories=(1,),
            location_ids=("1",),
            max_pages_per_query=1,
            max_search_pages_per_run=1,
            fetch_details=True,
        ),
        now=datetime(2026, 5, 4, 12, 0, tzinfo=UTC),
        listing_client=failing_client,
        state_store=s3,
    )

    first_details = _read_jsonl(tmp_path / "first" / "pf_listing_details.jsonl")
    first_state_update = first_release.metadata["_state_updates"][0]
    first_state = json.loads(Path(first_state_update["path"]).read_text(encoding="utf-8"))
    failed_state = first_state["listings"]["listing_id:apt-2"]

    assert first_details[0]["status"] == "detail_error"
    assert "last_detail_scraped_at" not in failed_state
    assert "detail_fingerprint" not in failed_state

    s3.json_objects[PropertyFinderListingsConfig().latest_delta_state_key] = first_state
    retry_client = FakePropertyFinderLatestDeltaClient(pages={1: [failed, existing]})

    extract_listings_release(
        tmp_path / "retry",
        config=PropertyFinderListingsConfig(
            mode="latest_delta",
            categories=(1,),
            location_ids=("1",),
            max_pages_per_query=1,
            max_search_pages_per_run=1,
            fetch_details=True,
            latest_delta_detail_audit_limit=1,
        ),
        now=datetime(2026, 5, 5, 12, 0, tzinfo=UTC),
        listing_client=retry_client,
        state_store=s3,
    )

    retry_properties = _read_jsonl(tmp_path / "retry" / "pf_listing_properties.jsonl")
    assert retry_client.detail_calls == [failed_path]
    assert {row["listing_id"]: row["delta_reason"] for row in retry_properties} == {
        "apt-2": "audit",
        "apt-1": "unchanged",
    }


def test_pf_listing_media_asset_hydrates_detail_images() -> None:
    s3 = FakeS3()
    image_url = "https://static.shared.propertyfinder.ae/listings/apt-1/full.jpg"
    agent_url = "https://static.shared.propertyfinder.ae/agents/agent-1.jpg"
    _put_pf_manifest(
        s3,
        run_id="run-1",
        details=[
            {
                "listing_id": "apt-1",
                "property_key": "listing_id:apt-1",
                "detail_property": {
                    "listing_id": "apt-1",
                    "images": {"property": [{"full": image_url}]},
                    "agent": {"image": {"url": agent_url}},
                },
            }
        ],
        properties=[],
    )
    downloader = FakeMediaDownloader({image_url: b"image", agent_url: b"agent"})

    result = hydrate_pf_listing_media_assets(
        s3=s3,
        config=PropertyFinderListingMediaHydrationConfig(
            include_search_listing_media=False,
            include_detail_media=True,
            max_concurrent_downloads=1,
        ),
        now=datetime(2026, 5, 4, 12, 0, tzinfo=UTC),
        download_client=downloader,
    )
    inventory_rows = _inventory_rows(s3, result["inventory_manifest_key"])
    rows_by_type = {row["asset_type"]: row for row in inventory_rows}

    assert result["downloaded"] == 2
    assert set(rows_by_type) == {"listing_image", "agent_image"}
    assert rows_by_type["listing_image"]["status"] == "downloaded"
    assert rows_by_type["listing_image"]["sha256"] == hashlib.sha256(b"image").hexdigest()
    assert rows_by_type["listing_image"]["target_key"].startswith(
        "media/pf_listings/listing_media/listing_id=apt-1/"
        "asset_type=listing_image/field_path=images.property.0/"
    )
    assert rows_by_type["agent_image"]["field_path"] == "agent.image"
    assert s3.objects[rows_by_type["agent_image"]["target_key"]] == b"agent"


def _filter_settings(*, property_types: tuple[tuple[str, str], ...]) -> dict[str, Any]:
    return {
        "filterChoices": {
            "filter[property_type_id]": [
                {"value": value, "label": label} for value, label in property_types
            ],
            "filter[number_of_bedrooms]": [
                {"value": "0", "label": "Studio"},
                {"value": "1", "label": "1 Bedroom"},
            ],
            "sort": [{"value": "nd", "label": "Newest"}],
        }
    }


def _search_payload(*, total_count: int, page_count: int, listings: list[dict[str, Any]]) -> dict:
    return {
        "pageProps": {
            "searchResult": {
                "listings": listings,
                "meta": {
                    "total_count": total_count,
                    "page_count": page_count,
                    "page": 1,
                },
            }
        }
    }


def _locations_payload(locations: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "data": {
            "attributes": locations,
            "meta": {"total_count": len(locations), "total_pages": 1},
        }
    }


def _listing_wrapper(
    *,
    listing_id: str,
    property_type: str,
    location_tree: list[dict[str, Any]],
    details_path: str,
) -> dict[str, Any]:
    return {
        "listing_type": "property",
        "property": {
            "id": listing_id,
            "listing_id": listing_id,
            "reference": f"PF-{listing_id}",
            "title": f"{property_type} listing",
            "type": property_type,
            "price": {"value": 1_000_000, "currency": "AED"},
            "size": {"value": 1200, "unit": "sqft"},
            "location": {"id": location_tree[-1]["id"], "lat": 25.1, "lon": 55.2},
            "location_tree": location_tree,
            "share_url": details_path,
            "images": [
                {
                    "medium": (
                        f"https://static.shared.propertyfinder.ae/listings/{listing_id}/medium.jpg"
                    )
                }
            ],
        },
    }


def _put_pf_manifest(
    s3: FakeS3,
    *,
    run_id: str,
    details: list[dict[str, Any]],
    properties: list[dict[str, Any]],
) -> tuple[str, str, str]:
    manifest_key = f"raw/source=pf_listings/manifests/{run_id}.json"
    detail_key = (
        f"raw/source=pf_listings/extract_date=2026-05-04/run_id={run_id}/pf_listing_details.jsonl"
    )
    properties_key = (
        f"raw/source=pf_listings/extract_date=2026-05-04/"
        f"run_id={run_id}/pf_listing_properties.jsonl"
    )
    s3.objects[detail_key] = _jsonl_bytes(details)
    s3.objects[properties_key] = _jsonl_bytes(properties)
    s3.objects[manifest_key] = json.dumps(
        {
            "source": "pf_listings",
            "run_id": run_id,
            "files": [
                {
                    "path": "pf_listing_details.jsonl",
                    "s3_key": detail_key,
                    "row_count": len(details),
                },
                {
                    "path": "pf_listing_properties.jsonl",
                    "s3_key": properties_key,
                    "row_count": len(properties),
                },
            ],
        }
    ).encode("utf-8")
    return manifest_key, detail_key, properties_key


def _put_pf_plan_manifest(
    s3: FakeS3,
    *,
    run_id: str,
    terminal_queries: list[dict[str, Any]],
    plan_state: dict[str, Any] | None = None,
) -> str:
    manifest_key = f"raw/source=pf_listings/manifests/{run_id}.json"
    plan_key = (
        f"raw/source=pf_listings/extract_date=2026-05-04/run_id={run_id}/"
        "pf_listing_query_plan.jsonl"
    )
    state_key = (
        f"raw/source=pf_listings/extract_date=2026-05-04/run_id={run_id}/"
        "pf_listing_plan_state.jsonl"
    )
    plan_rows = [
        {
            "endpoint": "search_plan",
            "query_signature": f"query-{index}",
            "terminal": True,
            "status": "terminal",
            "query": query,
        }
        for index, query in enumerate(terminal_queries)
    ]
    s3.objects[plan_key] = _jsonl_bytes(plan_rows)
    manifest_files = [
        {
            "path": "pf_listing_query_plan.jsonl",
            "s3_key": plan_key,
            "row_count": len(plan_rows),
        }
    ]
    if plan_state is not None:
        s3.objects[state_key] = _jsonl_bytes([plan_state])
        manifest_files.append(
            {
                "path": "pf_listing_plan_state.jsonl",
                "s3_key": state_key,
                "row_count": 1,
            }
        )
    s3.objects[manifest_key] = json.dumps(
        {
            "source": "pf_listings",
            "run_id": run_id,
            "files": manifest_files,
        }
    ).encode("utf-8")
    return manifest_key


def _raw_pf_release(*, run_id: str, metadata: dict[str, Any]) -> RawRelease:
    return RawRelease(
        source="pf_listings",
        run_id=run_id,
        extract_date="2026-05-04",
        created_at="2026-05-04T12:00:00+00:00",
        files=(),
        metadata=metadata,
    )


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _inventory_rows(s3: FakeS3, key: str) -> list[dict[str, Any]]:
    return [json.loads(line) for line in s3.read_text(key=key).splitlines() if line.strip()]
