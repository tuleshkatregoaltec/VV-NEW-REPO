from datetime import UTC, date, datetime
import json
from pathlib import Path
from typing import Any

from holocron.contracts import RawRelease
from holocron.platform.checkpoints import checkpoint_s3_key
from holocron.sources import registry
from holocron.sources.dld_open_data_orchestration import (
    open_data_checkpoint_operation,
    resolve_open_data_config,
    write_open_data_checkpoint,
)
from holocron.sources.dld_open_data_shared import DldOpenDataConfig
from holocron.sources.dld_od_brokers.extract import (
    extract_release as extract_brokers_release,
)
from holocron.sources.dld_od_buildings.extract import (
    extract_release as extract_buildings_release,
)
from holocron.sources.dld_od_lands.extract import extract_release as extract_lands_release
from holocron.sources.dld_od_rents.extract import extract_release as extract_rents_release
from holocron.sources.dld_od_transactions.extract import (
    extract_release as extract_transactions_release,
)
from holocron.sources.dld_od_units.extract import extract_release as extract_units_release


class FakeDldOpenDataClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, str]]] = []

    def fetch(self, *, command: str, payload: dict[str, str]) -> dict:
        self.calls.append((command, dict(payload)))
        skip = int(payload["P_SKIP"])
        take = int(payload["P_TAKE"])
        rows = [
            {"RN": index + 1, "TOTAL": 3, "RENT_ID": f"rent-{index + 1}"}
            for index in range(skip, min(skip + take, 3))
        ]
        return {
            "responseCode": 200,
            "validationErrorsList": [],
            "response": {"result": rows},
        }


class FakeWindowDateClient:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.calls: list[tuple[str, dict[str, str]]] = []

    def fetch(self, *, command: str, payload: dict[str, str]) -> dict:
        self.calls.append((command, dict(payload)))
        return {
            "responseCode": 200,
            "validationErrorsList": [],
            "response": {"result": self.rows},
        }


class FakeCheckpointS3:
    def __init__(self) -> None:
        self.objects: dict[str, dict[str, Any]] = {}

    def get_json(self, *, key: str) -> dict[str, Any] | None:
        return self.objects.get(key)

    def put_json(self, *, key: str, payload: dict[str, Any]) -> None:
        self.objects[key] = payload


def _raw_dld_release(*, metadata: dict[str, Any]) -> RawRelease:
    return RawRelease(
        source="dld_od_transactions",
        run_id="run-1",
        extract_date="2026-05-06",
        created_at="2026-05-06T12:00:00+00:00",
        files=(),
        metadata=metadata,
    )


def test_dld_open_data_sources_are_registered() -> None:
    for source_name in (
        "dld_od_transactions",
        "dld_od_rents",
        "dld_od_projects",
        "dld_od_valuations",
        "dld_od_lands",
        "dld_od_buildings",
        "dld_od_units",
        "dld_od_brokers",
        "dld_od_developers",
    ):
        assert registry.get(source_name).name == source_name


def test_dld_pulse_historic_source_is_registered() -> None:
    assert registry.get("dld_pulse_historic").name == "dld_pulse_historic"


def test_dld_transactions_request_includes_end_date_without_storing_next_day(
    tmp_path: Path,
) -> None:
    api_client = FakeWindowDateClient(
        [
            {
                "RN": 1,
                "TOTAL": 2,
                "TRANSACTION_NUMBER": "same-day",
                "INSTANCE_DATE": "2026-06-14T12:00:00",
            },
            {
                "RN": 2,
                "TOTAL": 2,
                "TRANSACTION_NUMBER": "next-day",
                "INSTANCE_DATE": "2026-06-15T00:00:00",
            },
        ]
    )

    release = extract_transactions_release(
        tmp_path,
        config={
            "mode": "backfill",
            "start_date": "2026-06-14",
            "end_date": "2026-06-14",
            "checkpointed_incremental": True,
            "incremental_overlap_days": 7,
            "page_size": 10,
        },
        now=datetime(2026, 6, 14, 12, 0, tzinfo=UTC),
        api_client=api_client,
    )

    assert release.metadata["row_count"] == 1
    assert api_client.calls[0][1]["P_FROM_DATE"] == "06/14/2026"
    assert api_client.calls[0][1]["P_TO_DATE"] == "06/15/2026"
    rows_file = next(file for file in release.files if file.path.endswith("_rows.jsonl"))
    rows = [
        json.loads(line) for line in Path(rows_file.path).read_text(encoding="utf-8").splitlines()
    ]
    assert [row["raw"]["TRANSACTION_NUMBER"] for row in rows] == ["same-day"]


