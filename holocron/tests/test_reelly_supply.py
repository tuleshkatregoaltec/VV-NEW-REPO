from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from dagster import Failure

from holocron.contracts import RawRelease
from holocron.orchestration.factory import _raw_release_file_path
from holocron.platform.checkpoints import checkpoint_s3_key
from holocron.sources import REELLY_SUPPLY_SOURCE, registry
from holocron.sources.reelly_supply.orchestration import (
    resolve_archive_config,
    write_archive_checkpoint,
)
from holocron.sources.reelly_supply.extract import (
    DocumentDownload,
    _fingerprint_payload,
    _has_matrix_signal,
    _matrix_candidates,
    _matrix_payload_error,
    _validate_document_url,
    extract_release,
)
from holocron.sources.reelly_supply.source import ReellySupplyConfig


class FakeReellyApi:
    def __init__(
        self,
        *,
        page_total: int = 10,
        items_by_page: dict[int, list[dict[str, Any]]] | None = None,
        details: dict[Any, dict[str, Any]] | None = None,
        documents: dict[Any, dict[str, Any] | list[Any] | Exception] | None = None,
        downloads: dict[str, bytes | Exception] | None = None,
        matrix_responses: dict[tuple[str, Any], dict[str, Any] | Exception] | None = None,
        matrix_errors: bool = False,
    ) -> None:
        self.page_total = page_total
        self.items_by_page = items_by_page or {}
        self.details = details or {}
        self.documents = documents or {}
        self.downloads = downloads or {}
        self.matrix_responses = matrix_responses or {}
        self.matrix_errors = matrix_errors
        self.auth_calls: list[tuple[str, str]] = []
        self.current_user_calls = 0
        self.list_calls: list[tuple[int, str, tuple[str, ...], Any | None]] = []
        self.detail_calls: list[Any] = []
        self.document_calls: list[Any] = []
        self.download_calls: list[str] = []
        self.matrix_calls: list[tuple[str, Any]] = []

    def authenticate(self, *, email: str, password: str) -> dict[str, Any]:
        self.auth_calls.append((email, password))
        return {"authToken": "token"}

    def current_user(self) -> dict[str, Any]:
        self.current_user_calls += 1
        return {"id": 777}

    def fetch_project_list(
        self,
        *,
        page: int,
        region: str,
        sale_statuses: tuple[str, ...],
        user_id: Any | None,
    ) -> dict[str, Any]:
        self.list_calls.append((page, region, sale_statuses, user_id))
        items = self.items_by_page.get(page, [{"id": page, "Project_name": f"Project {page}"}])
        return {"items": items, "pageTotal": self.page_total, "itemsTotal": self.page_total}

    def fetch_project_detail(self, *, project_id: Any, user_id: Any | None) -> dict[str, Any]:
        self.detail_calls.append(project_id)
        return self.details.get(
            project_id, {"id": project_id, "Project_name": f"Project {project_id}"}
        )

    def fetch_project_documents(self, *, project_id: Any) -> dict[str, Any] | list[Any]:
        self.document_calls.append(project_id)
        payload = self.documents.get(project_id, {"Links_Docs": []})
        if isinstance(payload, Exception):
            raise payload
        return payload

    def fetch_matrix_availability(self, *, endpoint: str, identifier: Any) -> dict[str, Any]:
        self.matrix_calls.append((endpoint, identifier))
        if self.matrix_errors:
            raise RuntimeError("matrix unavailable")
        payload = self.matrix_responses.get((endpoint, identifier))
        if isinstance(payload, Exception):
            raise payload
        if payload is not None:
            return payload
        return {"endpoint": endpoint, "identifier": identifier, "units": []}

    def download_document(self, url: str, *, max_bytes: int) -> DocumentDownload:
        self.download_calls.append(url)
        payload = self.downloads.get(url, b"document")
        if isinstance(payload, Exception):
            raise payload
        assert len(payload) <= max_bytes
        final_url = url.replace("vault.reelly.test", "cdn.reelly.test")
        return DocumentDownload(
            content=payload, content_type="application/pdf", final_url=final_url
        )


