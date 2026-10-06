from __future__ import annotations

import hashlib
import json
import time
from datetime import UTC, datetime
from typing import Any

from holocron.sources.reelly_supply.document_assets import (
    ReellyDocumentAssetHydrationConfig,
    _load_manifest_asset_rows,
    _load_manifest_document_rows,
    _plan_document_assets,
    _target_key,
    hydrate_reelly_document_assets,
)
from holocron.sources.reelly_supply.extract import DocumentDownload, DocumentTooLargeError
from tests.fakes import FakeS3, _jsonl_bytes


class FakeDownloader:
    def __init__(
        self,
        downloads: dict[str, bytes | Exception],
        *,
        delays: dict[str, float] | None = None,
    ) -> None:
        self.downloads = downloads
        self.delays = delays or {}
        self.calls: list[str] = []

    def download_document(self, url: str, *, max_bytes: int) -> DocumentDownload:
        self.calls.append(url)
        if delay_seconds := self.delays.get(url):
            time.sleep(delay_seconds)
        payload = self.downloads.get(url, b"document")
        if isinstance(payload, Exception):
            raise payload
        assert len(payload) <= max_bytes
        return DocumentDownload(content=payload, content_type="application/pdf", final_url=url)


def test_reelly_document_asset_loads_document_rows_from_raw_manifests() -> None:
    s3 = FakeS3()
    rows = [
        {
            "project_id": 501,
            "name": "Brochure",
            "url": "https://vault.reelly.test/brochure.pdf",
        }
    ]
    manifest_key, document_key = _put_manifest(s3, run_id="run-1", rows=rows)

    loaded_rows = _load_manifest_document_rows(
        s3=s3,
        manifest_prefix="raw/source=reelly_supply/manifests/",
    )

    assert len(loaded_rows) == 1
    assert loaded_rows[0].source_manifest_key == manifest_key
    assert loaded_rows[0].source_document_key == document_key
    assert loaded_rows[0].source_file_name == "reelly_supply_project_documents.jsonl"
    assert loaded_rows[0].source_manifest_run_id == "run-1"
    assert loaded_rows[0].line_number == 1
    assert loaded_rows[0].row == rows[0]


def test_reelly_document_asset_dedupes_project_and_normalized_url_across_manifests() -> None:
    s3 = FakeS3()
    _put_manifest(
        s3,
        run_id="run-1",
        rows=[
            {
                "project_id": "501",
                "name": "Brochure",
                "url": "https://drive.google.com/file/d/google-file-id/view?usp=sharing",
            }
        ],
    )
    _put_manifest(
        s3,
        run_id="run-2",
        rows=[
            {
                "project_id": "501",
                "name": "Duplicate brochure",
                "normalized_url": "https://drive.google.com/uc?export=download&id=google-file-id",
            }
        ],
    )

    source_rows = _load_manifest_document_rows(
        s3=s3,
        manifest_prefix="raw/source=reelly_supply/manifests/",
    )
    planned = _plan_document_assets(
        source_rows,
        config=ReellyDocumentAssetHydrationConfig(allowed_document_hosts=("drive.google.com",)),
    )

    assert len(source_rows) == 2
    assert len(planned) == 1
    assert planned[0].normalized_url == (
        "https://drive.google.com/uc?export=download&id=google-file-id"
    )


def test_reelly_document_asset_target_key_is_deterministic_and_safe() -> None:
    normalized_url = "https://vault.reelly.test/files/floor-plan.pdf"
    expected_hash = hashlib.sha256(normalized_url.encode("utf-8")).hexdigest()

    key = _target_key(
        target_prefix="media/reelly_supply/documents",
        project_id="Project 501 / A",
        normalized_url=normalized_url,
        name="Floor Plan 2026",
    )

    assert key == (
        "media/reelly_supply/documents/"
        f"project_id=Project_501_A/{expected_hash}/Floor_Plan_2026.pdf"
    )


def test_reelly_document_asset_skips_existing_objects_when_overwrite_is_false() -> None:
    s3 = FakeS3()
    url = "https://vault.reelly.test/files/existing.pdf"
    existing_key = _target_key(
        target_prefix="media/reelly_supply/documents",
        project_id="501",
        normalized_url=url,
        name="Existing",
    )
    s3.put_bytes(key=existing_key, payload=b"existing", content_type="application/pdf")
    _put_manifest(
        s3,
        run_id="run-1",
        rows=[{"project_id": "501", "name": "Existing", "url": url}],
    )
    downloader = FakeDownloader({url: b"replacement"})

    result = hydrate_reelly_document_assets(
        s3=s3,
        config=ReellyDocumentAssetHydrationConfig(
            allowed_document_hosts=("vault.reelly.test",),
            overwrite_existing=False,
        ),
        now=datetime(2026, 5, 3, 12, 0, tzinfo=UTC),
        download_client=downloader,
    )
    inventory_rows = _inventory_rows(s3, result["inventory_manifest_key"])

    assert downloader.calls == []
    assert s3.objects[existing_key] == b"existing"
    assert len(inventory_rows) == 1
    assert inventory_rows[0]["status"] == "already_exists"
    assert result["skipped_existing"] == 1


