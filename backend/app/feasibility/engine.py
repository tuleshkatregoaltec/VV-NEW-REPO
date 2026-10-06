import json
import shutil
import subprocess
from dataclasses import make_dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from app.feasibility.models import FeasibilityAssumptions
from app.feasibility.workbook import compute_feasibility_summary, compute_feasibility_workbook

__all__ = [
    "computeWorkbook",
    "compute_feasibility_summary",
    "compute_feasibility_workbook",
]

REPO_ROOT = Path(__file__).resolve().parents[3]
FRONTEND_ENGINE_PATH = REPO_ROOT / "frontend/src/lib/feasibility/workbook/engine.ts"


def _dump_assumptions(assumptions: FeasibilityAssumptions | dict[str, Any]) -> dict[str, Any]:
    if isinstance(assumptions, BaseModel):
        return assumptions.model_dump(mode="json")
    return json.loads(json.dumps(assumptions))


def _frontend_compute_workbook(assumptions: dict[str, Any]) -> dict[str, Any]:
    if shutil.which("bun") is None:
        raise RuntimeError("Bun is required to run the frontend feasibility workbook engine")

    script = "\n".join(
        [
            f"import {{ computeWorkbook }} from {json.dumps(str(FRONTEND_ENGINE_PATH))}",
            f"const assumptions = {json.dumps(assumptions)}",
            "console.log(JSON.stringify(computeWorkbook(assumptions)))",
        ]
    )
    result = subprocess.run(
        ["bun", "--eval", script],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def computeWorkbook(assumptions: FeasibilityAssumptions | dict[str, Any]):
    """Run the canonical frontend feasibility engine from Python.

    The Svelte workbook is the source of truth for financial calculations. This
    wrapper exists for parity tests and diagnostics, not for the HBU generation
    path.
    """

    outputs = _frontend_compute_workbook(_dump_assumptions(assumptions))
    cls = make_dataclass("WorkbookOutputs", [(key, Any) for key in outputs])
    return cls(**outputs)
