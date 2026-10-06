"""Coverage manifests and reconciliation helpers for DXB Interact rentals."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

MANIFEST_VERSION = 2
FILTER_ITEM_IDS = (
    "P74_PROP_TYPE",
    "P74_STATUS",
    "P74_BEDS",
)
_BROAD_LABELS = {"all", "any", "both", "all types", "all statuses", "all bedrooms"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def configuration_hash(configuration: Mapping[str, Any]) -> str:
    """Hash every setting that can change the result set or its provenance."""
    identity = {
        "manifest_version": int(configuration.get("manifest_version") or MANIFEST_VERSION),
        "manifest_hash": str(configuration.get("manifest_hash") or ""),
        "report_type": str(configuration.get("report_type") or "rentals"),
        "account": str(configuration.get("account") or ""),
        "profile_id": str(configuration.get("profile_id") or ""),
        "location_id": str(configuration.get("location_id") or ""),
        "location_text": str(configuration.get("location_text") or ""),
        "location_slug": str(configuration.get("location_slug") or ""),
        "collection_strategy": str(configuration.get("collection_strategy") or "split"),
        "collector_version": int(configuration.get("collector_version") or 2),
        "filters": dict(sorted((configuration.get("filters") or {}).items())),
    }
    return hashlib.sha256(canonical_json(identity).encode()).hexdigest()[:20]


def checkpoint_key(configuration: Mapping[str, Any], shard_key: str) -> str:
    config_hash = str(configuration.get("configuration_hash") or configuration_hash(configuration))
    parts = (
        str(configuration.get("report_type") or "rentals"),
        str(configuration.get("account") or "unknown"),
        str(configuration.get("profile_id") or "default"),
        str(configuration.get("location_id") or "unknown"),
        config_hash,
        shard_key,
    )
    return "|".join(parts)


def read_location_inventory(path: Path) -> list[dict[str, Any]]:
    locations: list[dict[str, Any]] = []
    seen: set[str] = set()
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            parts = stripped.split("\t")
            if len(parts) != 3 or not all(parts):
                raise ValueError(f"{path}:{line_number}: expected id, text, and slug")
            location_id, text, slug = parts
            if location_id in seen:
                raise ValueError(f"{path}:{line_number}: duplicate location id {location_id}")
            seen.add(location_id)
            locations.append(
                {
                    "id": location_id,
                    "text": text,
                    "slug": slug,
                    "kind": "area",
                    "selected": False,
                }
            )
    return locations


def _clean_option(option: Mapping[str, Any]) -> dict[str, str] | None:
    value = str(option.get("value") or "").strip()
    label = re.sub(r"\s+", " ", str(option.get("label") or option.get("text") or "")).strip()
    if not value or not label:
        return None
    return {"value": value, "label": label}


def normalize_filter_options(
    discovered: Mapping[str, Iterable[Mapping[str, Any]]],
) -> dict[str, list[dict[str, str]]]:
    normalized: dict[str, list[dict[str, str]]] = {}
    for item_id in FILTER_ITEM_IDS:
        unique: dict[str, dict[str, str]] = {}
        for raw_option in discovered.get(item_id, []):
            option = _clean_option(raw_option)
            if option:
                unique.setdefault(option["value"], option)
        if unique:
            normalized[item_id] = list(unique.values())
    return normalized


def _is_broad_option(option: Mapping[str, str], default_value: str) -> bool:
    label = re.sub(r"\s+", " ", option["label"].strip().lower())
    return option["value"] == default_value or label in _BROAD_LABELS or label.startswith("all ")


def validate_filter_discovery(
    discovered: Mapping[str, Iterable[Mapping[str, Any]]],
    default_filters: Mapping[str, str],
) -> dict[str, list[dict[str, str]]]:
    options = normalize_filter_options(discovered)
    incomplete = [
        item_id
        for item_id in FILTER_ITEM_IDS
        if item_id in default_filters
        and (
            len(options.get(item_id, [])) < 2
            or default_filters[item_id]
            not in {option["value"] for option in options.get(item_id, [])}
        )
    ]
    if incomplete:
        raise ValueError(f"incomplete authenticated filter discovery: {', '.join(incomplete)}")
    return options


def filter_options_signature(
    discovered: Mapping[str, Iterable[Mapping[str, Any]]],
) -> str:
    normalized = normalize_filter_options(discovered)
    stable = {
        item_id: sorted(item_options, key=lambda option: (option["value"], option["label"]))
        for item_id, item_options in normalized.items()
    }
    return hashlib.sha256(canonical_json(stable).encode()).hexdigest()


def build_rental_manifest(
    *,
    discovered_options: Mapping[str, Iterable[Mapping[str, Any]]],
    default_filters: Mapping[str, str],
    locations: Iterable[Mapping[str, Any]] = (),
    discovered_at: str | None = None,
) -> dict[str, Any]:
    """Build a manifest containing a broad profile and every discovered leaf profile."""
    options = normalize_filter_options(discovered_options)
    broad_filters = dict(default_filters)
    broad_options: dict[str, dict[str, str] | None] = {}
    for item_id, item_options in options.items():
        default_value = broad_filters.get(item_id, "")
        broad = next(
            (option for option in item_options if _is_broad_option(option, default_value)),
            None,
        )
        broad_options[item_id] = broad
        if broad:
            broad_filters[item_id] = broad["value"]

    profiles: list[dict[str, Any]] = [
        {
            "id": "broad",
            "label": "All rental records",
            "kind": "broad",
            "filters": broad_filters,
            "selected": True,
        }
    ]
    for item_id, item_options in options.items():
        broad = broad_options[item_id]
        for option in item_options:
            if broad and option["value"] == broad["value"]:
                continue
            profile_id = re.sub(r"[^a-z0-9]+", "-", f"{item_id}-{option['value']}".lower()).strip(
                "-"
            )
            profiles.append(
                {
                    "id": profile_id,
                    "label": f"{item_id}: {option['label']}",
                    "kind": "leaf",
                    "dimension": item_id,
                    "filters": {**broad_filters, item_id: option["value"]},
                    "selected": False,
                }
            )

    manifest_locations = [
        {
            "id": "1",
            "text": "Dubai",
            "slug": "dubai",
            "kind": "citywide",
            "selected": True,
        }
    ]
    seen_locations = {"1"}
    for raw_location in locations:
        location_id = str(raw_location.get("id") or "").strip()
        if not location_id or location_id in seen_locations:
            continue
        seen_locations.add(location_id)
        manifest_locations.append(
            {
                "id": location_id,
                "text": str(raw_location.get("text") or "").strip(),
                "slug": str(raw_location.get("slug") or "").strip(),
                "kind": str(raw_location.get("kind") or "area"),
                "selected": bool(raw_location.get("selected", False)),
            }
        )

    manifest: dict[str, Any] = {
        "manifest_version": MANIFEST_VERSION,
        "report_type": "rentals",
        "discovered_at": discovered_at or utc_now(),
        "filter_options": options,
        "profiles": profiles,
        "locations": manifest_locations,
        "selected_configurations": [{"profile_id": "broad", "location_id": "1"}],
        "validation": {"status": "pending"},
    }
    manifest["manifest_hash"] = manifest_hash(manifest)
    return manifest


def manifest_hash(manifest: Mapping[str, Any]) -> str:
    stable = {
        "manifest_version": manifest.get("manifest_version"),
        "report_type": manifest.get("report_type"),
        "filter_options": manifest.get("filter_options"),
        "profiles": manifest.get("profiles"),
        "locations": manifest.get("locations"),
        "selected_configurations": manifest.get("selected_configurations"),
    }
    return hashlib.sha256(canonical_json(stable).encode()).hexdigest()[:20]


def manifest_configurations(
    manifest: Mapping[str, Any],
    *,
    account: str,
    validation_candidates: bool = False,
    profile_ids: set[str] | None = None,
    location_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    profiles = list(manifest.get("profiles") or [])
    locations = list(manifest.get("locations") or [])
    broad_profile = next((profile for profile in profiles if profile.get("kind") == "broad"), None)
    citywide = next(
        (location for location in locations if location.get("kind") == "citywide"), None
    )
    if not broad_profile or not citywide:
        raise ValueError("rental manifest must contain a broad profile and citywide location")

    if validation_candidates and (profile_ids is not None or location_ids is not None):
        raise ValueError("validation candidates cannot be combined with explicit selections")

    profiles_by_id = {str(profile["id"]): profile for profile in profiles}
    locations_by_id = {str(location["id"]): location for location in locations}
    if validation_candidates:
        pairs = [(profile, location) for profile in profiles for location in locations]
    elif profile_ids is not None or location_ids is not None:
        requested_profiles = profile_ids if profile_ids is not None else {str(broad_profile["id"])}
        requested_locations = location_ids if location_ids is not None else {str(citywide["id"])}
        unknown_profiles = requested_profiles - profiles_by_id.keys()
        unknown_locations = requested_locations - locations_by_id.keys()
        if unknown_profiles:
            raise ValueError(f"unknown rental profile ids: {', '.join(sorted(unknown_profiles))}")
        if unknown_locations:
            raise ValueError(f"unknown rental location ids: {', '.join(sorted(unknown_locations))}")
        pairs = [
            (profiles_by_id[profile_id], locations_by_id[location_id])
            for profile_id in sorted(requested_profiles)
            for location_id in sorted(requested_locations)
        ]
    else:
        selections = list(manifest.get("selected_configurations") or [])
        pairs = [
            (
                profiles_by_id[str(selection["profile_id"])],
                locations_by_id[str(selection["location_id"])],
            )
            for selection in selections
        ]
    if not pairs:
        raise ValueError("rental manifest does not select any profile/location configurations")

    configurations: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for profile, location in pairs:
        pair_key = (str(profile["id"]), str(location["id"]))
        if pair_key in seen:
            continue
        seen.add(pair_key)
        configuration = {
            "manifest_version": int(manifest.get("manifest_version") or MANIFEST_VERSION),
            "manifest_hash": str(manifest.get("manifest_hash") or manifest_hash(manifest)),
            "report_type": str(manifest.get("report_type") or "rentals"),
            "account": account,
            "profile_id": pair_key[0],
            "profile_label": str(profile.get("label") or pair_key[0]),
            "location_id": pair_key[1],
            "location_text": str(location.get("text") or ""),
            "location_slug": str(location.get("slug") or ""),
            "filters": dict(profile.get("filters") or {}),
        }
        configuration["configuration_hash"] = configuration_hash(configuration)
        configurations.append(configuration)
    return configurations


def select_marginal_coverage(
    manifest: Mapping[str, Any],
    fingerprints: Mapping[tuple[str, str], Iterable[str] | Mapping[str, int]],
    *,
    validated_at: str | None = None,
) -> dict[str, Any]:
    """Select only leaf profiles and areas that add rows to the citywide broad union."""
    updated = json.loads(json.dumps(manifest))
    profiles = updated["profiles"]
    locations = updated["locations"]
    broad = next(profile for profile in profiles if profile["kind"] == "broad")
    citywide = next(location for location in locations if location["kind"] == "citywide")
    broad_key = (str(broad["id"]), str(citywide["id"]))
    covered = _fingerprint_counter(fingerprints.get(broad_key, ()))
    selected_configurations = [{"profile_id": str(broad["id"]), "location_id": str(citywide["id"])}]
    configuration_overlap: dict[str, dict[str, int]] = {}
    candidates = [
        (profile, location)
        for profile in profiles
        for location in locations
        if profile is not broad or location is not citywide
    ]
    candidates.sort(
        key=lambda pair: (
            pair[1] is not citywide,
            pair[0] is not broad,
            str(pair[0]["id"]),
            str(pair[1]["id"]),
        )
    )
    for profile, location in candidates:
        profile_id = str(profile["id"])
        location_id = str(location["id"])
        rows = _fingerprint_counter(fingerprints.get((profile_id, location_id), ()))
        marginal = rows - covered
        selected = bool(marginal)
        configuration_overlap[f"{profile_id}|{location_id}"] = {
            "rows": rows.total(),
            "overlap": (rows & covered).total(),
            "marginal": marginal.total(),
        }
        if selected:
            selected_configurations.append({"profile_id": profile_id, "location_id": location_id})
        covered |= rows

    selected_pairs = {
        (selection["profile_id"], selection["location_id"]) for selection in selected_configurations
    }
    for profile in profiles:
        profile["selected"] = any(pair[0] == str(profile["id"]) for pair in selected_pairs)
    for location in locations:
        location["selected"] = any(pair[1] == str(location["id"]) for pair in selected_pairs)
    updated["selected_configurations"] = selected_configurations

    updated["validation"] = {
        "status": "complete",
        "validated_at": validated_at or utc_now(),
        "broad_rows": _fingerprint_counter(fingerprints.get(broad_key, ())).total(),
        "union_rows": covered.total(),
        "configuration_overlap": configuration_overlap,
    }
    updated["manifest_hash"] = manifest_hash(updated)
    return updated


def _fingerprint_counter(values: Iterable[str] | Mapping[str, int]) -> Counter[str]:
    if isinstance(values, Mapping):
        counts = cast(Mapping[str, int], values)
        return Counter({str(key): int(value) for key, value in counts.items()})
    return Counter(str(value) for value in values)


def raw_row_fingerprint(payload: Mapping[str, Any]) -> str:
    columns = []
    for column in payload.get("columns") or []:
        columns.append(
            {
                "id": str(column.get("id") or ""),
                "text": str(column.get("text") or ""),
                "html": str(column.get("html") or ""),
                "attributes": column.get("attributes") or {},
                "links": column.get("links") or [],
            }
        )
    stable = {
        "columns": columns,
        "row_attributes": payload.get("row_attributes") or {},
        "hidden_attributes": payload.get("hidden_attributes") or {},
        "unit_number": str(payload.get("unit_number") or ""),
        "detail_url": str(payload.get("detail_url") or ""),
        "location_text": str(payload.get("location_text") or ""),
        "amount_text": str(payload.get("amount_text") or ""),
        "specs_text": str(payload.get("specs_text") or ""),
        "date_text": str(payload.get("date_text") or ""),
    }
    return hashlib.sha256(canonical_json(stable).encode()).hexdigest()
