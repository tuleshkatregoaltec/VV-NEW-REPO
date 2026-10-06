from calendar import monthrange
from datetime import date
from typing import Any

from app.feasibility.models import (
    DevelopmentModel,
    FeasibilityAssumptions,
    FeasibilityPaymentPlan,
    FeasibilityVatApplicability,
)

SCHEDULE_MONTH_OFFSETS = {
    "demolitionEnablingDate": 1,
    "salesCommencementDate": 3,
    "constructionDate": 4,
    "preHandoverMilestoneDate": 28,
    "handoverDate": 34,
}

WORKBOOK_DEFAULT_UPDATES: dict[str, Any] = {
    "buaMultiplier": 1.5,
    "nsaEfficiencyPct": 80.0,
    "standardParkingRatio": 1.0,
    "largeUnitThresholdSqm": 140.0,
    "largeUnitParkingRatio": 2.0,
    "designSupervisionPct": 6.0,
    "designSupervisionCostOverrideAed": 0.0,
    "constructionCostOverrideAed": 0.0,
    "salesAgentFeePct": 5.0,
    "marketingCostPct": 1.0,
    "salesAgentFeesOverrideAed": 0.0,
    "marketingCostOverrideAed": 0.0,
    "contingencyPct": 5.0,
    "contingencyCostOverrideAed": 0.0,
    "financeRatePct": 0.0,
    "arrangementFeePct": 1.0,
    "commitmentFeePct": 0.5,
    "debtToCostRatio": 0.0,
    "presaleThresholdPct": 35.0,
    "escrowRetentionPct": 5.0,
    "demolitionEnabled": False,
    "demolitionCostAed": 0.0,
    "infrastructureCostAed": 8_000_000.0,
    "governmentFeesAed": 5_000_000.0,
    "masterCommunityFeesAed": 3_500_000.0,
    "ffeOsePreopeningCostAed": 0.0,
    "midPointInflationPct": 4.0,
    "vatPct": 5.0,
    "debtFundingAed": 0.0,
    "equityFundingAed": 0.0,
    "brokerageFeeAed": 0.0,
    "legalDdCostAed": 0.0,
    "landLoanLtvPct": 70.0,
    "eiborRatePct": 4.85,
    "landLoanSpreadBps": 200.0,
    "constructionLoanSpreadBps": 200.0,
    "debtRepaymentMode": "bullet_at_handover",
    "salesPeriodMonths": 24,
    "basementParkingFloors": 4.0,
    "podiumFloors": 5.0,
    "residentialFloors": 30.0,
    "amenityRoofFloors": 1.0,
    "parkingAreaPerSpaceSqm": 30.0,
    "aboveGradeBuaFactor": 1.1,
    "serviceBohPlantPct": 0.03,
    "podiumParkingFloorsOutsideGfa": 0.0,
    "targetCoveragePct": 0.0,
    "targetBuildingCount": 0.0,
    "maxEfficientTowerFloorplateSqm": 0.0,
    "minEfficientTowerFloorplateSqm": 0.0,
    "floorToFloorHeightM": 3.2,
    "podiumFloorToFloorHeightM": 4.0,
    "groundFloorHeightM": 5.0,
    "roofPlantAllowanceM": 6.0,
    "landTransferFeePct": 0.04,
    "brokeragePct": 0.01,
    "legalDdPct": 0.005,
    "permitFeesPct": 0.02,
    "softCostPct": 0.15,
    "acquisitionDebtLtv": 0.7,
    "constructionDebtLtc": 0.7,
    "debtSpreadPa": 0.02,
    "financingFeePct": 0.01,
    "exitFeePct": 0.01,
    "preferredReturnPa": 0.08,
    "sponsorPromotePct": 0.2,
    "projectYears": 5.0,
    "constructionCurveSteepness": 8.0,
    "salesCurveSteepness": 8.0,
    "vatRefundLagMonths": 6.0,
    "selectedScenario": "base",
}

