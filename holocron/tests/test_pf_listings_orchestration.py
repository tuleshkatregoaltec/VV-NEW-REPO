from __future__ import annotations

from typing import Any

from holocron.platform.checkpoints import checkpoint_s3_key
from holocron.sources.pf_listings.orchestration import resolve_listings_config


class FakeCheckpointS3:
    def __init__(self) -> None:
        self.objects: dict[str, dict[str, Any]] = {}

    def get_json(self, *, key: str) -> dict[str, Any] | None:
        return self.objects.get(key)

    def put_json(self, *, key: str, payload: dict[str, Any]) -> None:
        self.objects[key] = payload


def test_pf_listings_search_checkpoint_requires_full_plan_manifest_list_match() -> None:
    s3 = FakeCheckpointS3()
    s3.objects[checkpoint_s3_key(source="pf_listings", operation="search_chunk")] = {
        "plan_manifest_s3_keys": [
            "raw/source=pf_listings/manifests/plan-a.json",
            "raw/source=pf_listings/manifests/plan-c.json",
        ],
        "plan_manifest_s3_key": "raw/source=pf_listings/manifests/plan-c.json",
        "next_query_index": 12,
        "next_page": 3,
        "completed": False,
    }

    config = resolve_listings_config(
        source_config={
            "mode": "search",
            "plan_manifest_s3_keys": [
                "raw/source=pf_listings/manifests/plan-b.json",
                "raw/source=pf_listings/manifests/plan-c.json",
            ],
        },
        object_storage_client=s3,
    )

    assert config["plan_manifest_s3_key"] == "raw/source=pf_listings/manifests/plan-c.json"
    assert config["plan_manifest_s3_keys"] == [
        "raw/source=pf_listings/manifests/plan-b.json",
        "raw/source=pf_listings/manifests/plan-c.json",
    ]
    assert "search_query_cursor" not in config
    assert "search_page_cursor" not in config


def test_pf_listings_search_checkpoint_keeps_legacy_last_key_fallback() -> None:
    s3 = FakeCheckpointS3()
    s3.objects[checkpoint_s3_key(source="pf_listings", operation="search_chunk")] = {
        "plan_manifest_s3_key": "raw/source=pf_listings/manifests/plan-c.json",
        "next_query_index": 12,
        "next_page": 3,
        "completed": False,
    }

    config = resolve_listings_config(
        source_config={
            "mode": "search",
            "plan_manifest_s3_keys": [
                "raw/source=pf_listings/manifests/plan-b.json",
                "raw/source=pf_listings/manifests/plan-c.json",
            ],
        },
        object_storage_client=s3,
    )

    assert config["search_query_cursor"] == 12
    assert config["search_page_cursor"] == 3
