from __future__ import annotations

import json
from dataclasses import dataclass

from holocron.platform.hydration import (
    hydrate_assets_in_order,
    partition_hydration_assets_by_existing,
    parse_jsonl_text,
    select_manifest_keys,
)


@dataclass(frozen=True, slots=True)
class PlannedAsset:
    target_key: str
    status: str | None = None


def test_partition_hydration_assets_skips_existing_before_limit() -> None:
    assets = [
        PlannedAsset("existing-1"),
        PlannedAsset("existing-2"),
        PlannedAsset("missing-1"),
        PlannedAsset("missing-2"),
    ]

    selected, skipped = partition_hydration_assets_by_existing(
        planned_assets=assets,
        object_exists={"existing-1", "existing-2"}.__contains__,
        overwrite_existing=False,
        max_assets_per_run=2,
    )

    assert selected == [PlannedAsset("missing-1"), PlannedAsset("missing-2")]
    assert len(skipped) == 2


def test_partition_hydration_assets_keeps_error_rows_and_overwrite_targets() -> None:
    assets = [
        PlannedAsset("existing", status="validation_error"),
        PlannedAsset("existing"),
    ]

    selected, skipped = partition_hydration_assets_by_existing(
        planned_assets=assets,
        object_exists={"existing"}.__contains__,
        overwrite_existing=True,
        max_assets_per_run=10,
    )

    assert selected == assets
    assert len(skipped) == 0


def test_select_manifest_keys_limits_latest_sorted_keys() -> None:
    keys = select_manifest_keys(
        listed_keys=(
            "raw/source=demo/manifests/2026-05-05T00-00-00Z.json",
            "raw/source=demo/manifests/2026-05-07T00-00-00Z.json",
            "raw/source=demo/manifests/2026-05-06T00-00-00Z.json",
        ),
        latest_count=2,
    )

    assert keys == (
        "raw/source=demo/manifests/2026-05-06T00-00-00Z.json",
        "raw/source=demo/manifests/2026-05-07T00-00-00Z.json",
    )


def test_select_manifest_keys_prefers_explicit_keys() -> None:
    keys = select_manifest_keys(
        listed_keys=("raw/source=demo/manifests/latest.json",),
        explicit_keys=("raw/source=demo/manifests/explicit.json",),
    )

    assert keys == ("raw/source=demo/manifests/explicit.json",)


def test_parse_jsonl_text_preserves_json_string_line_separators() -> None:
    line_separator = chr(0x2028)
    text = (
        json.dumps({"description": f"first{line_separator}second"}, ensure_ascii=False)
        + "\n"
        + json.dumps({"description": "third"})
        + "\n"
    )

    rows = parse_jsonl_text(text=text, source_key="raw/demo.jsonl", row_label="demo row")

    assert rows == [
        (1, {"description": f"first{line_separator}second"}),
        (2, {"description": "third"}),
    ]


def test_hydrate_assets_in_order_records_single_worker_failures() -> None:
    def hydrate_one(_index: int, _asset: PlannedAsset) -> dict[str, object]:
        raise RuntimeError("boom")

    rows = hydrate_assets_in_order(
        planned_assets=[PlannedAsset("asset-1")],
        worker_count=1,
        thread_name_prefix="test",
        hydrate_one=hydrate_one,
        failure_row=lambda index, asset, exc: {
            "index": index,
            "target_key": asset.target_key,
            "status": "download_error",
            "error": str(exc),
        },
    )

    assert rows == [
        {
            "index": 1,
            "target_key": "asset-1",
            "status": "download_error",
            "error": "boom",
        }
    ]
