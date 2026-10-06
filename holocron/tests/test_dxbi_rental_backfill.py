import importlib.util
import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import ModuleType


def _load_script() -> ModuleType:
    path = Path(__file__).parents[1] / "scripts" / "dxbi_rental_backfill.py"
    spec = importlib.util.spec_from_file_location("dxbi_rental_backfill", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _configuration() -> dict:
    return {
        "manifest_version": 2,
        "manifest_hash": "manifest",
        "report_type": "rentals",
        "account": "account-b",
        "profile_id": "broad",
        "profile_label": "All",
        "location_id": "1",
        "location_text": "Dubai",
        "location_slug": "dubai",
        "filters": {"P74_DEAL": "RENT"},
        "configuration_hash": "12345678901234567890",
    }


def test_filter_discovery_uses_live_rental_control_slugs() -> None:
    scraper = _load_script()

    class FakePage:
        def __init__(self) -> None:
            self.calls: list[dict[str, str]] = []

        def evaluate(self, _script: str, argument: dict[str, str]) -> list[dict[str, str]]:
            self.calls.append(argument)
            return [{"value": "A", "label": argument["domId"]}]

    page = FakePage()

    discovered = scraper.discover_filter_options(page)

    assert page.calls == [
        {"itemId": "P74_PROP_TYPE", "domId": "prop-type"},
        {"itemId": "P74_STATUS", "domId": "status"},
        {"itemId": "P74_BEDS", "domId": "beds"},
    ]
    assert set(discovered) == {"P74_PROP_TYPE", "P74_STATUS", "P74_BEDS"}


def test_apex_pagination_keeps_max_rows_as_page_size() -> None:
    scraper = _load_script()

    class FakePage:
        def evaluate(self, script: str, _payload: dict) -> dict:
            assert "params.set('p_pg_min_row', String(input.pageStart))" in script
            assert "params.set('p_pg_max_rows', '300')" in script
            assert "input.pageStart + 299" not in script
            return {"status": 200, "login_redirect": False, "rows": []}

    shard = {**scraper.initial_shards(date(2026, 8, 1))[0], "page_start": 301}
    scraper.fetch_rows(
        FakePage(),
        {"post_data": "p_json={}", "url": "https://example.test", "region_id": "region"},
        shard,
        {},
        scraper.DEFAULT_LOCATION,
        scraper.REPORTS["rentals"],
    )


def test_price_and_size_sharding_never_drops_a_capped_page() -> None:
    scraper = _load_script()
    root = scraper.initial_shards(date(2026, 7, 1))[0]

    price_children = scraper.split_capped_shard(root)
    price_bucket_size_children = scraper.split_capped_shard(price_children[1])
    size_children = scraper.split_capped_shard(
        {
            **root,
            "min_price": Decimal("100"),
            "max_price": Decimal("100"),
        }
    )
    price_children_at_exact_size = scraper.split_capped_shard(
        {
            **root,
            "min_price": Decimal("100"),
            "max_price": Decimal("199.99"),
            "min_size": Decimal("50"),
            "max_size": Decimal("50"),
        }
    )
    price_children_at_size_floor = scraper.split_capped_shard(
        {
            **root,
            "min_price": Decimal("100"),
            "max_price": Decimal("199.99"),
            "min_size": Decimal("0"),
            "max_size": Decimal("0.01"),
        }
    )
    unsplittable = scraper.split_capped_shard(
        {
            **root,
            "min_price": Decimal("100"),
            "max_price": Decimal("100"),
            "min_size": Decimal("50"),
            "max_size": Decimal("50"),
        }
    )

    assert price_children == [
        {**root, "min_price": minimum, "max_price": maximum}
        for minimum, maximum in scraper.PRICE_BUCKETS
    ]
    assert len(size_children) == len(scraper.SIZE_BUCKETS)
    assert price_bucket_size_children == [
        {**price_children[1], "min_size": minimum, "max_size": maximum}
        for minimum, maximum in scraper.SIZE_BUCKETS
    ]
    assert len(price_children_at_exact_size) == 2
    assert price_children_at_exact_size[0]["max_price"] == Decimal("150.00")
    assert price_children_at_exact_size[1]["min_price"] == Decimal("150.01")
    assert [
        (child["min_price"], child["max_price"])
        for child in price_children_at_size_floor
    ] == [
        (child["min_price"], child["max_price"])
        for child in price_children_at_exact_size
    ]
    assert unsplittable == []


def test_refine_paged_checkpoint_archives_old_pages(tmp_path: Path) -> None:
    scraper = _load_script()
    configuration = _configuration()
    shard = {
        **scraper.initial_shards(date(2025, 1, 1))[0],
        "min_price": Decimal("25000"),
        "max_price": Decimal("49999.99"),
        "min_size": Decimal("0"),
        "max_size": Decimal("0.00"),
    }
    root_key = scraper.checkpoint_key(configuration, scraper.shard_key(shard))
    page_key = scraper.checkpoint_key(
        configuration, scraper.shard_key({**shard, "page_start": 301})
    )
    raw_path = tmp_path / "shards" / "page.jsonl.gz"
    raw_path.parent.mkdir(parents=True)
    raw_path.write_bytes(b"old page")
    state = {
        "completed": {root_key: {"rows": 300, "path": "shards/page.jsonl.gz"}},
        "expanded": {},
        "failed": {page_key: {"reason": "empty page"}},
        "paged": {root_key: {"next_page_start": 301}},
    }
    children = scraper.split_capped_shard(shard)

    scraper.refine_paged_checkpoint(
        output_dir=tmp_path,
        state=state,
        root_key=root_key,
        children=children,
        configuration=configuration,
    )

    assert root_key not in state["completed"]
    assert page_key not in state["failed"]
    assert root_key not in state["paged"]
    assert state["expanded"][root_key]["reason"] == "refined_previously_paged_capped_shard"
    assert not raw_path.exists()
    assert raw_path.with_name("page.jsonl.gz.superseded").read_bytes() == b"old page"


def test_refine_expanded_checkpoint_archives_descendant_tree(tmp_path: Path) -> None:
    scraper = _load_script()
    configuration = _configuration()
    root = {
        **scraper.initial_shards(date(2025, 1, 1))[0],
        "min_price": Decimal("25000"),
        "max_price": Decimal("49999.99"),
        "min_size": Decimal("0"),
        "max_size": Decimal("0.01"),
    }
    old_child = {**root, "max_size": Decimal("0.00")}
    root_key = scraper.checkpoint_key(configuration, scraper.shard_key(root))
    old_child_key = scraper.checkpoint_key(configuration, scraper.shard_key(old_child))
    old_page_key = scraper.checkpoint_key(
        configuration, scraper.shard_key({**old_child, "page_start": 301})
    )
    raw_path = tmp_path / "shards" / "old-child.jsonl.gz"
    raw_path.parent.mkdir(parents=True)
    raw_path.write_bytes(b"old child")
    state = {
        "completed": {
            old_child_key: {"rows": 300, "path": "shards/old-child.jsonl.gz"}
        },
        "expanded": {root_key: {"children": [old_child_key]}},
        "failed": {old_page_key: {"reason": "empty page"}},
        "paged": {old_child_key: {"next_page_start": 301}},
    }
    children = scraper.split_capped_shard(root)

    scraper.refine_expanded_checkpoint(
        output_dir=tmp_path,
        state=state,
        root_key=root_key,
        children=children,
        configuration=configuration,
    )

    assert old_child_key not in state["completed"]
    assert old_page_key not in state["failed"]
    assert old_child_key not in state["paged"]
    assert state["expanded"][root_key]["reason"] == "refined_saved_expansion"
    assert not raw_path.exists()
    assert raw_path.with_name("old-child.jsonl.gz.superseded").read_bytes() == b"old child"


def test_checkpoint_rejects_a_different_configuration_hash(tmp_path: Path) -> None:
    scraper = _load_script()
    configuration = _configuration()
    state_path = tmp_path / "checkpoint.json"
    state = scraper.load_state(state_path, configuration)
    scraper.atomic_json(state_path, state)

    changed = {**configuration, "configuration_hash": "abcdefghijklmnopqrst"}

    try:
        scraper.load_state(state_path, changed)
    except RuntimeError as exc:
        assert "belongs to configuration" in str(exc)
    else:
        raise AssertionError("incompatible checkpoint was accepted")


def test_reconciliation_reports_cumulative_requests_after_resume(tmp_path: Path) -> None:
    scraper = _load_script()
    configuration = _configuration()
    state_path, _ = scraper.configuration_paths(tmp_path, configuration)
    state = scraper.load_state(state_path, configuration)
    state["requests"] = 7
    state["partitions"]["2026-07-01"] = {"status": "complete"}
    scraper.atomic_json(state_path, state)

    reconciliation = scraper.write_run_reconciliation(
        output_dir=tmp_path,
        configurations=[configuration],
        dates=[date(2026, 7, 1)],
        status="success",
        run_requests=2,
        manifest_hash="manifest",
    )

    assert reconciliation["run_requests"] == 7
    assert reconciliation["invocation_requests"] == 2


def test_complete_configuration_skips_browser_template_capture(monkeypatch, tmp_path: Path) -> None:
    scraper = _load_script()
    configuration = _configuration()
    state_path, _ = scraper.configuration_paths(tmp_path, configuration)
    state = scraper.load_state(state_path, configuration)
    state["partitions"]["2026-07-01"] = {"status": "complete"}
    scraper.atomic_json(state_path, state)

    def unexpected_capture(*args, **kwargs):
        raise AssertionError("completed configuration recaptured a browser template")

    monkeypatch.setattr(scraper, "capture_template", unexpected_capture)

    status, requests = scraper.scrape_configuration(
        page=object(),
        context=object(),
        credentials={},
        storage_path=tmp_path / "state.json",
        output_dir=tmp_path,
        configuration=configuration,
        dates=[date(2026, 7, 1)],
        direction="asc",
        template_date="2026-06-30",
        report=scraper.REPORTS["rentals"],
        delay_min=0,
        delay_max=0,
        request_limit=1,
    )

    assert status == "complete"
    assert requests == 0


def test_request_budget_exhaustion_is_incomplete(monkeypatch, tmp_path: Path) -> None:
    scraper = _load_script()
    monkeypatch.setattr(scraper, "capture_template", lambda *args, **kwargs: {})

    status, requests = scraper.scrape_configuration(
        page=object(),
        context=object(),
        credentials={},
        storage_path=tmp_path / "state.json",
        output_dir=tmp_path,
        configuration=_configuration(),
        dates=[date(2026, 7, 1)],
        direction="asc",
        template_date="2026-06-30",
        report=scraper.REPORTS["rentals"],
        delay_min=0,
        delay_max=0,
        request_limit=0,
    )

    assert status == "incomplete"
    assert requests == 0
    checkpoint = next((tmp_path / "checkpoints").glob("*.json"))
    state = json.loads(checkpoint.read_text())
    assert state["partitions"]["2026-07-01"]["reason"] == "request_budget_exhausted"

    monkeypatch.setattr(
        scraper,
        "fetch_rows",
        lambda *args, **kwargs: {
            "status": 200,
            "login_redirect": False,
            "rows": [],
            "error": "",
        },
    )
    monkeypatch.setattr(scraper.time, "sleep", lambda _: None)
    resumed_status, resumed_requests = scraper.scrape_configuration(
        page=object(),
        context=object(),
        credentials={},
        storage_path=tmp_path / "state.json",
        output_dir=tmp_path,
        configuration=_configuration(),
        dates=[date(2026, 7, 1)],
        direction="asc",
        template_date="2026-06-30",
        report=scraper.REPORTS["rentals"],
        delay_min=0,
        delay_max=0,
        request_limit=1,
    )

    assert resumed_status == "complete"
    assert resumed_requests == 1


def test_template_failure_is_persisted_for_restart(monkeypatch, tmp_path: Path) -> None:
    scraper = _load_script()

    def fail_template(*args, **kwargs):
        raise RuntimeError("APEX template unavailable")

    monkeypatch.setattr(scraper, "capture_template", fail_template)

    status, requests = scraper.scrape_configuration(
        page=object(),
        context=object(),
        credentials={},
        storage_path=tmp_path / "state.json",
        output_dir=tmp_path,
        configuration=_configuration(),
        dates=[date(2026, 7, 1)],
        direction="asc",
        template_date="2026-06-30",
        report=scraper.REPORTS["rentals"],
        delay_min=0,
        delay_max=0,
        request_limit=1,
    )

    assert status == "failed"
    assert requests == 0
    checkpoint = next((tmp_path / "checkpoints").glob("*.json"))
    state = json.loads(checkpoint.read_text())
    assert "template_capture_failed" in state["partitions"]["2026-07-01"]["reason"]


def test_recoverable_request_is_retried_and_partition_completes(
    monkeypatch, tmp_path: Path
) -> None:
    scraper = _load_script()
    responses = iter(
        [
            {"status": 598, "login_redirect": False, "rows": [], "error": "timeout"},
            {"status": 200, "login_redirect": False, "rows": [], "error": ""},
        ]
    )
    monkeypatch.setattr(scraper, "capture_template", lambda *args, **kwargs: {})
    monkeypatch.setattr(scraper, "fetch_rows", lambda *args, **kwargs: next(responses))
    monkeypatch.setattr(scraper.time, "sleep", lambda _: None)

    status, requests = scraper.scrape_configuration(
        page=object(),
        context=object(),
        credentials={},
        storage_path=tmp_path / "state.json",
        output_dir=tmp_path,
        configuration=_configuration(),
        dates=[date(2026, 7, 1)],
        direction="asc",
        template_date="2026-06-30",
        report=scraper.REPORTS["rentals"],
        delay_min=0,
        delay_max=0,
        request_limit=3,
    )

    assert status == "complete"
    assert requests == 2
    checkpoint = next((tmp_path / "checkpoints").glob("*.json"))
    state = json.loads(checkpoint.read_text())
    assert state["partitions"]["2026-07-01"]["status"] == "complete"


def test_budget_exhaustion_during_retry_is_not_reported_as_success_or_failure(
    monkeypatch, tmp_path: Path
) -> None:
    scraper = _load_script()
    monkeypatch.setattr(scraper, "capture_template", lambda *args, **kwargs: {})
    monkeypatch.setattr(
        scraper,
        "fetch_rows",
        lambda *args, **kwargs: {
            "status": 598,
            "login_redirect": False,
            "rows": [],
            "error": "timeout",
        },
    )
    monkeypatch.setattr(scraper.time, "sleep", lambda _: None)

    status, requests = scraper.scrape_configuration(
        page=object(),
        context=object(),
        credentials={},
        storage_path=tmp_path / "state.json",
        output_dir=tmp_path,
        configuration=_configuration(),
        dates=[date(2026, 7, 1)],
        direction="asc",
        template_date="2026-06-30",
        report=scraper.REPORTS["rentals"],
        delay_min=0,
        delay_max=0,
        request_limit=1,
    )

    assert status == "incomplete"
    assert requests == 1


def test_direct_pagination_follows_response_metadata_without_sharding(
    monkeypatch, tmp_path: Path
) -> None:
    scraper = _load_script()
    configuration = {
        **_configuration(),
        "source_run_id": "pagination-test",
        "collection_strategy": "paginate",
    }
    row = {
        "row_attributes": {},
        "hidden_attributes": {},
        "columns": [
            {
                "id": "UNIT",
                "label": "Unit",
                "text": "101",
                "html": "101",
                "links": [],
                "attributes": {},
            }
        ],
    }
    responses = iter(
        [
            {
                "status": 200,
                "login_redirect": False,
                "rows": [row] * 300,
                "error": "",
                "pagination_text": "1 - 300 of 302",
                "reported_total": 302,
                "has_next_page": True,
                "next_page_start": 301,
            },
            {
                "status": 200,
                "login_redirect": False,
                "rows": [row] * 2,
                "error": "",
                "pagination_text": "301 - 302 of 302",
                "reported_total": 302,
                "has_next_page": False,
                "next_page_start": None,
            },
        ]
    )
    monkeypatch.setattr(scraper, "capture_template", lambda *args, **kwargs: {})
    monkeypatch.setattr(scraper, "fetch_rows", lambda *args, **kwargs: next(responses))
    monkeypatch.setattr(scraper.time, "sleep", lambda _: None)

    status, requests = scraper.scrape_configuration(
        page=object(),
        context=object(),
        credentials={},
        storage_path=tmp_path / "state.json",
        output_dir=tmp_path,
        configuration=configuration,
        dates=[date(2026, 8, 1)],
        direction="asc",
        template_date="2026-08-01",
        report=scraper.REPORTS["rentals"],
        delay_min=0,
        delay_max=0,
        request_limit=2,
        collection_strategy="paginate",
    )

    assert status == "complete"
    assert requests == 2
    checkpoint = next((tmp_path / "checkpoints").glob("*.json"))
    state = json.loads(checkpoint.read_text())
    assert not state["expanded"]
    assert sum(item["rows"] for item in state["completed"].values()) == 302
    assert {item["requested_page_start"] for item in state["completed"].values()} == {1, 301}


def test_capped_page_followed_by_an_empty_page_fails_closed(
    monkeypatch, tmp_path: Path
) -> None:
    scraper = _load_script()
    configuration = {
        **_configuration(),
        "source_run_id": "empty-page-test",
        "collection_strategy": "paginate",
    }
    row = {
        "row_attributes": {},
        "hidden_attributes": {},
        "columns": [
            {
                "id": "UNIT",
                "label": "Unit",
                "text": "101",
                "html": "101",
                "links": [],
                "attributes": {},
            }
        ],
    }
    responses = iter(
        [
            {"status": 200, "login_redirect": False, "rows": [row] * 300, "error": ""},
            {"status": 200, "login_redirect": False, "rows": [], "error": ""},
        ]
    )
    monkeypatch.setattr(scraper, "capture_template", lambda *args, **kwargs: {})
    monkeypatch.setattr(scraper, "fetch_rows", lambda *args, **kwargs: next(responses))
    monkeypatch.setattr(scraper.time, "sleep", lambda _: None)

    status, requests = scraper.scrape_configuration(
        page=object(),
        context=object(),
        credentials={},
        storage_path=tmp_path / "state.json",
        output_dir=tmp_path,
        configuration=configuration,
        dates=[date(2026, 8, 1)],
        direction="asc",
        template_date="2026-08-01",
        report=scraper.REPORTS["rentals"],
        delay_min=0,
        delay_max=0,
        request_limit=2,
        collection_strategy="paginate",
    )

    assert status == "failed"
    assert requests == 2
    checkpoint = next((tmp_path / "checkpoints").glob("*.json"))
    state = json.loads(checkpoint.read_text())
    assert "requested page returned no rows" in state["partitions"]["2026-08-01"]["reason"]


def test_short_page_with_unreachable_reported_rows_fails_partition(
    monkeypatch, tmp_path: Path
) -> None:
    scraper = _load_script()
    monkeypatch.setattr(scraper, "capture_template", lambda *args, **kwargs: {})
    monkeypatch.setattr(
        scraper,
        "fetch_rows",
        lambda *args, **kwargs: {
            "status": 200,
            "login_redirect": False,
            "rows": [],
            "error": "",
            "pagination_text": "1 - 0 of 5",
            "reported_total": 5,
            "has_next_page": False,
            "next_page_start": None,
        },
    )
    monkeypatch.setattr(scraper.time, "sleep", lambda _: None)

    status, requests = scraper.scrape_configuration(
        page=object(),
        context=object(),
        credentials={},
        storage_path=tmp_path / "state.json",
        output_dir=tmp_path,
        configuration=_configuration(),
        dates=[date(2026, 8, 24)],
        direction="asc",
        template_date="2026-08-24",
        report=scraper.REPORTS["rentals"],
        delay_min=0,
        delay_max=0,
        request_limit=1,
    )

    assert status == "failed"
    assert requests == 1
    checkpoint = next((tmp_path / "checkpoints").glob("*.json"))
    state = json.loads(checkpoint.read_text())
    assert "pagination_invariant_failed" in state["partitions"]["2026-08-24"]["reason"]


def test_request_template_is_reused_across_location_configurations(
    monkeypatch, tmp_path: Path
) -> None:
    scraper = _load_script()
    captures = 0

    def capture(*args, **kwargs):
        nonlocal captures
        captures += 1
        return {"template": "shared"}

    monkeypatch.setattr(scraper, "capture_template", capture)
    monkeypatch.setattr(
        scraper,
        "fetch_rows",
        lambda *args, **kwargs: {"status": 200, "login_redirect": False, "rows": [], "error": ""},
    )
    monkeypatch.setattr(scraper.time, "sleep", lambda _: None)
    template_cache: dict = {}
    for location_id in ("10", "11"):
        configuration = {
            **_configuration(),
            "location_id": location_id,
            "configuration_hash": f"{location_id:0>20}",
        }
        status, _ = scraper.scrape_configuration(
            page=object(),
            context=object(),
            credentials={},
            storage_path=tmp_path / "state.json",
            output_dir=tmp_path,
            configuration=configuration,
            dates=[date(2026, 8, 24)],
            direction="asc",
            template_date="2025-07-01",
            report=scraper.REPORTS["rentals"],
            delay_min=0,
            delay_max=0,
            request_limit=1,
            template_cache=template_cache,
        )
        assert status == "complete"

    assert captures == 1