class FakeCheckpointS3:
    def __init__(self) -> None:
        self.objects: dict[str, dict[str, Any]] = {}

    def get_json(self, *, key: str) -> dict[str, Any] | None:
        return self.objects.get(key)

    def put_json(self, *, key: str, payload: dict[str, Any]) -> None:
        self.objects[key] = payload


def test_reelly_supply_source_is_registered() -> None:
    assert registry.get("reelly_supply") is REELLY_SUPPLY_SOURCE


def test_reelly_supply_config_defaults_to_bounded_daily_batch() -> None:
    config = ReellySupplyConfig()

    assert config.region == "2"
    assert config.sale_statuses == ("start_of_sales", "on_sale", "out_of_stock")
    assert config.pages_per_run == 5
    assert config.start_page == 1
    assert config.page_cursor is None
    assert config.max_pages is None
    assert config.download_documents is False
    assert config.download_all_project_docs is True
    assert config.max_document_mb == 100
    assert "api.reelly.io" in config.allowed_document_hosts
    assert "drive.google.com" in config.allowed_document_hosts
    assert "storage.googleapis.com" in config.allowed_document_hosts
    assert config.try_matrix_availability is True


def test_reelly_supply_config_accepts_comma_separated_sale_statuses() -> None:
    config = ReellySupplyConfig.model_validate({"sale_statuses": "start_of_sales,on_sale"})

    assert config.sale_statuses == ("start_of_sales", "on_sale")


def test_reelly_document_url_validation_allows_https_allowlisted_hosts() -> None:
    normalized = _validate_document_url(
        "https://drive.google.com/file/d/google-file-id/view?usp=sharing",
        allowed_hosts=("drive.google.com",),
    )

    assert normalized == "https://drive.google.com/uc?export=download&id=google-file-id"


def test_reelly_document_url_validation_rejects_http() -> None:
    with pytest.raises(ValueError, match="https"):
        _validate_document_url(
            "http://drive.google.com/file.pdf",
            allowed_hosts=("drive.google.com",),
        )


def test_reelly_document_url_validation_rejects_embedded_credentials() -> None:
    with pytest.raises(ValueError, match="credentials"):
        _validate_document_url(
            "https://user:pass@drive.google.com/file.pdf",
            allowed_hosts=("drive.google.com",),
        )


@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1/file.pdf",
        "https://10.0.0.1/file.pdf",
        "https://169.254.169.254/latest/meta-data/",
    ],
)
def test_reelly_document_url_validation_rejects_unsafe_ip_targets(url: str) -> None:
    host = url.split("/", 3)[2]

    with pytest.raises(ValueError, match="unsafe IP"):
        _validate_document_url(url, allowed_hosts=(host,))


def test_reelly_document_url_validation_rejects_unsafe_final_redirect_targets() -> None:
    with pytest.raises(ValueError, match="unsafe IP"):
        _validate_document_url(
            "https://169.254.169.254/latest/meta-data/",
            allowed_hosts=("169.254.169.254",),
        )


def test_raw_release_file_path_preserves_document_subdirectories(tmp_path: Path) -> None:
    document_path = tmp_path / "documents" / "501" / "brochure.pdf"
    document_path.parent.mkdir(parents=True)
    document_path.write_bytes(b"document")

    assert _raw_release_file_path(scratch_path=tmp_path, local_path=document_path) == (
        "documents/501/brochure.pdf"
    )


def test_reelly_archive_checkpoint_starts_without_cursor_when_empty() -> None:
    s3 = FakeCheckpointS3()

    config = resolve_archive_config(source_config={}, object_storage_client=s3)

    assert "page_cursor" not in config


