from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.feasibility.models import (
    FeasibilityChatState,
    FeasibilityChatStateMessage,
    FeasibilityStudyCreateRequest,
    FeasibilityStudyUpdateRequest,
    GenerateStudyResponse,
)
from app.feasibility.service import (
    create_saved_study,
    delete_saved_study,
    get_saved_study,
    list_saved_studies,
    update_saved_study,
)


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session
    await engine.dispose()


def assumptions_payload(**overrides):
    payload = {
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
        "landAcquisitionCostOverrideAed": 0.0,
        "designSupervisionCostOverrideAed": 0.0,
        "constructionCostOverrideAed": 0.0,
        "demolitionCostAed": 0.0,
        "infrastructureCostAed": 8000000.0,
        "governmentFeesAed": 5000000.0,
        "marketingCostOverrideAed": 0.0,
        "salesAgentFeesOverrideAed": 0.0,
        "masterCommunityFeesAed": 3500000.0,
        "ffeOsePreopeningCostAed": 0.0,
        "contingencyCostOverrideAed": 0.0,
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
        "developmentModel": "build_to_sell_residential",
    }
    return {**payload, **overrides}


def generated_study(**assumption_overrides):
    assumptions = assumptions_payload(**assumption_overrides)
    return GenerateStudyResponse.model_validate(
        {
            "plot_data": {
                "plot_number": "3460688",
                "community_name": "Business Bay",
                "project_name": "Business Bay Plot",
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
            "assumptions": assumptions,
            "research": {
                "plot_number": "3460688",
                "usage": "residential",
                "market_area": "Business Bay",
                "headline": "Initial HBU",
                "summary": ["Summary"],
                "constraints": [],
                "pricing_evidence": [],
                "competition_evidence": [],
                "land_sales_evidence": [],
                "market_pricing": [],
                "off_plan_market_pricing": [],
                "off_plan_pricing_confidence": None,
                "off_plan_unit_benchmarks": [],
                "assumptions": assumptions,
                "warnings": [],
                "land_cost_estimate_aed_low": None,
                "land_cost_estimate_aed_mid": None,
                "land_cost_estimate_aed_high": None,
            },
            "study_context": {
                "headline": "Initial HBU",
                "project_tier": "premium",
                "summary_points": ["Summary"],
                "market_summary": "",
            },
        }
    )


async def create_one(db_session, *, user_id="user-1", organization_id="org-1"):
    with patch(
        "app.feasibility.service.generate_seeded_study",
        new=AsyncMock(return_value=generated_study()),
    ):
        return await create_saved_study(
            db_session,
            request=FeasibilityStudyCreateRequest(
                name="Business Bay BTS",
                plot_number="3460688",
                development_model="build_to_sell_residential",
            ),
            user_id=user_id,
            organization_id=organization_id,
        )


async def test_saved_study_create_list_get_update_delete(db_session):
    created = await create_one(db_session)

    studies = await list_saved_studies(db_session, user_id="user-1", organization_id="org-1")
    assert [study.id for study in studies] == [created.id]
    assert studies[0].name == "Business Bay BTS"
    assert studies[0].plot_number == "3460688"

    loaded = await get_saved_study(
        db_session, study_id=created.id, user_id="user-1", organization_id="org-1"
    )
    assert loaded.assumptions["plotAreaSqm"] == 1000.0
    assert loaded.plot_data.project_name == "Business Bay Plot"
    assert loaded.chat_state == FeasibilityChatState()

    updated = await update_saved_study(
        db_session,
        study_id=created.id,
        request=FeasibilityStudyUpdateRequest(
            name="Renamed",
            assumptions={**loaded.assumptions, "landPricePsqm": 32000.0},
        ),
        user_id="user-1",
        organization_id="org-1",
    )
    assert updated.name == "Renamed"
    assert updated.assumptions["landPricePsqm"] == 32000.0
    assert updated.research.headline == "Initial HBU"
    assert updated.chat_state == FeasibilityChatState()

    await delete_saved_study(
        db_session, study_id=created.id, user_id="user-1", organization_id="org-1"
    )
    assert await list_saved_studies(db_session, user_id="user-1", organization_id="org-1") == []


async def test_saved_studies_enforce_user_and_organization_ownership(db_session):
    created = await create_one(db_session, user_id="user-1", organization_id="org-1")

    assert await list_saved_studies(db_session, user_id="user-2", organization_id="org-1") == []
    assert await list_saved_studies(db_session, user_id="user-1", organization_id="org-2") == []

    with pytest.raises(Exception) as exc_info:
        await get_saved_study(
            db_session,
            study_id=created.id,
            user_id="user-2",
            organization_id="org-1",
        )
    assert getattr(exc_info.value, "status_code", None) == 404


async def test_saved_study_update_does_not_regenerate_research(db_session):
    created = await create_one(db_session)
    loaded = await get_saved_study(
        db_session, study_id=created.id, user_id="user-1", organization_id="org-1"
    )

    with patch("app.feasibility.service.generate_seeded_study", new=AsyncMock()) as generate:
        await update_saved_study(
            db_session,
            study_id=created.id,
            request=FeasibilityStudyUpdateRequest(
                assumptions={**loaded.assumptions, "landPricePsqm": 35000.0}
            ),
            user_id="user-1",
            organization_id="org-1",
        )

    generate.assert_not_awaited()


async def test_saved_study_chat_state_round_trips_and_is_preserved(db_session):
    created = await create_one(db_session)
    loaded = await get_saved_study(
        db_session, study_id=created.id, user_id="user-1", organization_id="org-1"
    )
    chat_state = FeasibilityChatState(
        messages=[
            FeasibilityChatStateMessage(
                role="user",
                content="Explain the current returns.",
                created_at="2026-05-03T12:00:00.000Z",
            ),
            FeasibilityChatStateMessage(
                role="assistant",
                content="The current case is constrained by land cost.",
                created_at="2026-05-03T12:00:01.000Z",
            ),
        ],
        history_json='[{"kind":"request"}]',
    )

    updated = await update_saved_study(
        db_session,
        study_id=created.id,
        request=FeasibilityStudyUpdateRequest(chat_state=chat_state),
        user_id="user-1",
        organization_id="org-1",
    )

    assert updated.chat_state == chat_state

    preserved = await update_saved_study(
        db_session,
        study_id=created.id,
        request=FeasibilityStudyUpdateRequest(
            assumptions={**loaded.assumptions, "landPricePsqm": 33000.0}
        ),
        user_id="user-1",
        organization_id="org-1",
    )

    assert preserved.assumptions["landPricePsqm"] == 33000.0
    assert preserved.chat_state == chat_state


async def test_saved_study_assumptions_round_trip_full_workbook_json(db_session):
    created = await create_one(db_session)
    workbook_assumptions = {
        **created.assumptions,
        "constructionDebtLtc": 0.72,
        "landAcquisitionCostOverrideAed": None,
        "vatAppliesTo": {
            "land": False,
            "hardCosts": True,
            "softCosts": False,
            "permitFees": True,
            "contingency": False,
            "marketing": True,
            "salesAdmin": False,
        },
        "scenarioOverrides": {
            "downside": {
                "landAcquisitionCostOverrideAed": None,
                "constructionDebtLtc": 0.65,
            }
        },
    }

    updated = await update_saved_study(
        db_session,
        study_id=created.id,
        request=FeasibilityStudyUpdateRequest(assumptions=workbook_assumptions),
        user_id="user-1",
        organization_id="org-1",
    )
    loaded = await get_saved_study(
        db_session, study_id=created.id, user_id="user-1", organization_id="org-1"
    )

    assert updated.assumptions["constructionDebtLtc"] == 0.72
    assert updated.assumptions["landAcquisitionCostOverrideAed"] is None
    assert updated.assumptions["vatAppliesTo"] == workbook_assumptions["vatAppliesTo"]
    assert updated.assumptions["scenarioOverrides"] == workbook_assumptions["scenarioOverrides"]
    assert loaded.assumptions == updated.assumptions