def test_reelly_document_asset_inventory_records_success_and_failures() -> None:
    s3 = FakeS3()
    success_url = "https://vault.reelly.test/files/success.pdf"
    existing_url = "https://vault.reelly.test/files/existing.pdf"
    fail_url = "https://vault.reelly.test/files/fail.pdf"
    large_url = "https://vault.reelly.test/files/large.pdf"
    existing_key = _target_key(
        target_prefix="media/reelly_supply/documents",
        project_id="already",
        normalized_url=existing_url,
        name="Existing",
    )
    s3.put_bytes(key=existing_key, payload=b"existing", content_type="application/pdf")
    _put_manifest(
        s3,
        run_id="run-1",
        rows=[
            {"project_id": "ok", "name": "Success", "url": success_url},
            {"project_id": "already", "name": "Existing", "url": existing_url},
            {"project_id": "bad", "name": "Invalid", "url": "https://bad.example.test/doc.pdf"},
            {"project_id": "missing", "name": "Missing"},
            {"project_id": "fail", "name": "Fail", "url": fail_url},
            {"project_id": "large", "name": "Large", "url": large_url},
        ],
    )
    downloader = FakeDownloader(
        {
            success_url: b"success",
            fail_url: RuntimeError("download failed"),
            large_url: DocumentTooLargeError("document exceeds max size of 10 bytes"),
        }
    )

    result = hydrate_reelly_document_assets(
        s3=s3,
        config=ReellyDocumentAssetHydrationConfig(
            allowed_document_hosts=("vault.reelly.test",),
            max_assets_per_run=10,
            max_document_mb=1,
        ),
        now=datetime(2026, 5, 3, 12, 0, tzinfo=UTC),
        download_client=downloader,
    )
    inventory_rows = _inventory_rows(s3, result["inventory_manifest_key"])
    rows_by_project = {row["project_id"]: row for row in inventory_rows}

    assert rows_by_project["ok"]["status"] == "downloaded"
    assert rows_by_project["ok"]["sha256"] == hashlib.sha256(b"success").hexdigest()
    assert rows_by_project["ok"]["size_bytes"] == 7
    assert rows_by_project["ok"]["content_type"] == "application/pdf"
    assert rows_by_project["ok"]["public_url"].startswith("https://cdn.example.test/")
    assert s3.objects[rows_by_project["ok"]["target_key"]] == b"success"
    assert rows_by_project["bad"]["status"] == "validation_error"
    assert rows_by_project["already"]["status"] == "already_exists"
    assert rows_by_project["missing"]["status"] == "missing_url"
    assert rows_by_project["fail"]["status"] == "download_error"
    assert rows_by_project["large"]["status"] == "too_large"
    assert result["downloaded"] == 1
    assert result["skipped_existing"] == 1
    assert result["already_exists"] == 1
    assert result["errors"] == 4
    assert result["total_bytes"] == 7


def test_reelly_document_asset_parallel_hydration_preserves_inventory_order() -> None:
    s3 = FakeS3()
    urls = [
        "https://vault.reelly.test/files/one.pdf",
        "https://vault.reelly.test/files/two.pdf",
        "https://vault.reelly.test/files/three.pdf",
    ]
    _put_manifest(
        s3,
        run_id="run-1",
        rows=[
            {"project_id": "1", "name": "One", "url": urls[0]},
            {"project_id": "2", "name": "Two", "url": urls[1]},
            {"project_id": "3", "name": "Three", "url": urls[2]},
        ],
    )
    downloader = FakeDownloader(
        {url: f"payload-{index}".encode("utf-8") for index, url in enumerate(urls, start=1)},
        delays={urls[0]: 0.05},
    )

    result = hydrate_reelly_document_assets(
        s3=s3,
        config=ReellyDocumentAssetHydrationConfig(
            allowed_document_hosts=("vault.reelly.test",),
            max_assets_per_run=10,
            max_concurrent_downloads=2,
        ),
        now=datetime(2026, 5, 3, 12, 0, tzinfo=UTC),
        download_client=downloader,
    )
    inventory_rows = _inventory_rows(s3, result["inventory_manifest_key"])

    assert result["downloaded"] == 3
    assert result["max_concurrent_downloads"] == 2
    assert [row["project_id"] for row in inventory_rows] == ["1", "2", "3"]
    assert {row["normalized_url"] for row in inventory_rows} == set(urls)
    assert set(downloader.calls) == set(urls)