def test_dld_rents_registration_request_includes_end_date_without_storing_next_day(
    tmp_path: Path,
) -> None:
    api_client = FakeWindowDateClient(
        [
            {
                "RN": 1,
                "TOTAL": 2,
                "REGISTRATION_DATE": "2026-06-14T12:00:00",
            },
            {
                "RN": 2,
                "TOTAL": 2,
                "REGISTRATION_DATE": "2026-06-15T00:00:00",
            },
        ]
    )

    release = extract_rents_release(
        tmp_path,
        config={
            "mode": "backfill",
            "start_date": "2026-06-14",
            "end_date": "2026-06-14",
            "page_size": 10,
            "filters": {"P_DATE_TYPE": "3"},
            "row_date_field": "REGISTRATION_DATE",
            "request_to_date_offset_days": 1,
        },
        now=datetime(2026, 6, 14, 12, 0, tzinfo=UTC),
        api_client=api_client,
    )

    assert release.metadata["row_count"] == 1
    assert api_client.calls[0][1]["P_DATE_TYPE"] == "3"
    assert api_client.calls[0][1]["P_FROM_DATE"] == "06/14/2026"
    assert api_client.calls[0][1]["P_TO_DATE"] == "06/15/2026"


def test_checkpointed_incremental_uses_last_success_with_overlap(monkeypatch: Any) -> None:
    from holocron.sources import dld_open_data_orchestration as orchestration

    s3 = FakeCheckpointS3()
    s3.objects[
        checkpoint_s3_key(
            source="dld_od_rents",
            operation=open_data_checkpoint_operation("incremental"),
        )
    ] = {
        "mode": "incremental",
        "completed": True,
        "effective_end_date": "2026-06-10",
        "filters": {"P_DATE_TYPE": "3"},
        "sort": "",
    }
    monkeypatch.setattr(orchestration, "utc_now", lambda: datetime(2026, 6, 24, tzinfo=UTC))

    config = resolve_open_data_config(
        source_name="dld_od_rents",
        source_config={
            "mode": "incremental",
            "checkpointed_incremental": True,
            "lookback_days": 14,
            "incremental_overlap_days": 7,
            "filters": {"P_DATE_TYPE": "3"},
        },
        object_storage_client=s3,
    )

    assert config["start_date"] == "2026-06-03"
    assert config["end_date"] == "2026-06-24"
    assert config["checkpoint_explicit_date_window"] is False


def test_checkpointed_incremental_uses_lookback_without_checkpoint(monkeypatch: Any) -> None:
    from holocron.sources import dld_open_data_orchestration as orchestration

    monkeypatch.setattr(orchestration, "utc_now", lambda: datetime(2026, 6, 24, tzinfo=UTC))

    config = resolve_open_data_config(
        source_name="dld_od_rents",
        source_config={
            "mode": "incremental",
            "checkpointed_incremental": True,
            "lookback_days": 14,
            "incremental_overlap_days": 7,
        },
        object_storage_client=FakeCheckpointS3(),
    )

    assert config["start_date"] == "2026-06-10"
    assert config["end_date"] == "2026-06-24"