def test_reelly_archive_checkpoint_resumes_from_next_page() -> None:
    s3 = FakeCheckpointS3()
    s3.objects[checkpoint_s3_key(source="reelly_supply", operation="archive_chunk")] = {
        "next_page": 6,
        "completed": False,
    }

    config = resolve_archive_config(source_config={}, object_storage_client=s3)

    assert config["page_cursor"] == 6


def test_reelly_archive_checkpoint_write_advances_cursor_and_marks_completion() -> None:
    s3 = FakeCheckpointS3()

    write_archive_checkpoint(
        raw_release=_raw_reelly_release(
            run_id="run-1",
            metadata={
                "next_page": 11,
                "page_total": 20,
                "batch_completed_result_set": False,
            },
        ),
        manifest_key="raw/source=reelly_supply/manifests/run-1.json",
        object_storage_client=s3,
    )
    checkpoint = s3.objects[checkpoint_s3_key(source="reelly_supply", operation="archive_chunk")]

    assert checkpoint["next_page"] == 11
    assert checkpoint["completed"] is False
    assert checkpoint["last_run_id"] == "run-1"
    assert checkpoint["last_manifest_s3_key"] == "raw/source=reelly_supply/manifests/run-1.json"
    assert checkpoint["page_total"] == 20
    assert checkpoint["updated_at"]

    write_archive_checkpoint(
        raw_release=_raw_reelly_release(
            run_id="run-2",
            metadata={
                "next_page": 1,
                "page_total": 20,
                "batch_completed_result_set": True,
            },
        ),
        manifest_key="raw/source=reelly_supply/manifests/run-2.json",
        object_storage_client=s3,
    )
    checkpoint = s3.objects[checkpoint_s3_key(source="reelly_supply", operation="archive_chunk")]

    assert checkpoint["next_page"] == 1
    assert checkpoint["completed"] is True
    assert checkpoint["last_run_id"] == "run-2"


def test_reelly_archive_checkpoint_blocks_completed_rerun_unless_reset() -> None:
    s3 = FakeCheckpointS3()
    s3.objects[checkpoint_s3_key(source="reelly_supply", operation="archive_chunk")] = {
        "next_page": 1,
        "completed": True,
    }

    with pytest.raises(Failure, match="checkpoint is already completed"):
        resolve_archive_config(source_config={}, object_storage_client=s3)

    config = resolve_archive_config(
        source_config={"reset_checkpoint": True},
        object_storage_client=s3,
    )
    assert "page_cursor" not in config
    assert "reset_checkpoint" not in config


def test_reelly_supply_extract_authenticates_and_loads_current_user(tmp_path: Path) -> None:
    api_client = FakeReellyApi(page_total=1)

    extract_release(
        tmp_path,
        config=ReellySupplyConfig(email="agent@example.com", password="secret", pages_per_run=1),
        now=datetime(2026, 5, 2, 16, 0, tzinfo=UTC),
        api_client=api_client,
    )

    assert api_client.auth_calls == [("agent@example.com", "secret")]
    assert api_client.current_user_calls == 1
    assert api_client.list_calls[0][-1] == 777


def test_reelly_supply_default_fetches_five_list_pages(tmp_path: Path) -> None:
    api_client = FakeReellyApi(page_total=10)

    release = extract_release(
        tmp_path,
        config=ReellySupplyConfig(email="agent@example.com", password="secret"),
        now=datetime(2026, 5, 2, 16, 0, tzinfo=UTC),
        api_client=api_client,
    )

    assert [call[0] for call in api_client.list_calls] == [1, 2, 3, 4, 5]
    assert release.metadata["start_page"] == 1
    assert release.metadata["end_page"] == 5
    assert release.metadata["next_page"] == 6
    assert release.metadata["page_total"] == 10
    assert release.metadata["batch_completed_result_set"] is False


