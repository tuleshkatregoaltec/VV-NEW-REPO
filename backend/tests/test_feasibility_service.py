from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from app.feasibility.models import GenerateStudyRequest, PlotDetails, PlotResearch
from app.feasibility.queries import get_comparable_data, get_land_plots, search_land_plots
from app.feasibility.service import generate_seeded_study, get_comparable_or_404

MOCK_LAND_ROW = {
    "plot_number": "L001",
    "community_name": "Downtown Dubai",
    "project_name": "Burj Vista",
    "plot_area_sqm": 1000.0,
    "max_gfa_sqm": 4000.0,
    "max_height": "G+20",
    "max_coverage": "60%",
    "gfa_type": "Residential",
    "is_verified": True,
    "land_use": '[{"type":"Residential","use":"Apartment"}]',
}


async def test_get_comparable_data_empty_returns_none():
    assert await get_comparable_data([]) is None


async def test_get_land_plots_maps_rows_to_land_plot_models():
    with patch("app.feasibility.queries.query", new=AsyncMock(return_value=[MOCK_LAND_ROW])):
        plots = await get_land_plots("Downtown Dubai", 1000.0)

    assert len(plots) == 1
    assert plots[0].plot_number == "L001"
    assert plots[0].plot_area_sqm == 1000.0
    assert plots[0].community_name == "Downtown Dubai"
    assert plots[0].is_verified is True


async def test_get_land_plots_empty_db_returns_empty_list():
    with patch("app.feasibility.queries.query", new=AsyncMock(return_value=[])):
        plots = await get_land_plots("Downtown Dubai", 1000.0)

    assert plots == []


async def test_get_land_plots_null_optional_fields():
    row = {
        **MOCK_LAND_ROW,
        "plot_number": "",
        "project_name": "",
        "gfa_type": "",
        "land_use": "",
    }
    with patch("app.feasibility.queries.query", new=AsyncMock(return_value=[row])):
        plots = await get_land_plots("Downtown Dubai", 1000.0)

    assert plots[0].plot_number == ""
    assert plots[0].project_name == ""
    assert plots[0].gfa_type == ""
    assert plots[0].land_use_summary == []


async def test_search_land_plots_maps_rows():
    with patch("app.feasibility.queries.query", new=AsyncMock(return_value=[MOCK_LAND_ROW])):
        plots = await search_land_plots("Downtown Dubai", "L001")

    assert len(plots) == 1
    assert plots[0].plot_number == "L001"


async def test_get_comparable_data_unit_percentages():
    buildings_rows = [{"no_of_buildings": 2, "avg_floors": 10.0}]
    project_rows = [{"project_id": 1, "project_name_en": "Test Tower", "area_name_en": "JVC"}]
    units_rows = [
        {"unit_type": "1BR", "cnt": 40, "avg_size_sqm": 70.0},
        {"unit_type": "2BR", "cnt": 60, "avg_size_sqm": 100.0},
    ]

    with patch(
        "app.feasibility.queries.query",
        new=AsyncMock(side_effect=[buildings_rows, project_rows, units_rows, []]),
    ):
        result = await get_comparable_data([1])

    assert result is not None
    one_br = next(u for u in result.unit_mix if u.type == "1BR")
    two_br = next(u for u in result.unit_mix if u.type == "2BR")
    assert one_br.percentage == 40.0
    assert two_br.percentage == 60.0
    assert one_br.count + two_br.count == 100


async def test_get_comparable_data_price_by_type():
    buildings_rows = [{"no_of_buildings": 1, "avg_floors": 5.0}]
    project_rows = [{"project_id": 1, "project_name_en": "Test Tower", "area_name_en": "JVC"}]
    units_rows = [{"unit_type": "Studio", "cnt": 10, "avg_size_sqm": 40.0}]
    price_rows = [{"unit_type": "Studio", "median_price_sqm": 15000.0}]

    with patch(
        "app.feasibility.queries.query",
        new=AsyncMock(side_effect=[buildings_rows, project_rows, units_rows, price_rows]),
    ):
        result = await get_comparable_data([1])

    assert result is not None
    studio = result.unit_mix[0]
    assert studio.avg_price_sqm == 15000.0
    assert result.price_per_sqm_by_type["Studio"] == 15000.0