def test_dld_open_data_default_snapshot_checkpoint_resumes_effective_date_window() -> None:
    s3 = FakeCheckpointS3()
    s3.objects[
        checkpoint_s3_key(
            source="dld_od_transactions",
            operation=open_data_checkpoint_operation("snapshot"),
        )
    ] = {
        "mode": "snapshot",
        "completed": False,
        "next_window_index": 3,
        "next_skip": 20000,
        "start_date": "2026-01-01",
        "end_date": "2026-05-06",
        "explicit_date_window": False,
        "uses_date_windows": True,
        "effective_start_date": "2026-01-01",
        "effective_end_date": "2026-05-06",
        "slice_days": 366,
        "filters": {},
        "sort": "",
    }

    config = resolve_open_data_config(
        source_name="dld_od_transactions",
        source_config={
            "mode": "snapshot",
            "page_size": 10000,
            "max_pages": 1,
            "slice_days": 366,
        },
        object_storage_client=s3,
    )

    assert config["window_cursor"] == 3
    assert config["skip_cursor"] == 20000
    assert config["start_date"] == "2026-01-01"
    assert config["end_date"] == "2026-05-06"
    assert config["checkpoint_explicit_date_window"] is False


def test_dld_open_data_does_not_resume_date_window_checkpoint_without_effective_dates() -> None:
    s3 = FakeCheckpointS3()
    s3.objects[
        checkpoint_s3_key(
            source="dld_od_transactions",
            operation=open_data_checkpoint_operation("snapshot"),
        )
    ] = {
        "mode": "snapshot",
        "completed": False,
        "next_window_index": 3,
        "next_skip": 20000,
        "explicit_date_window": False,
        "uses_date_windows": True,
        "slice_days": 366,
        "filters": {},
        "sort": "",
    }

    config = resolve_open_data_config(
        source_name="dld_od_transactions",
        source_config={
            "mode": "snapshot",
            "page_size": 10000,
            "max_pages": 1,
            "slice_days": 366,
        },
        object_storage_client=s3,
    )

    assert "window_cursor" not in config
    assert "skip_cursor" not in config
    assert "start_date" not in config
    assert "end_date" not in config


def test_dld_open_data_default_snapshot_does_not_resume_explicit_date_checkpoint() -> None:
    s3 = FakeCheckpointS3()
    s3.objects[
        checkpoint_s3_key(
            source="dld_od_transactions",
            operation=open_data_checkpoint_operation("snapshot"),
        )
    ] = {
        "mode": "snapshot",
        "completed": False,
        "next_window_index": 3,
        "next_skip": 20000,
        "start_date": "2026-01-01",
        "end_date": "2026-05-06",
        "explicit_date_window": True,
        "slice_days": 366,
        "filters": {},
        "sort": "",
    }

    config = resolve_open_data_config(
        source_name="dld_od_transactions",
        source_config={
            "mode": "snapshot",
            "page_size": 10000,
            "max_pages": 1,
            "slice_days": 366,
        },
        object_storage_client=s3,
    )

    assert "window_cursor" not in config
    assert "skip_cursor" not in config


def test_dld_open_data_explicit_snapshot_dates_must_match_checkpoint() -> None:
    s3 = FakeCheckpointS3()
    s3.objects[
        checkpoint_s3_key(
            source="dld_od_transactions",
            operation=open_data_checkpoint_operation("snapshot"),
        )
    ] = {
        "mode": "snapshot",
        "completed": False,
        "next_window_index": 3,
        "next_skip": 20000,
        "start_date": "2026-01-01",
        "end_date": "2026-05-06",
        "slice_days": 366,
        "filters": {},
        "sort": "",
    }

    matching_config = resolve_open_data_config(
        source_name="dld_od_transactions",
        source_config={
            "mode": "snapshot",
            "start_date": "2026-01-01",
            "end_date": "2026-05-06",
            "slice_days": 366,
        },
        object_storage_client=s3,
    )
    mismatched_config = resolve_open_data_config(
        source_name="dld_od_transactions",
        source_config={
            "mode": "snapshot",
            "start_date": "2026-01-02",
            "end_date": "2026-05-06",
            "slice_days": 366,
        },
        object_storage_client=s3,
    )

    assert matching_config["window_cursor"] == 3
    assert matching_config["skip_cursor"] == 20000
    assert "window_cursor" not in mismatched_config
    assert "skip_cursor" not in mismatched_config


