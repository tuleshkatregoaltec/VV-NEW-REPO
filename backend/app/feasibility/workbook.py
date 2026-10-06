import math
from calendar import monthrange
from datetime import datetime, timedelta, timezone
from typing import Literal, NamedTuple

from app.feasibility.models import (
    FeasibilityAssumptions,
    FeasibilityCashFlowPeriod,
    FeasibilityCashFlowSummary,
    FeasibilityComputedSummary,
    FeasibilityCostLineItem,
    FeasibilityCostSummary,
    FeasibilityFinancingSummary,
    FeasibilityFundingSource,
    FeasibilityFundingSummary,
    FeasibilityProgramRow,
    FeasibilityProgramSummary,
    FeasibilityReturnsSummary,
    FeasibilityScheduleSummary,
    FeasibilitySiteEnvelope,
    FeasibilityWorkbook,
    PlotDetails,
    PlotResearch,
    Usage,
    ValidationIssue,
    ValidationSummary,
)
from app.feasibility.queries import normalize_unit_type

BuildingForm = Literal["low_rise", "mid_rise", "tower"]


class RatioBand:
    def __init__(self, low: float, base: float, high: float):
        self.low = low
        self.base = base
        self.high = high


class AreaRatioBenchmark:
    def __init__(
        self,
        usage: Usage,
        building_form: BuildingForm,
        coverage_ratio: RatioBand,
        bua_to_gfa_efficiency: RatioBand,
        gfa_to_gsa_efficiency: RatioBand,
        source_notes: list[str],
    ):
        self.usage = usage
        self.building_form = building_form
        self.coverage_ratio = coverage_ratio
        self.bua_to_gfa_efficiency = bua_to_gfa_efficiency
        self.gfa_to_gsa_efficiency = gfa_to_gsa_efficiency
        self.source_notes = source_notes


AREA_RATIO_BENCHMARKS: list[AreaRatioBenchmark] = [
    AreaRatioBenchmark(
        usage="residential",
        building_form="low_rise",
        coverage_ratio=RatioBand(low=0.55, base=0.60, high=0.65),
        bua_to_gfa_efficiency=RatioBand(low=0.89, base=0.91, high=0.93),
        gfa_to_gsa_efficiency=RatioBand(low=0.80, base=0.84, high=0.87),
        source_notes=[
            "Starter residential low-rise calibration band for apartments and townhouses.",
        ],
    ),
    AreaRatioBenchmark(
        usage="residential",
        building_form="mid_rise",
        coverage_ratio=RatioBand(low=0.40, base=0.45, high=0.50),
        bua_to_gfa_efficiency=RatioBand(low=0.85, base=0.88, high=0.90),
        gfa_to_gsa_efficiency=RatioBand(low=0.76, base=0.80, high=0.83),
        source_notes=["Starter residential mid-rise calibration band."],
    ),
    AreaRatioBenchmark(
        usage="residential",
        building_form="tower",
        coverage_ratio=RatioBand(low=0.35, base=0.38, high=0.40),
        bua_to_gfa_efficiency=RatioBand(low=0.83, base=0.86, high=0.88),
        gfa_to_gsa_efficiency=RatioBand(low=0.73, base=0.77, high=0.80),
        source_notes=["Starter residential tower calibration band."],
    ),
    AreaRatioBenchmark(
        usage="mixed_use",
        building_form="mid_rise",
        coverage_ratio=RatioBand(low=0.40, base=0.44, high=0.50),
        bua_to_gfa_efficiency=RatioBand(low=0.85, base=0.88, high=0.90),
        gfa_to_gsa_efficiency=RatioBand(low=0.75, base=0.78, high=0.81),
        source_notes=["Starter mixed-use mid-rise calibration band."],
    ),
    AreaRatioBenchmark(
        usage="commercial",
        building_form="mid_rise",
        coverage_ratio=RatioBand(low=0.35, base=0.42, high=0.45),
        bua_to_gfa_efficiency=RatioBand(low=0.84, base=0.87, high=0.89),
        gfa_to_gsa_efficiency=RatioBand(low=0.70, base=0.74, high=0.77),
        source_notes=["Starter commercial mid-rise calibration band."],
    ),
]


def _round(value: float, digits: int = 2) -> float:
    factor = 10**digits
    return math.floor(value * factor + 0.5) / factor


def _parse_percent(raw: str | None) -> float | None:
    if not raw:
        return None
    value = "".join(ch for ch in raw if ch.isdigit() or ch == ".")
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _parse_max_storeys(max_height: str | None) -> int | None:
    if not max_height:
        return None
    digits = "".join(ch if ch.isdigit() else " " for ch in max_height).split()
    if not digits:
        return None
    storeys = int(digits[-1])
    return storeys if storeys > 0 else None


def _classify_building_form(max_storeys: int | None) -> BuildingForm:
    storeys = max_storeys or 12
    if storeys <= 8:
        return "low_rise"
    if storeys <= 20:
        return "mid_rise"
    return "tower"


def _get_area_ratio_benchmark(usage: Usage, max_storeys: int | None) -> AreaRatioBenchmark:
    building_form = _classify_building_form(max_storeys)
    normalized_usage: Usage = (
        usage if usage in {"residential", "commercial", "mixed_use"} else "residential"
    )
    for benchmark in AREA_RATIO_BENCHMARKS:
        if benchmark.usage == normalized_usage and benchmark.building_form == building_form:
            return benchmark
    return AREA_RATIO_BENCHMARKS[0]