def test_reelly_catalog_delta_bootstrap_fetches_list_only_and_writes_state(
    tmp_path: Path,
) -> None:
    api_client = FakeReellyApi(
        page_total=1,
        items_by_page={1: [{"id": 101, "Project_name": "One"}]},
    )

    release = extract_release(
        tmp_path,
        config=ReellySupplyConfig(
            mode="catalog_delta",
            pages_per_run=10,
            download_documents=False,
            try_matrix_availability=False,
        ),
        now=datetime(2026, 5, 2, 16, 0, tzinfo=UTC),
        api_client=api_client,
        state_store=FakeCheckpointS3(),
    )

    assert [call[0] for call in api_client.list_calls] == [1]
    assert api_client.detail_calls == []
    assert api_client.document_calls == []
    assert release.metadata["mode"] == "catalog_delta"
    assert release.metadata["selected_project_count"] == 0
    state_update = release.metadata["_state_updates"][0]
    state = json.loads(Path(state_update["path"]).read_text(encoding="utf-8"))
    assert state["projects"]["101"]["list_item"]["Project_name"] == "One"


def test_reelly_catalog_delta_fetches_only_new_and_changed_project_details(
    tmp_path: Path,
) -> None:
    unchanged = {"id": 101, "Project_name": "One"}
    changed = {"id": 102, "Project_name": "Two changed"}
    s3 = FakeCheckpointS3()
    s3.objects[ReellySupplyConfig().catalog_state_key] = {
        "version": 1,
        "projects": {
            "101": {"list_fingerprint": _fingerprint_payload(unchanged)},
            "102": {"list_fingerprint": "old"},
        },
    }
    api_client = FakeReellyApi(
        page_total=1,
        items_by_page={1: [unchanged, changed, {"id": 103, "Project_name": "Three"}]},
        details={
            102: {"id": 102, "Project_name": "Two changed", "Last_Modified": "2026-05-02"},
            103: {"id": 103, "Project_name": "Three", "Last_Modified": "2026-05-02"},
        },
    )

    release = extract_release(
        tmp_path,
        config=ReellySupplyConfig(
            mode="catalog_delta",
            pages_per_run=1,
            detail_audit_limit=0,
            fetch_documents_for_delta=False,
            try_matrix_availability=False,
        ),
        now=datetime(2026, 5, 2, 16, 0, tzinfo=UTC),
        api_client=api_client,
        state_store=s3,
    )

    assert api_client.detail_calls == [102, 103]
    assert api_client.document_calls == []
    assert release.metadata["delta_reason_counts"] == {
        "unchanged": 1,
        "list_changed": 1,
        "new": 1,
    }


def test_reelly_availability_delta_uses_catalog_state_without_project_list_or_details(
    tmp_path: Path,
) -> None:
    s3 = FakeCheckpointS3()
    s3.objects[ReellySupplyConfig().catalog_state_key] = {
        "version": 1,
        "projects": {
            "101": {
                "project_id": 101,
                "project_availability_id": "avail-101",
                "list_item": {"id": 101, "project_availability_id": "avail-101"},
            },
            "102": {"project_id": 102, "list_item": {"id": 102}},
        },
    }
    api_client = FakeReellyApi(
        matrix_responses={
            ("floors", "avail-101"): {"availability": [], "building": {"id": "avail-101"}}
        }
    )

    release = extract_release(
        tmp_path,
        config=ReellySupplyConfig(
            mode="availability_delta",
            matrix_endpoints=("floors",),
        ),
        now=datetime(2026, 5, 2, 16, 0, tzinfo=UTC),
        api_client=api_client,
        state_store=s3,
    )

    assert api_client.list_calls == []
    assert api_client.detail_calls == []
    assert api_client.matrix_calls == [("floors", "avail-101")]
    assert release.metadata["candidate_project_count"] == 1
    assert release.metadata["matrix_attempt_count"] == 1