async def test_get_comparable_data_project_name_joined():
    buildings_rows = [{"no_of_buildings": 2, "avg_floors": 8.0}]
    project_rows = [
        {"project_id": 1, "project_name_en": "Alpha", "area_name_en": "JLT"},
        {"project_id": 2, "project_name_en": "Beta", "area_name_en": "JLT"},
    ]
    units_rows = [{"unit_type": "1BR", "cnt": 20, "avg_size_sqm": 75.0}]

    with patch(
        "app.feasibility.queries.query",
        new=AsyncMock(side_effect=[buildings_rows, project_rows, units_rows, []]),
    ):
        result = await get_comparable_data([1, 2])

    assert result is not None
    assert "Alpha" in result.project_name
    assert "Beta" in result.project_name


async def test_get_comparable_or_404_raises_when_missing():
    with patch("app.feasibility.service.get_comparable_data", new=AsyncMock(return_value=None)):
        try:
            await get_comparable_or_404("abc")
        except HTTPException as exc:
            assert exc.status_code == 404
            assert exc.detail == "No data found for given project IDs"
        else:
            raise AssertionError("Expected HTTPException")


async def test_generate_seeded_study_builds_response_from_plot_and_research():
    plot = PlotDetails.model_validate(
        {
            "plot_number": "L001",
            "community_name": "Downtown Dubai",
            "project_name": "Burj Vista",
            "master_developer": None,
            "plot_area_sqm": 1000.0,
            "max_gfa_sqm": 4000.0,
            "max_gfa_sqft": 43055.0,
            "max_height": "G+20",
            "max_coverage": "60%",
            "gfa_type": "Residential",
            "far": 4.0,
            "inferred_usage": "residential",
            "site_plan_issue_date": None,
            "site_plan_expiry_date": None,
            "is_verified": True,
            "verify_comments": None,
            "land_use": [],
            "general_notes": [],
            "setbacks": {},
            "coordinates": [],
            "warnings": [],
        }
    )
    research = PlotResearch.model_validate(
        {
            "plot_number": "L001",
            "usage": "residential",
            "market_area": "Downtown Dubai",
            "headline": "Initial HBU",
            "summary": ["Summary"],
            "constraints": ["Constraint"],
            "pricing_evidence": [],
            "competition_evidence": [],
            "land_sales_evidence": [],
            "market_pricing": [],
            "off_plan_market_pricing": [],
            "off_plan_pricing_confidence": None,
            "off_plan_unit_benchmarks": [],
            "assumptions": {
                "usage": "residential",
                "plotAreaSqm": 1000.0,
                "maxGfaSqm": 4000.0,
                "maxCoveragePct": 60.0,
                "maxStoreys": 20,
                "maxFar": 4.0,
                "numberOfTowers": 1,
                "numberOfFloors": 20,
                "buaMultiplier": 1.3,
                "nsaEfficiencyPct": 80.0,
                "landPricePsqm": 30000.0,
                "constructionCostPsqmBua": 4200.0,
                "designSupervisionPct": 6.0,
                "salesAgentFeePct": 5.0,
                "marketingCostPct": 1.0,
                "contingencyPct": 5.0,
                "financeRatePct": 9.0,
                "arrangementFeePct": 1.0,
                "commitmentFeePct": 0.5,
                "debtToCostRatio": 0.55,
                "presaleThresholdPct": 35.0,
                "escrowRetentionPct": 5.0,
                "standardParkingRatio": 1.0,
                "largeUnitThresholdSqm": 150.0,
                "largeUnitParkingRatio": 2.0,
                "demolitionEnabled": False,
                "salesCommencementDate": "2026-06-01",
                "salesPeriodMonths": 18,
                "demolitionEnablingDate": "2026-04-01",
                "constructionDate": "2026-07-01",
                "handoverDate": "2029-01-01",
                "landAcquisitionCostOverrideAed": None,
                "designSupervisionCostOverrideAed": None,
                "constructionCostOverrideAed": None,
                "demolitionCostAed": 0.0,
                "infrastructureCostAed": 8000000.0,
                "governmentFeesAed": 5000000.0,
                "marketingCostOverrideAed": None,
                "salesAgentFeesOverrideAed": None,
                "masterCommunityFeesAed": 3500000.0,
                "ffeOsePreopeningCostAed": 0.0,
                "contingencyCostOverrideAed": None,
                "midPointInflationPct": 4.0,
                "vatPct": 5.0,
                "debtFundingAed": 0.0,
                "equityFundingAed": 0.0,
                "brokerageFeeAed": 0.0,
                "legalDdCostAed": 0.0,
                "landAcquisitionDate": "2026-03-17",
                "landLoanLtvPct": 65.0,
                "eiborRatePct": 4.85,
                "landLoanSpreadBps": 365.0,
                "constructionLoanSpreadBps": 465.0,
                "preHandoverMilestoneDate": "2028-07-01",
                "debtRepaymentMode": "bullet_at_handover",
                "unitConfigs": [],
                "paymentPlan": {
                    "depositPct": 20.0,
                    "constructionPct": 40.0,
                    "handoverPct": 40.0,
                },
            },
            "warnings": [],
            "land_cost_estimate_aed_low": None,
            "land_cost_estimate_aed_mid": None,
            "land_cost_estimate_aed_high": None,
        }
    )

    with patch(
        "app.feasibility.service.generate_hbu_for_plot", new=AsyncMock(return_value=research)
    ):
        with patch(
            "app.feasibility.service.get_plot_details_or_404", new=AsyncMock(return_value=plot)
        ):
            response = await generate_seeded_study(
                GenerateStudyRequest(
                    plot_number="L001",
                    usage_override="residential",
                ),
            )

    assert response.plot_data.plot_number == "L001"
    assert response.assumptions.usage == "residential"
    assert response.study_context.headline == "Initial HBU"
    assert response.study_context.market_summary == "Constraint"


