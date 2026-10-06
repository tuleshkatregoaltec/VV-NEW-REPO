from pathlib import Path

from holocron.sources.dxbi.rental_coverage import (
    FILTER_ITEM_IDS,
    build_rental_manifest,
    checkpoint_key,
    configuration_hash,
    filter_options_signature,
    manifest_configurations,
    read_location_inventory,
    select_marginal_coverage,
    validate_filter_discovery,
)


DEFAULTS = {
    "P74_DEAL": "RENT",
    "P74_PROP_TYPE": "A",
    "P74_STATUS": "B",
}


def test_manifest_dimensions_are_only_filters_available_for_rentals() -> None:
    assert FILTER_ITEM_IDS == (
        "P74_PROP_TYPE",
        "P74_STATUS",
        "P74_BEDS",
    )


def test_checked_in_location_inventory_has_all_213_areas() -> None:
    inventory = Path(__file__).parents[1] / "scripts" / "dxbi_rental_locations.tsv"

    locations = read_location_inventory(inventory)

    assert len(locations) == 213
    assert len({location["id"] for location in locations}) == 213


def test_manifest_enumerates_broad_and_leaf_profiles() -> None:
    manifest = build_rental_manifest(
        discovered_options={
            "P74_PROP_TYPE": [
                {"value": "A", "label": "All"},
                {"value": "R", "label": "Residential"},
                {"value": "C", "label": "Commercial"},
            ],
            "P74_STATUS": [
                {"value": "B", "label": "Both"},
                {"value": "N", "label": "New"},
                {"value": "R", "label": "Renewed"},
            ],
        },
        default_filters=DEFAULTS,
        discovered_at="2026-09-04T00:00:00+00:00",
    )

    assert manifest["manifest_version"] == 2
    assert manifest["profiles"][0]["id"] == "broad"
    assert {profile["dimension"] for profile in manifest["profiles"][1:]} == {
        "P74_PROP_TYPE",
        "P74_STATUS",
    }
    assert len(manifest["profiles"]) == 5


def test_incomplete_filter_discovery_fails_loud() -> None:
    try:
        validate_filter_discovery(
            {"P74_PROP_TYPE": [{"value": "A", "label": "All"}]},
            {"P74_PROP_TYPE": "A"},
        )
    except ValueError as exc:
        assert "P74_PROP_TYPE" in str(exc)
    else:
        raise AssertionError("incomplete filter discovery was accepted")


def test_filter_signature_detects_choices_not_dom_order() -> None:
    first = {
        "P74_PROP_TYPE": [
            {"value": "A", "label": "All"},
            {"value": "C", "label": "Commercial"},
        ]
    }
    reordered = {"P74_PROP_TYPE": list(reversed(first["P74_PROP_TYPE"]))}
    changed = {"P74_PROP_TYPE": [*first["P74_PROP_TYPE"], {"value": "R", "label": "Residential"}]}

    assert filter_options_signature(first) == filter_options_signature(reordered)
    assert filter_options_signature(first) != filter_options_signature(changed)


def test_configuration_hash_and_checkpoint_isolate_all_source_dimensions() -> None:
    base = {
        "manifest_version": 2,
        "report_type": "rentals",
        "account": "account-b",
        "profile_id": "broad",
        "location_id": "1",
        "location_text": "Dubai",
        "location_slug": "dubai",
        "filters": DEFAULTS,
    }
    changed = {**base, "profile_id": "commercial"}

    base_hash = configuration_hash(base)
    changed_hash = configuration_hash(changed)

    assert len(base_hash) == 20
    assert base_hash != changed_hash
    assert checkpoint_key({**base, "configuration_hash": base_hash}, "2026-09-04") != (
        checkpoint_key({**changed, "configuration_hash": changed_hash}, "2026-09-04")
    )


def test_configuration_hash_isolates_collection_strategy() -> None:
    base = {
        "manifest_version": 2,
        "report_type": "rentals",
        "account": "account-b",
        "profile_id": "broad",
        "location_id": "1",
        "filters": DEFAULTS,
        "collection_strategy": "split",
    }

    assert configuration_hash(base) != configuration_hash(
        {**base, "collection_strategy": "paginate"}
    )
    assert configuration_hash(base) != configuration_hash({**base, "collector_version": 3})


