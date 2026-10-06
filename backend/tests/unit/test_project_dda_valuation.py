import pytest

from app.project import service as project_service


def test_dda_plot_valuation_uses_transaction_evidence_rates():
    evidence = {
        "business bay": [
            {
                "transaction_id": "tx-1",
                "plot_number": "3460001",
                "matched_plot_area_sqm": 950,
                "far_band": "development",
                "rate_aed_sqft": 400,
            },
            {
                "transaction_id": "tx-2",
                "plot_number": "3460002",
                "matched_plot_area_sqm": 1000,
                "far_band": "development",
                "rate_aed_sqft": 500,
            },
            {
                "transaction_id": "tx-3",
                "plot_number": "3460003",
                "matched_plot_area_sqm": 1050,
                "far_band": "development",
                "rate_aed_sqft": 600,
            },
            {
                "transaction_id": "tx-4",
                "plot_number": "3460004",
                "matched_plot_area_sqm": 1100,
                "far_band": "development",
                "rate_aed_sqft": 800,
            },
        ]
    }
    valuation = project_service._dda_plot_valuation(
        {
            "plot_number": "3460999",
            "community_name": "Business Bay",
            "plot_area_sqm": 1000,
            "max_gfa_sqm": 1000,
        },
        evidence,
    )

    assert valuation["valuation_rate_min_aed_sqft"] == 475.0
    assert valuation["valuation_rate_max_aed_sqft"] == 650.0
    assert valuation["valuation_min_aed"] == round(1000 * project_service.SQM_TO_SQFT * 475)
    assert valuation["valuation_max_aed"] == round(1000 * project_service.SQM_TO_SQFT * 650)
    assert valuation["valuation_confidence"] == "Medium"
    assert "4 DLD land sales" in valuation["valuation_note"]


def test_dda_plot_valuation_stays_pending_without_max_gfa():
    valuation = project_service._dda_plot_valuation(
        {
            "community_name": "Business Bay",
            "land_use": "Residential",
            "max_gfa_sqm": None,
        }
    )

    assert valuation["valuation_min_aed"] is None
    assert valuation["valuation_max_aed"] is None
    assert valuation["valuation_note"] == "Max GFA not available."


def test_dda_transaction_evidence_matches_transactions_to_nearest_plot_area():
    plot_indexes = project_service._dda_plot_indexes(
        [
            {
                "plot_number": "small",
                "community_name": "Business Bay",
                "plot_area_sqm": 1000,
                "max_gfa_sqm": 5000,
            },
            {
                "plot_number": "large",
                "community_name": "Business Bay",
                "plot_area_sqm": 5000,
                "max_gfa_sqm": 25000,
            },
        ]
    )

    evidence = project_service._transaction_evidence_by_community(
        [
            {
                "transaction_id": "tx-1",
                "area_name_en": "Business Bay",
                "plot_area_sqm": 1002,
                "price_aed": 25_000_000,
                "project_name_en": "Comparable",
                "procedure_name_en": "Sell",
            }
        ],
        plot_indexes,
    )

    business_bay = evidence["business bay"][0]
    assert business_bay["plot_number"] == "small"
    assert business_bay["rate_aed_sqft"] == 25_000_000 / (5000 * project_service.SQM_TO_SQFT)


def test_dda_development_evidence_distinguishes_direct_and_villa_subdivision_matches():
    rows = [
        {
            "plot_number": f"villa-{index}",
            "project_name": "Dubai Hills",
            "community_name": "Hadaeq Sheikh Mohammed Bin Rashid",
            "plot_area_sqm": 900,
            "land_use_summary": ["RESIDENTIAL VILLA"],
            "linked_asset_count": 1 if index == 0 else 0,
            "linked_physical_asset_count": 1 if index == 0 else 0,
            "site_plan_issue_date": None,
            "site_plan_expiry_date": None,
        }
        for index in range(5)
    ]

    project_service._annotate_dda_development_evidence(rows)

    assert rows[0]["development_status"] == "developed_confirmed"
    assert rows[0]["development_method"] == "parcel_id_exact"
    assert rows[1]["development_status"] == "developed_probable"
    assert rows[1]["development_method"] == "villa_subdivision_inference"
    assert rows[1]["subdivision_plot_count"] == 5
    assert rows[1]["subdivision_confirmed_count"] == 1


def test_dda_non_developable_land_is_not_reported_as_unbuilt_supply():
    rows = [
        {
            "plot_number": "park-1",
            "project_name": "",
            "community_name": "Example",
            "plot_area_sqm": 1_500,
            "land_use_summary": ["OPEN SPACE LANDSCAPE"],
            "linked_asset_count": 0,
            "linked_physical_asset_count": 0,
            "site_plan_issue_date": None,
            "site_plan_expiry_date": None,
        }
    ]

    project_service._annotate_dda_development_evidence(rows)

    assert rows[0]["development_status"] == "non_developable"
    assert rows[0]["development_method"] == "planning_land_use"


@pytest.mark.asyncio
async def test_dda_plot_bulk_layer_defers_valuation_lookup(monkeypatch):
    async def fake_geometries():
        return [
            {
                "plot_number": "bb-1",
                "project_name": "Business Bay Plot",
                "community_name": "Business Bay",
                "plot_area_sqm": 1000,
                "coordinates": [
                    [55.27, 25.18],
                    [55.28, 25.18],
                    [55.28, 25.19],
                    [55.27, 25.19],
                    [55.27, 25.18],
                ],
                "bounds": (55.27, 25.18, 55.28, 25.19),
                "land_use_summary": ["Residential"],
                "max_gfa_sqm": 5000,
                "max_height": None,
                "max_coverage": None,
                "land_use": "Residential",
                "gfa_type": None,
                "is_verified": True,
            }
        ]

    async def fail_valuation_lookup(*_args, **_kwargs):
        raise AssertionError("Bulk DDA map requests should not run transaction valuation lookup")

    monkeypatch.setattr(project_service, "_get_dda_plot_geometries", fake_geometries)
    monkeypatch.setattr(project_service, "_dda_transaction_valuation_lookup", fail_valuation_lookup)

    plots = await project_service.get_dda_plots_for_area(limit=100, include_valuations=False)

    assert len(plots) == 1
    assert plots[0].valuation_min_aed is None
    assert plots[0].valuation_note == "Valuation deferred for bulk map rendering."