def _derive_area_chain(
    plot: PlotDetails,
    usage: Usage,
) -> dict[str, float | int | list[str] | None]:
    max_storeys = _parse_max_storeys(plot.max_height)
    regulatory_coverage_pct = _parse_percent(plot.max_coverage)
    benchmark = _get_area_ratio_benchmark(usage, max_storeys)
    applied_coverage_pct = min(
        regulatory_coverage_pct
        if regulatory_coverage_pct is not None
        else benchmark.coverage_ratio.base * 100,
        benchmark.coverage_ratio.base * 100,
    )
    buildable_footprint = round(plot.plot_area_sqm * (applied_coverage_pct / 100), 2)
    storeys_from_gfa = (
        max(math.floor(plot.max_gfa_sqm / buildable_footprint), 1)
        if buildable_footprint > 0 and plot.max_gfa_sqm > 0
        else max_storeys or 1
    )
    derived_storeys = min(max_storeys or storeys_from_gfa, storeys_from_gfa)
    built_up_area = round(buildable_footprint * max(derived_storeys, 1), 2)
    modeled_gfa = round(
        min(
            plot.max_gfa_sqm
            if plot.max_gfa_sqm > 0
            else built_up_area * benchmark.bua_to_gfa_efficiency.base,
            built_up_area * benchmark.bua_to_gfa_efficiency.base,
        ),
        2,
    )
    gross_saleable_area = round(modeled_gfa * benchmark.gfa_to_gsa_efficiency.base, 2)
    notes = list(benchmark.source_notes)
    if regulatory_coverage_pct is not None:
        notes.insert(
            0,
            f"Applied footprint ratio is capped by GIS maximum coverage of {round(regulatory_coverage_pct, 1)}%.",
        )
    else:
        notes.insert(
            0, "GIS maximum coverage is missing, so benchmark footprint ratios were applied."
        )
    return {
        "max_storeys": max_storeys,
        "applied_coverage_pct": round(applied_coverage_pct, 2),
        "buildable_footprint_sqm": buildable_footprint,
        "built_up_area_sqm": built_up_area,
        "modeled_gfa_sqm": modeled_gfa,
        "gross_saleable_area_sqm": gross_saleable_area,
        "gfa_from_bua_efficiency_pct": round(benchmark.bua_to_gfa_efficiency.base * 100, 2),
        "gsa_from_gfa_efficiency_pct": round(benchmark.gfa_to_gsa_efficiency.base * 100, 2),
        "area_assumption_notes": notes,
    }


def _parse_workspace_date(raw: str, fallback: datetime) -> datetime:
    try:
        parsed = datetime.fromisoformat(raw)
    except (TypeError, ValueError):
        return fallback
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _months_between_dates(start: datetime, end: datetime) -> int:
    return max((end.year - start.year) * 12 + (end.month - start.month), 0)


def _month_start(dt: datetime, months: int) -> datetime:
    month = dt.month - 1 + months
    year = dt.year + month // 12
    month = month % 12 + 1
    return datetime(year, month, 1, tzinfo=timezone.utc)


def _month_end(dt: datetime) -> datetime:
    if dt.month == 12:
        return datetime(dt.year + 1, 1, 1, tzinfo=timezone.utc) - timedelta(days=1)
    return datetime(dt.year, dt.month + 1, 1, tzinfo=timezone.utc) - timedelta(days=1)


def _workspace_usage(study: PlotResearch | None, plot: PlotDetails) -> Usage:
    return study.usage if study is not None else plot.inferred_usage


def _workspace_headline(study: PlotResearch | None, plot: PlotDetails) -> str:
    return (
        study.headline
        if study and study.headline
        else f"Feasibility study for plot {plot.plot_number}"
    )


def _periodic_irr(cash_flows: list[float], periods_per_year: int) -> float | None:
    if not any(cf > 0 for cf in cash_flows) or not any(cf < 0 for cf in cash_flows):
        return None

    def _npv(rate: float) -> float:
        try:
            return sum(cf / ((1 + rate) ** idx) for idx, cf in enumerate(cash_flows))
        except OverflowError:
            return float("nan")

    rate = 0.05
    min_rate = -0.9999
    max_rate = 5.0
    newton_converged = False
    for _ in range(100):
        npv = _npv(rate)
        dnpv = sum(-(idx * cf) / ((1 + rate) ** (idx + 1)) for idx, cf in enumerate(cash_flows))
        if not math.isfinite(npv) or not math.isfinite(dnpv):
            break
        if abs(dnpv) < 1e-10:
            break
        next_rate = rate - (npv / dnpv)
        if not math.isfinite(next_rate):
            break
        next_rate = max(min(next_rate, max_rate), min_rate)
        if abs(next_rate - rate) < 1e-7:
            rate = next_rate
            newton_converged = True
            break
        rate = next_rate
    if newton_converged and min_rate < rate < max_rate and math.isfinite(rate):
        annualised = ((1 + rate) ** periods_per_year - 1) * 100
        if math.isfinite(annualised):
            return annualised
    # Bisection fallback
    lo, hi = -0.999, 5.0
    npv_lo, npv_hi = _npv(lo), _npv(hi)
    if not (math.isfinite(npv_lo) and math.isfinite(npv_hi)):
        return None
    if npv_lo * npv_hi > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2.0
        npv_mid = _npv(mid)
        if abs(npv_mid) < 1e-2 or (hi - lo) < 1e-8:
            rate = mid
            break
        if npv_lo * npv_mid < 0:
            hi = mid
            npv_hi = npv_mid
        else:
            lo = mid
            npv_lo = npv_mid
    else:
        rate = (lo + hi) / 2.0
    annualised = ((1 + rate) ** periods_per_year - 1) * 100
    return annualised if math.isfinite(annualised) else None


class _PeriodRevenue(NamedTuple):
    deposit: float
    pre_handover: float
    handover: float


def _add_months(value: datetime, months: int) -> datetime:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def _iter_month_ends(start: datetime, end: datetime) -> list[datetime]:
    cursor = _month_end(start)
    periods: list[datetime] = []
    while cursor < end:
        periods.append(cursor)
        cursor = _month_end(_add_months(cursor.replace(day=1), 1))
    periods.append(_month_end(end))
    deduped: list[datetime] = []
    for period in periods:
        if not deduped or deduped[-1] != period:
            deduped.append(period)
    return deduped


