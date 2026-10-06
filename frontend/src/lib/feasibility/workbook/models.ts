import type {
	Plot,
	PlotDetails,
	PlotResearchOutput as PlotResearch,
	StudyContext
} from '$lib/api/generated/hey-api/types.gen'

export type { Plot, PlotDetails, PlotResearch, StudyContext }

// ── Canonical model input ────────────────────────────────────────────────────
// FeasibilityAssumptions is the authoritative input contract for computeWorkbook.

export type UsageType = 'residential' | 'commercial' | 'mixed_use' | 'unknown'
export type DebtRepaymentMode = 'bullet_at_handover' | 'sales_sweep'
export type DevelopmentModel =
	| 'build_to_sell_residential'
	| 'build_to_rent_residential'
	| 'build_to_lease_commercial'

export interface FeasibilityPaymentPlan {
	depositPct: number // "Booking" in template (default 10%)
	constructionPct: number // "Pre-Handover" in template (default 30%)
	handoverPct: number // "On-Handover" in template (default 60%)
}

export interface UnitConfig {
	id: string
	label: string
	units: number
	avgSizeSqm: number
	sellingRatePsqm: number
	parkingRatio: number
}

export interface VatApplicability {
	land: boolean
	hardCosts: boolean
	softCosts: boolean
	permitFees: boolean
	contingency: boolean
	marketing: boolean
	salesAdmin: boolean
}

export interface FeasibilityAssumptions {
	// Usage — drives area chain benchmarks; seeded from research, editable
	usage: UsageType

	// Plot / area — seeded from plot_data, used by area chain calculations
	plotAreaSqm: number
	maxGfaSqm: number // regulatory max GFA; seeded from plot_data.max_gfa_sqm
	maxCoveragePct: number | null // regulatory max coverage; seeded from plot_data.max_coverage (parsed)
	maxStoreys: number | null // regulatory max storeys; seeded from plot_data.max_height (parsed)
	maxFar: number

	// Plot display metadata — seeded from plot_data
	plotNumber?: string
	communityName?: string
	projectName?: string
	gfaType?: string | null
	sitePlanIssueDate?: string | null
	sitePlanExpiryDate?: string | null
	plotWarnings?: string[]

	buaMultiplier: number
	nsaEfficiencyPct: number
	numberOfTowers: number
	numberOfFloors: number

	// ── Site massing / physical test-fit heuristics ─────────────────────────
	targetCoveragePct?: number
	targetBuildingCount?: number
	maxEfficientTowerFloorplateSqm?: number
	minEfficientTowerFloorplateSqm?: number
	floorToFloorHeightM?: number
	podiumFloorToFloorHeightM?: number
	groundFloorHeightM?: number
	roofPlantAllowanceM?: number

	// Unit mix
	unitConfigs: UnitConfig[]
	paymentPlan: FeasibilityPaymentPlan

	// Parking
	standardParkingRatio: number
	largeUnitThresholdSqm: number
	largeUnitParkingRatio: number

	// Land costs
	landPricePsqm: number
	landAcquisitionCostOverrideAed: number | null
	brokerageFeeAed: number
	legalDdCostAed: number

	// Construction
	constructionCostPsqmBua: number
	constructionCostOverrideAed: number | null
	midPointInflationPct: number

	// Professional fees
	designSupervisionPct: number
	designSupervisionCostOverrideAed: number | null

	// Selling costs
	marketingCostPct: number
	marketingCostOverrideAed: number | null
	salesAgentFeePct: number
	salesAgentFeesOverrideAed: number | null

	// Other direct costs
	infrastructureCostAed: number
	governmentFeesAed: number
	masterCommunityFeesAed: number
	ffeOsePreopeningCostAed: number
	contingencyPct: number
	contingencyCostOverrideAed: number | null
	demolitionEnabled: boolean
	demolitionCostAed: number
	vatPct: number

	// Financing (legacy — kept for backward compat)
	debtToCostRatio: number
	landLoanLtvPct: number
	eiborRatePct: number
	landLoanSpreadBps: number
	constructionLoanSpreadBps: number
	arrangementFeePct: number
	commitmentFeePct: number
	presaleThresholdPct: number
	escrowRetentionPct: number
	debtRepaymentMode: DebtRepaymentMode
	debtFundingAed: number
	equityFundingAed: number
	financeRatePct: number

	// Schedule
	landAcquisitionDate: string
	demolitionEnablingDate: string
	salesCommencementDate: string
	salesPeriodMonths: number
	constructionDate: string
	handoverDate: string
	preHandoverMilestoneDate: string

	// ── NEW: Building configuration (Area Bridge) ────────────────────────────
	basementParkingFloors?: number // default 4
	podiumFloors?: number // default 5
	residentialFloors?: number // default 30
	amenityRoofFloors?: number // default 1
	parkingAreaPerSpaceSqm?: number // default 30

	// ── NEW: Area Bridge inputs ──────────────────────────────────────────────
	aboveGradeBuaFactor?: number // default 1.1
	serviceBohPlantPct?: number // default 0.03
	podiumParkingFloorsOutsideGfa?: number // default 0

	// ── NEW: Template-aligned cost percentages ───────────────────────────────
	landTransferFeePct?: number // default 0.04
	brokeragePct?: number // default 0.01 (% of land cost)
	legalDdPct?: number // default 0.005 (% of land cost)
	permitFeesPct?: number // default 0.02 (% of hard cost)
	softCostPct?: number // default 0.15 (% of hard cost)