def test_reelly_supply_cursor_metadata_wraps_after_last_page(tmp_path: Path) -> None:
    api_client = FakeReellyApi(page_total=10)

    release = extract_release(
        tmp_path,
        config=ReellySupplyConfig(
            email="agent@example.com",
            password="secret",
            page_cursor=9,
            pages_per_run=3,
        ),
        now=datetime(2026, 5, 2, 16, 0, tzinfo=UTC),
        api_client=api_client,
    )

    assert [call[0] for call in api_client.list_calls] == [9, 10]
    assert release.metadata["start_page"] == 9
    assert release.metadata["end_page"] == 10
    assert release.metadata["next_page"] == 1
    assert release.metadata["batch_completed_result_set"] is True


def test_reelly_supply_hydrates_each_project_once(tmp_path: Path) -> None:
    api_client = FakeReellyApi(
        page_total=2,
        items_by_page={
            1: [{"id": 101}, {"id": 102}],
            2: [{"id": 101}, {"id": 103}],
        },
    )

    release = extract_release(
        tmp_path,
        config=ReellySupplyConfig(
            email="agent@example.com",
            password="secret",
            pages_per_run=2,
            download_documents=False,
            try_matrix_availability=False,
        ),
        now=datetime(2026, 5, 2, 16, 0, tzinfo=UTC),
        api_client=api_client,
    )

    assert api_client.detail_calls == [101, 102, 103]
    assert release.metadata["project_count"] == 4
    assert release.metadata["project_detail_count"] == 3


def test_reelly_supply_discovers_and_downloads_project_documents(tmp_path: Path) -> None:
    google_url = "https://drive.google.com/file/d/google-file-id/view?usp=sharing"
    xano_url = "https://vault.reelly.test/path/floor-plan.pdf"
    bad_url = "https://docs.reelly.test/bad.pdf"
    api_client = FakeReellyApi(
        page_total=1,
        items_by_page={1: [{"id": 501}]},
        details={
            501: {
                "id": 501,
                "Project_name": "Project 501",
                "Brochure": google_url,
                "files": [{"name": "Floor plan", "url": xano_url}],
            }
        },
        documents={501: {"Links_Docs": [{"name": "Bad PDF", "url": bad_url}]}},
        downloads={
            "https://drive.google.com/uc?export=download&id=google-file-id": b"brochure",
            xano_url: b"floor",
            bad_url: RuntimeError("download failed"),
        },
    )

    release = extract_release(
        tmp_path,
        config=ReellySupplyConfig(
            email="agent@example.com",
            password="secret",
            pages_per_run=1,
            download_documents=True,
            allowed_document_hosts=(
                "api.reelly.io",
                "drive.google.com",
                "vault.reelly.test",
                "docs.reelly.test",
                "cdn.reelly.test",
            ),
        ),
        now=datetime(2026, 5, 2, 16, 0, tzinfo=UTC),
        api_client=api_client,
    )

    rows = _read_jsonl(tmp_path / "reelly_supply_project_documents.jsonl")

    assert len(rows) == 3
    assert {row["status"] for row in rows} == {"downloaded", "download_error"}
    assert "https://drive.google.com/uc?export=download&id=google-file-id" in {
        row["normalized_url"] for row in rows
    }
    downloaded_paths = {row.get("downloaded_path") for row in rows if row["status"] == "downloaded"}
    assert all(path and path.startswith("documents/501/") for path in downloaded_paths)
    assert any(Path(file.path).parent.name == "501" for file in release.files)


def test_reelly_supply_records_invalid_project_document_urls(tmp_path: Path) -> None:
    api_client = FakeReellyApi(
        page_total=1,
        items_by_page={1: [{"id": 501}]},
        details={
            501: {
                "id": 501,
                "Project_name": "Project 501",
                "Brochure": "https://evil.reelly.test/brochure.pdf",
            }
        },
    )

    extract_release(
        tmp_path,
        config=ReellySupplyConfig(
            email="agent@example.com",
            password="secret",
            pages_per_run=1,
            try_matrix_availability=False,
            allowed_document_hosts=("drive.google.com",),
        ),
        now=datetime(2026, 5, 2, 16, 0, tzinfo=UTC),
        api_client=api_client,
    )

    rows = _read_jsonl(tmp_path / "reelly_supply_project_documents.jsonl")

    assert len(rows) == 1
    assert rows[0]["status"] == "validation_error"
    assert rows[0]["normalized_url"] == ""
    assert rows[0]["error"] == "document host is not allowlisted: evil.reelly.test"
    assert api_client.download_calls == []