BTR_WORKBOOK_DEFAULT_UPDATES: dict[str, Any] = {
    "btrHoldPeriodYears": 10.0,
    "btrLeaseUpPaceUnitsPerMonth": 20.0,
    "btrStabilizedOccupancyPct": 97.0,
    "btrFreeRentMonths": 0.0,
    "btrAnnualRentGrowthPct": 5.0,
    "btrMarketRentGrowthPct": 5.0,
    "btrRenewalRentGrowthPct": 5.0,
    "btrGeneralVacancyPct": 5.0,
    "btrPropertyManagementPct": 5.0,
    "btrRepairsMaintenancePsqm": 50.0,
    "btrInsurancePsqm": 10.0,
    "btrServiceChargePsqm": 80.0,
    "btrUtilitiesPsqm": 30.0,
    "btrMarketingLeasingPct": 2.0,
    "btrCapexReservePct": 5.0,
    "btrParkingIncomeAed": 0.0,
    "btrAncillaryIncomeAed": 0.0,
    "btrAncillaryGrowthPct": 3.0,
    "btrStabilizedFreeRentMonths": 0.0,
    "btrOpExGrowthPct": 3.0,
    "btrDevCostEscalationPct": 4.0,
    "btrTerminalGrowthPct": 4.0,
    "btrLeaseUpMarketingAed": 0.0,
    "btrCreditLossPct": 1.0,
    "btrPayrollPsqm": 40.0,
    "btrGeneralAdminPct": 1.0,
    "btrContractServicesPsqm": 25.0,
    "btrModelUnits": 1.0,
    "btrExitCapRatePct": 5.5,
    "btrExitCostPct": 6.0,
    "btrPermDebtLtvPct": 65.0,
    "btrPermDebtRatePct": 6.0,
    "btrPermDebtSpreadBps": 165.0,
    "btrPermDebtAmortYears": 25.0,
    "btrPermDebtPointsPct": 1.0,
    "btrPermDebtIoYears": 1.0,
    "btrDscrMinimum": 1.25,
    "btrRefiCapRatePct": 5.5,
}

MARKET_ASSUMPTION_FIELDS = (
    "usage",
    "developmentModel",
    "landPricePsqm",
    "landAcquisitionCostOverrideAed",
    "constructionCostPsqmBua",
    "unitConfigs",
    "btrUnitConfigs",
)

PROJECT_PHYSICAL_ASSUMPTION_FIELDS = (
    "podiumFloors",
    "residentialFloors",
    "amenityRoofFloors",
    "targetCoveragePct",
    "targetBuildingCount",
    "maxEfficientTowerFloorplateSqm",
    "minEfficientTowerFloorplateSqm",
)


def add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, monthrange(year, month)[1])
    return date(year, month, day)


def schedule_default_updates(generation_date: date | None = None) -> dict[str, str]:
    base = generation_date or date.today()
    return {
        "landAcquisitionDate": base.isoformat(),
        **{
            field: add_months(base, offset).isoformat()
            for field, offset in SCHEDULE_MONTH_OFFSETS.items()
        },
    }


def deterministic_default_updates(generation_date: date | None = None) -> dict[str, Any]:
    return {
        **WORKBOOK_DEFAULT_UPDATES,
        **BTR_WORKBOOK_DEFAULT_UPDATES,
        **schedule_default_updates(generation_date),
        "paymentPlan": FeasibilityPaymentPlan(
            depositPct=10.0, constructionPct=30.0, handoverPct=60.0
        ),
        "vatAppliesTo": FeasibilityVatApplicability(),
    }


def sanitize_generated_assumptions(
    assumptions: FeasibilityAssumptions,
    *,
    scaffold: FeasibilityAssumptions,
    generation_date: date | None = None,
    development_model: DevelopmentModel,
) -> FeasibilityAssumptions:
    market_updates = {field: getattr(assumptions, field) for field in MARKET_ASSUMPTION_FIELDS}
    market_updates["developmentModel"] = development_model
    scaffold_physical_updates = {
        field: getattr(scaffold, field) for field in PROJECT_PHYSICAL_ASSUMPTION_FIELDS
    }
    deterministic_updates = deterministic_default_updates(generation_date)
    if development_model == "build_to_rent_residential":
        deterministic_updates.update(
            {
                "salesAgentFeePct": 0.0,
                "marketingCostPct": 0.0,
                "marketingCostOverrideAed": 0.0,
                "salesAgentFeesOverrideAed": 0.0,
            }
        )
    return scaffold.model_copy(
        deep=True,
        update={
            **deterministic_updates,
            **market_updates,
            **scaffold_physical_updates,
        },
    )
