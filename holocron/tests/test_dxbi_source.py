import json
import os
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, cast

import pytest

from holocron.sources import DXBI_SOURCE, registry
from holocron.sources.dxbi.extract import (
    _apply_date_slice,
    _extract_heatmap_files,
    _extract_table_rows,
    _heatmap_client_signature,
    _heatmap_rental_queries,
    _raise_if_blocked_ajax,
    _resolve_browser_executable,
    _virtual_display_if_needed,
    extract_release,
    load_page_urls,
)
from holocron.sources.dxbi.source import DateSlice, DxbiConfig, build_date_slices


def test_dxbi_source_is_registered() -> None:
    assert registry.get("dxbi_transactions") is DXBI_SOURCE


def test_incremental_date_slices_use_lookback_window() -> None:
    config = DxbiConfig(mode="incremental", lookback_days=2, slice_days=2)

    slices = build_date_slices(config, today=date(2026, 3, 31))

    assert slices == (
        DateSlice(start_date=date(2026, 3, 29), end_date=date(2026, 3, 30)),
        DateSlice(start_date=date(2026, 3, 31), end_date=date(2026, 3, 31)),
    )


def test_backfill_requires_explicit_dates() -> None:
    with pytest.raises(ValueError, match="start_date and end_date"):
        DxbiConfig(mode="backfill")


def test_dxbi_config_coerces_comprehensive_query_lists() -> None:
    config = DxbiConfig.model_validate(
        {"heatmap_property_types": "Apartment,Villa", "heatmap_bedrooms": "0,1,2"}
    )

    assert config.scrape_mode == "comprehensive"
    assert config.heatmap_property_types == ("Apartment", "Villa")
    assert config.heatmap_bedrooms == ("0", "1", "2")


def test_load_page_urls_defaults_and_dedupes() -> None:
    urls = load_page_urls(
        page_urls_text="https://dxbinteract.com/\nhttps://dxbinteract.com/projects/a",
        page_urls_file="",
    )

    assert urls == ["https://dxbinteract.com/", "https://dxbinteract.com/projects/a"]


def test_extract_release_writes_one_jsonl_file_per_slice(tmp_path: Path) -> None:
    config = DxbiConfig(
        mode="backfill",
        start_date=date(2026, 3, 1),
        end_date=date(2026, 3, 3),
        slice_days=2,
    )

    def page_scraper(**kwargs):
        date_slice = kwargs["date_slice"]
        return [
            {
                "table": "sales",
                "cells": ["row"],
                "_slice_start_date": date_slice.start_date.isoformat(),
                "_slice_end_date": date_slice.end_date.isoformat(),
            }
        ]

    release = extract_release(
        tmp_path,
        config=config,
        now=datetime(2026, 3, 31, 8, 0, tzinfo=UTC),
        page_scraper=page_scraper,
    )

    assert release.run_id == "2026-03-31T08-00-00Z"
    assert len(release.files) == 2
    assert all(file.path.endswith(".jsonl") for file in release.files)


def test_resolve_browser_executable_uses_explicit_path(tmp_path: Path) -> None:
    chrome = tmp_path / "chrome"
    chrome.write_text("", encoding="utf-8")

    assert _resolve_browser_executable(str(chrome)) == str(chrome)


def test_resolve_browser_executable_raises_when_explicit_missing() -> None:
    with pytest.raises(FileNotFoundError, match="DXBI browser executable not found"):
        _resolve_browser_executable("/does/not/exist/chrome")