def _scurve_weights(n: int) -> list[float]:
    if n <= 1:
        return [1.0]
    k = 8.0 / max(n, 1)
    mid = (n - 1) / 2.0
    raw = [math.exp(k * (i - mid)) / (1 + math.exp(k * (i - mid))) ** 2 for i in range(n)]
    total = sum(raw) or 1.0
    return [w / total for w in raw]


def _add_period_revenue(
    result: dict[datetime, _PeriodRevenue],
    period_end: datetime,
    deposit: float = 0.0,
    pre_handover: float = 0.0,
    handover: float = 0.0,
) -> None:
    if period_end not in result:
        return
    prev = result[period_end]
    result[period_end] = _PeriodRevenue(
        round(prev.deposit + deposit, 2),
        round(prev.pre_handover + pre_handover, 2),
        round(prev.handover + handover, 2),
    )


def _allocate_evenly_by_period(
    result: dict[datetime, _PeriodRevenue],
    periods: list[datetime],
    amount: float,
    field: str,
) -> None:
    if amount <= 0 or not periods:
        return
    per_period = round(amount / len(periods), 2)
    running_total = 0.0
    for index, period_end in enumerate(periods):
        allocated = per_period if index < len(periods) - 1 else round(amount - running_total, 2)
        running_total = round(running_total + allocated, 2)
        if field == "pre_handover":
            _add_period_revenue(result, period_end, pre_handover=allocated)
        elif field == "deposit":
            _add_period_revenue(result, period_end, deposit=allocated)
        elif field == "handover":
            _add_period_revenue(result, period_end, handover=allocated)


def _revenue_by_period(
    month_ends: list[datetime],
    sales_start: datetime,
    handover: datetime,
    sales_period_months: int,
    deposit_revenue: float,
    pre_handover_revenue: float,
    handover_revenue: float,
    milestone_date: datetime | None,
) -> dict[datetime, _PeriodRevenue]:
    result: dict[datetime, _PeriodRevenue] = {m: _PeriodRevenue(0.0, 0.0, 0.0) for m in month_ends}
    sales_end = _add_months(sales_start, sales_period_months - 1)
    sales_months = [m for m in month_ends if _month_end(sales_start) <= m <= _month_end(sales_end)]
    if not sales_months:
        sales_months = [_month_end(sales_start)] if month_ends else []
    weights = _scurve_weights(len(sales_months))
    handover_me = _month_end(handover)
    last_pre_handover_me = _month_end(_add_months(handover, -1))
    milestone_me: datetime | None = None
    if milestone_date is not None:
        candidate = _month_end(milestone_date)
        if _month_end(sales_start) < candidate < handover_me and candidate in result:
            milestone_me = candidate
    for index, sale_period_end in enumerate(sales_months):
        weight = weights[index]
        cohort_deposit = round(deposit_revenue * weight, 2)
        cohort_pre_handover = round(pre_handover_revenue * weight, 2)
        cohort_handover = round(handover_revenue * weight, 2)
        _add_period_revenue(result, sale_period_end, deposit=cohort_deposit)
        if cohort_pre_handover > 0 and sale_period_end < handover_me:
            if milestone_me is not None:
                collection_period = (
                    milestone_me if sale_period_end <= milestone_me else sale_period_end
                )
                collection_period = min(collection_period, last_pre_handover_me)
                _add_period_revenue(result, collection_period, pre_handover=cohort_pre_handover)
            else:
                collection_periods = [m for m in month_ends if sale_period_end < m < handover_me]
                if not collection_periods:
                    collection_periods = [sale_period_end]
                _allocate_evenly_by_period(
                    result, collection_periods, cohort_pre_handover, "pre_handover"
                )
        _add_period_revenue(result, handover_me, handover=cohort_handover)
    # Reconcile rounding differences to the handover period
    total_deposit = sum(v.deposit for v in result.values())
    total_pre_handover = sum(v.pre_handover for v in result.values())
    total_handover = sum(v.handover for v in result.values())
    deposit_diff = round(deposit_revenue - total_deposit, 2)
    pre_handover_diff = round(pre_handover_revenue - total_pre_handover, 2)
    handover_diff = round(handover_revenue - total_handover, 2)
    if handover_me in result and (deposit_diff or pre_handover_diff or handover_diff):
        _add_period_revenue(
            result,
            handover_me,
            deposit=deposit_diff,
            pre_handover=pre_handover_diff,
            handover=handover_diff,
        )
    return result


