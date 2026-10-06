from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import DateTime
from sqlmodel import JSON, Column, SQLModel
from sqlmodel import Field as SQLField

Usage = Literal["residential", "commercial", "mixed_use", "unknown"]
DevelopmentModel = Literal[
    "build_to_sell_residential",
    "build_to_rent_residential",
    "build_to_lease_commercial",
]


class GISLandUse(BaseModel):
    type: str
    use: str


class Plot(BaseModel):
    plot_number: str
    community_name: str
    project_name: str
    plot_area_sqm: float
    max_gfa_sqm: float
    max_height: str
    max_coverage: str
    gfa_type: str
    is_verified: bool
    land_use_summary: list[str] = Field(default_factory=list)


class LandPlot(Plot):
    """Backward-compatible alias for older feasibility imports."""


class PlotDetails(BaseModel):
    plot_number: str
    community_name: str
    project_name: str
    master_developer: str | None = None
    plot_area_sqm: float
    max_gfa_sqm: float
    max_gfa_sqft: float
    max_height: str
    max_coverage: str
    gfa_type: str
    far: float | None = None
    inferred_usage: Usage
    site_plan_issue_date: str | None = None
    site_plan_expiry_date: str | None = None
    is_verified: bool
    verify_comments: str | None = None
    land_use: list[GISLandUse] = Field(default_factory=list)
    general_notes: list[str] = Field(default_factory=list)
    setbacks: dict[str, str] = Field(default_factory=dict)
    coordinates: list[list[float]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class MarketPricingRow(BaseModel):
    unit_type: str
    transaction_count: int
    median_price_sqm: float
    avg_area_sqm: float | None = None


class RentalMarketSummary(BaseModel):
    area_name: str
    rental_contract_count_12m: int
    median_annual_rent: float | None = None
    avg_rent_price_sqm_12m: float | None = None
    gross_yield_pct: float | None = None
    top_developers: list[str] = Field(default_factory=list)
    top_master_projects: list[str] = Field(default_factory=list)


class RentalComparableProject(BaseModel):
    project_id: int
    project_name: str
    area_name: str
    completion_status: str | None = None
    pipeline_status: str | None = None
    score: float
    no_of_units: int | None = None
    rental_contract_count_12m: int = 0
    median_annual_rent: float | None = None
    avg_rent_price_sqm_12m: float | None = None
    gross_yield_pct: float | None = None
    rationale: list[str] = Field(default_factory=list)


class OffPlanPricingRow(BaseModel):
    unit_type: str
    horizon_bucket: str
    avg_months_to_completion: float
    transaction_count: int
    median_price_sqm: float
    avg_area_sqm: float | None = None
    last_transaction_date: str | None = None


class OffPlanPricingConfidence(BaseModel):
    target_horizon_months: int
    matched_transactions: int
    confidence_score: float
    confidence_label: Literal["high", "medium", "low"]
    sample_score: float
    horizon_score: float
    recency_score: float
    note: str


class OffPlanUnitPricingBenchmark(BaseModel):
    unit_type: str
    selected_horizon_bucket: str
    avg_months_to_completion: float
    transaction_count: int
    selected_price_sqm: float
    fallback_used: bool = False
    confidence_score: float
    confidence_label: Literal["high", "medium", "low"]
    sample_score: float
    horizon_score: float
    recency_score: float
    last_transaction_date: str | None = None
    note: str


class LandSaleEvidence(BaseModel):
    transaction_id: str
    instance_date: str
    area_name: str
    project_name: str
    procedure_name: str
    property_usage: str
    plot_area_sqm: float
    price_aed: float
    price_sqm: float
    price_per_gfa_sqm: float | None = None
    nearest_landmark: str | None = None


class RentalRateBySizeBand(BaseModel):
    unit_type_proxy: str  # studio / 1br / 2br / 3br / 4br+
    size_band_label: str  # e.g. "< 55 sqm"
    median_rent_psm_annual: float
    median_annual_rent: float
    contract_count: int


class ComparableProject(BaseModel):
    project_id: int
    project_name: str
    area_name: str
    project_status: str | None = None
    comparison_type: Literal["pricing", "pipeline"]
    score: float
    total_land_area_sqm: float | None = None
    land_area_delta_pct: float | None = None
    no_of_buildings: int | None = None
    no_of_units: int | None = None
    median_price_sqm: float | None = None
    dominant_unit_type: str | None = None
    rationale: list[str] = Field(default_factory=list)


class UnitTypeData(BaseModel):
    type: str
    count: int
    percentage: float
    avg_size_sqm: float
    avg_price_sqm: Optional[float]


class ComparableData(BaseModel):
    project_id: int
    project_name: str
    area_name: str
    no_of_buildings: int
    avg_floors: Optional[float]
    unit_mix: list[UnitTypeData]
    price_per_sqm_by_type: dict[str, float]


class PlotResearch(BaseModel):
    plot_number: str
    usage: Usage
    market_area: str
    headline: str
    summary: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    pricing_evidence: list[ComparableProject] = Field(default_factory=list)
    competition_evidence: list[ComparableProject] = Field(default_factory=list)
    land_sales_evidence: list[LandSaleEvidence] = Field(default_factory=list)
    market_pricing: list[MarketPricingRow] = Field(default_factory=list)
    off_plan_market_pricing: list[OffPlanPricingRow] = Field(default_factory=list)
    off_plan_pricing_confidence: OffPlanPricingConfidence | None = None
    off_plan_unit_benchmarks: list[OffPlanUnitPricingBenchmark] = Field(default_factory=list)
    rental_market_summary: RentalMarketSummary | None = None
    rental_comparables: list[RentalComparableProject] = Field(default_factory=list)
    rental_rates_by_size_band: list[RentalRateBySizeBand] = Field(default_factory=list)
    assumptions: "FeasibilityAssumptions"
    warnings: list[str] = Field(default_factory=list)
    land_cost_estimate_aed_low: float | None = None
    land_cost_estimate_aed_mid: float | None = None
    land_cost_estimate_aed_high: float | None = None


class ValidationIssue(BaseModel):
    code: str
    severity: Literal["hard_fail", "warning", "missing_evidence"]
    message: str
    field: str | None = None


class ValidationSummary(BaseModel):
    status: Literal["ready", "needs_review", "invalid"]
    hard_failures: int
    warnings: int
    missing_evidence: int
    issues: list[ValidationIssue] = Field(default_factory=list)


class FeasibilityUnitConfig(BaseModel):
    id: str
    label: str
    units: int
    avgSizeSqm: float
    sellingRatePsqm: float
    typicalFloor: int = 0
    parkingRatio: float = 0.0


class FeasibilityPaymentPlan(BaseModel):
    depositPct: float = 10.0
    constructionPct: float = 30.0
    handoverPct: float = 60.0


class FeasibilityVatApplicability(BaseModel):
    land: bool = True
    hardCosts: bool = True
    softCosts: bool = True
    permitFees: bool = True
    contingency: bool = True
    marketing: bool = True
    salesAdmin: bool = True


class BtrUnitConfig(BaseModel):
    id: str
    label: str
    units: int = 0
    avgSizeSqm: float = 0.0
    monthlyRentAed: float = 0.0
    parkingRatio: float = 0.0


class FeasibilityAssumptions(BaseModel):
    usage: Usage = "unknown"
    plotAreaSqm: float
    maxGfaSqm: float = 0.0
    maxCoveragePct: float = 0.0
    maxStoreys: int = 0
    maxFar: float
    numberOfTowers: int
    numberOfFloors: int
    buaMultiplier: float
    nsaEfficiencyPct: float
    landPricePsqm: float
    constructionCostPsqmBua: float
    designSupervisionPct: float
    salesAgentFeePct: float
    marketingCostPct: float
    contingencyPct: float
    financeRatePct: float
    arrangementFeePct: float
    commitmentFeePct: float
    debtToCostRatio: float
    presaleThresholdPct: float
    escrowRetentionPct: float
    standardParkingRatio: float
    largeUnitThresholdSqm: float
    largeUnitParkingRatio: float
    demolitionEnabled: bool
    salesCommencementDate: str
    salesPeriodMonths: int
    demolitionEnablingDate: str
    constructionDate: str
    handoverDate: str
    landAcquisitionCostOverrideAed: float = 0.0
    designSupervisionCostOverrideAed: float = 0.0
    constructionCostOverrideAed: float = 0.0
    demolitionCostAed: float
    infrastructureCostAed: float
    governmentFeesAed: float
    marketingCostOverrideAed: float = 0.0
    salesAgentFeesOverrideAed: float = 0.0
    masterCommunityFeesAed: float
    ffeOsePreopeningCostAed: float
    contingencyCostOverrideAed: float = 0.0
    midPointInflationPct: float
    vatPct: float
    debtFundingAed: float
    equityFundingAed: float
    brokerageFeeAed: float
    legalDdCostAed: float
    landAcquisitionDate: str
    landLoanLtvPct: float
    eiborRatePct: float
    landLoanSpreadBps: float
    constructionLoanSpreadBps: float
    preHandoverMilestoneDate: str
    debtRepaymentMode: Literal["bullet_at_handover", "sales_sweep"]
    unitConfigs: list[FeasibilityUnitConfig] = Field(default_factory=list)
    paymentPlan: FeasibilityPaymentPlan = Field(default_factory=FeasibilityPaymentPlan)
    developmentModel: DevelopmentModel = "build_to_sell_residential"
    basementParkingFloors: float = 4.0
    podiumFloors: float = 5.0
    residentialFloors: float = 30.0
    amenityRoofFloors: float = 1.0
    parkingAreaPerSpaceSqm: float = 30.0
    aboveGradeBuaFactor: float = 1.1
    serviceBohPlantPct: float = 0.03
    podiumParkingFloorsOutsideGfa: float = 0.0
    targetCoveragePct: float = 0.0
    targetBuildingCount: float = 0.0
    maxEfficientTowerFloorplateSqm: float = 0.0
    minEfficientTowerFloorplateSqm: float = 0.0
    floorToFloorHeightM: float = 3.2
    podiumFloorToFloorHeightM: float = 4.0
    groundFloorHeightM: float = 5.0
    roofPlantAllowanceM: float = 6.0
    landTransferFeePct: float = 0.04
    brokeragePct: float = 0.01
    legalDdPct: float = 0.005
    permitFeesPct: float = 0.02
    softCostPct: float = 0.15
    acquisitionDebtLtv: float = 0.7
    constructionDebtLtc: float = 0.7
    debtSpreadPa: float = 0.02
    financingFeePct: float = 0.01
    exitFeePct: float = 0.01
    preferredReturnPa: float = 0.08
    sponsorPromotePct: float = 0.2
    projectYears: float = 5.0
    constructionCurveSteepness: float = 8.0
    salesCurveSteepness: float = 8.0
    vatAppliesTo: FeasibilityVatApplicability = Field(default_factory=FeasibilityVatApplicability)
    vatRefundLagMonths: float = 6.0
    selectedScenario: Literal["base", "conservative", "optimistic"] = "base"
    btrUnitConfigs: list[BtrUnitConfig] = Field(default_factory=list)
    # All BTR scalar fields use 0.0 as "unset" sentinel — Pydantic schema cannot ship
    # `anyOf:[number,null]` to Gemini's structured-output API. _ensure_btr_assumptions
    # treats 0 as falsy and applies model defaults via `or` fallbacks.
    btrHoldPeriodYears: float = 0.0
    btrLeaseUpPaceUnitsPerMonth: float = 0.0
    btrStabilizedOccupancyPct: float = 0.0
    btrFreeRentMonths: float = 0.0
    btrAnnualRentGrowthPct: float = 0.0
    btrMarketRentGrowthPct: float = 0.0
    btrRenewalRentGrowthPct: float = 0.0
    btrGeneralVacancyPct: float = 0.0
    btrPropertyManagementPct: float = 0.0
    btrRepairsMaintenancePsqm: float = 0.0
    btrInsurancePsqm: float = 0.0
    btrServiceChargePsqm: float = 0.0
    btrUtilitiesPsqm: float = 0.0
    btrMarketingLeasingPct: float = 0.0
    btrCapexReservePct: float = 0.0
    btrParkingIncomeAed: float = 0.0
    btrAncillaryIncomeAed: float = 0.0
    btrAncillaryGrowthPct: float = 0.0
    btrStabilizedFreeRentMonths: float = 0.0
    btrOpExGrowthPct: float = 0.0
    btrDevCostEscalationPct: float = 0.0
    btrTerminalGrowthPct: float = 0.0
    btrLeaseUpMarketingAed: float = 0.0
    btrCreditLossPct: float = 0.0
    btrPayrollPsqm: float = 0.0
    btrGeneralAdminPct: float = 0.0
    btrContractServicesPsqm: float = 0.0
    btrModelUnits: float = 0.0
    btrExitCapRatePct: float = 0.0
    btrExitCostPct: float = 0.0
    btrPermDebtLtvPct: float = 0.0
    btrPermDebtRatePct: float = 0.0
    btrPermDebtSpreadBps: float = 0.0
    btrPermDebtAmortYears: float = 0.0
    btrPermDebtPointsPct: float = 0.0
    btrPermDebtIoYears: float = 0.0
    btrDscrMinimum: float = 0.0
    btrRefiCapRatePct: float = 0.0

    @field_validator(
        "maxCoveragePct",
        "maxStoreys",
        "landAcquisitionCostOverrideAed",
        "designSupervisionCostOverrideAed",
        "constructionCostOverrideAed",
        "marketingCostOverrideAed",
        "salesAgentFeesOverrideAed",
        "contingencyCostOverrideAed",
        mode="before",
    )
    @classmethod
    def _none_numeric_unset_to_zero(cls, value):
        return 0 if value is None else value


class FeasibilitySiteEnvelope(BaseModel):
    plot_number: str
    community_name: str
    project_name: str
    permitted_use: Usage
    plot_area_sqm: float
    max_gfa_sqm: float
    max_storeys: int | None = None
    far: float | None = None
    applied_coverage_pct: float | None = None
    buildable_footprint_sqm: float | None = None
    built_up_area_sqm: float | None = None
    modeled_gfa_sqm: float | None = None
    gross_saleable_area_sqm: float | None = None
    gfa_from_bua_efficiency_pct: float | None = None
    gsa_from_gfa_efficiency_pct: float | None = None
    max_height: str
    max_coverage: str
    gfa_type: str
    site_plan_issue_date: str | None = None
    site_plan_expiry_date: str | None = None
    is_verified: bool
    area_assumption_notes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class FeasibilityProgramRow(BaseModel):
    unit_type: str
    share_pct: float
    suggested_units: int
    avg_size_sqm: float
    saleable_area_sqm: float
    sales_rate_aed_per_sqm: float
    gross_revenue_aed: float
    parking_ratio: float = 0.0
    parking_spaces: float = 0.0


class FeasibilityProgramSummary(BaseModel):
    usage: Usage
    market_area: str
    headline: str
    gfa_sqm: float
    saleable_area_sqm: float
    saleable_efficiency_pct: float
    total_units: int
    total_parking_spaces: float = 0.0
    weighted_avg_sales_rate_aed_per_sqm: float
    gross_revenue_aed: float
    rows: list[FeasibilityProgramRow] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class FeasibilityCostLineItem(BaseModel):
    code: str
    label: str
    amount_aed: float
    basis: str
    basis_value: float | None = None
    basis_unit: str | None = None
    source: Literal["evidence", "heuristic", "derived", "input"] = "derived"
    timing_rule: Literal[
        "land_acquisition",
        "construction_straight_line",
        "sales_velocity",
        "non_cash_placeholder",
    ] = "construction_straight_line"
    timing_group: Literal[
        "land",
        "hard_cost",
        "professional_fees",
        "authority_and_infrastructure",
        "selling_costs",
        "contingency",
        "financing_fees",
        "other",
    ] = "other"


class FeasibilityCostSummary(BaseModel):
    total_costs_excl_vat_aed: float
    vat_amount_aed: float
    total_costs_incl_vat_aed: float
    cost_to_revenue_pct: float
    gross_profit_aed: float
    gross_margin_pct: float
    line_items: list[FeasibilityCostLineItem] = Field(default_factory=list)


class FeasibilityFundingSource(BaseModel):
    code: str
    label: str
    amount_aed: float
    basis: str


class FeasibilityFundingSummary(BaseModel):
    deposit_pct: float
    pre_handover_pct: float
    handover_pct: float
    presale_threshold_pct: float
    presales_at_construction_start_aed: float
    escrow_retention_pct: float
    debt_to_cost_ratio: float
    debt_repayment_mode: Literal["bullet_at_handover", "sales_sweep"]
    off_plan_proceeds_aed: float
    debt_funding_aed: float
    equity_funding_aed: float
    vat_refunds_aed: float
    total_sources_aed: float
    total_uses_aed: float
    funding_gap_aed: float
    sources: list[FeasibilityFundingSource] = Field(default_factory=list)


class FeasibilityScheduleSummary(BaseModel):
    sales_commencement_date: str
    construction_start_date: str
    handover_date: str
    sales_period_months: int
    construction_duration_months: int
    sales_to_handover_months: int


class FeasibilityCashFlowPeriod(BaseModel):
    period_label: str
    period_end_date: str
    revenue_inflows_aed: float
    operating_outflows_aed: float
    debt_draw_aed: float
    debt_repayment_aed: float
    interest_paid_aed: float
    commitment_fee_paid_aed: float
    equity_contribution_aed: float
    equity_distribution_aed: float
    debt_balance_aed: float
    debt_headroom_aed: float
    escrow_balance_aed: float
    unlevered_net_cash_flow_aed: float
    levered_net_cash_flow_aed: float
    deposit_inflows_aed: float = 0.0
    pre_handover_inflows_aed: float = 0.0
    handover_inflows_aed: float = 0.0
    land_loan_balance_aed: float = 0.0
    construction_loan_balance_aed: float = 0.0
    cost_land_aed: float = 0.0
    cost_construction_aed: float = 0.0
    cost_marketing_aed: float = 0.0
    cost_sales_agent_aed: float = 0.0
    cost_contingency_aed: float = 0.0
    cost_vat_aed: float = 0.0
    land_draw_aed: float = 0.0
    construction_draw_aed: float = 0.0
    vat_refund_inflows_aed: float = 0.0


class FeasibilityCashFlowSummary(BaseModel):
    periods: list[FeasibilityCashFlowPeriod] = Field(default_factory=list)


class FeasibilityReturnsSummary(BaseModel):
    project_profit_aed: float
    gross_margin_pct: float
    all_in_project_profit_aed: float | None = None
    all_in_margin_pct: float | None = None
    project_irr_pct: float | None = None
    project_moic: float | None = None
    equity_irr_pct: float | None = None
    equity_moic: float | None = None
    peak_debt_aed: float | None = None
    peak_equity_aed: float | None = None
    total_interest_paid_aed: float | None = None
    total_commitment_fees_aed: float | None = None


class FeasibilityFinancingSummary(BaseModel):
    base_project_cost_aed: float
    all_in_project_cost_aed: float
    all_in_cost_to_revenue_pct: float
    presale_coverage_pct_at_construction: float
    required_completion_reserve_aed: float
    completion_reserve_coverage_pct: float
    sponsor_release_capacity_aed: float
    debt_commitment_utilization_pct: float
    debt_commitment_aed: float
    peak_debt_aed: float
    min_debt_headroom_aed: float
    arrangement_fee_aed: float
    initial_commitment_fee_aed: float
    capitalized_interest_aed: float
    commitment_fee_carry_aed: float
    total_finance_costs_aed: float
    equity_contributed_aed: float
    equity_distributed_aed: float
    closing_debt_balance_aed: float
    closing_escrow_balance_aed: float


class FeasibilityWorkbook(BaseModel):
    generated_at: datetime
    plot_number: str
    site: FeasibilitySiteEnvelope
    program: FeasibilityProgramSummary
    costs: FeasibilityCostSummary
    funding: FeasibilityFundingSummary
    schedule: FeasibilityScheduleSummary
    cash_flow: FeasibilityCashFlowSummary
    returns: FeasibilityReturnsSummary
    financing: FeasibilityFinancingSummary
    validation: ValidationSummary


class FeasibilityComputedSummary(BaseModel):
    plot_number: str
    usage: Usage
    market_area: str
    headline: str
    total_units: int
    total_saleable_area_sqm: float
    total_parking_spaces: float
    modeled_gfa_sqm: float
    gross_saleable_area_sqm: float | None = None
    gsa_as_pct_of_gfa: float | None = None
    weighted_avg_sales_rate_aed_per_sqm: float
    gross_revenue_aed: float
    total_costs_incl_vat_aed: float
    gross_profit_aed: float
    gross_margin_pct: float
    off_plan_proceeds_aed: float
    debt_funding_aed: float
    equity_funding_aed: float
    funding_gap_aed: float
    project_irr_pct: float | None = None
    equity_irr_pct: float | None = None
    project_moic: float | None = None
    equity_moic: float | None = None
    peak_debt_aed: float | None = None
    total_interest_paid_aed: float | None = None
    total_commitment_fees_aed: float | None = None
    validation: ValidationSummary
    warnings: list[str] = Field(default_factory=list)


class StudyContext(BaseModel):
    headline: str = ""
    project_tier: str = "premium"
    positioning: str = ""
    summary_points: list[str] = Field(default_factory=list)
    unit_mix_rationale: str = ""
    pricing_rationale: str = ""
    cost_rationale: str = ""
    timing_rationale: str = ""
    financing_rationale: str = ""
    market_summary: str = ""


class GenerateStudyRequest(BaseModel):
    plot_number: str
    usage_override: Usage | None = None
    development_model: DevelopmentModel | None = None


class GenerateStudyResponse(BaseModel):
    status: str = "ready"
    plot_data: PlotDetails
    assumptions: FeasibilityAssumptions
    research: PlotResearch
    study_context: StudyContext
    chat: dict = Field(default_factory=lambda: {"history": []})


class FeasibilitySavedStudy(SQLModel, table=True):
    __tablename__ = "feasibility_studies"

    id: int | None = SQLField(default=None, primary_key=True)
    user_id: str = SQLField(index=True)
    organization_id: str = SQLField(index=True)
    name: str
    plot_number: str = SQLField(index=True)
    development_model: str
    assumptions: dict[str, Any] = SQLField(sa_column=Column(JSON, nullable=False))
    plot_data: dict[str, Any] = SQLField(sa_column=Column(JSON, nullable=False))
    research: dict[str, Any] = SQLField(sa_column=Column(JSON, nullable=False))
    study_context: dict[str, Any] = SQLField(sa_column=Column(JSON, nullable=False))
    chat_state: dict[str, Any] = SQLField(sa_column=Column(JSON, nullable=False))
    created_at: datetime = SQLField(sa_column=Column(DateTime(timezone=True), nullable=False))
    updated_at: datetime = SQLField(sa_column=Column(DateTime(timezone=True), nullable=False))


class FeasibilityChatStateMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str
    created_at: str | None = None


class FeasibilityChatState(BaseModel):
    messages: list[FeasibilityChatStateMessage] = Field(default_factory=list)
    history_json: str | None = None


class FeasibilityStudyCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    plot_number: str = Field(min_length=1)
    usage_override: Usage | None = None
    development_model: DevelopmentModel = "build_to_sell_residential"


class FeasibilityStudyUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    development_model: DevelopmentModel | None = None
    assumptions: dict[str, Any] | None = None
    plot_data: PlotDetails | None = None
    research: PlotResearch | None = None
    study_context: StudyContext | None = None
    chat_state: FeasibilityChatState | None = None


class FeasibilitySavedStudyResponse(BaseModel):
    id: int
    name: str
    plot_number: str
    development_model: DevelopmentModel
    assumptions: dict[str, Any]
    plot_data: PlotDetails
    research: PlotResearch
    study_context: StudyContext
    chat_state: FeasibilityChatState
    created_at: datetime
    updated_at: datetime


class FeasibilitySavedStudyListItem(BaseModel):
    id: int
    name: str
    plot_number: str
    development_model: DevelopmentModel
    plot_data: PlotDetails
    created_at: datetime
    updated_at: datetime


class FeasibilityChatRequest(BaseModel):
    messages: list[dict]
    plot_data: PlotDetails
    assumptions: dict[str, Any]
    research: dict | None = None
    history_json: str | None = None
