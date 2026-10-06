import json
import shutil
import subprocess
from dataclasses import asdict
from pathlib import Path

import pytest

from app.feasibility.engine import computeWorkbook
from app.feasibility.models import FeasibilityAssumptions

REPO_ROOT = Path(__file__).resolve().parents[3]
FRONTEND_ENGINE_PATH = REPO_ROOT / "frontend/src/lib/feasibility/workbook/engine.ts"


def _base_assumptions() -> dict:
    return {
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
        "brokerageFeeAed": 600_000.0,
        "legalDdCostAed": 150_000.0,
        "landAcquisitionDate": "2026-03-01",
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
                "sellingRatePsqm": 20_000.0,
                "typicalFloor": 12,
                "parkingRatio": 1.0,
            }
        ],
        "paymentPlan": {
            "depositPct": 20.0,
            "constructionPct": 40.0,
            "handoverPct": 40.0,
        },
    }


def _frontend_compute_workbook(tmp_path: Path, assumptions: dict) -> dict:
    if shutil.which("bun") is None:
        pytest.skip("bun is required for frontend/backend engine parity tests")

    script_path = tmp_path / "compute_frontend_engine.ts"
    payload = json.dumps(assumptions)
    script_path.write_text(
        "\n".join(
            [
                f"import {{ computeWorkbook }} from {json.dumps(str(FRONTEND_ENGINE_PATH))}",
                f"const assumptions = {payload}",
                "console.log(JSON.stringify(computeWorkbook(assumptions)))",
            ]
        )
    )

    result = subprocess.run(
        ["bun", str(script_path)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def _backend_compute_workbook(assumptions: dict) -> dict:
    model = FeasibilityAssumptions.model_validate(assumptions)
    return asdict(computeWorkbook(model))


@pytest.mark.parametrize(
    "assumptions",
    [
        _base_assumptions(),
        {
            **_base_assumptions(),
            "usage": "mixed_use",
            "maxCoveragePct": None,
            "maxStoreys": 12,
            "plotAreaSqm": 3250.0,
            "maxGfaSqm": 7200.0,
            "numberOfTowers": 2,
            "numberOfFloors": 12,
            "debtFundingAed": 0.0,
            "equityFundingAed": 0.0,
            "unitConfigs": [
                {
                    "id": "studio",
                    "label": "Studio",
                    "units": 30,
                    "avgSizeSqm": 42.0,
                    "sellingRatePsqm": 18500.0,
                    "typicalFloor": 3,
                    "parkingRatio": 0.8,
                },
                {
                    "id": "retail",
                    "label": "Retail",
                    "units": 8,
                    "avgSizeSqm": 95.0,
                    "sellingRatePsqm": 24000.0,
                    "typicalFloor": 1,
                    "parkingRatio": 1.2,
                },
            ],
        },
        {
            **_base_assumptions(),
            "usage": "commercial",
            "plotAreaSqm": 1800.0,
            "maxGfaSqm": 5100.0,
            "maxCoveragePct": 45.0,
            "maxStoreys": 8,
            "buaMultiplier": 1.15,
            "nsaEfficiencyPct": 72.0,
            "landPricePsqm": 22500.0,
            "constructionCostPsqmBua": 5100.0,
            "demolitionEnabled": True,
            "demolitionCostAed": 1_250_000.0,
            "marketingCostOverrideAed": 900_000.0,
            "salesAgentFeesOverrideAed": 0.0,
            "contingencyCostOverrideAed": 1_800_000.0,
            "salesPeriodMonths": 18,
            "debtRepaymentMode": "sales_sweep",
            "unitConfigs": [
                {
                    "id": "office",
                    "label": "Office",
                    "units": 22,
                    "avgSizeSqm": 110.0,
                    "sellingRatePsqm": 16500.0,
                    "typicalFloor": 4,
                    "parkingRatio": 1.5,
                }
            ],
        },
    ],
)
def test_frontend_and_backend_engines_match_exactly(tmp_path: Path, assumptions: dict):
    frontend_outputs = _frontend_compute_workbook(tmp_path, assumptions)
    backend_outputs = _backend_compute_workbook(assumptions)

    assert backend_outputs == frontend_outputs