def compute_feasibility_workbook(
    plot: PlotDetails,
    assumptions: FeasibilityAssumptions,
    study: PlotResearch | None = None,
) -> FeasibilityWorkbook:
    usage = assumptions.usage if assumptions.usage != "unknown" else _workspace_usage(study, plot)
    area_chain = _derive_area_chain(plot, usage)

    modeled_gfa_sqm = (
        assumptions.maxGfaSqm
        if assumptions.maxGfaSqm > 0
        else _round(assumptions.plotAreaSqm * assumptions.maxFar)
    )
    built_up_area_sqm = _round(modeled_gfa_sqm * assumptions.buaMultiplier)
    gross_saleable_area_sqm = _round(modeled_gfa_sqm * (assumptions.nsaEfficiencyPct / 100))

    site = FeasibilitySiteEnvelope(
        plot_number=plot.plot_number,
        community_name=plot.community_name,
        project_name=plot.project_name,
        permitted_use=usage,
        plot_area_sqm=_round(assumptions.plotAreaSqm),
        max_gfa_sqm=modeled_gfa_sqm,
        max_storeys=assumptions.numberOfFloors,
        far=_round(assumptions.maxFar, 4),
        applied_coverage_pct=float(area_chain["applied_coverage_pct"])
        if area_chain["applied_coverage_pct"]
        else None,
        buildable_footprint_sqm=float(area_chain["buildable_footprint_sqm"])
        if area_chain["buildable_footprint_sqm"]
        else None,
        built_up_area_sqm=built_up_area_sqm,
        modeled_gfa_sqm=modeled_gfa_sqm,
        gross_saleable_area_sqm=gross_saleable_area_sqm,
        gfa_from_bua_efficiency_pct=float(area_chain["gfa_from_bua_efficiency_pct"])
        if area_chain["gfa_from_bua_efficiency_pct"]
        else None,
        gsa_from_gfa_efficiency_pct=_round(assumptions.nsaEfficiencyPct),
        max_height=plot.max_height,
        max_coverage=plot.max_coverage,
        gfa_type=plot.gfa_type,
        site_plan_issue_date=plot.site_plan_issue_date,
        site_plan_expiry_date=plot.site_plan_expiry_date,
        is_verified=plot.is_verified,
        area_assumption_notes=list(area_chain["area_assumption_notes"] or []),
        warnings=list(plot.warnings),
    )

    active_unit_rows = [row for row in assumptions.unitConfigs if row.units > 0]
    total_saleable_area = sum(
        max(row.units, 0) * max(row.avgSizeSqm, 0) for row in active_unit_rows
    )
    program_rows: list[FeasibilityProgramRow] = []
    for row in active_unit_rows:
        saleable_area = _round(max(row.units, 0) * max(row.avgSizeSqm, 0))
        share_pct = (
            _round((saleable_area / total_saleable_area) * 100, 1)
            if total_saleable_area > 0
            else 0.0
        )
        parking_spaces = _round(max(row.units, 0) * max(row.parkingRatio, 0.0), 2)
        program_rows.append(
            FeasibilityProgramRow(
                unit_type=normalize_unit_type(row.label),
                share_pct=share_pct,
                suggested_units=max(row.units, 0),
                avg_size_sqm=_round(max(row.avgSizeSqm, 0)),
                saleable_area_sqm=saleable_area,
                sales_rate_aed_per_sqm=_round(max(row.sellingRatePsqm, 0)),
                gross_revenue_aed=_round(saleable_area * max(row.sellingRatePsqm, 0)),
                parking_ratio=_round(max(row.parkingRatio, 0.0), 2),
                parking_spaces=parking_spaces,
            )
        )
    if program_rows:
        delta = _round(100 - sum(row.share_pct for row in program_rows), 1)
        program_rows[0].share_pct = _round(program_rows[0].share_pct + delta, 1)

    total_program_saleable_area = _round(sum(row.saleable_area_sqm for row in program_rows))
    total_parking_spaces = _round(sum(row.parking_spaces for row in program_rows), 2)
    weighted_avg_sales_rate = (
        _round(
            sum(row.sales_rate_aed_per_sqm * row.saleable_area_sqm for row in program_rows)
            / total_program_saleable_area
        )
        if total_program_saleable_area > 0
        else 0.0
    )
    program = FeasibilityProgramSummary(
        usage=usage,
        market_area=study.market_area if study else plot.community_name,
        headline=_workspace_headline(study, plot),
        gfa_sqm=modeled_gfa_sqm,
        saleable_area_sqm=total_program_saleable_area,
        saleable_efficiency_pct=_round(assumptions.nsaEfficiencyPct),
        total_units=sum(row.suggested_units for row in program_rows),
        total_parking_spaces=total_parking_spaces,
        weighted_avg_sales_rate_aed_per_sqm=weighted_avg_sales_rate,
        gross_revenue_aed=_round(sum(row.gross_revenue_aed for row in program_rows)),
        rows=program_rows,
        warnings=[*(study.warnings if study else []), *(study.constraints if study else [])],
    )

    land_cost = _round(
        assumptions.landAcquisitionCostOverrideAed
        or (assumptions.plotAreaSqm * assumptions.landPricePsqm)
    )
    construction_cost = _round(
        assumptions.constructionCostOverrideAed
        or (built_up_area_sqm * assumptions.constructionCostPsqmBua)
    )
    design_cost = _round(
        assumptions.designSupervisionCostOverrideAed
        or (construction_cost * assumptions.designSupervisionPct / 100)
    )
    marketing_cost = _round(
        assumptions.marketingCostOverrideAed
        or (program.gross_revenue_aed * assumptions.marketingCostPct / 100)
    )
    sales_agent_fees = _round(
        assumptions.salesAgentFeesOverrideAed
        or (program.gross_revenue_aed * assumptions.salesAgentFeePct / 100)
    )
    contingency_base = (
        construction_cost
        + design_cost
        + marketing_cost
        + sales_agent_fees
        + assumptions.infrastructureCostAed
        + assumptions.governmentFeesAed
        + assumptions.masterCommunityFeesAed
        + assumptions.demolitionCostAed
        + assumptions.legalDdCostAed
        + assumptions.brokerageFeeAed
    )
    contingency_cost = _round(
        assumptions.contingencyCostOverrideAed
        or (contingency_base * assumptions.contingencyPct / 100)
    )
    cost_specs = [
        (
            "land",
            "Land acquisition",
            land_cost,
            "plot area x land rate",
            _round(assumptions.plotAreaSqm),
            "sqm",
            "evidence",
            "land_acquisition",
            "land",
        ),
        (
            "construction",
            "Construction",
            construction_cost,
            "built-up area x construction rate",
            built_up_area_sqm,
            "sqm",
            "heuristic",
            "construction_straight_line",
            "hard_cost",
        ),
        (
            "design",
            "Design and supervision",
            design_cost,
            "% of construction",
            _round(assumptions.designSupervisionPct),
            "%",
            "derived",
            "construction_straight_line",
            "professional_fees",
        ),
        (
            "marketing",
            "Marketing",
            marketing_cost,
            "% of revenue",
            _round(assumptions.marketingCostPct),
            "%",
            "derived",
            "sales_velocity",
            "selling_costs",
        ),
        (
            "sales_agent",
            "Sales agent fees",
            sales_agent_fees,
            "% of revenue",
            _round(assumptions.salesAgentFeePct),
            "%",
            "derived",
            "sales_velocity",
            "selling_costs",
        ),
        (
            "infrastructure",
            "Infrastructure",
            _round(assumptions.infrastructureCostAed),
            "input",
            None,
            None,
            "input",
            "construction_straight_line",
            "authority_and_infrastructure",
        ),
        (
            "authority",
            "Authority fees",
            _round(assumptions.governmentFeesAed),
            "input",
            None,
            None,
            "input",
            "construction_straight_line",
            "authority_and_infrastructure",
        ),
        (
            "community",
            "Master community fees",
            _round(assumptions.masterCommunityFeesAed),
            "input",
            None,
            None,
            "input",
            "construction_straight_line",
            "authority_and_infrastructure",
        ),
        (
            "demolition",
            "Demolition",
            _round(assumptions.demolitionCostAed),
            "input",
            None,
            None,
            "input",
            "construction_straight_line",
            "other",
        ),
        (
            "legal_dd",
            "Legal and due diligence",
            _round(assumptions.legalDdCostAed),
            "input",
            None,
            None,
            "input",
            "construction_straight_line",
            "other",
        ),
        (
            "brokerage",
            "Brokerage",
            _round(assumptions.brokerageFeeAed),
            "input",
            None,
            None,
            "input",
            "construction_straight_line",
            "other",
        ),
        (
            "contingency",
            "Contingency",
            contingency_cost,
            "% of non-land costs",
            _round(assumptions.contingencyPct),
            "%",
            "derived",
            "construction_straight_line",
            "contingency",
        ),
    ]
    cost_items = [
        FeasibilityCostLineItem(
            code=code,
            label=label,
            amount_aed=amount_aed,
            basis=basis,
            basis_value=basis_value,
            basis_unit=basis_unit,
            source=source,
            timing_rule=timing_rule,
            timing_group=timing_group,
        )
        for code, label, amount_aed, basis, basis_value, basis_unit, source, timing_rule, timing_group in cost_specs
    ]
    total_costs_excl_vat = _round(sum(item.amount_aed for item in cost_items))
    vat_amount = _round(total_costs_excl_vat * assumptions.vatPct / 100)
    total_costs_incl_vat = _round(total_costs_excl_vat + vat_amount)
    gross_profit = _round(program.gross_revenue_aed - total_costs_incl_vat)
    costs = FeasibilityCostSummary(
        total_costs_excl_vat_aed=total_costs_excl_vat,
        vat_amount_aed=vat_amount,
        total_costs_incl_vat_aed=total_costs_incl_vat,
        cost_to_revenue_pct=_round((total_costs_incl_vat / program.gross_revenue_aed) * 100)
        if program.gross_revenue_aed > 0
        else 0.0,
        gross_profit_aed=gross_profit,
        gross_margin_pct=_round((gross_profit / program.gross_revenue_aed) * 100)
        if program.gross_revenue_aed > 0
        else 0.0,
        line_items=cost_items,
    )

    deposit_pct = assumptions.paymentPlan.depositPct
    pre_handover_pct = assumptions.paymentPlan.constructionPct
    handover_pct = assumptions.paymentPlan.handoverPct
    off_plan_proceeds = _round(
        program.gross_revenue_aed * (max(deposit_pct, 0) + max(pre_handover_pct, 0)) / 100
    )
    vat_refunds = _round(costs.vat_amount_aed)
    # Capital-stack view only: off-plan collections and VAT refunds are operating cash inflows,
    # not underwriting sources. Keeping them in sources lets sponsor equity collapse or turn
    # negative on strong presale cases.
    total_sources = _round(assumptions.debtFundingAed + assumptions.equityFundingAed)
    funding = FeasibilityFundingSummary(
        deposit_pct=_round(deposit_pct),
        pre_handover_pct=_round(pre_handover_pct),
        handover_pct=_round(handover_pct),
        presale_threshold_pct=_round(assumptions.presaleThresholdPct),
        presales_at_construction_start_aed=_round(program.gross_revenue_aed * deposit_pct / 100),
        escrow_retention_pct=_round(assumptions.escrowRetentionPct),
        debt_to_cost_ratio=_round(assumptions.debtToCostRatio, 4),
        debt_repayment_mode=assumptions.debtRepaymentMode,
        off_plan_proceeds_aed=off_plan_proceeds,
        debt_funding_aed=_round(assumptions.debtFundingAed),
        equity_funding_aed=_round(assumptions.equityFundingAed),
        vat_refunds_aed=vat_refunds,
        total_sources_aed=total_sources,
        total_uses_aed=costs.total_costs_incl_vat_aed,
        funding_gap_aed=_round(costs.total_costs_incl_vat_aed - total_sources),
        sources=[
            FeasibilityFundingSource(code=code, label=label, amount_aed=amount_aed, basis=basis)
            for code, label, amount_aed, basis in [
                ("debt", "Senior debt", _round(assumptions.debtFundingAed), "input"),
                ("equity", "Sponsor equity", _round(assumptions.equityFundingAed), "input"),
            ]
        ],
    )

    sales_start = _parse_workspace_date(
        assumptions.salesCommencementDate, datetime(2026, 6, 1, tzinfo=timezone.utc)
    )
    construction_start = _parse_workspace_date(
        assumptions.constructionDate, datetime(2026, 7, 1, tzinfo=timezone.utc)
    )
    handover_date = _parse_workspace_date(
        assumptions.handoverDate, datetime(2029, 1, 1, tzinfo=timezone.utc)
    )
    land_acq_date = _parse_workspace_date(assumptions.landAcquisitionDate, sales_start)
    milestone_date: datetime | None = None
    if assumptions.preHandoverMilestoneDate:
        try:
            _parsed_ms = datetime.fromisoformat(assumptions.preHandoverMilestoneDate)
            milestone_date = (
                _parsed_ms.replace(tzinfo=timezone.utc)
                if _parsed_ms.tzinfo is None
                else _parsed_ms.astimezone(timezone.utc)
            )
        except (TypeError, ValueError):
            pass
    schedule = FeasibilityScheduleSummary(
        sales_commencement_date=assumptions.salesCommencementDate,
        construction_start_date=assumptions.constructionDate,
        handover_date=assumptions.handoverDate,
        sales_period_months=max(int(assumptions.salesPeriodMonths), 1),
        construction_duration_months=max(
            _months_between_dates(construction_start, handover_date), 1
        ),
        sales_to_handover_months=max(_months_between_dates(sales_start, handover_date), 1),
    )

    start = min(land_acq_date, sales_start, construction_start)
    month_ends = _iter_month_ends(start, handover_date)
    land_period_end = _month_end(land_acq_date)
    handover_me = _month_end(handover_date)
    construction_start_me = _month_end(construction_start)
    construction_active_periods = [
        m for m in month_ends if construction_start_me <= m < handover_me
    ]
    construction_active_count = max(len(construction_active_periods), 1)

    deposit_revenue = _round(program.gross_revenue_aed * deposit_pct / 100)
    pre_handover_revenue = _round(program.gross_revenue_aed * pre_handover_pct / 100)
    handover_revenue = _round(program.gross_revenue_aed * handover_pct / 100)
    revenue_map = _revenue_by_period(
        month_ends,
        sales_start,
        handover_date,
        schedule.sales_period_months,
        deposit_revenue,
        pre_handover_revenue,
        handover_revenue,
        milestone_date,
    )
    monthly_vat = _round(costs.vat_amount_aed / construction_active_count)
    annual_rate = (assumptions.eiborRatePct + assumptions.constructionLoanSpreadBps / 100) / 100
    monthly_rate = annual_rate / 12
    commitment_rate = assumptions.commitmentFeePct / 100 / 12
    debt_limit = funding.debt_funding_aed
    construction_pool = sum(
        item.amount_aed
        for item in cost_items
        if item.code not in {"land", "marketing", "sales_agent", "contingency"}
    )
    monthly_construction = _round(construction_pool / construction_active_count)
    monthly_marketing = _round((marketing_cost + sales_agent_fees) / max(len(month_ends), 1))
    monthly_contingency = _round(contingency_cost / construction_active_count)

    cash_flow_periods: list[FeasibilityCashFlowPeriod] = []
    debt_balance = 0.0
    escrow_balance = 0.0
    last_period_end = month_ends[-1] if month_ends else handover_me
    for period_end in month_ends:
        rev = revenue_map.get(period_end, _PeriodRevenue(0.0, 0.0, 0.0))
        deposit_inflows = rev.deposit
        pre_handover_inflows = rev.pre_handover
        current_handover_inflow = rev.handover
        revenue_inflows = _round(deposit_inflows + pre_handover_inflows + current_handover_inflow)
        construction_active = construction_start_me <= period_end < handover_me
        cost_land = land_cost if period_end == land_period_end else 0.0
        cost_construction = monthly_construction if construction_active else 0.0
        marketing_and_sales = monthly_marketing
        cost_contingency = monthly_contingency if construction_active else 0.0
        cost_vat = monthly_vat if construction_active else 0.0
        operating_outflows = _round(
            cost_land + cost_construction + marketing_and_sales + cost_contingency + cost_vat
        )
        vat_refund_inflow = costs.vat_amount_aed if period_end == last_period_end else 0.0
        cash_before_debt = escrow_balance + revenue_inflows - operating_outflows
        debt_draw = (
            min(-cash_before_debt, max(debt_limit - debt_balance, 0.0))
            if cash_before_debt < 0
            else 0.0
        )
        commitment_fee_paid = _round(max(debt_limit - debt_balance, 0.0) * commitment_rate)
        interest_paid = _round(max(debt_balance, 0.0) * monthly_rate)
        debt_balance = _round(debt_balance + debt_draw + interest_paid + commitment_fee_paid)
        cash_after_debt = escrow_balance + revenue_inflows + debt_draw - operating_outflows
        debt_repayment = 0.0
        is_last = period_end == last_period_end
        if is_last or funding.debt_repayment_mode == "sales_sweep":
            debt_repayment = _round(min(max(cash_after_debt, 0.0), debt_balance))
            debt_balance = _round(debt_balance - debt_repayment)
        escrow_balance = _round(cash_after_debt - debt_repayment)
        equity_contribution = 0.0
        if escrow_balance < 0:
            equity_contribution = _round(-escrow_balance)
            escrow_balance = 0.0
        equity_distribution = 0.0
        if is_last and escrow_balance > 0:
            equity_distribution = _round(
                max(escrow_balance * (1 - funding.escrow_retention_pct / 100), 0.0)
            )
            escrow_balance = _round(escrow_balance - equity_distribution)
        cash_flow_periods.append(
            FeasibilityCashFlowPeriod(
                period_label=period_end.strftime("%b %Y"),
                period_end_date=period_end.date().isoformat(),
                revenue_inflows_aed=revenue_inflows,
                operating_outflows_aed=operating_outflows,
                debt_draw_aed=_round(debt_draw),
                debt_repayment_aed=debt_repayment,
                interest_paid_aed=interest_paid,
                commitment_fee_paid_aed=commitment_fee_paid,
                equity_contribution_aed=equity_contribution,
                equity_distribution_aed=equity_distribution,
                debt_balance_aed=_round(debt_balance),
                debt_headroom_aed=_round(max(debt_limit - debt_balance, 0.0)),
                escrow_balance_aed=_round(escrow_balance),
                unlevered_net_cash_flow_aed=_round(
                    revenue_inflows + vat_refund_inflow - operating_outflows
                ),
                levered_net_cash_flow_aed=_round(
                    revenue_inflows
                    - operating_outflows
                    + debt_draw
                    - debt_repayment
                    - equity_contribution
                    + equity_distribution
                ),
                deposit_inflows_aed=_round(deposit_inflows),
                pre_handover_inflows_aed=_round(pre_handover_inflows),
                handover_inflows_aed=_round(current_handover_inflow),
                land_loan_balance_aed=_round(min(debt_balance, debt_limit * 0.35)),
                construction_loan_balance_aed=_round(max(debt_balance - debt_limit * 0.35, 0.0)),
                cost_land_aed=_round(cost_land),
                cost_construction_aed=_round(cost_construction),
                cost_marketing_aed=_round(marketing_and_sales),
                cost_sales_agent_aed=0.0,
                cost_contingency_aed=_round(cost_contingency),
                cost_vat_aed=_round(cost_vat),
                land_draw_aed=_round(min(debt_draw, cost_land)),
                construction_draw_aed=_round(max(debt_draw - cost_land, 0.0)),
                vat_refund_inflows_aed=vat_refund_inflow,
            )
        )
    cash_flow = FeasibilityCashFlowSummary(periods=cash_flow_periods)

    project_cashflows = [period.unlevered_net_cash_flow_aed for period in cash_flow_periods]
    equity_cashflows = [
        -period.equity_contribution_aed + period.equity_distribution_aed
        for period in cash_flow_periods
    ]
    project_irr = _periodic_irr(project_cashflows, 12)
    equity_irr = _periodic_irr(equity_cashflows, 12)
    total_interest = _round(sum(period.interest_paid_aed for period in cash_flow_periods))
    total_commitment_fees = _round(
        sum(period.commitment_fee_paid_aed for period in cash_flow_periods)
    )
    total_equity_contributed = _round(
        sum(period.equity_contribution_aed for period in cash_flow_periods)
    )
    total_equity_distributed = _round(
        sum(period.equity_distribution_aed for period in cash_flow_periods)
    )
    all_in_project_cost = _round(
        costs.total_costs_incl_vat_aed + total_interest + total_commitment_fees
    )
    all_in_project_profit = _round(program.gross_revenue_aed - all_in_project_cost)
    returns = FeasibilityReturnsSummary(
        project_profit_aed=costs.gross_profit_aed,
        gross_margin_pct=costs.gross_margin_pct,
        all_in_project_profit_aed=all_in_project_profit,
        all_in_margin_pct=_round((all_in_project_profit / program.gross_revenue_aed) * 100)
        if program.gross_revenue_aed > 0
        else None,
        project_irr_pct=_round(project_irr) if project_irr is not None else None,
        project_moic=_round(program.gross_revenue_aed / costs.total_costs_incl_vat_aed, 3)
        if costs.total_costs_incl_vat_aed > 0
        else None,
        equity_irr_pct=_round(equity_irr) if equity_irr is not None else None,
        equity_moic=_round(total_equity_distributed / total_equity_contributed, 3)
        if total_equity_contributed > 0
        else None,
        peak_debt_aed=max((period.debt_balance_aed for period in cash_flow_periods), default=0.0),
        peak_equity_aed=max(
            (period.equity_contribution_aed for period in cash_flow_periods), default=0.0
        ),
        total_interest_paid_aed=total_interest,
        total_commitment_fees_aed=total_commitment_fees,
    )

    peak_debt = max((period.debt_balance_aed for period in cash_flow_periods), default=0.0)
    min_debt_headroom = min(
        (period.debt_headroom_aed for period in cash_flow_periods), default=funding.debt_funding_aed
    )
    arrangement_fee = _round(funding.debt_funding_aed * assumptions.arrangementFeePct / 100)
    initial_commitment_fee = _round(funding.debt_funding_aed * assumptions.commitmentFeePct / 100)
    total_finance_costs = _round(
        arrangement_fee + initial_commitment_fee + total_interest + total_commitment_fees
    )
    final_period = cash_flow_periods[-1] if cash_flow_periods else None
    financing = FeasibilityFinancingSummary(
        base_project_cost_aed=costs.total_costs_incl_vat_aed,
        all_in_project_cost_aed=_round(costs.total_costs_incl_vat_aed + total_finance_costs),
        all_in_cost_to_revenue_pct=_round(
            ((costs.total_costs_incl_vat_aed + total_finance_costs) / program.gross_revenue_aed)
            * 100
        )
        if program.gross_revenue_aed > 0
        else 0.0,
        presale_coverage_pct_at_construction=_round(
            (funding.presales_at_construction_start_aed / program.gross_revenue_aed) * 100
        )
        if program.gross_revenue_aed > 0
        else 0.0,
        required_completion_reserve_aed=_round(
            program.gross_revenue_aed * (funding.escrow_retention_pct / 100)
        ),
        completion_reserve_coverage_pct=_round(
            (
                (final_period.escrow_balance_aed if final_period else 0.0)
                / max(program.gross_revenue_aed * (funding.escrow_retention_pct / 100), 1.0)
            )
            * 100
        ),
        sponsor_release_capacity_aed=_round(
            sum(period.equity_distribution_aed for period in cash_flow_periods)
        ),
        debt_commitment_utilization_pct=_round((peak_debt / funding.debt_funding_aed) * 100)
        if funding.debt_funding_aed > 0
        else 0.0,
        debt_commitment_aed=funding.debt_funding_aed,
        peak_debt_aed=peak_debt,
        min_debt_headroom_aed=min_debt_headroom,
        arrangement_fee_aed=arrangement_fee,
        initial_commitment_fee_aed=initial_commitment_fee,
        capitalized_interest_aed=total_interest,
        commitment_fee_carry_aed=total_commitment_fees,
        total_finance_costs_aed=total_finance_costs,
        equity_contributed_aed=total_equity_contributed,
        equity_distributed_aed=total_equity_distributed,
        closing_debt_balance_aed=final_period.debt_balance_aed if final_period else 0.0,
        closing_escrow_balance_aed=final_period.escrow_balance_aed if final_period else 0.0,
    )

    validation = compute_validation_summary(site, program, study, costs, funding, returns)
    return FeasibilityWorkbook(
        generated_at=datetime.now(timezone.utc),
        plot_number=plot.plot_number,
        site=site,
        program=program,
        costs=costs,
        funding=funding,
        schedule=schedule,
        cash_flow=cash_flow,
        returns=returns,
        financing=financing,
        validation=validation,
    )