	// ── NEW: Dual-tranche financing ──────────────────────────────────────────
	acquisitionDebtLtv?: number // default 0.70
	constructionDebtLtc?: number // default 0.70
	debtSpreadPa?: number // default 0.02 (annual spread over EIBOR)
	financingFeePct?: number // default 0.01 (% of total debt commitment)
	exitFeePct?: number // default 0.01 (% of opening debt at handover)

	// ── NEW: Equity waterfall ────────────────────────────────────────────────
	preferredReturnPa?: number // default 0.08
	sponsorPromotePct?: number // default 0.20
	projectYears?: number // default 5

	// ── NEW: S-curve configuration ───────────────────────────────────────────
	constructionCurveSteepness?: number // default 8
	salesCurveSteepness?: number // default 8

	// ── NEW: VAT per-category applicability ──────────────────────────────────
	vatAppliesTo?: VatApplicability
	vatRefundLagMonths?: number // default 6

	// ── NEW: Scenario selector (Phase 3) ─────────────────────────────────────
	selectedScenario?: 'base' | 'conservative' | 'optimistic'

	// ── Development model selector ───────────────────────────────────────────
	developmentModel?: DevelopmentModel

	// ── BTR (Build-to-Rent) assumptions ──────────────────────────────────────
	// Only used when developmentModel = 'build_to_rent_residential'
	btrUnitConfigs?: BtrUnitConfig[]
	btrHoldPeriodYears?: number // default 10
	btrLeaseUpPaceUnitsPerMonth?: number // default 20
	btrStabilizedOccupancyPct?: number // default 97
	btrFreeRentMonths?: number // default 0
	btrAnnualRentGrowthPct?: number // default 5
	btrMarketRentGrowthPct?: number // default 5 (new leases / market rent growth)
	btrRenewalRentGrowthPct?: number // default 5 (renewal rent growth)
	btrGeneralVacancyPct?: number // default 5

	// BTR operating expenses (AED/yr or % of EGR)
	btrPropertyManagementPct?: number // default 5 (% of EGR)
	btrRepairsMaintenancePsqm?: number // default 50 AED/sqm/yr
	btrInsurancePsqm?: number // default 10 AED/sqm/yr
	btrServiceChargePsqm?: number // default 80 AED/sqm/yr (Dubai RERA)
	btrUtilitiesPsqm?: number // default 30 AED/sqm/yr
	btrMarketingLeasingPct?: number // default 2 (% of EGR)
	btrCapexReservePct?: number // default 5 (% of NOI)

	// BTR other income (AED/yr)
	btrParkingIncomeAed?: number // default 0
	btrAncillaryIncomeAed?: number // default 0 (gym, pool, retail)
	btrAncillaryGrowthPct?: number // default 3

	// BTR lease details
	btrStabilizedFreeRentMonths?: number // default 0 (renewal concessions)

	// BTR OpEx escalation
	btrOpExGrowthPct?: number // default 3 (annual OpEx escalation %)
	btrDevCostEscalationPct?: number // default 4 (annual development cost escalation %)
	btrTerminalGrowthPct?: number // default 4 (forward NOI growth for terminal valuation)

	// BTR lease-up costs (replaces GDV-based marketing/sales-admin)
	btrLeaseUpMarketingAed?: number // default 0 (flat budget)

	// BTR additional OpEx line items
	btrCreditLossPct?: number // default 1 (% of TPI, separate from vacancy)
	btrPayrollPsqm?: number // default 40 (AED/sqm/yr — building staff)
	btrGeneralAdminPct?: number // default 1 (% of EGR — G&A)
	btrContractServicesPsqm?: number // default 25 (AED/sqm/yr — cleaning, landscaping)
	btrModelUnits?: number // default 1 (non-revenue show/model unit)

	// BTR exit / valuation
	btrExitCapRatePct?: number // default 5.5
	btrExitCostPct?: number // default 6 (4% DLD + 1% broker + 1% legal)

	// BTR permanent debt (refi at stabilization)
	btrPermDebtLtvPct?: number // default 65
	btrPermDebtRatePct?: number // default 6 (all-in)
	btrPermDebtSpreadBps?: number // default 165 (over EIBOR; derives all-in rate when set)
	btrPermDebtAmortYears?: number // default 25
	btrPermDebtPointsPct?: number // default 1 (points/fees on perm loan)
	btrPermDebtIoYears?: number // default 1 (interest-only period)
	btrDscrMinimum?: number // default 1.25
	btrRefiCapRatePct?: number // default 5.5 (valuation cap at refi)
}

export interface BtrUnitConfig {
	id: string
	label: string // e.g. "Studio", "1BR", "2BR"
	units: number
	avgSizeSqm: number
	monthlyRentAed: number // gross rent per unit per month
	parkingRatio: number
}

export interface FeasibilityChatMessage {
	role: 'system' | 'user' | 'assistant'
	content: string
	created_at?: string
}

export interface FeasibilityChatState {
	messages: FeasibilityChatMessage[]
	history_json: string | null
}

// ── Workbook-first study shape ───────────────────────────────────────────────
// assumptions is the canonical mutable model.
// outputs is derived reactively from assumptions by computeWorkbook.
// study_context and research are secondary — display and evidence, not model inputs.

export interface FeasibilityStudy {
	status: 'ready'
	plot_data: PlotDetails
	assumptions: FeasibilityAssumptions
	study_context: StudyContext
	research: PlotResearch
	chat: {
		history: FeasibilityChatMessage[]
	}
}

export interface PlotDataResponse {
	plot_data: PlotDetails
}