def test_reelly_project_media_asset_hydrates_project_detail_media_with_structured_keys() -> None:
    s3 = FakeS3()
    cover_url = "https://api.reelly.io/vault/project/cover.jpg"
    floorplan_url = "https://api.reelly.io/vault/project/floorplans.pdf"
    _put_project_detail_manifest(
        s3,
        run_id="run-1",
        rows=[
            {
                "endpoint": "projects",
                "project_id": "501",
                "raw": {
                    "id": "501",
                    "cover": {"url": cover_url, "name": "Hero Cover.jpg"},
                    "Units_layouts_PDF": [{"url": floorplan_url, "name": "Floor Plans"}],
                },
            }
        ],
    )
    downloader = FakeDownloader({cover_url: b"cover", floorplan_url: b"floorplan"})

    result = hydrate_reelly_document_assets(
        s3=s3,
        config=ReellyDocumentAssetHydrationConfig(
            target_prefix="media/reelly_supply/project_media",
            inventory_prefix="raw/source=reelly_supply/project_media_asset_manifests",
            inventory_file_name="reelly_supply_project_media_assets.jsonl",
            include_project_documents=False,
            include_project_detail_media=True,
            structured_target_keys=True,
            allowed_document_hosts=("api.reelly.io",),
        ),
        now=datetime(2026, 5, 3, 12, 0, tzinfo=UTC),
        download_client=downloader,
    )
    inventory_rows = _inventory_rows(s3, result["inventory_manifest_key"])
    rows_by_type = {row["asset_type"]: row for row in inventory_rows}

    assert result["downloaded"] == 2
    assert set(rows_by_type) == {"cover_image", "floorplan"}
    assert rows_by_type["cover_image"]["field_path"] == "cover"
    assert rows_by_type["cover_image"]["source_file_name"] == "reelly_supply_project_details.jsonl"
    assert rows_by_type["cover_image"]["target_key"].startswith(
        "media/reelly_supply/project_media/project_id=501/asset_type=cover_image/field_path=cover/"
    )
    assert rows_by_type["floorplan"]["field_path"] == "Units_layouts_PDF.0"
    assert rows_by_type["floorplan"]["target_key"].startswith(
        "media/reelly_supply/project_media/project_id=501/"
        "asset_type=floorplan/field_path=Units_layouts_PDF.0/"
    )


def test_reelly_project_media_asset_plans_project_detail_media_without_documents() -> None:
    s3 = FakeS3()
    _put_manifest(
        s3,
        run_id="run-docs",
        rows=[
            {
                "project_id": "501",
                "name": "Brochure",
                "url": "https://drive.google.com/file/d/google-file-id/view?usp=sharing",
            }
        ],
    )
    _put_project_detail_manifest(
        s3,
        run_id="run-media",
        rows=[
            {
                "endpoint": "projects",
                "project_id": "501",
                "raw": {"Developer": [{"Logo_image": [{"url": "https://api.reelly.io/logo.png"}]}]},
            }
        ],
    )

    source_rows = _load_manifest_asset_rows(
        s3=s3,
        config=ReellyDocumentAssetHydrationConfig(
            include_project_documents=False,
            include_project_detail_media=True,
            allowed_document_hosts=("api.reelly.io",),
        ),
    )
    planned = _plan_document_assets(
        source_rows,
        config=ReellyDocumentAssetHydrationConfig(
            target_prefix="media/reelly_supply/project_media",
            include_project_documents=False,
            include_project_detail_media=True,
            structured_target_keys=True,
            allowed_document_hosts=("api.reelly.io",),
        ),
    )

    assert len(source_rows) == 1
    assert len(planned) == 1
    assert planned[0].asset_type == "developer_logo"
    assert planned[0].target_key.startswith(
        "media/reelly_supply/project_media/project_id=501/"
        "asset_type=developer_logo/field_path=Developer.0.Logo_image.0/"
    )
    assert planned[0].target_key.endswith("/Developer.0.Logo_image.0.png")


def _put_manifest(
    s3: FakeS3,
    *,
    run_id: str,
    rows: list[dict[str, Any]],
) -> tuple[str, str]:
    manifest_key = f"raw/source=reelly_supply/manifests/{run_id}.json"
    document_key = (
        f"raw/source=reelly_supply/extract_date=2026-05-03/"
        f"run_id={run_id}/reelly_supply_project_documents.jsonl"
    )
    s3.objects[document_key] = _jsonl_bytes(rows)
    s3.objects[manifest_key] = json.dumps(
        {
            "source": "reelly_supply",
            "run_id": run_id,
            "files": [
                {
                    "path": "reelly_supply_project_documents.jsonl",
                    "s3_key": document_key,
                    "row_count": len(rows),
                }
            ],
        }
    ).encode("utf-8")
    return manifest_key, document_key


def _put_project_detail_manifest(
    s3: FakeS3,
    *,
    run_id: str,
    rows: list[dict[str, Any]],
) -> tuple[str, str]:
    manifest_key = f"raw/source=reelly_supply/manifests/{run_id}.json"
    detail_key = (
        f"raw/source=reelly_supply/extract_date=2026-05-03/"
        f"run_id={run_id}/reelly_supply_project_details.jsonl"
    )
    s3.objects[detail_key] = _jsonl_bytes(rows)
    s3.objects[manifest_key] = json.dumps(
        {
            "source": "reelly_supply",
            "run_id": run_id,
            "files": [
                {
                    "path": "reelly_supply_project_details.jsonl",
                    "s3_key": detail_key,
                    "row_count": len(rows),
                }
            ],
        }
    ).encode("utf-8")
    return manifest_key, detail_key


def _inventory_rows(s3: FakeS3, key: str) -> list[dict[str, Any]]:
    return [json.loads(line) for line in s3.read_text(key=key).splitlines() if line.strip()]