def test_compute_feasibility_workbook_builds_core_sections():
    from app.feasibility.engine import compute_feasibility_summary, compute_feasibility_workbook
    from app.feasibility.models import (
        FeasibilityAssumptions,
        FeasibilityPaymentPlan,
        FeasibilityUnitConfig,
    )

    plot = PlotDetails.model_validate(
        {
            "plot_number": "L001",
            "community_name": "Downtown Dubai",
            "project_name": "Burj Vista",
            "master_developer": None,
            "plot_area_sqm": 1000.0,
            "max_gfa_sqm": 4000.0,
            "max_gfa_sqft": 43055.0,
            "max_height": "G+20",
            "max_coverage": "60%",
            "gfa_type": "Residential",
            "far": 4.0,
            "inferred_usage": "residential",
            "site_plan_issue_date": None,
            "site_plan_expiry_date": None,
            "is_verified": True,
            "verify_comments": None,
            "land_use": [],
            "general_notes": [],
            "setbacks": {},
            "coordinates": [],
            "warnings": [],
        }
    )
    study = PlotResearch.model_validate(
        {
            "plot_number": "L001",
            "usage": "residential",
            "market_area": "Downtown Dubai",
            "headline": "Initial HBU",
            "summary": ["Summary"],
            "constraints": ["Constraint"],
            "pricing_evidence": [],
            "competition_evidence": [],
            "land_sales_evidence": [
                {
                    "transaction_id": "tx-1",
                    "instance_date": "2025-01-01",
                    "area_name": "Downtown Dubai",
                    "project_name": "Land comp",
                    "procedure_name": "Sale",
                    "property_usage": "Residential",
                    "plot_area_sqm": 1000.0,
                    "price_aed": 30_000_000.0,
                    "price_sqm": 30_000.0,
                    "nearest_landmark": None,
                }
            ],
            "market_pricing": [
                {
                    "unit_type": "1br",
                    "transaction_count": 10,
                    "median_price_sqm": 20000.0,
                    "avg_area_sqm": 75.0,
                }
            ],
            "off_plan_market_pricing": [
                {
                    "unit_type": "1br",
                    "horizon_bucket": "13-24m",
                    "avg_months_to_completion": 18.0,
                    "transaction_count": 5,
                    "median_price_sqm": 21000.0,
                    "avg_area_sqm": 76.0,
                    "last_transaction_date": "2025-06-01",
                }
            ],
            "off_plan_unit_benchmarks": [],
            "assumptions": {
                "plotAreaSqm": 1000.0,
                "maxFar": 4.0,
                "numberOfTowers": 1,
                "numberOfFloors": 20,
                "buaMultiplier": 1.3,
                "nsaEfficiencyPct": 80,
                "landPricePsqm": 30000.0,
                "constructionCostPsqmBua": 4200.0,
                "designSupervisionPct": 6.0,
                "salesAgentFeePct": 5.0,
                "marketingCostPct": 1.0,
                "contingencyPct": 5.0,
                "financeRatePct": 9.0,
                "arrangementFeePct": 1.0,
                "commitmentFeePct": 0.5,
                "debtToCostRatio": 0.55,
                "presaleThresholdPct": 35.0,
                "escrowRetentionPct": 5.0,
                "standardParkingRatio": 1.0,
                "largeUnitThresholdSqm": 150.0,
                "largeUnitParkingRatio": 2.0,
                "demolitionEnabled": False,
                "salesCommencementDate": "2026-06-01",
                "salesPeriodMonths": 12,
                "demolitionEnablingDate": "2026-04-01",
                "constructionDate": "2026-07-01",
                "handoverDate": "2029-01-01",
                "landAcquisitionCostOverrideAed": None,
                "designSupervisionCostOverrideAed": None,
                "constructionCostOverrideAed": None,
                "demolitionCostAed": 0.0,
                "infrastructureCostAed": 8_000_000.0,
                "governmentFeesAed": 5_000_000.0,
                "marketingCostOverrideAed": None,
                "salesAgentFeesOverrideAed": None,
                "masterCommunityFeesAed": 3_500_000.0,
                "ffeOsePreopeningCostAed": 0.0,
                "contingencyCostOverrideAed": None,
                "midPointInflationPct": 4.0,
                "vatPct": 5.0,
                "debtFundingAed": 70_000_000.0,
                "equityFundingAed": 50_000_000.0,
                "brokerageFeeAed": 0.0,
                "legalDdCostAed": 0.0,
                "landAcquisitionDate": "2026-03-17",
                "landLoanLtvPct": 65.0,
                "eiborRatePct": 4.85,
                "landLoanSpreadBps": 365.0,
                "constructionLoanSpreadBps": 465.0,
                "preHandoverMilestoneDate": "2028-07-01",
                "debtRepaymentMode": "bullet_at_handover",
                "unitConfigs": [
                    {
                        "id": "onebr",
                        "label": "1BR",
                        "units": 40,
                        "avgSizeSqm": 75.0,
                        "sellingRatePsqm": 20000.0,
                        "typicalFloor": 12,
                        "parkingRatio": 1.0,
                    }
                ],
                "paymentPlan": {"depositPct": 20.0, "constructionPct": 40.0, "handoverPct": 40.0},
            },
            "warnings": [],
            "land_cost_estimate_aed_mid": 30_000_000.0,
        }
    )

    inputs = FeasibilityAssumptions(
        plotAreaSqm=1000.0,
        maxFar=4.0,
        numberOfTowers=1,
        numberOfFloors=20,
        buaMultiplier=1.3,
        nsaEfficiencyPct=80,
        landPricePsqm=30_000.0,
        constructionCostPsqmBua=4200.0,
        designSupervisionPct=6.0,
        salesAgentFeePct=5.0,
        marketingCostPct=1.0,
        contingencyPct=5.0,
        financeRatePct=9.0,
        arrangementFeePct=1.0,
        commitmentFeePct=0.5,
        debtToCostRatio=0.55,
        presaleThresholdPct=35.0,
        escrowRetentionPct=5.0,
        standardParkingRatio=1.0,
        largeUnitThresholdSqm=150.0,
        largeUnitParkingRatio=2.0,
        demolitionEnabled=False,
        salesCommencementDate="2026-06-01",
        salesPeriodMonths=12,
        demolitionEnablingDate="2026-04-01",
        constructionDate="2026-07-01",
        handoverDate="2029-01-01",
        demolitionCostAed=0.0,
        infrastructureCostAed=8_000_000.0,
        governmentFeesAed=5_000_000.0,
        masterCommunityFeesAed=3_500_000.0,
        ffeOsePreopeningCostAed=0.0,
        midPointInflationPct=4.0,
        vatPct=5.0,
        debtFundingAed=70_000_000.0,
        equityFundingAed=50_000_000.0,
        brokerageFeeAed=600_000.0,
        legalDdCostAed=150_000.0,
        landAcquisitionDate="2026-03-01",
        landLoanLtvPct=65.0,
        eiborRatePct=4.85,
        landLoanSpreadBps=365.0,
        constructionLoanSpreadBps=465.0,
        preHandoverMilestoneDate="2028-07-01",
        debtRepaymentMode="bullet_at_handover",
        unitConfigs=[
            FeasibilityUnitConfig(
                id="onebr",
                label="1BR",
                units=40,
                avgSizeSqm=75.0,
                sellingRatePsqm=20_000.0,
                parkingRatio=1.0,
            )
        ],
        paymentPlan=FeasibilityPaymentPlan(depositPct=20.0, constructionPct=40.0, handoverPct=40.0),
    )

    workbook = compute_feasibility_workbook(plot, inputs, study)
    summary = compute_feasibility_summary(workbook)

    assert workbook.plot_number == "L001"
    assert workbook.program.total_units == 40
    assert workbook.costs.total_costs_incl_vat_aed > 0
    assert workbook.funding.total_uses_aed == workbook.costs.total_costs_incl_vat_aed
    assert workbook.cash_flow.periods
    assert workbook.validation.status in {"ready", "needs_review", "invalid"}
    assert summary.plot_number == "L001"
    assert summary.total_units == 40