def test_dld_open_data_checkpoint_write_keeps_configured_and_effective_dates_separate() -> None:
    s3 = FakeCheckpointS3()

    write_open_data_checkpoint(
        raw_release=_raw_dld_release(
            metadata={
                "stage": "snapshot",
                "completed_result_set": False,
                "next_window_index": 3,
                "next_skip": 20000,
                "window_count": 4,
                "page_count": 50,
                "row_count": 500000,
                "effective_start_date": "2026-01-01",
                "effective_end_date": "2026-05-06",
                "config": {
                    "mode": "snapshot",
                    "slice_days": 366,
                    "filters": {},
                    "sort": "",
                },
            },
        ),
        manifest_key="raw/source=dld_od_transactions/manifests/run-1.json",
        object_storage_client=s3,
    )

    checkpoint = s3.objects[
        checkpoint_s3_key(
            source="dld_od_transactions",
            operation=open_data_checkpoint_operation("snapshot"),
        )
    ]
    assert checkpoint["start_date"] is None
    assert checkpoint["end_date"] is None
    assert checkpoint["explicit_date_window"] is False
    assert checkpoint["uses_date_windows"] is None
    assert checkpoint["effective_start_date"] == "2026-01-01"
    assert checkpoint["effective_end_date"] == "2026-05-06"
    assert checkpoint["next_window_index"] == 3
    assert checkpoint["next_skip"] == 20000


def test_dld_open_data_checkpoint_write_preserves_implicit_date_window_after_resume() -> None:
    s3 = FakeCheckpointS3()

    write_open_data_checkpoint(
        raw_release=_raw_dld_release(
            metadata={
                "stage": "snapshot",
                "completed_result_set": False,
                "next_window_index": 3,
                "next_skip": 20000,
                "window_count": 4,
                "page_count": 50,
                "row_count": 500000,
                "uses_date_windows": True,
                "explicit_date_window": False,
                "effective_start_date": "2026-01-01",
                "effective_end_date": "2026-05-06",
                "config": {
                    "mode": "snapshot",
                    "start_date": "2026-01-01",
                    "end_date": "2026-05-06",
                    "checkpoint_explicit_date_window": False,
                    "slice_days": 366,
                    "filters": {},
                    "sort": "",
                },
            },
        ),
        manifest_key="raw/source=dld_od_transactions/manifests/run-1.json",
        object_storage_client=s3,
    )

    checkpoint = s3.objects[
        checkpoint_s3_key(
            source="dld_od_transactions",
            operation=open_data_checkpoint_operation("snapshot"),
        )
    ]
    assert checkpoint["start_date"] == "2026-01-01"
    assert checkpoint["end_date"] == "2026-05-06"
    assert checkpoint["explicit_date_window"] is False
    assert checkpoint["uses_date_windows"] is True