def compute_feasibility_summary(workbook: FeasibilityWorkbook) -> FeasibilityComputedSummary:
    return FeasibilityComputedSummary(
        plot_number=workbook.plot_number,
        usage=workbook.site.permitted_use,
        market_area=workbook.program.market_area,
        headline=workbook.program.headline,
        total_units=workbook.program.total_units,
        total_saleable_area_sqm=workbook.program.saleable_area_sqm,
        total_parking_spaces=workbook.program.total_parking_spaces,
        modeled_gfa_sqm=workbook.site.modeled_gfa_sqm or workbook.site.max_gfa_sqm,
        gross_saleable_area_sqm=workbook.site.gross_saleable_area_sqm,
        gsa_as_pct_of_gfa=_round(
            (workbook.program.saleable_area_sqm / workbook.site.max_gfa_sqm) * 100
        )
        if workbook.site.max_gfa_sqm > 0
        else None,
        weighted_avg_sales_rate_aed_per_sqm=workbook.program.weighted_avg_sales_rate_aed_per_sqm,
        gross_revenue_aed=workbook.program.gross_revenue_aed,
        total_costs_incl_vat_aed=workbook.costs.total_costs_incl_vat_aed,
        gross_profit_aed=workbook.costs.gross_profit_aed,
        gross_margin_pct=workbook.costs.gross_margin_pct,
        off_plan_proceeds_aed=workbook.funding.off_plan_proceeds_aed,
        debt_funding_aed=workbook.funding.debt_funding_aed,
        equity_funding_aed=workbook.funding.equity_funding_aed,
        funding_gap_aed=workbook.funding.funding_gap_aed,
        project_irr_pct=workbook.returns.project_irr_pct,
        equity_irr_pct=workbook.returns.equity_irr_pct,
        project_moic=workbook.returns.project_moic,
        equity_moic=workbook.returns.equity_moic,
        peak_debt_aed=workbook.returns.peak_debt_aed,
        total_interest_paid_aed=workbook.returns.total_interest_paid_aed,
        total_commitment_fees_aed=workbook.returns.total_commitment_fees_aed,
        validation=workbook.validation,
        warnings=[*workbook.site.warnings, *workbook.program.warnings],
    )


