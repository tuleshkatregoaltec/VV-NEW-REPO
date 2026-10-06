from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from app.feasibility.models import ComparableData, GenerateStudyResponse, LandPlot, UnitTypeData

MOCK_LAND_PLOT = LandPlot(
    plot_number="L001",
    community_name="Downtown Dubai",
    project_name="Burj Vista",
    plot_area_sqm=1000.0,
    max_gfa_sqm=4000.0,
    max_height="G+20",
    max_coverage="60%",
    gfa_type="Residential",
    is_verified=True,
)

MOCK_COMPARABLE = ComparableData(
    project_id=1,
    project_name="Test Tower",
    area_name="JVC",
    no_of_buildings=2,
    avg_floors=10.0,
    unit_mix=[
        UnitTypeData(
            type="1BR", count=50, percentage=50.0, avg_size_sqm=70.0, avg_price_sqm=15000.0
        )
    ],
    price_per_sqm_by_type={"1BR": 15000.0},
)


# ── Auth enforcement ─────────────────────────────────────────────────────────


async def test_areas_requires_auth(client_no_auth):
    resp = await client_no_auth.get("/api/v1/feasibility/areas")
    assert resp.status_code == 401


async def test_land_requires_auth(client_no_auth):
    resp = await client_no_auth.get("/api/v1/feasibility/land?area=Downtown Dubai&size_sqm=1000")
    assert resp.status_code == 401


async def test_comparable_requires_auth(client_no_auth):
    resp = await client_no_auth.get("/api/v1/feasibility/comparable?project_ids=1")
    assert resp.status_code == 401


# ── /areas ───────────────────────────────────────────────────────────────────


async def test_areas_returns_list(client):
    with patch(
        "app.feasibility.router.list_transaction_areas",
        new=AsyncMock(return_value=["Downtown Dubai", "JVC"]),
    ):
        resp = await client.get("/api/v1/feasibility/areas")

    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert "Downtown Dubai" in data


# ── /land ─────────────────────────────────────────────────────────────────────


async def test_land_returns_plots(client):
    with patch(
        "app.feasibility.router.list_nearby_land_plots",
        new=AsyncMock(return_value=[MOCK_LAND_PLOT]),
    ):
        resp = await client.get("/api/v1/feasibility/land?area=Downtown Dubai&size_sqm=1000")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["plot_number"] == "L001"
    assert data[0]["plot_area_sqm"] == 1000.0


async def test_land_missing_params_returns_422(client):
    resp = await client.get("/api/v1/feasibility/land")
    assert resp.status_code == 422


async def test_land_tolerance_out_of_range_returns_422(client):
    resp = await client.get("/api/v1/feasibility/land?area=JVC&size_sqm=500&tolerance=1.5")
    assert resp.status_code == 422


# ── /land/search ──────────────────────────────────────────────────────────────


async def test_land_search_returns_plots(client):
    with patch(
        "app.feasibility.router.search_nearby_land_plots",
        new=AsyncMock(return_value=[MOCK_LAND_PLOT]),
    ):
        resp = await client.get("/api/v1/feasibility/land/search?area=Downtown Dubai&q=L001")

    assert resp.status_code == 200
    assert resp.json()[0]["plot_number"] == "L001"


async def test_land_search_empty_query_returns_422(client):
    resp = await client.get("/api/v1/feasibility/land/search?area=Downtown Dubai&q=")
    assert resp.status_code == 422


# ── /comparable ───────────────────────────────────────────────────────────────


async def test_comparable_returns_data(client):
    with patch(
        "app.feasibility.router.get_comparable_or_404",
        new=AsyncMock(return_value=MOCK_COMPARABLE),
    ):
        resp = await client.get("/api/v1/feasibility/comparable?project_ids=1")

    assert resp.status_code == 200
    data = resp.json()
    assert data["project_id"] == 1
    assert data["area_name"] == "JVC"
    assert len(data["unit_mix"]) == 1


async def test_comparable_returns_404_when_no_data(client):
    with patch(
        "app.feasibility.router.get_comparable_or_404",
        new=AsyncMock(side_effect=HTTPException(404, "No data found for given project IDs")),
    ):
        resp = await client.get("/api/v1/feasibility/comparable?project_ids=9999")

    assert resp.status_code == 404


async def test_comparable_ignores_non_digit_ids(client):
    # "abc" should be filtered out, leaving an empty list -> 404
    with patch(
        "app.feasibility.router.get_comparable_or_404",
        new=AsyncMock(side_effect=HTTPException(404, "No data found for given project IDs")),
    ):
        resp = await client.get("/api/v1/feasibility/comparable?project_ids=abc")

    assert resp.status_code == 404


async def test_generate_study_delegates_to_service(client):
    response_model = GenerateStudyResponse.model_validate(
        {
            "plot_data": {
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
            },
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
            "research": {
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
            },
            "study_context": {
                "headline": "Initial HBU",
                "project_tier": "premium",
                "positioning": "",
                "summary_points": ["Summary"],
                "unit_mix_rationale": "",
                "pricing_rationale": "",
                "cost_rationale": "",
                "timing_rationale": "",
                "financing_rationale": "",
                "market_summary": "Constraint",
            },
            "chat": {"history": []},
        }
    )

    with patch(
        "app.feasibility.router.generate_seeded_study",
        new=AsyncMock(return_value=response_model),
    ) as generate_seeded_study:
        resp = await client.post(
            "/api/v1/feasibility/generate-study",
            json={"plot_number": "L001", "usage_override": "residential"},
        )

    assert resp.status_code == 200
    assert resp.json()["plot_data"]["plot_number"] == "L001"
    generate_seeded_study.assert_awaited_once()