def test_validation_selects_only_profiles_and_locations_with_marginal_rows() -> None:
    manifest = build_rental_manifest(
        discovered_options={
            "P74_PROP_TYPE": [
                {"value": "A", "label": "All"},
                {"value": "R", "label": "Residential"},
                {"value": "C", "label": "Commercial"},
            ]
        },
        default_filters=DEFAULTS,
        locations=[{"id": "99", "text": "Dense Area", "slug": "dense-area"}],
        discovered_at="2026-09-04T00:00:00+00:00",
    )
    residential_id = manifest["profiles"][1]["id"]
    commercial_id = manifest["profiles"][2]["id"]

    selected = select_marginal_coverage(
        manifest,
        {
            ("broad", "1"): {"a", "b"},
            (residential_id, "1"): {"a"},
            (commercial_id, "1"): {"b", "c"},
            ("broad", "99"): {"a", "d"},
        },
        validated_at="2026-09-04T01:00:00+00:00",
    )

    by_profile = {profile["id"]: profile for profile in selected["profiles"]}
    assert by_profile[residential_id]["selected"] is False
    assert by_profile[commercial_id]["selected"] is True
    assert selected["locations"][1]["selected"] is True
    assert selected["validation"]["union_rows"] == 4


def test_validation_compares_multiset_multiplicity_not_only_distinct_rows() -> None:
    manifest = build_rental_manifest(
        discovered_options={
            "P74_PROP_TYPE": [
                {"value": "A", "label": "All"},
                {"value": "R", "label": "Residential"},
            ]
        },
        default_filters=DEFAULTS,
    )
    leaf_id = manifest["profiles"][1]["id"]

    selected = select_marginal_coverage(
        manifest,
        {("broad", "1"): {"same-row": 1}, (leaf_id, "1"): {"same-row": 2}},
    )

    assert selected["profiles"][1]["selected"] is True
    assert selected["validation"]["union_rows"] == 2


def test_validation_candidates_cover_every_profile_and_inventory_location(tmp_path: Path) -> None:
    inventory = tmp_path / "locations.tsv"
    inventory.write_text("10\tArea One\tarea-one\n11\tArea Two\tarea-two\n")
    manifest = build_rental_manifest(
        discovered_options={
            "P74_PROP_TYPE": [
                {"value": "A", "label": "All"},
                {"value": "R", "label": "Residential"},
            ]
        },
        default_filters=DEFAULTS,
        locations=read_location_inventory(inventory),
    )

    configurations = manifest_configurations(
        manifest,
        account="account-b",
        validation_candidates=True,
    )

    assert {(config["profile_id"], config["location_id"]) for config in configurations} == {
        (profile["id"], location["id"])
        for profile in manifest["profiles"]
        for location in manifest["locations"]
    }
    assert all(config["account"] == "account-b" for config in configurations)


def test_explicit_diagnostic_selections_use_only_requested_cross_product() -> None:
    manifest = build_rental_manifest(
        discovered_options={
            "P74_PROP_TYPE": [
                {"value": "A", "label": "All"},
                {"value": "R", "label": "Residential"},
            ]
        },
        default_filters=DEFAULTS,
        locations=[
            {"id": "10", "text": "Area One", "slug": "area-one"},
            {"id": "11", "text": "Area Two", "slug": "area-two"},
        ],
    )
    leaf_id = manifest["profiles"][1]["id"]

    configurations = manifest_configurations(
        manifest,
        account="account-b",
        profile_ids={"broad", leaf_id},
        location_ids={"1", "11"},
    )

    assert {(config["profile_id"], config["location_id"]) for config in configurations} == {
        ("broad", "1"),
        ("broad", "11"),
        (leaf_id, "1"),
        (leaf_id, "11"),
    }


def test_explicit_diagnostic_selection_rejects_unknown_ids() -> None:
    manifest = build_rental_manifest(
        discovered_options={
            "P74_PROP_TYPE": [
                {"value": "A", "label": "All"},
                {"value": "R", "label": "Residential"},
            ]
        },
        default_filters=DEFAULTS,
    )

    try:
        manifest_configurations(manifest, account="account-b", profile_ids={"missing"})
    except ValueError as exc:
        assert "unknown rental profile ids" in str(exc)
    else:
        raise AssertionError("unknown diagnostic profile was accepted")