def compute_validation_summary(
    site: FeasibilitySiteEnvelope,
    program: FeasibilityProgramSummary,
    study: PlotResearch | None,
    costs: FeasibilityCostSummary,
    funding: FeasibilityFundingSummary,
    returns: FeasibilityReturnsSummary,
) -> ValidationSummary:
    issues: list[ValidationIssue] = []

    def add_issue(
        severity: Literal["hard_fail", "warning", "missing_evidence"],
        code: str,
        message: str,
        field: str | None = None,
    ) -> None:
        issues.append(ValidationIssue(severity=severity, code=code, message=message, field=field))

    if site.plot_area_sqm <= 0:
        add_issue(
            "hard_fail", "plot_area_invalid", "Plot area must be greater than zero.", "plotAreaSqm"
        )
    if site.max_gfa_sqm <= 0:
        add_issue("missing_evidence", "max_gfa_missing", "Maximum GFA is missing.", "max_gfa_sqm")
    if not site.is_verified:
        add_issue(
            "warning", "plot_not_verified", "GIS plot is not marked as verified.", "is_verified"
        )
    if program.saleable_area_sqm > max(site.modeled_gfa_sqm or site.max_gfa_sqm, 0) * 1.02:
        add_issue(
            "hard_fail",
            "saleable_exceeds_gfa",
            "Saleable area materially exceeds modeled GFA.",
            "saleable_area_sqm",
        )
    if study is not None:
        if not study.market_pricing:
            add_issue(
                "missing_evidence",
                "market_pricing_missing",
                "No existing-sales pricing evidence was found.",
            )
        if not study.off_plan_market_pricing:
            add_issue(
                "missing_evidence",
                "off_plan_pricing_missing",
                "No off-plan pricing curve was found.",
            )
        if not study.land_sales_evidence:
            add_issue(
                "missing_evidence",
                "land_sales_missing",
                "No land sale evidence was attached to the study.",
            )
    if costs.gross_margin_pct < 0:
        add_issue(
            "warning",
            "negative_gross_margin",
            "The current draft is loss-making before financing.",
            "gross_margin_pct",
        )
    if abs(funding.funding_gap_aed) > max(funding.total_uses_aed * 0.01, 1_000_000):
        add_issue(
            "warning",
            "funding_gap_present",
            "Current draft sources and uses do not reconcile cleanly.",
            "funding_gap_aed",
        )
    if returns.project_irr_pct is not None and returns.project_irr_pct < 0:
        add_issue("warning", "project_irr_negative", "Project IRR is negative.", "project_irr_pct")
    if returns.equity_irr_pct is not None and returns.equity_irr_pct < 0:
        add_issue("warning", "equity_irr_negative", "Equity IRR is negative.", "equity_irr_pct")

    hard_failures = sum(1 for issue in issues if issue.severity == "hard_fail")
    warnings = sum(1 for issue in issues if issue.severity == "warning")
    missing_evidence = sum(1 for issue in issues if issue.severity == "missing_evidence")
    status: Literal["ready", "needs_review", "invalid"]
    if hard_failures:
        status = "invalid"
    elif warnings or missing_evidence:
        status = "needs_review"
    else:
        status = "ready"
    return ValidationSummary(
        status=status,
        hard_failures=hard_failures,
        warnings=warnings,
        missing_evidence=missing_evidence,
        issues=issues,
    )