def test_resolve_browser_executable_falls_back_to_detected_candidate(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    detected = tmp_path / "google-chrome"
    detected.write_text("", encoding="utf-8")

    def fake_which(name: str) -> str | None:
        if name == "google-chrome":
            return str(detected)
        return None

    monkeypatch.setattr("holocron.sources.dxbi.extract.shutil.which", fake_which)

    assert _resolve_browser_executable("") == str(detected)


def test_raise_if_blocked_ajax_noop_when_all_ok() -> None:
    _raise_if_blocked_ajax(statuses=[200, 204], url="https://dxbinteract.com/")


def test_raise_if_blocked_ajax_raises_for_error_statuses() -> None:
    with pytest.raises(RuntimeError, match="HTTP 403, 429"):
        _raise_if_blocked_ajax(
            statuses=[200, 403, 429],
            url="https://dxbinteract.com/",
        )


def test_virtual_display_starts_xvfb_for_headful_without_display(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.setattr(
        "holocron.sources.dxbi.extract.shutil.which",
        lambda name: "/usr/bin/Xvfb" if name == "Xvfb" else None,
    )
    monkeypatch.setattr("holocron.sources.dxbi.extract.Path.exists", lambda _path: False)
    monkeypatch.setattr("holocron.sources.dxbi.extract.time.sleep", lambda _seconds: None)

    processes = []

    class FakeProcess:
        def __init__(self) -> None:
            self.terminated = False
            self.killed = False

        def poll(self) -> None:
            return None

        def terminate(self) -> None:
            self.terminated = True

        def kill(self) -> None:
            self.killed = True

        def wait(self, *, timeout: int) -> int:
            assert timeout == 5
            return 0

    def fake_popen(*args, **kwargs):
        process = FakeProcess()
        processes.append((args, kwargs, process))
        return process

    monkeypatch.setattr("holocron.sources.dxbi.extract.subprocess.Popen", fake_popen)

    with _virtual_display_if_needed(DxbiConfig(headless=False)):
        assert os.environ["DISPLAY"] == ":90"

    assert "DISPLAY" not in os.environ
    assert processes[0][0][0][:2] == ["Xvfb", ":90"]
    assert processes[0][2].terminated
    assert not processes[0][2].killed


def test_apply_date_slice_waits_for_report_refresh_not_existing_rows() -> None:
    class FakePage:
        wait_script = ""
        wait_arg = {}

        def evaluate(self, script: str, arg: list[str]) -> dict:
            assert "soldRows > 0" not in script
            assert "apex.region('soldhistory').refresh()" in script
            assert "apex.region('rentHistory').refresh()" in script
            return {"status": "ok", "token": "refresh-token"}

        def wait_for_function(self, script: str, *, arg: dict, timeout: int) -> None:
            self.wait_script = script
            self.wait_arg = arg
            assert timeout == 20000

        def wait_for_timeout(self, timeout: int) -> None:
            raise AssertionError(f"unexpected timeout fallback: {timeout}")

    page = FakePage()

    _apply_date_slice(
        page=cast(Any, page),
        date_slice=DateSlice(start_date=date(2026, 3, 1), end_date=date(2026, 3, 3)),
    )

    assert page.wait_arg == {"token": "refresh-token"}
    assert "soldRows > 0" not in page.wait_script
    assert "rentRows > 0" not in page.wait_script
    assert "soldReady && rentReady" in page.wait_script


def test_extract_table_rows_preserves_ordered_columns_links_and_html() -> None:
    class FakePage:
        def evaluate(self, script: str, arg: str) -> dict:
            assert arg == "#report_table_soldhistory"
            return {
                "headers": {"TOTAL_PRICE": "Price", "DETAIL_LINK": ""},
                "rows": [
                    [
                        {
                            "header": "TOTAL_PRICE",
                            "label": "Price",
                            "text": "AED\n 604,500\n\nAED 1,799 /sqft",
                            "html": "<a href='https://dxb.is/hjldwudy'>AED 604,500</a>",
                            "links": [
                                {
                                    "text": "AED\n604,500",
                                    "href": "https://dxb.is/hjldwudy",
                                    "title": "",
                                    "aria_label": "",
                                    "class": "",
                                }
                            ],
                        },
                        {
                            "header": "DETAIL_LINK",
                            "label": "",
                            "text": "Share Details",
                            "html": "<a class='detailBtn' href='https://dxb.is/hjldwudy'>Details</a>",
                            "links": [
                                {
                                    "text": "Details",
                                    "href": "https://dxb.is/hjldwudy",
                                    "title": "",
                                    "aria_label": "",
                                    "class": "detailBtn",
                                }
                            ],
                        },
                    ]
                ],
            }

    rows = _extract_table_rows(
        page=cast(Any, FakePage()),
        table_selector="#report_table_soldhistory",
        table_name="sales",
        page_number=1,
        url="https://dxbinteract.com/",
        run_id="run-1",
        scraped_at="2026-03-31T08:00:00+00:00",
        date_slice=DateSlice(start_date=date(2026, 3, 1), end_date=date(2026, 3, 1)),
    )

    assert rows[0]["cells"] == ["AED 604,500 AED 1,799 /sqft", "Share Details"]
    assert rows[0]["columns"][0] == {
        "id": "TOTAL_PRICE",
        "label": "Price",
        "text": "AED 604,500 AED 1,799 /sqft",
        "html": "<a href='https://dxb.is/hjldwudy'>AED 604,500</a>",
        "links": [
            {
                "text": "AED 604,500",
                "href": "https://dxb.is/hjldwudy",
                "title": "",
                "aria_label": "",
                "class": "",
            }
        ],
    }
    assert rows[0]["links"] == [
        {
            "cell_header": "TOTAL_PRICE",
            "cell_label": "Price",
            "text": "AED 604,500",
            "href": "https://dxb.is/hjldwudy",
            "title": "",
            "aria_label": "",
            "class": "",
        },
        {
            "cell_header": "DETAIL_LINK",
            "cell_label": "",
            "text": "Details",
            "href": "https://dxb.is/hjldwudy",
            "title": "",
            "aria_label": "",
            "class": "detailBtn",
        },
    ]
    assert rows[0]["detail_urls"] == ["https://dxb.is/hjldwudy"]


def test_heatmap_client_signature_shape() -> None:
    signature = _heatmap_client_signature(timestamp=1_777_907_620)

    assert len(signature) == 172


def test_heatmap_rental_queries_cover_property_type_and_bedroom_matrix() -> None:
    config = DxbiConfig(heatmap_property_types=("Apartment", "Villa"), heatmap_bedrooms=("0", "1"))

    assert _heatmap_rental_queries(config) == [
        {
            "Area": 0,
            "Location": 0,
            "Type": "Apartment",
            "Bedrooms": "0",
            "RentalRange": {"Min": None, "Max": None},
        },
        {
            "Area": 0,
            "Location": 0,
            "Type": "Apartment",
            "Bedrooms": "1",
            "RentalRange": {"Min": None, "Max": None},
        },
        {
            "Area": 0,
            "Location": 0,
            "Type": "Villa",
            "Bedrooms": "0",
            "RentalRange": {"Min": None, "Max": None},
        },
        {
            "Area": 0,
            "Location": 0,
            "Type": "Villa",
            "Bedrooms": "1",
            "RentalRange": {"Min": None, "Max": None},
        },
    ]


def test_extract_heatmap_files_writes_deduped_building_payloads(tmp_path: Path) -> None:
    class FakeLog:
        def info(self, *_args) -> None:
            pass

        def warning(self, *_args) -> None:
            pass

    class FakePage:
        def __init__(self) -> None:
            self.calls = []

        def evaluate(self, _script: str, arg: dict) -> dict:
            self.calls.append(arg)
            url = arg["url"]
            if url.endswith("/api/v1/rentals"):
                return {
                    "url": url,
                    "method": arg["method"],
                    "status": 200,
                    "content_type": "application/json",
                    "payload": [
                        {
                            "location_id": 1,
                            "location": "Building One",
                            "area_name": "Area",
                            "cor": [55.1, 25.1],
                        },
                        {
                            "location_id": 1,
                            "location": "Building One",
                            "area_name": "Area",
                            "cor": [55.1, 25.1],
                        },
                    ],
                    "text": "",
                }
            if "/api/v1/building-status/" in url:
                payload = {"Status": 200, "BuildingStatus": {"is_offplan": "N"}}
            elif "/api/v1/chessboard/" in url:
                payload = {
                    "Status": 200,
                    "Chessboard": {
                        "Floors": [
                            {
                                "Floor": 1,
                                "Units": [
                                    {
                                        "PropertyNumber": "101",
                                        "Price": 650000,
                                        "Rental": {"Amount": 48025},
                                    }
                                ],
                            }
                        ]
                    },
                }
            elif "/api/v1/building/" in url:
                payload = {"Status": 200, "Building": {"location_id": 1, "project": "Project"}}
            elif "fam-erp.com/property/xd/map/buildings" in url:
                payload = {"items": [{"location_id": 1, "project": "Project"}]}
            else:
                raise AssertionError(url)
            return {
                "url": url,
                "method": arg["method"],
                "status": 200,
                "content_type": "application/json",
                "payload": payload,
                "text": "",
            }

        def wait_for_timeout(self, _timeout: int) -> None:
            pass

    files, metadata = _extract_heatmap_files(
        output_path=tmp_path,
        run_id="run-1",
        scraped_at="2026-05-04T16:00:00+00:00",
        page=cast(Any, FakePage()),
        config=DxbiConfig(
            heatmap_property_types=("Apartment",),
            heatmap_bedrooms=("1",),
            heatmap_request_pause_seconds=0,
        ),
        progress_log=FakeLog(),
    )

    assert {Path(file.path).name for file in files} == {
        "dxbi_heatmap_rental_buildings.jsonl",
        "dxbi_heatmap_buildings.jsonl",
        "dxbi_heatmap_building_statuses.jsonl",
        "dxbi_heatmap_chessboards.jsonl",
        "dxbi_fam_map_buildings.jsonl",
    }
    assert metadata["heatmap_rental_building_rows"] == 2
    assert metadata["heatmap_unique_buildings_discovered"] == 1
    assert metadata["heatmap_buildings_attempted"] == 1

    chessboard = tmp_path / "dxbi_heatmap_chessboards.jsonl"
    row = json.loads(chessboard.read_text().splitlines()[0])
    assert row["location_id"] == "1"
    assert row["payload"]["Chessboard"]["Floors"][0]["Units"][0]["PropertyNumber"] == "101"