def test_dld_open_data_date_backfill_paginates_rows(tmp_path: Path) -> None:
    api_client = FakeDldOpenDataClient()

    release = extract_rents_release(
        tmp_path,
        config=DldOpenDataConfig(
            mode="backfill",
            start_date=date(2026, 2, 9),
            end_date=date(2026, 2, 9),
            page_size=2,
        ),
        now=datetime(2026, 5, 6, 12, 0, tzinfo=UTC),
        api_client=api_client,
    )

    assert release.source == "dld_od_rents"
    assert release.metadata["row_count"] == 3
    assert release.metadata["page_count"] == 2
    assert release.metadata["effective_start_date"] == "2026-02-09"
    assert release.metadata["effective_end_date"] == "2026-02-09"
    assert {Path(file.path).name: file.row_count for file in release.files} == {
        "dld_od_rents_rows.jsonl": 3,
        "dld_od_rents_pages.jsonl": 2,
    }
    assert api_client.calls[0] == (
        "rents",
        {
            "P_DATE_TYPE": "1",
            "P_IS_FREE_HOLD": "",
            "P_VERSION": "",
            "P_AREA_ID": "",
            "P_USAGE_ID": "",
            "P_PROP_TYPE_ID": "",
            "P_FROM_DATE": "02/09/2026",
            "P_TO_DATE": "02/09/2026",
            "P_TAKE": "2",
            "P_SKIP": "0",
            "P_SORT": "REGISTRATION_DATE_DESC",
        },
    )
    assert api_client.calls[1][1]["P_SKIP"] == "2"


def test_dld_open_data_max_pages_returns_resume_cursor(tmp_path: Path) -> None:
    api_client = FakeDldOpenDataClient()

    release = extract_rents_release(
        tmp_path,
        config=DldOpenDataConfig(
            mode="backfill",
            start_date=date(2026, 2, 9),
            end_date=date(2026, 2, 10),
            page_size=2,
            max_pages=1,
        ),
        now=datetime(2026, 5, 6, 12, 0, tzinfo=UTC),
        api_client=api_client,
    )

    assert release.metadata["completed_result_set"] is False
    assert release.metadata["window_count"] == 2
    assert release.metadata["next_window_index"] == 0
    assert release.metadata["next_skip"] == 2


def test_dld_open_data_inventory_sources_support_incremental_windows(tmp_path: Path) -> None:
    extractors = (
        ("lands", extract_lands_release),
        ("units", extract_units_release),
        ("brokers", extract_brokers_release),
    )

    for command, extractor in extractors:
        api_client = FakeDldOpenDataClient()

        release = extractor(
            tmp_path / command,
            config={
                "mode": "incremental",
                "lookback_days": 1,
                "slice_days": 2,
                "page_size": 2,
                "max_pages": 1,
            },
            now=datetime(2026, 5, 6, 12, 0, tzinfo=UTC),
            api_client=api_client,
        )

        assert release.source == f"dld_od_{command}"
        request = api_client.calls[0][1]
        assert request["P_FROM_DATE"] == "05/05/2026"
        assert request["P_TO_DATE"] == "05/06/2026"


def test_dld_open_data_snapshot_source_omits_date_filters(tmp_path: Path) -> None:
    api_client = FakeDldOpenDataClient()

    release = extract_lands_release(
        tmp_path,
        config={"mode": "snapshot", "page_size": 2, "max_pages": 1},
        now=datetime(2026, 5, 6, 12, 0, tzinfo=UTC),
        api_client=api_client,
    )

    assert release.source == "dld_od_lands"
    assert release.metadata["page_count"] == 1
    assert release.metadata["uses_date_windows"] is False
    assert release.metadata["effective_start_date"] is None
    assert release.metadata["effective_end_date"] is None
    request = api_client.calls[0][1]
    assert "P_FROM_DATE" not in request
    assert "P_TO_DATE" not in request
    assert request["P_SORT"] == "AREA_EN_ASC"


def test_dld_open_data_optional_date_snapshot_sends_blank_date_filters(tmp_path: Path) -> None:
    api_client = FakeDldOpenDataClient()

    release = extract_buildings_release(
        tmp_path,
        config={"mode": "snapshot", "page_size": 2, "max_pages": 1},
        now=datetime(2026, 5, 6, 12, 0, tzinfo=UTC),
        api_client=api_client,
    )

    assert release.source == "dld_od_buildings"
    request = api_client.calls[0][1]
    assert request["P_FROM_DATE"] == ""
    assert request["P_TO_DATE"] == ""