def test_reelly_supply_records_matrix_failures_without_failing(tmp_path: Path) -> None:
    api_client = FakeReellyApi(
        page_total=1,
        items_by_page={1: [{"id": 701}]},
        details={
            701: {
                "id": 701,
                "Project_name": "Matrix Project",
                "project_availability_id": "matrix-project",
                "project_api": "matrix-api",
                "units_in_sale": 4,
            }
        },
        matrix_errors=True,
    )

    release = extract_release(
        tmp_path,
        config=ReellySupplyConfig(email="agent@example.com", password="secret", pages_per_run=1),
        now=datetime(2026, 5, 2, 16, 0, tzinfo=UTC),
        api_client=api_client,
    )

    rows = _read_jsonl(tmp_path / "reelly_supply_matrix_availability.jsonl")

    assert release.source == "reelly_supply"
    assert api_client.matrix_calls
    assert rows
    assert {row["status"] for row in rows} == {"error"}


def test_reelly_supply_records_matrix_api_error_payloads_without_fallback(tmp_path: Path) -> None:
    api_client = FakeReellyApi(
        page_total=1,
        items_by_page={1: [{"id": 701}]},
        details={
            701: {
                "id": 701,
                "Project_name": "Matrix Project",
                "project_availability_id": "bad-matrix-id",
                "project_api": "ignored-matrix-id",
                "units_in_sale": 4,
            }
        },
        matrix_responses={
            (
                "floors",
                "bad-matrix-id",
            ): {
                "building": "[Line 2:Char 15] r.filter is not a function",
                "availability": "[Line 2:Char 15] t.filter is not a function",
            },
            ("floors", "ignored-matrix-id"): {"building": [], "availability": []},
        },
    )

    extract_release(
        tmp_path,
        config=ReellySupplyConfig(
            email="agent@example.com",
            password="secret",
            pages_per_run=1,
            matrix_endpoints=("floors",),
        ),
        now=datetime(2026, 5, 2, 16, 0, tzinfo=UTC),
        api_client=api_client,
    )

    rows = _read_jsonl(tmp_path / "reelly_supply_matrix_availability.jsonl")

    assert [call[1] for call in api_client.matrix_calls] == ["bad-matrix-id"]
    assert [row["status"] for row in rows] == ["api_error"]
    assert "not a function" in rows[0]["error"]


def test_reelly_matrix_signal_and_candidates_only_use_availability_id() -> None:
    project = {
        "Project_name": "No Matrix Project",
        "project_availability_id": "0",
        "project_api": "matrix-api",
        "units_in_sale": 4,
    }

    assert _has_matrix_signal(project) is False

    project["project_availability_id"] = "matrix-availability-id"

    assert _has_matrix_signal(project) is True
    assert _matrix_candidates(project_id=701, project=project) == ["matrix-availability-id"]


def test_reelly_matrix_payload_error_detects_xano_script_error_strings() -> None:
    error = _matrix_payload_error(
        {
            "building": "[Line 2:Char 15] r.filter is not a function",
            "availability": "[Line 2:Char 15] Cannot read properties of undefined",
        }
    )

    assert "building" in error
    assert "availability" in error


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _raw_reelly_release(*, run_id: str, metadata: dict[str, Any]) -> RawRelease:
    return RawRelease(
        source="reelly_supply",
        run_id=run_id,
        extract_date="2026-05-02",
        created_at="2026-05-02T16:00:00+00:00",
        files=(),
        metadata=metadata,
    )
