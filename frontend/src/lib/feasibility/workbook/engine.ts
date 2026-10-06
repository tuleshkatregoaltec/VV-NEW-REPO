// ══════════════════════════════════════════════════════════════════════════════
// Workbook Engine — Template-aligned implementation
// ══════════════════════════════════════════════════════════════════════════════
// Core contract: computeWorkbook(assumptions) → outputs
// All calculations derive from assumptions. No external dependencies.
//
// Aligned to: "Developer Feasibility Model - VAT & Scenarios.xlsx"
// Key features: dual-tranche debt, S-curve allocation, per-category VAT
// with refund lag, area bridge, equity waterfall, annual CF rollup.
// ══════════════════════════════════════════════════════════════════════════════

import { SQM_TO_SQFT } from '$lib/utils/units'
import { BTR_WORKBOOK_DEFAULTS, WORKBOOK_OPTION_DEFAULTS } from './defaults'
import type { BtrUnitConfig, FeasibilityAssumptions, UsageType } from './models'

// ── Defaults for optional assumption fields ─────────────────────────────────

const DEFAULTS = WORKBOOK_OPTION_DEFAULTS

function d<K extends keyof typeof DEFAULTS>(
	a: FeasibilityAssumptions,
	key: K
): (typeof DEFAULTS)[K] {
	const v = (a as unknown as Record<string, unknown>)[key]
	return (v !== undefined && v !== null ? v : DEFAULTS[key]) as (typeof DEFAULTS)[K]
}

function positiveOverride(value: number | null | undefined): number | undefined {
	return typeof value === 'number' && Number.isFinite(value) && value > 0 ? value : undefined
}

function assumptionNumber(a: FeasibilityAssumptions, key: string, fallback: number): number {
	const value = (a as unknown as Record<string, unknown>)[key]
	return typeof value === 'number' && Number.isFinite(value) ? value : fallback
}

function positiveAssumptionNumber(
	a: FeasibilityAssumptions,
	key: string,
	fallback: number
): number {
	const value = assumptionNumber(a, key, fallback)
	return value > 0 ? value : fallback
}

// ── Output Types ─────────────────────────────────────────────────────────────

export interface AreaBridgeOutputs {
	plotAreaSqm: number
	maxGfaSqm: number
	maxStoreys: number | null
	aboveGradeCostableBua: number
	basementParkingBua: number
	podiumParkingBuaAddon: number
	serviceBohPlantAddon: number
	totalCostableBua: number
	sellableArea: number
	nsaGfaRatio: number
	nsaCostableBuaRatio: number
	costableBuaGfaRatio: number
	// Legacy compat fields
	appliedCoveragePct: number
	buildableFootprintSqm: number
	builtUpAreaSqm: number
	modeledGfaSqm: number
	grossSaleableAreaSqm: number
	parkingBuaAllowanceSqm: number
	totalBuaSqm: number
	notes: string[]
}

// Alias for backward compat
export type AreaOutputs = AreaBridgeOutputs

export interface BuildingScheduleRow {
	id: string
	label: string
	buildingType: 'tower' | 'mid_rise_block' | 'low_rise_block'
	footprintSqm: number
	grossFloorplateSqm: number
	netFloorplateSqm: number
	allocatedGfaSqm: number
	residentialFloors: number
	podiumFloors: number
	amenityFloors: number
	totalFloors: number
	estimatedHeightM: number
	unitsPerTypicalFloor: number
	totalUnits: number
	warnings: string[]
}

export interface SiteMassingOutputs {
	plotAreaSqm: number
	maxGfaSqm: number
	buildingForm: BuildingForm
	appliedCoveragePct: number
	coveredFootprintSqm: number
	totalFootprintSqm: number
	physicalMaxGfaSqm: number
	requiredFloorsAtCoverage: number
	requiredResidentialFloorsForUnits: number
	requiredTotalFloorsForProgram: number
	requiredCoverageAtMaxStoreysPct: number
	gfaShortfallSqm: number
	buildingCount: number
	typicalGrossFloorplateSqm: number
	weightedAvgUnitSizeSqm: number
	targetUnitCount: number
	unitCapacityGap: number
	totalPhysicalUnitCapacity: number
	totalAllocatedGfaSqm: number
	gfaUtilizationPct: number
	coverageUtilizationPct: number
	estimatedMaxHeightM: number
	buildings: BuildingScheduleRow[]
	warnings: string[]
}

export interface ProgramRow {
	id: string
	label: string
	units: number
	avgSizeSqm: number
	totalAreaSqm: number
	sellingRatePsqm: number
	revenueAed: number
	parkingSpaces: number
}

export interface ProgramOutputs {
	rows: ProgramRow[]
	totalUnits: number
	totalAreaSqm: number
	totalParkingSpaces: number
	grossRevenueAed: number
	weightedAvgSalesRatePsqm: number
}

export interface CostOutputs {
	// Acquisition costs
	landAcquisitionAed: number
	landTransferFeeAed: number
	brokerageFeeAed: number
	legalDdCostAed: number
	totalLandCostAed: number // acquisition subtotal

	// Construction costs
	permitFeesAed: number
	hardCostAed: number
	softCostAed: number
	contingencyCostAed: number
	totalConstructionCostAed: number // construction subtotal

	// Revenue-linked costs
	marketingCostAed: number
	salesAdminCostAed: number
	totalRevenueCostAed: number // revenue subtotal

	// VAT per-category
	vatLandAed: number
	vatHardCostAed: number
	vatSoftCostAed: number
	vatPermitFeesAed: number
	vatContingencyAed: number
	vatMarketingAed: number
	vatSalesAdminAed: number
	totalVatAed: number

	// Totals
	totalDevCostExclVatAed: number
	totalDevCostInclVatAed: number

	// Legacy compat aliases
	constructionCostAed: number
	inflationCostAed: number
	constructionCostInclInflationAed: number
	designSupervisionCostAed: number
	salesAgentFeesAed: number
	infrastructureCostAed: number
	governmentFeesAed: number
	masterCommunityFeesAed: number
	ffeOsePreopeningCostAed: number
	demolitionCostAed: number
	totalCostsExclVatAed: number
	vatAmountAed: number
	totalCostsInclVatAed: number
}

export interface FundingOutputs {
	// Payment plan
	depositPct: number
	preHandoverPct: number
	handoverPct: number
	// Debt parameters (from assumptions — informational)
	landLoanCapacityAed: number
	constructionLoanCapacityAed: number
	totalDebtCapacityAed: number
	landLoanRatePct: number
	constructionLoanRatePct: number
	// Actual funding (derived from CF — single source of truth)
	offPlanProceedsAed: number
	debtFundingAed: number
	equityFundingAed: number
	vatRefundsAed: number
	peakDebtAed: number
	peakEquityAed: number
	// Cash reconciliation (cumulative flows — NOT the capital-stack S&U sheet)
	cashReconSourcesAed: number
	cashReconUsesAed: number
	cashReconGapAed: number
}

export interface CashFlowPeriod {
	periodLabel: string
	periodEndDate: string
	// S-curve percentages
	constructionCurvePct: number
	salesCurvePct: number
	// Revenue inflows
	revenueInflowsAed: number
	depositInflowsAed: number
	preHandoverInflowsAed: number
	handoverInflowsAed: number
	contractedRevenueAed: number
	// Cost outflows (S-curve allocated)
	costLandAed: number
	costLandFeesAed: number
	costPermitFeesAed: number
	costHardAed: number
	costSoftAed: number
	costContingencyAed: number
	costMarketingAed: number
	costSalesAdminAed: number
	operatingOutflowsAed: number
	// VAT
	vatPaidAed: number
	vatRefundInflowsAed: number
	// Financing costs
	financingFeeAed: number
	exitFeeAed: number
	interestAcqAed: number
	interestConAed: number
	interestPaidAed: number
	// Total uses
	totalUsesAed: number
	// Net CF
	unleveredNetCashFlowAed: number
	netCfBeforeDebtAed: number
	// Debt — acquisition tranche
	acqEligibleUsesAed: number
	acqDebtCommitmentAed: number
	openingAcqDebtAed: number
	acqDebtDrawAed: number
	acqDebtRepaymentAed: number
	closingAcqDebtAed: number
	// Debt — construction tranche
	conEligibleUsesAed: number
	cumulativeConEligibleAed: number
	conDebtMaxAllowedAed: number
	openingConDebtAed: number
	conDebtDrawAed: number
	conDebtRepaymentAed: number
	closingConDebtAed: number
	// Debt totals
	debtDrawAed: number
	debtRepaymentAed: number
	debtBalanceAed: number
	debtHeadroomAed: number
	// Equity
	equityContributionAed: number
	equityDistributionAed: number
	leveredNetCashFlowAed: number
	// Legacy compat
	commitmentFeePaidAed: number
	landLoanBalanceAed: number
	constructionLoanBalanceAed: number
	costPaidFromEscrowAed: number
	escrowBalanceAed: number
	landDrawAed: number
	constructionDrawAed: number
	costConstructionAed: number
	costProfessionalFeesAed: number
	costSalesAgentAed: number
	costInfrastructureAed: number
	costAuthorityFeesAed: number
	costCommunityFeesAed: number
	costVatAed: number
}

export interface CashFlowOutputs {
	periods: CashFlowPeriod[]
	totalRevenueAed: number
	totalCostsAed: number
	peakFundingAed: number
}

function peakNetSponsorCapital(periods: CashFlowPeriod[]): number {
	let runningEquityAtRisk = 0
	let peakEquityAtRisk = 0
	for (const period of periods) {
		runningEquityAtRisk = round(
			runningEquityAtRisk + period.equityContributionAed - period.equityDistributionAed
		)
		peakEquityAtRisk = Math.max(peakEquityAtRisk, runningEquityAtRisk)
	}
	return round(peakEquityAtRisk)
}

export interface ReturnsOutputs {
	grossProfitAed: number
	grossMarginPct: number
	allInProjectCostAed: number
	allInProjectProfitAed: number
	allInMarginPct: number
	projectIrrPct: number | null
	projectMoic: number
	equityIrrPct: number | null
	equityMoic: number
	totalInterestPaidAed: number
	totalCommitmentFeesAed: number
	arrangementFeeAed: number
	peakDebtAed: number
	peakEquityAed: number
	// New template metrics
	leveredMarginOnEquityPct: number
	debtAsPctOfCost: number
	breakEvenSaleRateAedSqft: number
	averageDebtOutstandingAed: number
	financingFeeAed: number
	exitFeeAed: number
	totalFinancingCostsAed: number
}

export interface FinancingOutputs {
	baseProjectCostAed: number
	allInProjectCostAed: number
	allInCostToRevenuePct: number
	presaleCoveragePctAtConstruction: number
	requiredCompletionReserveAed: number
	completionReserveCoveragePct: number
	sponsorReleaseCapacityAed: number
	debtCommitmentUtilizationPct: number
	debtCommitmentAed: number
	peakDebtAed: number
	minDebtHeadroomAed: number
	arrangementFeeAed: number
	initialCommitmentFeeAed: number
	capitalizedInterestAed: number
	commitmentFeeCarryAed: number
	totalFinanceCostsAed: number
	equityContributedAed: number
	equityDistributedAed: number
	closingDebtBalanceAed: number
	closingEscrowBalanceAed: number
}

export interface BudgetTimingPeriod {
	periodLabel: string
	periodEndDate: string
	budgetedCostsAed: number
	sellingCostsAed: number
	constructionRelatedCostsAed: number
	vatCostsAed: number
}

export interface BudgetTimingOutputs {
	periods: BudgetTimingPeriod[]
	totalBudgetedCostsAed: number
}

export interface SourcesUsesRow {
	category: 'source' | 'use'
	code: string
	label: string
	amountAed: number
	basis: string
}

export interface SourcesUsesOutputs {
	sources: SourcesUsesRow[]
	uses: SourcesUsesRow[]
	totalSourcesAed: number
	totalUsesAed: number
	gapAed: number
}

export interface WaterfallOutputs {
	totalEquityContributions: number
	totalEquityDistributions: number
	returnOfCapital: number
	cashRemainingAfterRoc: number
	preferredReturnHurdle: number
	preferredReturnPaid: number
	cashRemainingAfterPref: number
	residualToEquity: number
	sponsorPromote: number
}

export interface VatBridgeOutputs {
	categories: Array<{
		label: string
		costAed: number
		vatApplicable: boolean
		vatAed: number
	}>
	totalCostAed: number
	totalVatAed: number
	totalVatPaidMonthly: number
	totalVatRefunded: number
	netVatPosition: number
}

export interface MilestonesOutputs {
	landAcquisition: string
	constructionStart: string
	salesCommencement: string
	preHandoverMilestone: string
	handover: string
	constructionMonths: number
	salesPeriodMonths: number
	totalProjectMonths: number
}

export interface AnnualCashFlowRow {
	year: number
	revenueAed: number
	costsAed: number
	unleveredCfAed: number
	debtDrawAed: number
	debtRepayAed: number
	interestAed: number
	equityInAed: number
	equityOutAed: number
	leveredCfAed: number
	closingDebtAed: number
}

export interface AnnualCashFlowOutputs {
	rows: AnnualCashFlowRow[]
}

// ── BTR (Build-to-Rent) Output Types ─────────────────────────────────────────

export interface BtrProgramRow {
	id: string
	label: string
	units: number
	avgSizeSqm: number
	totalAreaSqm: number
	monthlyRentAed: number
	annualRentAed: number // units × monthlyRent × 12
	parkingSpaces: number
}

export interface BtrProgramOutputs {
	rows: BtrProgramRow[]
	totalUnits: number
	totalAreaSqm: number
	totalParkingSpaces: number
	grossPotentialRentAed: number // annual at 100% occupancy, no concessions
	weightedAvgRentPsqmMonth: number
}

export interface BtrOperatingYear {
	year: number
	yearLabel: string
	isLeaseUp: boolean
	occupancyPct: number
	// Revenue
	grossPotentialRentAed: number
	modelUnitDeductionAed: number // non-revenue show unit deduction
	concessionsAed: number
	effectiveRentalIncomeAed: number
	otherIncomeAed: number
	totalPotentialIncomeAed: number
	vacancyAed: number // vacancy loss (% of TPI)
	creditLossAed: number // credit loss (% of TPI)
	vacancyCreditLossAed: number // combined for backward compat
	effectiveGrossRevenueAed: number
	// Expenses
	propertyManagementAed: number
	repairsMaintenanceAed: number
	payrollAed: number // building staff cost
	generalAdminAed: number // G&A
	contractServicesAed: number // cleaning, landscaping
	insuranceAed: number
	serviceChargeAed: number
	utilitiesAed: number
	marketingLeasingAed: number
	totalOpExAed: number
	opExRatio: number
	// NOI & CFO
	noiAed: number
	capexReserveAed: number
	cfoAed: number // Cash Flow from Operations
	// Permanent debt service (post-refi)
	debtServiceAed: number
	cfafAed: number // Cash Flow After Financing
}

export interface BtrUnitIncomeYear {
	id: string
	label: string
	units: number
	grossPotentialRentAed: number
	effectiveRentalIncomeAed: number
}

export interface BtrOperatingMonth {
	month: number
	periodLabel: string
	year: number
	isLeaseUp: boolean
	occupancyPct: number
	grossPotentialRentAed: number
	unitTypeIncomes: BtrUnitIncomeYear[]
	modelUnitDeductionAed: number
	concessionsAed: number
	effectiveRentalIncomeAed: number
	otherIncomeAed: number
	totalPotentialIncomeAed: number
	vacancyAed: number
	creditLossAed: number
	vacancyCreditLossAed: number
	effectiveGrossRevenueAed: number
	propertyManagementAed: number
	repairsMaintenanceAed: number
	payrollAed: number
	generalAdminAed: number
	contractServicesAed: number
	insuranceAed: number
	serviceChargeAed: number
	utilitiesAed: number
	marketingLeasingAed: number
	totalOpExAed: number
	opExRatio: number
	noiAed: number
	capexReserveAed: number
	cfoAed: number
	debtServiceAed: number
	cfafAed: number
}

export interface BtrExitOutputs {
	exitYear: number
	terminalNoiAed: number
	exitCapRatePct: number
	grossSalePriceAed: number
	exitCostsAed: number
	netSaleProceedsAed: number
	// Yield metrics
	devYieldPct: number // stabilized NOI / total dev cost
	grossYieldPct: number // gross rent / total dev cost
	netYieldPct: number // stabilized NOI / net sale proceeds
	developmentSpreadBps: number // dev yield minus exit cap rate
}

export interface BtrPermDebtOutputs {
	stabilizedValueAed: number
	maxPermDebtAed: number // LTV × stabilized value
	dscrConstrained: boolean // true if DSCR limits debt below LTV
	actualPermDebtAed: number
	ioDebtServiceAed: number // interest-only annual payment (during IO period)
	annualDebtServiceAed: number // fully amortizing P&I annual payment
	dscrAtOrigination: number
	debtYieldPct: number // NOI / debt balance
	loanPayoffAed: number // remaining balance at exit (after IO + partial amortization)
	refiProceedsAed: number // net proceeds distributed at refi (perm loan - dev debt payoff)
	refiPointsCostAed: number // points/fees on permanent loan
}

export interface BtrReturnsOutputs {
	// Development phase
	totalDevCostAed: number
	totalDevFinancingCostsAed: number
	totalProjectCostAed: number
	// Operating returns
	stabilizedNoiAed: number
	stabilizedYieldOnCostPct: number
	// Full-cycle returns
	unleveredIrrPct: number | null
	unleveredXirrPct: number | null
	unleveredMoic: number
	leveredIrrPct: number | null
	leveredXirrPct: number | null
	leveredMoic: number
	totalProfitAed: number
	totalEquityInvestedAed: number
	peakEquityAed: number
	// Dev funding breakdown
	devDebtFundedAed: number
	devEquityFundedAed: number
	devInterestReserveAed: number
	devDebtCarryToRefiAed: number
}

export interface BtrSensitivityCase {
	label: string
	exitCapRatePct: number
	rentGrowthPct: number
	stabilizedYieldOnCostPct: number
	unleveredIrrPct: number | null
	leveredIrrPct: number | null
	leveredMoic: number
	grossSalePriceAed: number
	totalProfitAed: number
}

export interface BtrSensitivityOutputs {
	exitCapRate: BtrSensitivityCase[]
	rentGrowth: BtrSensitivityCase[]
	hardCost: BtrSensitivityCase[]
	occupancy: BtrSensitivityCase[]
	permDebtLtv: BtrSensitivityCase[]
}

export interface BtrWaterfallYear {
	yearLabel: string
	distributableCashFlowAed: number
	returnOfCapitalAed: number
	preferredReturnAed: number
	lpDistributionAed: number
	gpDistributionAed: number
	endingUnreturnedCapitalAed: number
	endingAccruedPrefAed: number
}

export interface BtrWaterfallOutputs {
	preferredReturnPct: number
	sponsorPromotePct: number
	totalDistributableCashFlowAed: number
	totalReturnOfCapitalAed: number
	totalPreferredReturnAed: number
	totalLpDistributionAed: number
	totalGpDistributionAed: number
	endingUnreturnedCapitalAed: number
	endingAccruedPrefAed: number
	years: BtrWaterfallYear[]
}

/** Annual row for BTR full-cycle CF (dev + ops + exit in one timeline) */
export interface BtrAnnualCashFlowRow {
	yearLabel: string
	yearIndex: number // 0 = dev start
	// Development
	devCostsAed: number
	devDebtDrawAed: number
	devDebtRepaymentAed: number
	devInterestAed: number
	devEquityAed: number
	// Operating
	cfoAed: number
	// Permanent debt
	permDebtProceedsAed: number
	permDebtServiceAed: number
	permLoanPayoffAed: number
	// Disposition
	salePriceAed: number
	saleExpensesAed: number
	// Net flows
	unleveredCfAed: number
	leveredCfAed: number
}

export interface BtrDevCostOutputs {
	// Acquisition costs (same as BTS)
	landAcquisitionAed: number
	landTransferFeeAed: number
	brokerageFeeAed: number
	legalDdCostAed: number
	totalLandCostAed: number
	// Construction costs
	permitFeesAed: number
	hardCostAed: number
	softCostAed: number
	contingencyCostAed: number
	totalConstructionCostAed: number
	// Statutory & development costs (same categories as BTS)
	infrastructureCostAed: number
	governmentFeesAed: number
	masterCommunityFeesAed: number
	ffeOsePreopeningCostAed: number
	demolitionCostAed: number
	// Lease-up costs (replaces GDV-based marketing/sales-admin)
	leaseUpMarketingAed: number
	// VAT
	totalVatAed: number
	// Totals
	totalDevCostExclVatAed: number
	totalDevCostInclVatAed: number
}

export interface BtrDevPeriod {
	month: number
	periodLabel: string
	// Cost breakdown
	costOutflowAed: number // operating outflows excl. VAT (matches BTS operatingOutflowsAed)
	vatPaidAed: number
	vatRefundAed: number
	// Debt — dual-tranche
	acqDebtDrawAed: number
	acqDebtBalanceAed: number
	conDebtDrawAed: number
	conDebtBalanceAed: number
	devDebtDrawAed: number // acqDraw + conDraw (for backward compat)
	devDebtBalanceAed: number // acqBalance + conBalance (for backward compat)
	interestAed: number
	financingFeeAed: number
	exitFeeAed: number
	// Equity
	equityContributionAed: number
	// Total uses (costOutflow + vatPaid + interest)
	totalUsesAed: number
}

export interface BtrSourcesUses {
	// Uses
	totalDevCostExclVatAed: number
	totalVatAed: number
	devFinancingCostsAed: number
	totalUsesAed: number
	// Sources
	peakAcqDebtAed: number
	peakConDebtAed: number
	actualEquityAed: number
	vatRefundsAed: number
	totalSourcesAed: number
}

export interface BtrOutputs {
	program: BtrProgramOutputs
	devCosts: BtrDevCostOutputs
	devCashFlow: BtrDevPeriod[]
	operatingMonths: BtrOperatingMonth[]
	operatingYears: BtrOperatingYear[]
	exit: BtrExitOutputs
	permDebt: BtrPermDebtOutputs
	returns: BtrReturnsOutputs
	annualCashFlow: BtrAnnualCashFlowRow[]
	sourcesUses: BtrSourcesUses
	sensitivities: BtrSensitivityOutputs
	waterfall: BtrWaterfallOutputs
	// Stabilization info
	stabilizationYear: number // 1-based operating year when stabilized
	leaseUpMonths: number
}

export interface WorkbookOutputs {
	area: AreaBridgeOutputs
	siteMassing: SiteMassingOutputs
	program: ProgramOutputs
	costs: CostOutputs
	funding: FundingOutputs
	cashFlow: CashFlowOutputs
	returns: ReturnsOutputs
	financing: FinancingOutputs
	budgetTiming: BudgetTimingOutputs
	sourcesUses: SourcesUsesOutputs
	waterfall: WaterfallOutputs
	vatBridge: VatBridgeOutputs
	milestones: MilestonesOutputs
	annualCashFlow: AnnualCashFlowOutputs
	// BTR outputs — only populated when developmentModel = 'build_to_rent_residential'
	btr?: BtrOutputs
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function round(value: number, digits = 2): number {
	const factor = 10 ** digits
	return Math.round(value * factor) / factor
}

function parseIsoDate(s: string, fallback: Date): Date {
	const parsed = new Date(s)
	return Number.isNaN(parsed.getTime()) ? fallback : parsed
}

function monthsBetween(a: Date, b: Date): number {
	return Math.max(
		(b.getUTCFullYear() - a.getUTCFullYear()) * 12 + (b.getUTCMonth() - a.getUTCMonth()),
		0
	)
}

function addMonths(dt: Date, months: number): Date {
	return new Date(Date.UTC(dt.getUTCFullYear(), dt.getUTCMonth() + months, 1))
}

function endOfMonth(d: Date): Date {
	return new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 0))
}

function iterMonthEnds(start: Date, end: Date): Date[] {
	let cursor = endOfMonth(start)
	const periods: Date[] = []
	while (cursor < end) {
		periods.push(cursor)
		cursor = endOfMonth(addMonths(cursor, 1))
	}
	periods.push(endOfMonth(end))
	return periods.filter((m, i) => i === 0 || m.getTime() !== periods[i - 1].getTime())
}

function periodicIrr(cashFlows: number[], periodsPerYear: number): number | null {
	if (!cashFlows.some((cf) => cf > 0) || !cashFlows.some((cf) => cf < 0)) return null
	const npv = (rate: number) => cashFlows.reduce((sum, cf, idx) => sum + cf / (1 + rate) ** idx, 0)
	let rate = 0.05
	const minRate = -0.9999
	const maxRate = 5.0
	let newtonConverged = false
	for (let i = 0; i < 100; i++) {
		const n = npv(rate)
		const dn = cashFlows.reduce((sum, cf, idx) => sum - (idx * cf) / (1 + rate) ** (idx + 1), 0)
		if (!Number.isFinite(n) || !Number.isFinite(dn)) break
		if (Math.abs(dn) < 1e-10) break
		let nextRate = rate - n / dn
		if (!Number.isFinite(nextRate)) break
		nextRate = Math.max(Math.min(nextRate, maxRate), minRate)
		if (Math.abs(nextRate - rate) < 1e-7) {
			rate = nextRate
			newtonConverged = true
			break
		}
		rate = nextRate
	}
	if (newtonConverged && rate > minRate && rate < maxRate && Number.isFinite(rate)) {
		const annualised = ((1 + rate) ** periodsPerYear - 1) * 100
		if (Number.isFinite(annualised)) return annualised
	}
	let lo = -0.999
	let hi = 5.0
	let npvLo = npv(lo)
	const npvHi = npv(hi)
	if (!Number.isFinite(npvLo) || !Number.isFinite(npvHi)) return null
	if (npvLo * npvHi > 0) return null
	for (let i = 0; i < 200; i++) {
		const mid = (lo + hi) / 2
		const npvMid = npv(mid)
		if (Math.abs(npvMid) < 1e-2 || hi - lo < 1e-8) {
			rate = mid
			break
		}
		if (npvLo * npvMid < 0) {
			hi = mid
		} else {
			lo = mid
			npvLo = npvMid
		}
	}
	const annualised = ((1 + rate) ** periodsPerYear - 1) * 100
	return Number.isFinite(annualised) ? annualised : null
}

function computeXirr(cashFlows: Array<{ date: Date; amount: number }>): number | null {
	const datedCashFlows = cashFlows
		.filter((cf) => Number.isFinite(cf.amount) && Number.isFinite(cf.date.getTime()))
		.sort((a, b) => a.date.getTime() - b.date.getTime())
	if (!datedCashFlows.some((cf) => cf.amount > 0) || !datedCashFlows.some((cf) => cf.amount < 0)) {
		return null
	}

	const start = datedCashFlows[0].date.getTime()
	const yearsFromStart = (date: Date) => (date.getTime() - start) / (365.25 * 24 * 60 * 60 * 1000)
	const npv = (rate: number) =>
		datedCashFlows.reduce(
			(total, cf) => total + cf.amount / (1 + rate) ** yearsFromStart(cf.date),
			0
		)

	let lo = -0.9999
	let hi = 10
	let npvLo = npv(lo)
	let npvHi = npv(hi)
	for (let i = 0; i < 30 && npvLo * npvHi > 0; i++) {
		hi *= 2
		npvHi = npv(hi)
		if (!Number.isFinite(npvHi)) break
	}
	if (!Number.isFinite(npvLo) || !Number.isFinite(npvHi) || npvLo * npvHi > 0) return null

	for (let i = 0; i < 200; i++) {
		const mid = (lo + hi) / 2
		const npvMid = npv(mid)
		if (!Number.isFinite(npvMid)) return null
		if (Math.abs(npvMid) < 1e-2 || hi - lo < 1e-8) return mid * 100
		if (npvLo * npvMid <= 0) {
			hi = mid
			npvHi = npvMid
		} else {
			lo = mid
			npvLo = npvMid
		}
	}
	return ((lo + hi) / 2) * 100
}

function debtSpreadPct(a: FeasibilityAssumptions): number {
	if (a.debtSpreadPa !== undefined && a.debtSpreadPa !== null) {
		return a.debtSpreadPa * 100
	}
	return a.constructionLoanSpreadBps / 100
}

function scurveWeights(n: number, steepness: number = 8): number[] {
	if (n <= 1) return [1.0]
	const k = steepness / Math.max(n, 1)
	const mid = (n - 1) / 2.0
	const raw = Array.from({ length: n }, (_, i) => {
		const x = Math.exp(k * (i - mid))
		return x / (1 + x) ** 2
	})
	const total = raw.reduce((s, v) => s + v, 0) || 1.0
	return raw.map((w) => w / total)
}

// ── Area Chain Benchmarks (legacy — used as fallback) ────────────────────────

export type BuildingForm = 'low_rise' | 'mid_rise' | 'tower'

interface RatioBand {
	low: number
	base: number
	high: number
}

interface AreaBenchmark {
	usage: 'residential' | 'commercial' | 'mixed_use'
	buildingForm: BuildingForm
	coverageRatio: RatioBand
	buaToGfaEfficiency: RatioBand
	gfaToGsaEfficiency: RatioBand
}

const AREA_BENCHMARKS: AreaBenchmark[] = [
	{
		usage: 'residential',
		buildingForm: 'low_rise',
		coverageRatio: { low: 0.55, base: 0.6, high: 0.65 },
		buaToGfaEfficiency: { low: 0.89, base: 0.91, high: 0.93 },
		gfaToGsaEfficiency: { low: 0.8, base: 0.84, high: 0.87 }
	},
	{
		usage: 'residential',
		buildingForm: 'mid_rise',
		coverageRatio: { low: 0.4, base: 0.45, high: 0.5 },
		buaToGfaEfficiency: { low: 0.85, base: 0.88, high: 0.9 },
		gfaToGsaEfficiency: { low: 0.76, base: 0.8, high: 0.83 }
	},
	{
		usage: 'residential',
		buildingForm: 'tower',
		coverageRatio: { low: 0.4, base: 0.45, high: 0.5 },
		buaToGfaEfficiency: { low: 0.83, base: 0.86, high: 0.88 },
		gfaToGsaEfficiency: { low: 0.73, base: 0.77, high: 0.8 }
	},
	{
		usage: 'mixed_use',
		buildingForm: 'mid_rise',
		coverageRatio: { low: 0.4, base: 0.44, high: 0.5 },
		buaToGfaEfficiency: { low: 0.85, base: 0.88, high: 0.9 },
		gfaToGsaEfficiency: { low: 0.75, base: 0.78, high: 0.81 }
	},
	{
		usage: 'commercial',
		buildingForm: 'mid_rise',
		coverageRatio: { low: 0.35, base: 0.42, high: 0.45 },
		buaToGfaEfficiency: { low: 0.84, base: 0.87, high: 0.89 },
		gfaToGsaEfficiency: { low: 0.7, base: 0.74, high: 0.77 }
	}
]

function classifyBuildingForm(maxStoreys: number | null | undefined): BuildingForm {
	const storeys = maxStoreys && maxStoreys > 0 ? maxStoreys : 12
	if (storeys <= 8) return 'low_rise'
	if (storeys <= 20) return 'mid_rise'
	return 'tower'
}

function getBenchmark(usage: UsageType, maxStoreys: number | null | undefined): AreaBenchmark {
	const normalizedUsage: AreaBenchmark['usage'] =
		usage === 'commercial' || usage === 'mixed_use' || usage === 'residential'
			? usage
			: 'residential'
	const buildingForm = classifyBuildingForm(maxStoreys)
	return (
		AREA_BENCHMARKS.find((b) => b.usage === normalizedUsage && b.buildingForm === buildingForm) ??
		AREA_BENCHMARKS[0]
	)
}

// ── Calculation Modules ──────────────────────────────────────────────────────

function computeArea(a: FeasibilityAssumptions): AreaBridgeOutputs {
	const benchmark = getBenchmark(a.usage, a.maxStoreys)
	const maxGfa = a.maxGfaSqm > 0 ? a.maxGfaSqm : a.plotAreaSqm * a.maxFar
	const aboveGradeBuaFactor = d(a, 'aboveGradeBuaFactor')
	const serviceBohPlantPct = d(a, 'serviceBohPlantPct')
	const basementParkingFloors = d(a, 'basementParkingFloors')
	const podiumParkingFloorsOutsideGfa = d(a, 'podiumParkingFloorsOutsideGfa')
	const parkingAreaPerSpaceSqm = d(a, 'parkingAreaPerSpaceSqm')

	// Area Bridge calculations
	const aboveGradeCostableBua = round(maxGfa * aboveGradeBuaFactor)
	const basementParkingCapacityBua = round(basementParkingFloors * a.plotAreaSqm)
	const requiredParkingBua = round(targetParkingSpaces(a) * parkingAreaPerSpaceSqm)
	const basementParkingBua =
		requiredParkingBua > 0
			? Math.min(basementParkingCapacityBua, requiredParkingBua)
			: basementParkingCapacityBua
	const podiumParkingBuaAddon = round(podiumParkingFloorsOutsideGfa * a.plotAreaSqm)
	const serviceBohPlantAddon = round(aboveGradeCostableBua * serviceBohPlantPct)
	const totalCostableBua = round(
		aboveGradeCostableBua + basementParkingBua + podiumParkingBuaAddon + serviceBohPlantAddon
	)
	const efficiencyRatio = a.nsaEfficiencyPct / 100
	const sellableArea = round(maxGfa * efficiencyRatio)
	const nsaGfaRatio = maxGfa > 0 ? round(sellableArea / maxGfa, 4) : 0
	const nsaCostableBuaRatio = totalCostableBua > 0 ? round(sellableArea / totalCostableBua, 4) : 0
	const costableBuaGfaRatio = maxGfa > 0 ? round(totalCostableBua / maxGfa, 4) : 0

	// Legacy compat. 0/null/undefined all mean "not set" (no plot has 0 storeys / 0% coverage).
	const coveragePctOrDefault =
		a.maxCoveragePct && a.maxCoveragePct > 0 ? a.maxCoveragePct : benchmark.coverageRatio.base * 100
	const appliedCoveragePct = Math.min(coveragePctOrDefault, benchmark.coverageRatio.base * 100)
	const buildableFootprintSqm = round(a.plotAreaSqm * (appliedCoveragePct / 100))
	const maxStoreysOrFallback = a.maxStoreys && a.maxStoreys > 0 ? a.maxStoreys : 0
	const storeysFromGfa =
		buildableFootprintSqm > 0 && maxGfa > 0
			? Math.max(Math.floor(maxGfa / buildableFootprintSqm), 1)
			: maxStoreysOrFallback || 1
	const derivedStoreys = Math.min(maxStoreysOrFallback || storeysFromGfa, storeysFromGfa)
	const builtUpAreaSqm = round(buildableFootprintSqm * Math.max(derivedStoreys, 1))

	const notes: string[] = []
	if (a.maxCoveragePct && a.maxCoveragePct > 0) {
		notes.push(
			`Applied footprint ratio capped by GIS max coverage of ${round(a.maxCoveragePct, 1)}%.`
		)
	} else {
		notes.push('GIS max coverage missing, benchmark footprint ratios applied.')
	}
	if (requiredParkingBua > 0 && basementParkingBua < basementParkingCapacityBua) {
		notes.push('Basement parking BUA capped to modeled parking demand.')
	}

	return {
		plotAreaSqm: a.plotAreaSqm,
		maxGfaSqm: maxGfa,
		maxStoreys: a.maxStoreys,
		aboveGradeCostableBua,
		basementParkingBua,
		podiumParkingBuaAddon,
		serviceBohPlantAddon,
		totalCostableBua,
		sellableArea,
		nsaGfaRatio,
		nsaCostableBuaRatio,
		costableBuaGfaRatio,
		// Legacy compat
		appliedCoveragePct: round(appliedCoveragePct),
		buildableFootprintSqm,
		builtUpAreaSqm,
		modeledGfaSqm: maxGfa,
		grossSaleableAreaSqm: sellableArea,
		parkingBuaAllowanceSqm: basementParkingBua + podiumParkingBuaAddon,
		totalBuaSqm: totalCostableBua,
		notes
	}
}

function defaultMaxEfficientFloorplateSqm(buildingForm: BuildingForm): number {
	if (buildingForm === 'tower') return 2000
	if (buildingForm === 'mid_rise') return 2400
	return 3500
}

function defaultMinEfficientFloorplateSqm(buildingForm: BuildingForm): number {
	if (buildingForm === 'tower') return 700
	if (buildingForm === 'mid_rise') return 900
	return 1200
}

function massingBuildingType(buildingForm: BuildingForm): BuildingScheduleRow['buildingType'] {
	if (buildingForm === 'tower') return 'tower'
	if (buildingForm === 'mid_rise') return 'mid_rise_block'
	return 'low_rise_block'
}

function getActiveUnitConfigs(
	a: FeasibilityAssumptions
): Array<{ units: number; avgSizeSqm: number; parkingRatio?: number }> {
	const btrConfigs =
		a.developmentModel === 'build_to_rent_residential' && (a.btrUnitConfigs?.length ?? 0) > 0
			? a.btrUnitConfigs
			: null
	const configs = btrConfigs ?? a.unitConfigs
	return (configs ?? [])
		.filter((row) => row.units > 0 && row.avgSizeSqm > 0)
		.map((row) => ({
			units: row.units,
			avgSizeSqm: row.avgSizeSqm,
			parkingRatio: row.parkingRatio
		}))
}

function getActiveUnitMix(a: FeasibilityAssumptions): Array<{ units: number; avgSizeSqm: number }> {
	return getActiveUnitConfigs(a).map((row) => ({
		units: row.units,
		avgSizeSqm: row.avgSizeSqm
	}))
}

function targetParkingSpaces(a: FeasibilityAssumptions): number {
	return round(
		getActiveUnitConfigs(a).reduce((sum, row) => {
			const fallbackRatio =
				row.avgSizeSqm > a.largeUnitThresholdSqm ? a.largeUnitParkingRatio : a.standardParkingRatio
			const parkingRatio =
				typeof row.parkingRatio === 'number' && Number.isFinite(row.parkingRatio)
					? row.parkingRatio
					: fallbackRatio
			return sum + row.units * parkingRatio
		}, 0)
	)
}

function weightedAverageUnitSizeSqm(a: FeasibilityAssumptions): number {
	const mix = getActiveUnitMix(a)
	const totalUnits = mix.reduce((sum, row) => sum + row.units, 0)
	if (totalUnits <= 0) return 85
	return round(mix.reduce((sum, row) => sum + row.units * row.avgSizeSqm, 0) / totalUnits, 1)
}

function targetUnitCount(a: FeasibilityAssumptions): number {
	return getActiveUnitMix(a).reduce((sum, row) => sum + row.units, 0)
}

function targetUnitAreaSqm(a: FeasibilityAssumptions): number {
	return getActiveUnitMix(a).reduce((sum, row) => sum + row.units * row.avgSizeSqm, 0)
}

function computeSiteMassing(
	a: FeasibilityAssumptions,
	area: AreaBridgeOutputs
): SiteMassingOutputs {
	const selectedPodiumFloors = d(a, 'podiumFloors')
	const selectedResidentialFloors = d(a, 'residentialFloors')
	const selectedAmenityFloors = d(a, 'amenityRoofFloors')
	const selectedTotalFloors =
		selectedPodiumFloors + selectedResidentialFloors + selectedAmenityFloors
	const regulatoryMaxStoreys = a.maxStoreys && a.maxStoreys > 0 ? a.maxStoreys : 0
	const cappedTotalFloors =
		regulatoryMaxStoreys > 0
			? Math.min(selectedTotalFloors, regulatoryMaxStoreys)
			: selectedTotalFloors
	const benchmarkStoreys = regulatoryMaxStoreys || selectedTotalFloors
	const benchmark = getBenchmark(a.usage, benchmarkStoreys)
	const buildingForm = classifyBuildingForm(benchmarkStoreys)
	const maxGfa = area.maxGfaSqm
	const targetCoverage = positiveAssumptionNumber(
		a,
		'targetCoveragePct',
		benchmark.coverageRatio.base * 100
	)
	const gisCoverage = a.maxCoveragePct && a.maxCoveragePct > 0 ? a.maxCoveragePct : targetCoverage
	const appliedCoveragePct = round(
		Math.min(targetCoverage, gisCoverage, benchmark.coverageRatio.high * 100),
		1
	)
	const coveredFootprintSqm = round(a.plotAreaSqm * (appliedCoveragePct / 100))
	const physicalMaxGfaSqm = round(coveredFootprintSqm * Math.max(cappedTotalFloors, 0))
	const requiredFloorsAtCoverage =
		coveredFootprintSqm > 0 && maxGfa > 0 ? Math.ceil(maxGfa / coveredFootprintSqm) : 0
	const requiredCoverageAtMaxStoreysPct =
		a.plotAreaSqm > 0 && cappedTotalFloors > 0 && maxGfa > 0
			? round((maxGfa / (a.plotAreaSqm * cappedTotalFloors)) * 100, 1)
			: 0
	const gfaShortfallSqm = round(Math.max(maxGfa - physicalMaxGfaSqm, 0))
	const maxEfficientFloorplate = positiveAssumptionNumber(
		a,
		'maxEfficientTowerFloorplateSqm',
		defaultMaxEfficientFloorplateSqm(buildingForm)
	)
	const minEfficientFloorplate = positiveAssumptionNumber(
		a,
		'minEfficientTowerFloorplateSqm',
		defaultMinEfficientFloorplateSqm(buildingForm)
	)
	const floorToFloorHeightM = assumptionNumber(a, 'floorToFloorHeightM', 3.2)
	const podiumFloorToFloorHeightM = assumptionNumber(a, 'podiumFloorToFloorHeightM', 4)
	const groundFloorHeightM = assumptionNumber(a, 'groundFloorHeightM', 5)
	const roofPlantAllowanceM = assumptionNumber(a, 'roofPlantAllowanceM', 6)
	const weightedAvgUnitSize = weightedAverageUnitSizeSqm(a)
	const targetUnits = targetUnitCount(a)
	const targetAreaSqm = targetUnitAreaSqm(a)
	const nsaEfficiency = Math.max(0, a.nsaEfficiencyPct / 100)
	const overrideBuildingCount = assumptionNumber(a, 'targetBuildingCount', 0)
	const buildingCount =
		overrideBuildingCount > 0
			? Math.max(1, Math.round(overrideBuildingCount))
			: Math.max(1, Math.ceil(coveredFootprintSqm / maxEfficientFloorplate))

	const gfaPerBuilding = maxGfa / buildingCount
	const availableFootprintPerBuilding = coveredFootprintSqm / buildingCount
	const typicalGrossFloorplate = round(Math.max(1, availableFootprintPerBuilding))

	const allowableFloorsPerBuilding = Math.max(cappedTotalFloors, 0)
	const podiumFloors = Math.min(selectedPodiumFloors, Math.max(allowableFloorsPerBuilding - 1, 0))
	const amenityFloors = Math.min(
		selectedAmenityFloors,
		Math.max(allowableFloorsPerBuilding - podiumFloors - 1, 0)
	)
	const residentialFloors = Math.max(0, allowableFloorsPerBuilding - podiumFloors - amenityFloors)
	const netFloorplate = round(typicalGrossFloorplate * nsaEfficiency)
	const netFloorplateAllBuildings = Math.max(netFloorplate * buildingCount, 0)
	const requiredResidentialFloorsForUnits =
		netFloorplateAllBuildings > 0 && targetAreaSqm > 0
			? Math.ceil(targetAreaSqm / netFloorplateAllBuildings)
			: 0
	const requiredTotalFloorsForProgram =
		selectedPodiumFloors + requiredResidentialFloorsForUnits + selectedAmenityFloors
	const unitsPerTypicalFloor =
		weightedAvgUnitSize > 0 ? Math.max(1, Math.floor(netFloorplate / weightedAvgUnitSize)) : 0
	const totalPhysicalUnitCapacity = unitsPerTypicalFloor * residentialFloors * buildingCount
	const unitCapacityGap = totalPhysicalUnitCapacity - targetUnits
	const allocatedGfaPerBuilding = round(
		Math.min(gfaPerBuilding, typicalGrossFloorplate * allowableFloorsPerBuilding)
	)
	const estimatedHeightM = round(
		groundFloorHeightM +
			podiumFloors * podiumFloorToFloorHeightM +
			(residentialFloors + amenityFloors) * floorToFloorHeightM +
			roofPlantAllowanceM,
		1
	)
	const buildingWarnings: string[] = []
	if (typicalGrossFloorplate > maxEfficientFloorplate) {
		buildingWarnings.push('Typical gross floorplate exceeds the efficient floorplate threshold.')
	}
	if (typicalGrossFloorplate < minEfficientFloorplate) {
		buildingWarnings.push('Typical gross floorplate is below the efficient floorplate threshold.')
	}
	if (requiredFloorsAtCoverage > allowableFloorsPerBuilding) {
		buildingWarnings.push('Required floors exceed the selected / capped floor count.')
	}
	if (requiredResidentialFloorsForUnits > residentialFloors) {
		buildingWarnings.push(
			'Required residential floors exceed the selected residential floor count.'
		)
	}

	const buildings: BuildingScheduleRow[] = Array.from({ length: buildingCount }, (_, index) => ({
		id: `building-${index + 1}`,
		label: buildingCount === 1 ? 'Building 1' : `Building ${index + 1}`,
		buildingType: massingBuildingType(buildingForm),
		footprintSqm: typicalGrossFloorplate,
		grossFloorplateSqm: typicalGrossFloorplate,
		netFloorplateSqm: netFloorplate,
		allocatedGfaSqm: allocatedGfaPerBuilding,
		residentialFloors,
		podiumFloors,
		amenityFloors,
		totalFloors: allowableFloorsPerBuilding,
		estimatedHeightM,
		unitsPerTypicalFloor,
		totalUnits: unitsPerTypicalFloor * residentialFloors,
		warnings: buildingWarnings
	}))

	const totalFootprintSqm = round(buildings.reduce((sum, row) => sum + row.footprintSqm, 0))
	const totalAllocatedGfaSqm = round(buildings.reduce((sum, row) => sum + row.allocatedGfaSqm, 0))
	const gfaUtilizationPct = maxGfa > 0 ? round((totalAllocatedGfaSqm / maxGfa) * 100, 1) : 0
	const coverageUtilizationPct =
		coveredFootprintSqm > 0 ? round((totalFootprintSqm / coveredFootprintSqm) * 100, 1) : 0
	const warnings: string[] = []
	if (!(a.maxCoveragePct && a.maxCoveragePct > 0)) {
		warnings.push('GIS max coverage is missing; benchmark coverage was applied.')
	}
	if (totalFootprintSqm > coveredFootprintSqm + 1) {
		warnings.push('Total building footprint exceeds the covered footprint allowance.')
	}
	if (regulatoryMaxStoreys > 0 && selectedTotalFloors > regulatoryMaxStoreys) {
		warnings.push('Selected floor count exceeds regulatory max storeys; massing is capped.')
	}
	if (requiredFloorsAtCoverage > allowableFloorsPerBuilding) {
		warnings.push(
			'Required floors exceed selected / capped floors; increase coverage, floors, or building count.'
		)
	}
	if (requiredTotalFloorsForProgram > allowableFloorsPerBuilding) {
		warnings.push(
			'Required unit-mix floors exceed selected / capped floors; increase residential floors, coverage, efficiency, or building count.'
		)
	}
	if (buildingCount === 1 && coveredFootprintSqm > maxEfficientFloorplate) {
		warnings.push(
			'Single-building floorplate is inefficient; multi-building massing is recommended.'
		)
	}
	if (gfaShortfallSqm > 0) {
		warnings.push(
			'Current coverage and selected floors cannot physically deliver the full maximum GFA.'
		)
	}
	if (targetUnits > 0) {
		const variance = Math.abs(unitCapacityGap) / targetUnits
		if (unitCapacityGap < 0 && variance > 0.1) {
			warnings.push('Physical unit capacity is below the modeled unit count.')
		} else if (variance > 0.1) {
			warnings.push('Physical unit capacity exceeds the modeled unit mix by more than 10%.')
		}
	}
	if (gfaUtilizationPct < 98) {
		warnings.push(
			'Massing does not fully utilize maximum GFA under current floorplate/storey assumptions.'
		)
	}

	return {
		plotAreaSqm: a.plotAreaSqm,
		maxGfaSqm: maxGfa,
		buildingForm,
		appliedCoveragePct,
		coveredFootprintSqm,
		totalFootprintSqm,
		physicalMaxGfaSqm,
		requiredFloorsAtCoverage,
		requiredResidentialFloorsForUnits,
		requiredTotalFloorsForProgram,
		requiredCoverageAtMaxStoreysPct,
		gfaShortfallSqm,
		buildingCount,
		typicalGrossFloorplateSqm: typicalGrossFloorplate,
		weightedAvgUnitSizeSqm: weightedAvgUnitSize,
		targetUnitCount: targetUnits,
		unitCapacityGap,
		totalPhysicalUnitCapacity,
		totalAllocatedGfaSqm,
		gfaUtilizationPct,
		coverageUtilizationPct,
		estimatedMaxHeightM: Math.max(0, ...buildings.map((row) => row.estimatedHeightM)),
		buildings,
		warnings
	}
}

function computeProgram(a: FeasibilityAssumptions): ProgramOutputs {
	const rows: ProgramRow[] = a.unitConfigs
		.filter((row) => row.units > 0)
		.map((row) => ({
			id: row.id,
			label: row.label,
			units: row.units,
			avgSizeSqm: row.avgSizeSqm,
			totalAreaSqm: round(row.units * row.avgSizeSqm),
			sellingRatePsqm: row.sellingRatePsqm,
			revenueAed: round(row.units * row.avgSizeSqm * row.sellingRatePsqm),
			parkingSpaces: round(row.units * row.parkingRatio)
		}))

	const totalUnits = rows.reduce((sum, row) => sum + row.units, 0)
	const totalAreaSqm = rows.reduce((sum, row) => sum + row.totalAreaSqm, 0)
	const totalParkingSpaces = rows.reduce((sum, row) => sum + row.parkingSpaces, 0)
	const grossRevenueAed = rows.reduce((sum, row) => sum + row.revenueAed, 0)
	const weightedAvgSalesRatePsqm = totalAreaSqm > 0 ? round(grossRevenueAed / totalAreaSqm) : 0

	return {
		rows,
		totalUnits,
		totalAreaSqm,
		totalParkingSpaces,
		grossRevenueAed,
		weightedAvgSalesRatePsqm
	}
}

function computeCosts(
	a: FeasibilityAssumptions,
	area: AreaBridgeOutputs,
	program: ProgramOutputs
): CostOutputs {
	const vatRate = a.vatPct / 100
	const vat = d(a, 'vatAppliesTo')

	// ── Acquisition costs ──
	const landAcquisitionAed =
		positiveOverride(a.landAcquisitionCostOverrideAed) ?? round(a.plotAreaSqm * a.landPricePsqm)
	const landTransferFeeAed = round(
		landAcquisitionAed * (a.landTransferFeePct ?? DEFAULTS.landTransferFeePct)
	)
	const brokerageFeeAed =
		a.brokerageFeeAed > 0
			? a.brokerageFeeAed
			: round(landAcquisitionAed * (a.brokeragePct ?? DEFAULTS.brokeragePct))
	const legalDdCostAed =
		a.legalDdCostAed > 0
			? a.legalDdCostAed
			: round(landAcquisitionAed * (a.legalDdPct ?? DEFAULTS.legalDdPct))
	const totalLandCostAed = round(
		landAcquisitionAed + landTransferFeeAed + brokerageFeeAed + legalDdCostAed
	)

	// ── Construction costs ──
	const costableBua = area.totalCostableBua
	const baseHardCost = round(costableBua * a.constructionCostPsqmBua)
	const inflationCost = round(baseHardCost * (a.midPointInflationPct / 100))
	const hardCostAed =
		positiveOverride(a.constructionCostOverrideAed) ?? round(baseHardCost + inflationCost)

	const permitFeesPct = a.permitFeesPct ?? DEFAULTS.permitFeesPct
	const permitFeesAed = round(hardCostAed * permitFeesPct)

	const softCostPctVal = d(a, 'softCostPct')
	const softCostAed =
		positiveOverride(a.designSupervisionCostOverrideAed) ?? round(hardCostAed * softCostPctVal)

	const contingencyCostAed =
		positiveOverride(a.contingencyCostOverrideAed) ?? round(hardCostAed * (a.contingencyPct / 100))

	const totalConstructionCostAed = round(
		permitFeesAed + hardCostAed + softCostAed + contingencyCostAed
	)

	// ── Revenue-linked costs ──
	const gdv = program.grossRevenueAed
	const marketingCostAed =
		positiveOverride(a.marketingCostOverrideAed) ?? round(gdv * (a.marketingCostPct / 100))
	const salesAdminCostAed =
		positiveOverride(a.salesAgentFeesOverrideAed) ?? round(gdv * (a.salesAgentFeePct / 100))
	const totalRevenueCostAed = round(marketingCostAed + salesAdminCostAed)

	// ── VAT per-category ──
	const vatLandAed = vat.land ? round(landAcquisitionAed * vatRate) : 0
	const vatHardCostAed = vat.hardCosts ? round(hardCostAed * vatRate) : 0
	const vatSoftCostAed = vat.softCosts ? round(softCostAed * vatRate) : 0
	const vatPermitFeesAed = vat.permitFees ? round(permitFeesAed * vatRate) : 0
	const vatContingencyAed = vat.contingency ? round(contingencyCostAed * vatRate) : 0
	const vatMarketingAed = vat.marketing ? round(marketingCostAed * vatRate) : 0
	const vatSalesAdminAed = vat.salesAdmin ? round(salesAdminCostAed * vatRate) : 0
	const totalVatAed = round(
		vatLandAed +
			vatHardCostAed +
			vatSoftCostAed +
			vatPermitFeesAed +
			vatContingencyAed +
			vatMarketingAed +
			vatSalesAdminAed
	)

	// ── Statutory & development costs (infrastructure, permits, community) ──
	// These are user inputs timed separately in the CF but must be included in total cost.
	const demolitionCostAed = a.demolitionEnabled ? a.demolitionCostAed : 0
	const statutoryCostAed = round(
		a.infrastructureCostAed +
			a.governmentFeesAed +
			a.masterCommunityFeesAed +
			demolitionCostAed +
			a.ffeOsePreopeningCostAed
	)

	// ── Totals ──
	const totalDevCostExclVatAed = round(
		totalLandCostAed + totalConstructionCostAed + totalRevenueCostAed + statutoryCostAed
	)
	const totalDevCostInclVatAed = round(totalDevCostExclVatAed + totalVatAed)

	return {
		landAcquisitionAed,
		landTransferFeeAed,
		brokerageFeeAed,
		legalDdCostAed,
		totalLandCostAed,
		permitFeesAed,
		hardCostAed,
		softCostAed,
		contingencyCostAed,
		totalConstructionCostAed,
		marketingCostAed,
		salesAdminCostAed,
		totalRevenueCostAed,
		vatLandAed,
		vatHardCostAed,
		vatSoftCostAed,
		vatPermitFeesAed,
		vatContingencyAed,
		vatMarketingAed,
		vatSalesAdminAed,
		totalVatAed,
		totalDevCostExclVatAed,
		totalDevCostInclVatAed,
		// Legacy compat aliases
		constructionCostAed: baseHardCost,
		inflationCostAed: inflationCost,
		constructionCostInclInflationAed: hardCostAed,
		designSupervisionCostAed: softCostAed,
		salesAgentFeesAed: salesAdminCostAed,
		infrastructureCostAed: a.infrastructureCostAed,
		governmentFeesAed: a.governmentFeesAed,
		masterCommunityFeesAed: a.masterCommunityFeesAed,
		ffeOsePreopeningCostAed: a.ffeOsePreopeningCostAed,
		demolitionCostAed,
		totalCostsExclVatAed: totalDevCostExclVatAed,
		vatAmountAed: totalVatAed,
		totalCostsInclVatAed: totalDevCostInclVatAed
	}
}

/**
 * deriveFunding — runs AFTER the cash flow.
 *
 * All funding amounts are derived from actual CF periods.
 * No pre-CF estimates, no backfilling. The CF is the single source of truth
 * for how the project is funded: costs go out → collections come in → debt
 * fills the gap (up to LTV/LTC) → equity fills the residual.
 */
function deriveFunding(
	a: FeasibilityAssumptions,
	costs: CostOutputs,
	periods: CashFlowPeriod[]
): FundingOutputs {
	// Payment plan
	const depositPct = a.paymentPlan.depositPct
	const preHandoverPct = a.paymentPlan.constructionPct
	const handoverPct = a.paymentPlan.handoverPct

	// Debt capacity (informational — what LTV/LTC allows)
	const acqLtv = d(a, 'acquisitionDebtLtv')
	const conLtc = d(a, 'constructionDebtLtc')
	const landLoanCapacityAed = round(costs.totalLandCostAed * acqLtv)
	const constructionLoanCapacityAed = round(costs.totalConstructionCostAed * conLtc)
	const totalDebtCapacityAed = round(landLoanCapacityAed + constructionLoanCapacityAed)

	// Per-tranche rates (matching computeCashFlow)
	const eiborPct = a.eiborRatePct
	const acqSpreadPct = a.landLoanSpreadBps > 0 ? a.landLoanSpreadBps / 100 : debtSpreadPct(a)
	const conSpreadPct =
		a.constructionLoanSpreadBps > 0 ? a.constructionLoanSpreadBps / 100 : debtSpreadPct(a)
	const landLoanRatePct = round(eiborPct + acqSpreadPct, 2)
	const constructionLoanRatePct = round(eiborPct + conSpreadPct, 2)

	// Actual funding — all derived from the monthly CF periods
	const offPlanProceedsAed = round(
		periods.reduce((sum, p) => sum + p.depositInflowsAed + p.preHandoverInflowsAed, 0)
	)
	const debtFundingAed = round(periods.reduce((sum, p) => sum + p.debtDrawAed, 0))
	const equityFundingAed = round(periods.reduce((sum, p) => sum + p.equityContributionAed, 0))
	const vatRefundsAed = round(periods.reduce((sum, p) => sum + p.vatRefundInflowsAed, 0))
	const peakDebtAed = Math.max(...periods.map((p) => p.debtBalanceAed), 0)
	const peakEquityAed = peakNetSponsorCapital(periods)

	// Total project cost = dev costs + financing + VAT
	const totalFinancingCosts = round(
		periods.reduce((sum, p) => sum + p.financingFeeAed + p.interestPaidAed + p.exitFeeAed, 0)
	)
	const cashReconUsesAed = round(
		costs.totalDevCostExclVatAed + totalFinancingCosts + costs.totalVatAed
	)
	const cashReconSourcesAed = round(
		offPlanProceedsAed + debtFundingAed + equityFundingAed + vatRefundsAed
	)
	const cashReconGapAed = round(cashReconUsesAed - cashReconSourcesAed)

	return {
		depositPct,
		preHandoverPct,
		handoverPct,
		landLoanCapacityAed,
		constructionLoanCapacityAed,
		totalDebtCapacityAed,
		landLoanRatePct,
		constructionLoanRatePct,
		offPlanProceedsAed,
		debtFundingAed,
		equityFundingAed,
		vatRefundsAed,
		peakDebtAed,
		peakEquityAed,
		cashReconSourcesAed,
		cashReconUsesAed,
		cashReconGapAed
	}
}

// ── Monthly Cash Flow — Dual-tranche, S-curve, VAT lag ──────────────────────

function computeCashFlow(
	a: FeasibilityAssumptions,
	costs: CostOutputs,
	program: ProgramOutputs
): CashFlowOutputs {
	const salesStart = parseIsoDate(a.salesCommencementDate, new Date(Date.UTC(2026, 5, 1)))
	const constructionStartDate = parseIsoDate(a.constructionDate, new Date(Date.UTC(2026, 0, 1)))
	const handoverDate = parseIsoDate(a.handoverDate, new Date(Date.UTC(2029, 0, 1)))
	const landAcqDate = parseIsoDate(a.landAcquisitionDate, constructionStartDate)
	const demolitionDate = parseIsoDate(a.demolitionEnablingDate, constructionStartDate)
	const vatLagMonths = d(a, 'vatRefundLagMonths')

	const salesPeriodMonths = Math.max(Math.round(a.salesPeriodMonths), 1)

	// Timeline extends past handover to capture VAT refunds
	const timelineStart = new Date(
		Math.min(landAcqDate.getTime(), salesStart.getTime(), constructionStartDate.getTime())
	)
	const timelineEnd = addMonths(handoverDate, vatLagMonths)
	const monthEnds = iterMonthEnds(timelineStart, timelineEnd)

	const landPeriodEnd = endOfMonth(landAcqDate)
	const handoverMe = endOfMonth(handoverDate)
	const constructionStartMe = endOfMonth(constructionStartDate)
	const demolitionMe = endOfMonth(demolitionDate)
	const salesStartMe = endOfMonth(salesStart)

	const key = (d: Date) => d.toISOString().slice(0, 10)

	// ── Construction period months ──
	const constructionMonthEnds = monthEnds.filter(
		(m) => m.getTime() >= constructionStartMe.getTime() && m.getTime() < handoverMe.getTime()
	)
	const constructionCount = Math.max(constructionMonthEnds.length, 1)

	// ── Sales period months ──
	const salesEndMe = endOfMonth(addMonths(salesStart, salesPeriodMonths - 1))
	const salesMonthEnds = monthEnds.filter(
		(m) => m.getTime() >= salesStartMe.getTime() && m.getTime() <= salesEndMe.getTime()
	)
	const salesCount = Math.max(salesMonthEnds.length, 1)

	// ── S-curve weights ──
	const conSteepness = d(a, 'constructionCurveSteepness')
	const saleSteepness = d(a, 'salesCurveSteepness')
	const conWeights = scurveWeights(constructionCount, conSteepness)
	const saleWeights = scurveWeights(salesCount, saleSteepness)

	// Map month-end key → weight index
	const conWeightMap = new Map<string, number>()
	constructionMonthEnds.forEach((m, i) => {
		conWeightMap.set(key(m), i)
	})
	const saleWeightMap = new Map<string, number>()
	salesMonthEnds.forEach((m, i) => {
		saleWeightMap.set(key(m), i)
	})

	// ── Pre-compute collections using S-curve sales weights ──
	const grossRevenue = program.grossRevenueAed
	const bookingPct = a.paymentPlan.depositPct / 100
	const preHandoverPct = a.paymentPlan.constructionPct / 100
	const onHandoverPct = a.paymentPlan.handoverPct / 100

	// Build collections per month
	type CollectionEntry = {
		contracted: number
		booking: number
		preHandover: number
		onHandover: number
	}
	const collectionsMap = new Map<string, CollectionEntry>(
		monthEnds.map((m) => [key(m), { contracted: 0, booking: 0, preHandover: 0, onHandover: 0 }])
	)

	// Each sales month cohort
	for (let idx = 0; idx < salesMonthEnds.length; idx++) {
		const saleMonth = salesMonthEnds[idx]
		const w = saleWeights[idx]
		const cohortRevenue = round(grossRevenue * w)
		const cohortBooking = round(cohortRevenue * bookingPct)
		const cohortPreHandover = round(cohortRevenue * preHandoverPct)
		const cohortOnHandover = round(cohortRevenue * onHandoverPct)

		// Contracted revenue in sale month
		const sk = key(saleMonth)
		const sEntry = collectionsMap.get(sk)
		if (sEntry) {
			sEntry.contracted += cohortRevenue
			sEntry.booking += cohortBooking
		}

		// Pre-handover: spread evenly from sale month+1 to handover-1
		if (cohortPreHandover > 0 && saleMonth.getTime() < handoverMe.getTime()) {
			const phMonths = monthEnds.filter(
				(m) => m.getTime() > saleMonth.getTime() && m.getTime() < handoverMe.getTime()
			)
			if (phMonths.length > 0) {
				const perMonth = round(cohortPreHandover / phMonths.length)
				let allocated = 0
				for (let j = 0; j < phMonths.length; j++) {
					const amt = j < phMonths.length - 1 ? perMonth : round(cohortPreHandover - allocated)
					const pk = key(phMonths[j])
					const pEntry = collectionsMap.get(pk)
					if (pEntry) pEntry.preHandover += amt
					allocated += amt
				}
			} else {
				// Very short timeline — collect in sale month
				if (sEntry) sEntry.preHandover += cohortPreHandover
			}
		}

		// On-handover: all at handover month
		const hk = key(handoverMe)
		const hEntry = collectionsMap.get(hk)
		if (hEntry) hEntry.onHandover += cohortOnHandover
	}

	// ── Debt parameters ──
	const acqLtv = d(a, 'acquisitionDebtLtv')
	const conLtc = d(a, 'constructionDebtLtc')
	const financingFeePct = d(a, 'financingFeePct')
	const exitFeePct = d(a, 'exitFeePct')

	// Per-tranche all-in rates — land facilities typically carry wider spread
	const eiborPa = a.eiborRatePct / 100
	const acqSpreadPa = a.landLoanSpreadBps > 0 ? a.landLoanSpreadBps / 10000 : debtSpreadPct(a) / 100
	const conSpreadPa =
		a.constructionLoanSpreadBps > 0 ? a.constructionLoanSpreadBps / 10000 : debtSpreadPct(a) / 100
	const acqMonthlyRate = (eiborPa + acqSpreadPa) / 12
	const conMonthlyRate = (eiborPa + conSpreadPa) / 12

	// Acquisition eligible = land + land fees (month 1 only)
	const acqEligibleTotal =
		costs.landAcquisitionAed +
		costs.landTransferFeeAed +
		costs.brokerageFeeAed +
		costs.legalDdCostAed
	const acqDebtCommitment = round(acqEligibleTotal * acqLtv)

	// Construction eligible = permit + hard + soft + contingency
	const conEligibleTotal =
		costs.permitFeesAed + costs.hardCostAed + costs.softCostAed + costs.contingencyCostAed
	const conDebtMaxTotal = round(conEligibleTotal * conLtc)
	const totalDebtCommitment = round(acqDebtCommitment + conDebtMaxTotal)

	// ── Monthly iteration ──
	const cashFlowPeriods: CashFlowPeriod[] = []
	let acqDebtBalance = 0
	let conDebtBalance = 0
	let cumulativeConEligible = 0
	const vatPaidHistory: number[] = [] // for lag refund

	for (let mi = 0; mi < monthEnds.length; mi++) {
		const periodEnd = monthEnds[mi]
		const pk = key(periodEnd)
		const isHandover = periodEnd.getTime() === handoverMe.getTime()
		const isAfterHandover = periodEnd.getTime() > handoverMe.getTime()

		// S-curve indices
		const conIdx = conWeightMap.get(pk)
		const saleIdx = saleWeightMap.get(pk)
		const conPct = conIdx !== undefined ? conWeights[conIdx] : 0
		const salePct = saleIdx !== undefined ? saleWeights[saleIdx] : 0

		// ── Cost allocation ──
		const isLandMonth = periodEnd.getTime() === landPeriodEnd.getTime()
		const isConstructionStart = periodEnd.getTime() === constructionStartMe.getTime()
		const isDemolitionMonth = a.demolitionEnabled && periodEnd.getTime() === demolitionMe.getTime()
		const costLand = isLandMonth ? costs.landAcquisitionAed : 0
		const costLandFees = isLandMonth
			? round(costs.landTransferFeeAed + costs.brokerageFeeAed + costs.legalDdCostAed)
			: 0
		const costPermitFees = round(costs.permitFeesAed * conPct)
		const costHard = round(costs.hardCostAed * conPct)
		const costSoft = round(costs.softCostAed * conPct)
		const costContingency = round(costs.contingencyCostAed * conPct)
		const costMarketing = round(costs.marketingCostAed * salePct)
		const costSalesAdmin = round(costs.salesAdminCostAed * salePct)

		// Statutory & development costs — Section D of budget
		// Infrastructure: spread over construction period (S-curve weighted)
		const costInfrastructure = round(costs.infrastructureCostAed * conPct)
		// Government/authority fees: lump sum at construction start
		const costGovernmentFees = isConstructionStart ? costs.governmentFeesAed : 0
		// Master community fees + FFE/pre-opening: lump sum at handover
		const costCommunityFees = isHandover ? costs.masterCommunityFeesAed : 0
		const costFFE = isHandover ? costs.ffeOsePreopeningCostAed : 0
		// Demolition/enabling works: lump sum at demolition enabling date
		const costDemolition = isDemolitionMonth ? costs.demolitionCostAed : 0

		const operatingOutflows = round(
			costLand +
				costLandFees +
				costPermitFees +
				costHard +
				costSoft +
				costContingency +
				costMarketing +
				costSalesAdmin +
				costInfrastructure +
				costGovernmentFees +
				costCommunityFees +
				costFFE +
				costDemolition
		)

		// ── VAT ──
		const vat = d(a, 'vatAppliesTo')
		const vatRate = a.vatPct / 100
		const vatThisMonth = round(
			(vat.land ? costLand * vatRate : 0) +
				(vat.hardCosts ? costHard * vatRate : 0) +
				(vat.softCosts ? costSoft * vatRate : 0) +
				(vat.permitFees ? costPermitFees * vatRate : 0) +
				(vat.contingency ? costContingency * vatRate : 0) +
				(vat.marketing ? costMarketing * vatRate : 0) +
				(vat.salesAdmin ? costSalesAdmin * vatRate : 0)
		)
		vatPaidHistory.push(vatThisMonth)
		const vatRefund = mi >= vatLagMonths ? vatPaidHistory[mi - vatLagMonths] : 0

		// ── Collections ──
		const collections = collectionsMap.get(pk) ?? {
			contracted: 0,
			booking: 0,
			preHandover: 0,
			onHandover: 0
		}
		const totalCollections = round(
			collections.booking + collections.preHandover + collections.onHandover
		)

		// ── Financing fee (month 1) ──
		const financingFee = isLandMonth ? round(totalDebtCommitment * financingFeePct) : 0

		// ── Interest on opening balances (per-tranche rates) ──
		const interestAcq = round(acqDebtBalance * acqMonthlyRate)
		const interestCon = round(conDebtBalance * conMonthlyRate)
		const totalInterest = round(interestAcq + interestCon)

		// ── Exit fee (handover month) ──
		const openingTotalDebt = round(acqDebtBalance + conDebtBalance)
		const exitFee = isHandover ? round(openingTotalDebt * exitFeePct) : 0

		// ── Total uses ──
		const totalUses = round(
			operatingOutflows + vatThisMonth + financingFee + exitFee + totalInterest
		)

		// ── Net CF before debt ──
		const netCfBeforeDebt = round(totalCollections + vatRefund - totalUses)

		// ── Unlevered CF (excludes financing costs) ──
		const unleveredCf = round(totalCollections + vatRefund - operatingOutflows - vatThisMonth)

		// ── Acquisition eligible uses ──
		const acqEligibleThisMonth = costLand + costLandFees
		// Construction eligible uses
		const conEligibleThisMonth = costPermitFees + costHard + costSoft + costContingency
		cumulativeConEligible += conEligibleThisMonth

		// ── Acquisition debt ──
		const openingAcqDebt = acqDebtBalance
		let acqDraw = 0
		let acqRepay = 0
		if (isLandMonth) {
			acqDraw = acqDebtCommitment
		}
		if (isHandover) {
			acqRepay = round(acqDebtBalance + acqDraw)
		}
		acqDebtBalance = round(acqDebtBalance + acqDraw - acqRepay)

		// ── Construction debt ──
		const openingConDebt = conDebtBalance
		const conMaxAllowed = round(cumulativeConEligible * conLtc)
		let conDraw = 0
		let conRepay = 0

		if (!isAfterHandover && !isHandover) {
			// Draw: min(max allowed - current balance, max(net funding gap, 0))
			const maxDrawable = Math.max(conMaxAllowed - conDebtBalance, 0)
			// Net funding gap = uses - collections - acq draw - vat refund
			const netGapForCon = round(totalUses - totalCollections - vatRefund - acqDraw)
			if (netGapForCon > 0) {
				conDraw = round(Math.min(maxDrawable, netGapForCon))
			}
		}
		if (!isHandover && !isAfterHandover) {
			// Repay from excess CF when net positive (after handover-month is handled below)
			const cfAfterDraw = round(netCfBeforeDebt + acqDraw + conDraw)
			if (cfAfterDraw > 0 && conDebtBalance + conDraw > 0) {
				conRepay = round(Math.min(cfAfterDraw, conDebtBalance + conDraw))
			}
		}
		if (isHandover) {
			// Bullet repay remainder at handover
			const cfAfterAcqAndCon = round(netCfBeforeDebt + acqDraw + conDraw - acqRepay)
			conRepay = round(Math.min(Math.max(cfAfterAcqAndCon, 0), conDebtBalance + conDraw))
		}
		conDebtBalance = round(conDebtBalance + conDraw - conRepay)

		// ── Total debt ──
		const totalDebtDraw = round(acqDraw + conDraw)
		const totalDebtRepay = round(acqRepay + conRepay)
		const closingDebt = round(acqDebtBalance + conDebtBalance)
		const debtHeadroom = round(Math.max(totalDebtCommitment - closingDebt, 0))

		// ── Equity ──
		const cfAfterDebt = round(
			totalCollections + vatRefund - totalUses + totalDebtDraw - totalDebtRepay
		)
		let equityContribution = 0
		let equityDistribution = 0
		if (cfAfterDebt < 0) {
			equityContribution = round(-cfAfterDebt)
		} else if (cfAfterDebt > 0) {
			equityDistribution = round(cfAfterDebt)
		}

		// ── Levered CF ──
		const leveredCf = round(-equityContribution + equityDistribution)

		cashFlowPeriods.push({
			periodLabel: periodEnd.toLocaleString('en-US', {
				month: 'short',
				year: 'numeric',
				timeZone: 'UTC'
			}),
			periodEndDate: pk,
			constructionCurvePct: round(conPct * 100, 2),
			salesCurvePct: round(salePct * 100, 2),
			revenueInflowsAed: totalCollections,
			depositInflowsAed: round(collections.booking),
			preHandoverInflowsAed: round(collections.preHandover),
			handoverInflowsAed: round(collections.onHandover),
			contractedRevenueAed: round(collections.contracted),
			costLandAed: costLand,
			costLandFeesAed: costLandFees,
			costPermitFeesAed: costPermitFees,
			costHardAed: costHard,
			costSoftAed: costSoft,
			costContingencyAed: costContingency,
			costMarketingAed: costMarketing,
			costSalesAdminAed: costSalesAdmin,
			operatingOutflowsAed: operatingOutflows,
			vatPaidAed: vatThisMonth,
			vatRefundInflowsAed: vatRefund,
			financingFeeAed: financingFee,
			exitFeeAed: exitFee,
			interestAcqAed: interestAcq,
			interestConAed: interestCon,
			interestPaidAed: totalInterest,
			totalUsesAed: totalUses,
			unleveredNetCashFlowAed: unleveredCf,
			netCfBeforeDebtAed: netCfBeforeDebt,
			acqEligibleUsesAed: acqEligibleThisMonth,
			acqDebtCommitmentAed: acqDebtCommitment,
			openingAcqDebtAed: openingAcqDebt,
			acqDebtDrawAed: acqDraw,
			acqDebtRepaymentAed: acqRepay,
			closingAcqDebtAed: acqDebtBalance,
			conEligibleUsesAed: conEligibleThisMonth,
			cumulativeConEligibleAed: round(cumulativeConEligible),
			conDebtMaxAllowedAed: conMaxAllowed,
			openingConDebtAed: openingConDebt,
			conDebtDrawAed: conDraw,
			conDebtRepaymentAed: conRepay,
			closingConDebtAed: conDebtBalance,
			debtDrawAed: totalDebtDraw,
			debtRepaymentAed: totalDebtRepay,
			debtBalanceAed: closingDebt,
			debtHeadroomAed: debtHeadroom,
			equityContributionAed: equityContribution,
			equityDistributionAed: equityDistribution,
			leveredNetCashFlowAed: leveredCf,
			// Legacy compat
			commitmentFeePaidAed: 0,
			landLoanBalanceAed: acqDebtBalance,
			constructionLoanBalanceAed: conDebtBalance,
			costPaidFromEscrowAed: 0,
			escrowBalanceAed: 0,
			landDrawAed: acqDraw,
			constructionDrawAed: conDraw,
			costConstructionAed: round(costHard + costSoft + costPermitFees),
			costProfessionalFeesAed: costSoft,
			costSalesAgentAed: costSalesAdmin,
			costInfrastructureAed: costInfrastructure,
			costAuthorityFeesAed: costGovernmentFees,
			costCommunityFeesAed: round(costCommunityFees + costFFE + costDemolition),
			costVatAed: vatThisMonth
		})
	}

	const totalRevenueAed = program.grossRevenueAed
	const totalCostsAed = costs.totalDevCostInclVatAed
	const peakFundingAed = Math.max(...cashFlowPeriods.map((p) => p.debtBalanceAed), 0)

	return {
		periods: cashFlowPeriods,
		totalRevenueAed,
		totalCostsAed,
		peakFundingAed
	}
}

// ── Waterfall ────────────────────────────────────────────────────────────────

function computeWaterfall(a: FeasibilityAssumptions, periods: CashFlowPeriod[]): WaterfallOutputs {
	const prefReturn = d(a, 'preferredReturnPa')
	const sponsorPromote = d(a, 'sponsorPromotePct')
	const years = d(a, 'projectYears')

	const totalEquityContributions = round(
		periods.reduce((sum, p) => sum + p.equityContributionAed, 0)
	)
	const totalEquityDistributions = round(
		periods.reduce((sum, p) => sum + p.equityDistributionAed, 0)
	)

	// Step 1: Return of capital
	const returnOfCapital = totalEquityContributions
	const cashRemainingAfterRoc = round(Math.max(totalEquityDistributions - returnOfCapital, 0))

	// Step 2: Preferred return
	const preferredReturnHurdle = round(totalEquityContributions * ((1 + prefReturn) ** years - 1))
	const preferredReturnPaid = round(Math.min(cashRemainingAfterRoc, preferredReturnHurdle))
	const cashRemainingAfterPref = round(Math.max(cashRemainingAfterRoc - preferredReturnPaid, 0))

	// Step 3: Residual split
	const residualToEquity = round(cashRemainingAfterPref * (1 - sponsorPromote))
	const sponsorPromoteAmt = round(cashRemainingAfterPref * sponsorPromote)

	return {
		totalEquityContributions,
		totalEquityDistributions,
		returnOfCapital,
		cashRemainingAfterRoc,
		preferredReturnHurdle,
		preferredReturnPaid,
		cashRemainingAfterPref,
		residualToEquity,
		sponsorPromote: sponsorPromoteAmt
	}
}

// ── Returns ──────────────────────────────────────────────────────────────────

function computeReturns(
	_a: FeasibilityAssumptions,
	program: ProgramOutputs,
	costs: CostOutputs,
	area: AreaBridgeOutputs,
	periods: CashFlowPeriod[]
): ReturnsOutputs {
	const projectCashflows = periods.map((p) => p.unleveredNetCashFlowAed)
	const equityCashflows = periods.map((p) => -p.equityContributionAed + p.equityDistributionAed)

	const projectIrrPct = periodicIrr(projectCashflows, 12)
	const equityIrrPct = periodicIrr(equityCashflows, 12)

	const totalInterestPaidAed = round(periods.reduce((sum, p) => sum + p.interestPaidAed, 0))
	const totalFinancingFeeAed = round(periods.reduce((sum, p) => sum + p.financingFeeAed, 0))
	const totalExitFeeAed = round(periods.reduce((sum, p) => sum + p.exitFeeAed, 0))
	const totalFinancingCostsAed = round(
		totalInterestPaidAed + totalFinancingFeeAed + totalExitFeeAed
	)

	const grossProfitAed = round(program.grossRevenueAed - costs.totalDevCostInclVatAed)
	const grossMarginPct =
		program.grossRevenueAed > 0 ? round((grossProfitAed / program.grossRevenueAed) * 100) : 0

	const allInProjectCostAed = round(costs.totalDevCostInclVatAed + totalFinancingCostsAed)
	const allInProjectProfitAed = round(program.grossRevenueAed - allInProjectCostAed)
	const allInMarginPct =
		program.grossRevenueAed > 0 ? round((allInProjectProfitAed / program.grossRevenueAed) * 100) : 0

	const projectMoic =
		costs.totalDevCostInclVatAed > 0
			? round(program.grossRevenueAed / costs.totalDevCostInclVatAed, 3)
			: 0

	const totalEquityContributed = round(periods.reduce((sum, p) => sum + p.equityContributionAed, 0))
	const totalEquityDistributed = round(periods.reduce((sum, p) => sum + p.equityDistributionAed, 0))
	const equityMoic =
		totalEquityContributed > 0 ? round(totalEquityDistributed / totalEquityContributed, 3) : 0

	const peakDebtAed = Math.max(...periods.map((p) => p.debtBalanceAed), 0)
	const peakEquityAed = peakNetSponsorCapital(periods)

	// New template metrics
	const leveredProfit = round(totalEquityDistributed - totalEquityContributed)
	const leveredMarginOnEquityPct =
		totalEquityContributed > 0 ? round((leveredProfit / totalEquityContributed) * 100) : 0
	const debtAsPctOfCost =
		costs.totalDevCostInclVatAed > 0 ? round((peakDebtAed / costs.totalDevCostInclVatAed) * 100) : 0

	// Break-even sale rate (total cost / sellable area in sqft)
	const sellableAreaSqft = area.sellableArea * SQM_TO_SQFT
	const breakEvenSaleRateAedSqft =
		sellableAreaSqft > 0 ? round(allInProjectCostAed / sellableAreaSqft, 0) : 0

	// Average debt outstanding
	const totalDebtMonths = periods.reduce((sum, p) => sum + p.debtBalanceAed, 0)
	const averageDebtOutstandingAed = periods.length > 0 ? round(totalDebtMonths / periods.length) : 0

	return {
		grossProfitAed,
		grossMarginPct,
		allInProjectCostAed,
		allInProjectProfitAed,
		allInMarginPct,
		projectIrrPct: projectIrrPct !== null ? round(projectIrrPct) : null,
		projectMoic,
		equityIrrPct: equityIrrPct !== null ? round(equityIrrPct) : null,
		equityMoic,
		totalInterestPaidAed,
		totalCommitmentFeesAed: 0, // legacy — no commitment fees in template model
		arrangementFeeAed: totalFinancingFeeAed,
		peakDebtAed,
		peakEquityAed,
		leveredMarginOnEquityPct,
		debtAsPctOfCost,
		breakEvenSaleRateAedSqft,
		averageDebtOutstandingAed,
		financingFeeAed: totalFinancingFeeAed,
		exitFeeAed: totalExitFeeAed,
		totalFinancingCostsAed
	}
}

// ── Financing ────────────────────────────────────────────────────────────────

function computeFinancing(
	a: FeasibilityAssumptions,
	costs: CostOutputs,
	program: ProgramOutputs,
	periods: CashFlowPeriod[]
): FinancingOutputs {
	const peakDebtAed = Math.max(...periods.map((p) => p.debtBalanceAed), 0)
	// Debt commitment from assumptions (LTV × land + LTC × construction)
	const acqLtv = d(a, 'acquisitionDebtLtv')
	const conLtc = d(a, 'constructionDebtLtc')
	const totalDebtCommitment = round(
		costs.totalLandCostAed * acqLtv + costs.totalConstructionCostAed * conLtc
	)
	const minDebtHeadroomAed = periods.length
		? Math.min(...periods.map((p) => p.debtHeadroomAed))
		: totalDebtCommitment
	const financingFeeAed = round(periods.reduce((sum, p) => sum + p.financingFeeAed, 0))
	const capitalizedInterestAed = round(periods.reduce((sum, p) => sum + p.interestPaidAed, 0))
	const exitFeeAed = round(periods.reduce((sum, p) => sum + p.exitFeeAed, 0))
	const totalFinanceCostsAed = round(financingFeeAed + capitalizedInterestAed + exitFeeAed)
	const finalPeriod = periods[periods.length - 1] ?? null
	const presalesAtConstructionStart = round(
		program.grossRevenueAed * (a.paymentPlan.depositPct / 100)
	)

	return {
		baseProjectCostAed: costs.totalDevCostInclVatAed,
		allInProjectCostAed: round(costs.totalDevCostInclVatAed + totalFinanceCostsAed),
		allInCostToRevenuePct:
			program.grossRevenueAed > 0
				? round(
						((costs.totalDevCostInclVatAed + totalFinanceCostsAed) / program.grossRevenueAed) * 100
					)
				: 0,
		presaleCoveragePctAtConstruction:
			program.grossRevenueAed > 0
				? round((presalesAtConstructionStart / program.grossRevenueAed) * 100)
				: 0,
		requiredCompletionReserveAed: round(program.grossRevenueAed * (a.escrowRetentionPct / 100)),
		completionReserveCoveragePct: 100, // simplified — escrow model not used in template
		sponsorReleaseCapacityAed: round(periods.reduce((sum, p) => sum + p.equityDistributionAed, 0)),
		debtCommitmentUtilizationPct:
			totalDebtCommitment > 0 ? round((peakDebtAed / totalDebtCommitment) * 100) : 0,
		debtCommitmentAed: totalDebtCommitment,
		peakDebtAed,
		minDebtHeadroomAed,
		arrangementFeeAed: financingFeeAed,
		initialCommitmentFeeAed: 0,
		capitalizedInterestAed,
		commitmentFeeCarryAed: exitFeeAed,
		totalFinanceCostsAed,
		equityContributedAed: round(periods.reduce((sum, p) => sum + p.equityContributionAed, 0)),
		equityDistributedAed: round(periods.reduce((sum, p) => sum + p.equityDistributionAed, 0)),
		closingDebtBalanceAed: finalPeriod?.debtBalanceAed ?? 0,
		closingEscrowBalanceAed: 0
	}
}

// ── Budget Timing ────────────────────────────────────────────────────────────

function computeBudgetTiming(periods: CashFlowPeriod[]): BudgetTimingOutputs {
	const budgetPeriods: BudgetTimingPeriod[] = periods.map((p) => ({
		periodLabel: p.periodLabel,
		periodEndDate: p.periodEndDate,
		budgetedCostsAed: round(p.operatingOutflowsAed),
		sellingCostsAed: round(p.costMarketingAed + p.costSalesAdminAed),
		constructionRelatedCostsAed: round(
			p.costHardAed + p.costSoftAed + p.costPermitFeesAed + p.costContingencyAed
		),
		vatCostsAed: p.vatPaidAed
	}))
	return {
		periods: budgetPeriods,
		totalBudgetedCostsAed: round(periods.reduce((sum, p) => sum + p.operatingOutflowsAed, 0))
	}
}

// ── Sources & Uses ───────────────────────────────────────────────────────────

function computeSourcesUses(costs: CostOutputs, periods: CashFlowPeriod[]): SourcesUsesOutputs {
	// ── Uses side: total project cost (dev costs + financing + VAT) ──
	const totalFinancingCosts = round(
		periods.reduce((sum, p) => sum + p.financingFeeAed + p.interestPaidAed + p.exitFeeAed, 0)
	)
	// Peak outstanding balance = max closing balance across all periods (not opening + draw,
	// which would ignore same-period repayments and overstate the peak).
	const peakAcquisitionDebtAed = round(Math.max(0, ...periods.map((p) => p.closingAcqDebtAed)))
	const peakConstructionDebtAed = round(Math.max(0, ...periods.map((p) => p.closingConDebtAed)))

	// ── Sources side: actual capital deployed ──
	// Equity = actual equity contributed month-by-month (never zero if equity was deployed).
	// Off-plan proceeds = plug = totalUses - peakDebt - actualEquity (portion that directly
	// funded costs, not profit returns or debt repayment recycling).
	const actualEquityAed = round(periods.reduce((sum, p) => sum + p.equityContributionAed, 0))

	const uses: SourcesUsesRow[] = [
		{
			category: 'use',
			code: 'land',
			label: 'Land acquisition',
			amountAed: costs.landAcquisitionAed,
			basis: 'plot area × land rate'
		},
		{
			category: 'use',
			code: 'land_fees',
			label: 'Land fees & legal',
			amountAed: round(costs.landTransferFeeAed + costs.brokerageFeeAed + costs.legalDdCostAed),
			basis: 'transfer + brokerage + legal'
		},
		{
			category: 'use',
			code: 'permit',
			label: 'Permit / authority fees',
			amountAed: costs.permitFeesAed,
			basis: '% of hard cost'
		},
		{
			category: 'use',
			code: 'hard_cost',
			label: 'Hard cost',
			amountAed: costs.hardCostAed,
			basis: 'costable BUA × rate'
		},
		{
			category: 'use',
			code: 'soft_cost',
			label: 'Soft cost',
			amountAed: costs.softCostAed,
			basis: '% of hard cost'
		},
		{
			category: 'use',
			code: 'contingency',
			label: 'Contingency',
			amountAed: costs.contingencyCostAed,
			basis: '% of hard cost'
		},
		...(costs.infrastructureCostAed > 0
			? [
					{
						category: 'use' as const,
						code: 'infrastructure',
						label: 'Infrastructure & utilities',
						amountAed: costs.infrastructureCostAed,
						basis: 'fixed AED'
					}
				]
			: []),
		...(costs.governmentFeesAed > 0
			? [
					{
						category: 'use' as const,
						code: 'govt_fees',
						label: 'Authority & connection fees',
						amountAed: costs.governmentFeesAed,
						basis: 'fixed AED'
					}
				]
			: []),
		...(costs.masterCommunityFeesAed > 0
			? [
					{
						category: 'use' as const,
						code: 'community_fees',
						label: 'Master community fees',
						amountAed: costs.masterCommunityFeesAed,
						basis: 'fixed AED'
					}
				]
			: []),
		...(costs.demolitionCostAed > 0
			? [
					{
						category: 'use' as const,
						code: 'demolition',
						label: 'Demolition / enabling works',
						amountAed: costs.demolitionCostAed,
						basis: 'fixed AED'
					}
				]
			: []),
		...(costs.ffeOsePreopeningCostAed > 0
			? [
					{
						category: 'use' as const,
						code: 'ffe',
						label: 'FF&E / pre-opening',
						amountAed: costs.ffeOsePreopeningCostAed,
						basis: 'fixed AED'
					}
				]
			: []),
		{
			category: 'use',
			code: 'marketing',
			label: 'Marketing',
			amountAed: costs.marketingCostAed,
			basis: '% of GDV'
		},
		{
			category: 'use',
			code: 'sales_admin',
			label: 'Sales admin',
			amountAed: costs.salesAdminCostAed,
			basis: '% of GDV'
		},
		{
			category: 'use',
			code: 'financing',
			label: 'Financing costs',
			amountAed: totalFinancingCosts,
			basis: 'fee + interest + exit fee'
		},
		{
			category: 'use',
			code: 'vat',
			label: 'VAT (net)',
			amountAed: costs.totalVatAed,
			basis: '5% on applicable categories'
		}
	]

	const totalUsesAed = round(uses.reduce((sum, u) => sum + u.amountAed, 0))

	// Proceeds as source = plug after peak debt and actual equity.
	// This represents the portion of buyer receipts that directly funded project costs
	// (as opposed to repaying debt or returning profit to the developer).
	const debtCoverage = peakAcquisitionDebtAed + peakConstructionDebtAed
	const proceedsAsSource = round(Math.max(totalUsesAed - debtCoverage - actualEquityAed, 0))

	const sources: SourcesUsesRow[] = [
		{
			category: 'source',
			code: 'land_loan',
			label: 'Acquisition debt',
			amountAed: peakAcquisitionDebtAed,
			basis: 'peak acquisition tranche commitment'
		},
		{
			category: 'source',
			code: 'construction_loan',
			label: 'Construction debt',
			amountAed: peakConstructionDebtAed,
			basis: 'peak construction tranche commitment'
		},
		{
			category: 'source',
			code: 'off_plan_proceeds',
			label: 'Off-plan proceeds',
			amountAed: proceedsAsSource,
			basis: 'buyer collections applied to project costs (excl. profit & debt recycling)'
		},
		{
			category: 'source',
			code: 'sponsor_equity',
			label: 'Sponsor equity',
			amountAed: actualEquityAed,
			basis: 'actual equity contributed by sponsor'
		}
	]

	const totalSourcesAed = round(sources.reduce((sum, s) => sum + s.amountAed, 0))

	return {
		sources,
		uses,
		totalSourcesAed,
		totalUsesAed,
		gapAed: round(totalUsesAed - totalSourcesAed)
	}
}

// ── VAT Bridge ───────────────────────────────────────────────────────────────

function computeVatBridge(costs: CostOutputs, periods: CashFlowPeriod[]): VatBridgeOutputs {
	const categories = [
		{
			label: 'Land Acquisition',
			costAed: costs.landAcquisitionAed,
			vatApplicable: costs.vatLandAed > 0,
			vatAed: costs.vatLandAed
		},
		{
			label: 'Hard Cost',
			costAed: costs.hardCostAed,
			vatApplicable: costs.vatHardCostAed > 0,
			vatAed: costs.vatHardCostAed
		},
		{
			label: 'Soft Cost',
			costAed: costs.softCostAed,
			vatApplicable: costs.vatSoftCostAed > 0,
			vatAed: costs.vatSoftCostAed
		},
		{
			label: 'Permit Fees',
			costAed: costs.permitFeesAed,
			vatApplicable: costs.vatPermitFeesAed > 0,
			vatAed: costs.vatPermitFeesAed
		},
		{
			label: 'Contingency',
			costAed: costs.contingencyCostAed,
			vatApplicable: costs.vatContingencyAed > 0,
			vatAed: costs.vatContingencyAed
		},
		{
			label: 'Marketing',
			costAed: costs.marketingCostAed,
			vatApplicable: costs.vatMarketingAed > 0,
			vatAed: costs.vatMarketingAed
		},
		{
			label: 'Sales Admin',
			costAed: costs.salesAdminCostAed,
			vatApplicable: costs.vatSalesAdminAed > 0,
			vatAed: costs.vatSalesAdminAed
		}
	]

	const totalCostAed = round(categories.reduce((sum, c) => sum + c.costAed, 0))
	const totalVatAed = round(categories.reduce((sum, c) => sum + c.vatAed, 0))
	const totalVatPaidMonthly = round(periods.reduce((sum, p) => sum + p.vatPaidAed, 0))
	const totalVatRefunded = round(periods.reduce((sum, p) => sum + p.vatRefundInflowsAed, 0))

	return {
		categories,
		totalCostAed,
		totalVatAed,
		totalVatPaidMonthly,
		totalVatRefunded,
		netVatPosition: round(totalVatPaidMonthly - totalVatRefunded)
	}
}

// ── Milestones ───────────────────────────────────────────────────────────────

function computeMilestones(a: FeasibilityAssumptions): MilestonesOutputs {
	const conStart = parseIsoDate(a.constructionDate, new Date())
	const handover = parseIsoDate(a.handoverDate, new Date())
	const salesStart = parseIsoDate(a.salesCommencementDate, new Date())
	const landAcq = parseIsoDate(a.landAcquisitionDate, new Date())
	const timelineStart = new Date(
		Math.min(landAcq.getTime(), conStart.getTime(), salesStart.getTime())
	)

	return {
		landAcquisition: a.landAcquisitionDate,
		constructionStart: a.constructionDate,
		salesCommencement: a.salesCommencementDate,
		preHandoverMilestone: a.preHandoverMilestoneDate,
		handover: a.handoverDate,
		constructionMonths: monthsBetween(conStart, handover),
		salesPeriodMonths: Math.round(a.salesPeriodMonths),
		totalProjectMonths: monthsBetween(timelineStart, handover)
	}
}

// ── Annual Cash Flow Rollup ──────────────────────────────────────────────────

function computeAnnualCashFlow(periods: CashFlowPeriod[]): AnnualCashFlowOutputs {
	const byYear = new Map<number, AnnualCashFlowRow>()
	for (const p of periods) {
		const year = parseInt(p.periodEndDate.slice(0, 4), 10)
		if (!byYear.has(year)) {
			byYear.set(year, {
				year,
				revenueAed: 0,
				costsAed: 0,
				unleveredCfAed: 0,
				debtDrawAed: 0,
				debtRepayAed: 0,
				interestAed: 0,
				equityInAed: 0,
				equityOutAed: 0,
				leveredCfAed: 0,
				closingDebtAed: 0
			})
		}
		const row = byYear.get(year)
		if (!row) continue
		row.revenueAed += p.revenueInflowsAed
		row.costsAed += p.operatingOutflowsAed
		row.unleveredCfAed += p.unleveredNetCashFlowAed
		row.debtDrawAed += p.debtDrawAed
		row.debtRepayAed += p.debtRepaymentAed
		row.interestAed += p.interestPaidAed
		row.equityInAed += p.equityContributionAed
		row.equityOutAed += p.equityDistributionAed
		row.leveredCfAed += p.leveredNetCashFlowAed
		row.closingDebtAed = p.debtBalanceAed // last month of year
	}
	const rows = Array.from(byYear.values()).sort((a, b) => a.year - b.year)
	// Round all values
	for (const row of rows) {
		row.revenueAed = round(row.revenueAed)
		row.costsAed = round(row.costsAed)
		row.unleveredCfAed = round(row.unleveredCfAed)
		row.debtDrawAed = round(row.debtDrawAed)
		row.debtRepayAed = round(row.debtRepayAed)
		row.interestAed = round(row.interestAed)
		row.equityInAed = round(row.equityInAed)
		row.equityOutAed = round(row.equityOutAed)
		row.leveredCfAed = round(row.leveredCfAed)
	}
	return { rows }
}

// ── Main Entry Point ─────────────────────────────────────────────────────────

// ══════════════════════════════════════════════════════════════════════════════
// BTR (Build-to-Rent) Engine
// ══════════════════════════════════════════════════════════════════════════════
// Computes operating income, NOI, exit valuation, permanent debt sizing,
// and full-cycle levered/unlevered returns for a build-to-rent hold strategy.
//
// The development phase (area, costs, construction CF) reuses the BTS engine.
// BTR adds: lease-up ramp, annual operating P&L, exit via cap rate, perm refi.
// ══════════════════════════════════════════════════════════════════════════════

const BTR_DEFAULTS = BTR_WORKBOOK_DEFAULTS

function btr<K extends keyof typeof BTR_DEFAULTS>(a: FeasibilityAssumptions, key: K): number {
	const v = (a as unknown as Record<string, unknown>)[key]
	return (v !== undefined && v !== null ? v : BTR_DEFAULTS[key]) as number
}

function computeBtrProgram(a: FeasibilityAssumptions): BtrProgramOutputs {
	const configs: BtrUnitConfig[] = a.btrUnitConfigs ?? []
	// If no BTR configs, derive from BTS unit configs with default rents
	const effectiveConfigs: BtrUnitConfig[] =
		configs.length > 0
			? configs
			: (a.unitConfigs ?? []).map((uc) => ({
					id: uc.id,
					label: uc.label,
					units: uc.units,
					avgSizeSqm: uc.avgSizeSqm,
					monthlyRentAed: Math.round(uc.avgSizeSqm * 10.764 * 8), // rough: 8 AED/sqft/month
					parkingRatio: uc.parkingRatio
				}))

	const rows: BtrProgramRow[] = effectiveConfigs.map((c) => {
		const totalAreaSqm = round(c.units * c.avgSizeSqm)
		const annualRentAed = round(c.units * c.monthlyRentAed * 12)
		const parkingSpaces = Math.ceil(c.units * c.parkingRatio)
		return {
			id: c.id,
			label: c.label,
			units: c.units,
			avgSizeSqm: c.avgSizeSqm,
			totalAreaSqm,
			monthlyRentAed: c.monthlyRentAed,
			annualRentAed,
			parkingSpaces
		}
	})

	const totalUnits = rows.reduce((s, r) => s + r.units, 0)
	const totalAreaSqm = round(rows.reduce((s, r) => s + r.totalAreaSqm, 0))
	const totalParkingSpaces = rows.reduce((s, r) => s + r.parkingSpaces, 0)
	const grossPotentialRentAed = round(rows.reduce((s, r) => s + r.annualRentAed, 0))
	const weightedAvgRentPsqmMonth =
		totalAreaSqm > 0 ? round(grossPotentialRentAed / 12 / totalAreaSqm, 2) : 0

	return {
		rows,
		totalUnits,
		totalAreaSqm,
		totalParkingSpaces,
		grossPotentialRentAed,
		weightedAvgRentPsqmMonth
	}
}

// ── BTR Development Costs (no GDV-based marketing/sales-admin) ──────────────

function computeBtrDevCosts(a: FeasibilityAssumptions, area: AreaBridgeOutputs): BtrDevCostOutputs {
	const plotArea = a.plotAreaSqm
	const costableBua = area.totalCostableBua ?? a.maxGfaSqm * (a.buaMultiplier || 1.1)

	// Land acquisition
	const landAcquisition =
		positiveOverride(a.landAcquisitionCostOverrideAed) ?? round(plotArea * a.landPricePsqm)
	const landTransferFee = round(landAcquisition * (a.landTransferFeePct ?? 0.04))
	const brokerageFee = round(landAcquisition * (a.brokeragePct ?? 0.01))
	const legalDd = round(landAcquisition * (a.legalDdPct ?? 0.005))
	const totalLand = round(landAcquisition + landTransferFee + brokerageFee + legalDd)

	// Construction
	const constructionStartDate = parseIsoDate(a.constructionDate, new Date())
	const handoverDate = parseIsoDate(a.handoverDate, addMonths(constructionStartDate, 24))
	const constructionYearsToMidpoint =
		Math.max(monthsBetween(constructionStartDate, handoverDate), 1) / 24
	const devEscalation = btr(a, 'btrDevCostEscalationPct') / 100
	const hardCostBase = round(costableBua * a.constructionCostPsqmBua)
	const hardCostEscalated = round(hardCostBase * (1 + devEscalation) ** constructionYearsToMidpoint)
	const hardCost = positiveOverride(a.constructionCostOverrideAed) ?? hardCostEscalated
	const softCost = round(hardCost * (a.softCostPct ?? 0.15))
	const permitFees = round(hardCost * (a.permitFeesPct ?? 0.02))
	const contingency =
		positiveOverride(a.contingencyCostOverrideAed) ?? round(hardCost * (a.contingencyPct / 100))
	const totalConstruction = round(permitFees + hardCost + softCost + contingency)

	// Lease-up marketing: flat budget, NOT derived from GDV
	const leaseUpMarketing = round(btr(a, 'btrLeaseUpMarketingAed'))

	// Statutory & development costs — same categories as BTS (fixed in April 2025)
	const demolitionCostAed = a.demolitionEnabled ? (a.demolitionCostAed ?? 0) : 0
	const infrastructureCostAed = a.infrastructureCostAed ?? 0
	const governmentFeesAed = a.governmentFeesAed ?? 0
	const masterCommunityFeesAed = a.masterCommunityFeesAed ?? 0
	const ffeOsePreopeningCostAed = a.ffeOsePreopeningCostAed ?? 0
	const totalStatutory = round(
		infrastructureCostAed +
			governmentFeesAed +
			masterCommunityFeesAed +
			ffeOsePreopeningCostAed +
			demolitionCostAed
	)

	const totalExclVat = round(totalLand + totalConstruction + leaseUpMarketing + totalStatutory)

	// VAT (same logic as BTS but no marketing/salesAdmin from GDV)
	const vatPct = a.vatPct / 100
	const vat = a.vatAppliesTo ?? {
		land: true,
		hardCosts: true,
		softCosts: true,
		permitFees: true,
		contingency: true,
		marketing: true,
		salesAdmin: true
	}
	const totalVat = round(
		(vat.land ? landAcquisition * vatPct : 0) +
			(vat.hardCosts ? hardCost * vatPct : 0) +
			(vat.softCosts ? softCost * vatPct : 0) +
			(vat.permitFees ? permitFees * vatPct : 0) +
			(vat.contingency ? contingency * vatPct : 0) +
			(vat.marketing ? leaseUpMarketing * vatPct : 0)
	)

	return {
		landAcquisitionAed: landAcquisition,
		landTransferFeeAed: landTransferFee,
		brokerageFeeAed: brokerageFee,
		legalDdCostAed: legalDd,
		totalLandCostAed: totalLand,
		permitFeesAed: permitFees,
		hardCostAed: hardCost,
		softCostAed: softCost,
		contingencyCostAed: contingency,
		totalConstructionCostAed: totalConstruction,
		infrastructureCostAed,
		governmentFeesAed,
		masterCommunityFeesAed,
		ffeOsePreopeningCostAed,
		demolitionCostAed,
		leaseUpMarketingAed: leaseUpMarketing,
		totalVatAed: totalVat,
		totalDevCostExclVatAed: totalExclVat,
		totalDevCostInclVatAed: round(totalExclVat + totalVat)
	}
}

// ── BTR Development Cash Flow (equity + dev debt only, NO sale proceeds) ────

function computeBtrDevCashFlow(
	a: FeasibilityAssumptions,
	devCosts: BtrDevCostOutputs
): {
	periods: BtrDevPeriod[]
	totalDevDebt: number
	totalDevEquity: number
	totalDevInterest: number
	constructionMonths: number
} {
	const constructionStartDate = parseIsoDate(a.constructionDate, new Date())
	const handoverDate = parseIsoDate(a.handoverDate, addMonths(constructionStartDate, 24))
	const landAcqDate = parseIsoDate(a.landAcquisitionDate, constructionStartDate)
	const demolitionDate = parseIsoDate(a.demolitionEnablingDate, constructionStartDate)
	const vatLagMonths = d(a, 'vatRefundLagMonths')

	// Timeline: land acquisition → handover + VAT refund tail
	const timelineStart = new Date(Math.min(landAcqDate.getTime(), constructionStartDate.getTime()))
	const timelineEnd = addMonths(handoverDate, vatLagMonths)
	const monthEnds = iterMonthEnds(timelineStart, timelineEnd)

	const constructionStartMe = endOfMonth(constructionStartDate)
	const handoverMe = endOfMonth(handoverDate)
	const landPeriodEnd = endOfMonth(landAcqDate)
	const demolitionMe = endOfMonth(demolitionDate)

	const key = (dt: Date) => dt.toISOString().slice(0, 10)

	// Construction period for S-curve
	const constructionMonthEnds = monthEnds.filter(
		(m) => m.getTime() >= constructionStartMe.getTime() && m.getTime() < handoverMe.getTime()
	)
	const constructionCount = Math.max(constructionMonthEnds.length, 1)
	const constructionMonths = constructionCount

	const conSteepness = d(a, 'constructionCurveSteepness')
	const conWeights = scurveWeights(constructionCount, conSteepness)
	const conWeightMap = new Map<string, number>()
	constructionMonthEnds.forEach((m, i) => {
		conWeightMap.set(key(m), i)
	})

	// ── Debt parameters — dual-tranche ──
	const acqLtv = d(a, 'acquisitionDebtLtv')
	const conLtc = d(a, 'constructionDebtLtc')
	const eiborPa = (a.eiborRatePct ?? 4.85) / 100
	const acqSpreadPa = a.landLoanSpreadBps > 0 ? a.landLoanSpreadBps / 10000 : debtSpreadPct(a) / 100
	const conSpreadPa =
		a.constructionLoanSpreadBps > 0 ? a.constructionLoanSpreadBps / 10000 : debtSpreadPct(a) / 100
	const acqMonthlyRate = (eiborPa + acqSpreadPa) / 12
	const conMonthlyRate = (eiborPa + conSpreadPa) / 12

	// Acq eligible = land + land fees (drawn at land month)
	const acqEligibleTotal =
		devCosts.landAcquisitionAed +
		devCosts.landTransferFeeAed +
		devCosts.brokerageFeeAed +
		devCosts.legalDdCostAed
	const acqDebtCommitment = round(acqEligibleTotal * acqLtv)

	// Con eligible = permit + hard + soft + contingency
	const conEligibleTotal =
		devCosts.permitFeesAed +
		devCosts.hardCostAed +
		devCosts.softCostAed +
		devCosts.contingencyCostAed
	const conDebtMaxTotal = round(conEligibleTotal * conLtc)
	const financingFeePct = d(a, 'financingFeePct')
	const exitFeePct = d(a, 'exitFeePct')
	const totalDebtCommitment = round(acqDebtCommitment + conDebtMaxTotal)

	// ── VAT ──
	const vat = d(a, 'vatAppliesTo')
	const vatRate = a.vatPct / 100
	const vatPaidHistory: number[] = []

	const periods: BtrDevPeriod[] = []
	let acqDebtBalance = 0
	let conDebtBalance = 0
	let cumulativeConEligible = 0
	let totalInterest = 0

	for (let mi = 0; mi < monthEnds.length; mi++) {
		const periodEnd = monthEnds[mi]
		const pk = key(periodEnd)
		const isLandMonth = periodEnd.getTime() === landPeriodEnd.getTime()
		const isHandover = periodEnd.getTime() === handoverMe.getTime()
		const isConstructionStart = periodEnd.getTime() === constructionStartMe.getTime()
		const isDemolitionMonth =
			(a.demolitionEnabled ?? false) && periodEnd.getTime() === demolitionMe.getTime()
		const isAfterHandover = periodEnd.getTime() > handoverMe.getTime()

		const conIdx = conWeightMap.get(pk)
		const conPct = conIdx !== undefined ? conWeights[conIdx] : 0

		// ── Cost allocation (same timing rules as BTS) ──
		const costLand = isLandMonth ? devCosts.landAcquisitionAed : 0
		const costLandFees = isLandMonth
			? round(devCosts.landTransferFeeAed + devCosts.brokerageFeeAed + devCosts.legalDdCostAed)
			: 0
		const costPermitFees = round(devCosts.permitFeesAed * conPct)
		const costHard = round(devCosts.hardCostAed * conPct)
		const costSoft = round(devCosts.softCostAed * conPct)
		const costContingency = round(devCosts.contingencyCostAed * conPct)
		// Lease-up marketing: spread over construction period (proxy for pre-opening activity)
		const costLeaseUpMarketing = round(devCosts.leaseUpMarketingAed * conPct)
		// Statutory: same timing as BTS
		const costInfrastructure = round(devCosts.infrastructureCostAed * conPct)
		const costGovernmentFees = isConstructionStart ? devCosts.governmentFeesAed : 0
		const costCommunityFees = isHandover ? devCosts.masterCommunityFeesAed : 0
		const costFFE = isHandover ? devCosts.ffeOsePreopeningCostAed : 0
		const costDemolition = isDemolitionMonth ? devCosts.demolitionCostAed : 0

		const operatingOutflows = isAfterHandover
			? 0
			: round(
					costLand +
						costLandFees +
						costPermitFees +
						costHard +
						costSoft +
						costContingency +
						costLeaseUpMarketing +
						costInfrastructure +
						costGovernmentFees +
						costCommunityFees +
						costFFE +
						costDemolition
				)

		// ── VAT ──
		const vatThisMonth = isAfterHandover
			? 0
			: round(
					(vat.land ? costLand * vatRate : 0) +
						(vat.hardCosts ? costHard * vatRate : 0) +
						(vat.softCosts ? costSoft * vatRate : 0) +
						(vat.permitFees ? costPermitFees * vatRate : 0) +
						(vat.contingency ? costContingency * vatRate : 0) +
						(vat.marketing ? costLeaseUpMarketing * vatRate : 0)
				)
		vatPaidHistory.push(vatThisMonth)
		const vatRefund = mi >= vatLagMonths ? (vatPaidHistory[mi - vatLagMonths] ?? 0) : 0

		// ── Interest on opening balances ──
		const acqInterest = round(acqDebtBalance * acqMonthlyRate)
		const conInterest = round(conDebtBalance * conMonthlyRate)
		const totalInterestThisMonth = round(acqInterest + conInterest)
		totalInterest += totalInterestThisMonth
		const financingFee = isLandMonth ? round(totalDebtCommitment * financingFeePct) : 0
		const exitFee = isHandover ? round((acqDebtBalance + conDebtBalance) * exitFeePct) : 0

		// ── Funding need = outflows + VAT + interest - VAT refund received ──
		const fundingNeed = round(
			operatingOutflows + vatThisMonth + totalInterestThisMonth + financingFee + exitFee - vatRefund
		)

		// ── Acq tranche: draw full commitment at land month ──
		let acqDebtDraw = 0
		if (isLandMonth) {
			acqDebtDraw = round(Math.min(acqDebtCommitment, Math.max(fundingNeed, 0)))
		}
		acqDebtBalance = round(acqDebtBalance + acqDebtDraw)

		// ── Con tranche: draw up to LTC × cumulative eligible ──
		const conEligibleThisMonth = round(costPermitFees + costHard + costSoft + costContingency)
		cumulativeConEligible = round(cumulativeConEligible + conEligibleThisMonth)
		const maxConDebt = round(Math.min(cumulativeConEligible * conLtc, conDebtMaxTotal))
		const remainingAfterAcq = round(fundingNeed - acqDebtDraw)
		const conDebtDraw = round(
			Math.min(Math.max(maxConDebt - conDebtBalance, 0), Math.max(remainingAfterAcq, 0))
		)
		conDebtBalance = round(conDebtBalance + conDebtDraw)

		// ── Equity fills the residual ──
		const totalDebtDraw = round(acqDebtDraw + conDebtDraw)
		const totalDebtBalance = round(acqDebtBalance + conDebtBalance)
		const equity = round(fundingNeed - totalDebtDraw)
		const totalUses = round(
			operatingOutflows + vatThisMonth + totalInterestThisMonth + financingFee + exitFee
		)

		const periodDate = monthEnds[mi]
		periods.push({
			month: mi + 1,
			periodLabel: `${periodDate.getUTCFullYear()}-${String(periodDate.getUTCMonth() + 1).padStart(2, '0')}`,
			costOutflowAed: operatingOutflows,
			vatPaidAed: vatThisMonth,
			vatRefundAed: vatRefund,
			acqDebtDrawAed: acqDebtDraw,
			acqDebtBalanceAed: acqDebtBalance,
			conDebtDrawAed: conDebtDraw,
			conDebtBalanceAed: conDebtBalance,
			devDebtDrawAed: totalDebtDraw,
			devDebtBalanceAed: totalDebtBalance,
			interestAed: totalInterestThisMonth,
			financingFeeAed: financingFee,
			exitFeeAed: exitFee,
			equityContributionAed: equity,
			totalUsesAed: totalUses
		})
	}

	const totalDevDebt = round(periods.reduce((s, p) => s + p.devDebtDrawAed, 0))
	const totalDevEquity = round(periods.reduce((s, p) => s + p.equityContributionAed, 0))
	const totalFees = round(periods.reduce((s, p) => s + p.financingFeeAed + p.exitFeeAed, 0))

	return {
		periods,
		totalDevDebt,
		totalDevEquity,
		totalDevInterest: round(totalInterest + totalFees),
		constructionMonths
	}
}

// ── BTR Operating P&L ───────────────────────────────────────────────────────

function computeBtrOperatingMonths(
	a: FeasibilityAssumptions,
	btrProgram: BtrProgramOutputs,
	permDebt: BtrPermDebtOutputs,
	stabilizationYear: number,
	devDebtBalanceAtHandover = 0
): BtrOperatingMonth[] {
	const holdYears = btr(a, 'btrHoldPeriodYears')
	const leaseUpPace = btr(a, 'btrLeaseUpPaceUnitsPerMonth')
	const stabilizedOccPct = btr(a, 'btrStabilizedOccupancyPct') / 100
	const freeRentMonths = btr(a, 'btrFreeRentMonths')
	const stabilizedFreeRent = btr(a, 'btrStabilizedFreeRentMonths')
	const annualRentGrowth =
		(btr(a, 'btrMarketRentGrowthPct') || btr(a, 'btrAnnualRentGrowthPct')) / 100
	const generalVacancy = btr(a, 'btrGeneralVacancyPct') / 100
	const pmFeePct = btr(a, 'btrPropertyManagementPct') / 100
	const rmPsqm = btr(a, 'btrRepairsMaintenancePsqm')
	const insurancePsqm = btr(a, 'btrInsurancePsqm')
	const scPsqm = btr(a, 'btrServiceChargePsqm')
	const utilPsqm = btr(a, 'btrUtilitiesPsqm')
	const mktPct = btr(a, 'btrMarketingLeasingPct') / 100
	const capexPct = btr(a, 'btrCapexReservePct') / 100
	const parkingIncome = btr(a, 'btrParkingIncomeAed')
	const ancillaryIncome = btr(a, 'btrAncillaryIncomeAed')
	const ancillaryGrowth = btr(a, 'btrAncillaryGrowthPct') / 100
	const opExGrowth = btr(a, 'btrOpExGrowthPct') / 100
	const creditLossPct = btr(a, 'btrCreditLossPct') / 100
	const payrollPsqm = btr(a, 'btrPayrollPsqm')
	const generalAdminPct = btr(a, 'btrGeneralAdminPct') / 100
	const contractServicesPsqm = btr(a, 'btrContractServicesPsqm')
	const modelUnits = btr(a, 'btrModelUnits')
	const ioYears = btr(a, 'btrPermDebtIoYears')

	const totalUnits = btrProgram.totalUnits
	const totalArea = btrProgram.totalAreaSqm
	if (totalUnits <= 0) return []

	const unitsToLeaseUp = Math.ceil(totalUnits * stabilizedOccPct)
	const leaseUpMonths = leaseUpPace > 0 ? Math.ceil(unitsToLeaseUp / leaseUpPace) : 12
	const handoverDate = parseIsoDate(a.handoverDate, new Date())
	const firstOpsMonth = addMonths(endOfMonth(handoverDate), 1)
	const rows: BtrOperatingMonth[] = []

	for (let month = 1; month <= holdYears * 12; month++) {
		const periodDate = endOfMonth(addMonths(firstOpsMonth, month - 1))
		const year = Math.ceil(month / 12)
		const yearsElapsed = (month - 1) / 12
		const rentGrowthFactor = (1 + annualRentGrowth) ** yearsElapsed
		const opExGrowthFactor = (1 + opExGrowth) ** yearsElapsed
		const ancillaryGrowthFactor = (1 + ancillaryGrowth) ** yearsElapsed
		const isLeaseUp = month <= leaseUpMonths
		const occupiedUnits = isLeaseUp
			? Math.min(month * leaseUpPace, unitsToLeaseUp)
			: totalUnits * stabilizedOccPct
		const avgOccupancy = isLeaseUp
			? Math.min(occupiedUnits / totalUnits, stabilizedOccPct)
			: stabilizedOccPct

		const unitTypeIncomes = btrProgram.rows.map((unit) => {
			const grossPotentialRentAed = round(unit.units * unit.monthlyRentAed * rentGrowthFactor)
			const effectiveRentalIncomeAed = round(grossPotentialRentAed * avgOccupancy)
			return {
				id: unit.id,
				label: unit.label,
				units: unit.units,
				grossPotentialRentAed,
				effectiveRentalIncomeAed
			}
		})

		const grossPotentialRent = round(
			unitTypeIncomes.reduce((s, row) => s + row.grossPotentialRentAed, 0)
		)
		const baseModelUnitDeductionMonth =
			((btrProgram.grossPotentialRentAed / 12) * modelUnits) / totalUnits
		const modelUnitDeduction = round(baseModelUnitDeductionMonth * rentGrowthFactor)
		const adjustedGPR = round(grossPotentialRent - modelUnitDeduction)
		const concessionsFreeMonths = isLeaseUp ? freeRentMonths : stabilizedFreeRent
		const concessionsPct = concessionsFreeMonths / 12
		const concessions = round(adjustedGPR * avgOccupancy * concessionsPct)
		const effectiveRentalIncome = round(adjustedGPR * avgOccupancy - concessions)
		const otherIncome = round(
			((parkingIncome + ancillaryIncome) / 12) * ancillaryGrowthFactor * avgOccupancy
		)
		const totalPotentialIncome = round(effectiveRentalIncome + otherIncome)
		const vacancyLoss = round(totalPotentialIncome * generalVacancy)
		const creditLoss = round(totalPotentialIncome * creditLossPct)
		const vacancyCreditLoss = round(vacancyLoss + creditLoss)
		const egr = round(totalPotentialIncome - vacancyCreditLoss)

		const propertyManagement = round(egr * pmFeePct)
		const repairsMaintenance = round((totalArea * rmPsqm * opExGrowthFactor * avgOccupancy) / 12)
		const payroll = round((totalArea * payrollPsqm * opExGrowthFactor) / 12)
		const generalAdmin = round(egr * generalAdminPct)
		const contractServices = round((totalArea * contractServicesPsqm * opExGrowthFactor) / 12)
		const insurance = round((totalArea * insurancePsqm * opExGrowthFactor) / 12)
		const serviceCharge = round((totalArea * scPsqm * opExGrowthFactor) / 12)
		const utilities = round((totalArea * utilPsqm * opExGrowthFactor * avgOccupancy) / 12)
		const marketingLeasing = round(egr * mktPct)
		const totalOpEx = round(
			propertyManagement +
				repairsMaintenance +
				payroll +
				generalAdmin +
				contractServices +
				insurance +
				serviceCharge +
				utilities +
				marketingLeasing
		)
		const opExRatio = egr > 0 ? round(totalOpEx / egr, 4) : 0
		const noi = round(egr - totalOpEx)
		const capexReserve = round(Math.max(noi, 0) * capexPct)
		const cfo = round(noi - capexReserve)

		let debtService = 0
		if (year < stabilizationYear && devDebtBalanceAtHandover > 0) {
			// Carry is capitalized until the refi event; do not also deduct it from operating CF.
			debtService = 0
		} else if (year >= stabilizationYear) {
			const yearsAfterRefi = year - stabilizationYear
			debtService = round(
				(yearsAfterRefi < ioYears ? permDebt.ioDebtServiceAed : permDebt.annualDebtServiceAed) / 12
			)
		}
		const cfaf = round(cfo - debtService)

		rows.push({
			month,
			periodLabel: `${periodDate.getUTCFullYear()}-${String(periodDate.getUTCMonth() + 1).padStart(2, '0')}`,
			year,
			isLeaseUp,
			occupancyPct: round((isLeaseUp ? avgOccupancy : stabilizedOccPct) * 100, 1),
			grossPotentialRentAed: grossPotentialRent,
			unitTypeIncomes,
			modelUnitDeductionAed: modelUnitDeduction,
			concessionsAed: concessions,
			effectiveRentalIncomeAed: effectiveRentalIncome,
			otherIncomeAed: otherIncome,
			totalPotentialIncomeAed: totalPotentialIncome,
			vacancyAed: vacancyLoss,
			creditLossAed: creditLoss,
			vacancyCreditLossAed: vacancyCreditLoss,
			effectiveGrossRevenueAed: egr,
			propertyManagementAed: propertyManagement,
			repairsMaintenanceAed: repairsMaintenance,
			payrollAed: payroll,
			generalAdminAed: generalAdmin,
			contractServicesAed: contractServices,
			insuranceAed: insurance,
			serviceChargeAed: serviceCharge,
			utilitiesAed: utilities,
			marketingLeasingAed: marketingLeasing,
			totalOpExAed: totalOpEx,
			opExRatio,
			noiAed: noi,
			capexReserveAed: capexReserve,
			cfoAed: cfo,
			debtServiceAed: debtService,
			cfafAed: cfaf
		})
	}

	return rows
}

function aggregateBtrOperatingYears(months: BtrOperatingMonth[]): BtrOperatingYear[] {
	const years: BtrOperatingYear[] = []
	const yearNumbers = [...new Set(months.map((month) => month.year))]
	for (const year of yearNumbers) {
		const rows = months.filter((month) => month.year === year)
		const total = (field: keyof BtrOperatingMonth) =>
			round(
				rows.reduce(
					(sum, row) => sum + (typeof row[field] === 'number' ? (row[field] as number) : 0),
					0
				)
			)
		const egr = total('effectiveGrossRevenueAed')
		const noi = total('noiAed')
		years.push({
			year,
			yearLabel: `Year ${year}`,
			isLeaseUp: rows.some((row) => row.isLeaseUp),
			occupancyPct: round(rows.reduce((sum, row) => sum + row.occupancyPct, 0) / rows.length, 1),
			grossPotentialRentAed: total('grossPotentialRentAed'),
			modelUnitDeductionAed: total('modelUnitDeductionAed'),
			concessionsAed: total('concessionsAed'),
			effectiveRentalIncomeAed: total('effectiveRentalIncomeAed'),
			otherIncomeAed: total('otherIncomeAed'),
			totalPotentialIncomeAed: total('totalPotentialIncomeAed'),
			vacancyAed: total('vacancyAed'),
			creditLossAed: total('creditLossAed'),
			vacancyCreditLossAed: total('vacancyCreditLossAed'),
			effectiveGrossRevenueAed: egr,
			propertyManagementAed: total('propertyManagementAed'),
			repairsMaintenanceAed: total('repairsMaintenanceAed'),
			payrollAed: total('payrollAed'),
			generalAdminAed: total('generalAdminAed'),
			contractServicesAed: total('contractServicesAed'),
			insuranceAed: total('insuranceAed'),
			serviceChargeAed: total('serviceChargeAed'),
			utilitiesAed: total('utilitiesAed'),
			marketingLeasingAed: total('marketingLeasingAed'),
			totalOpExAed: total('totalOpExAed'),
			opExRatio: egr > 0 ? round(total('totalOpExAed') / egr, 4) : 0,
			noiAed: noi,
			capexReserveAed: total('capexReserveAed'),
			cfoAed: total('cfoAed'),
			debtServiceAed: total('debtServiceAed'),
			cfafAed: total('cfafAed')
		})
	}
	return years
}

function computeBtrExit(
	a: FeasibilityAssumptions,
	operatingYears: BtrOperatingYear[],
	totalDevCostAed: number
): BtrExitOutputs {
	const exitCapRate = btr(a, 'btrExitCapRatePct') / 100
	const exitCostPct = btr(a, 'btrExitCostPct') / 100
	const holdYears = btr(a, 'btrHoldPeriodYears')

	const lastYear = operatingYears[operatingYears.length - 1]
	const terminalGrowth = btr(a, 'btrTerminalGrowthPct') / 100
	const opExGrowth = btr(a, 'btrOpExGrowthPct') / 100
	const pmFeePct = btr(a, 'btrPropertyManagementPct') / 100
	const mktPct = btr(a, 'btrMarketingLeasingPct') / 100
	const generalAdminPct = btr(a, 'btrGeneralAdminPct') / 100
	const fixedVariableOpEx = lastYear
		? lastYear.totalOpExAed -
			lastYear.propertyManagementAed -
			lastYear.marketingLeasingAed -
			lastYear.generalAdminAed
		: 0
	const terminalEgr = round((lastYear?.effectiveGrossRevenueAed ?? 0) * (1 + terminalGrowth))
	const terminalFixedVariableOpEx = round(fixedVariableOpEx * (1 + opExGrowth))
	const terminalRatioBasedOpEx = round(terminalEgr * (pmFeePct + mktPct + generalAdminPct))
	const terminalNoi = round(terminalEgr - terminalFixedVariableOpEx - terminalRatioBasedOpEx)

	const grossSalePrice = exitCapRate > 0 ? round(terminalNoi / exitCapRate) : 0
	const exitCosts = round(grossSalePrice * exitCostPct)
	const netSaleProceeds = round(grossSalePrice - exitCosts)

	const stabilizedYear = operatingYears.find((y) => !y.isLeaseUp) ?? lastYear
	const stabilizedNoi = stabilizedYear?.noiAed ?? 0
	const grossPotentialRent = stabilizedYear?.grossPotentialRentAed ?? 0

	const devYield = totalDevCostAed > 0 ? round((stabilizedNoi / totalDevCostAed) * 100, 2) : 0
	const grossYield =
		totalDevCostAed > 0 ? round((grossPotentialRent / totalDevCostAed) * 100, 2) : 0
	const devSpreadBps = round((devYield - btr(a, 'btrExitCapRatePct')) * 100)

	return {
		exitYear: holdYears,
		terminalNoiAed: terminalNoi,
		exitCapRatePct: btr(a, 'btrExitCapRatePct'),
		grossSalePriceAed: grossSalePrice,
		exitCostsAed: exitCosts,
		netSaleProceedsAed: netSaleProceeds,
		devYieldPct: devYield,
		grossYieldPct: grossYield,
		netYieldPct: netSaleProceeds > 0 ? round((stabilizedNoi / netSaleProceeds) * 100, 2) : 0,
		developmentSpreadBps: devSpreadBps
	}
}

function computeBtrDevDebtCarryToRefi(
	a: FeasibilityAssumptions,
	devDebtBalance: number,
	stabilizationYear: number
): number {
	if (devDebtBalance <= 0 || stabilizationYear <= 1) return 0
	const eiborPa = (a.eiborRatePct ?? 4.85) / 100
	const conSpreadPa =
		a.constructionLoanSpreadBps > 0 ? a.constructionLoanSpreadBps / 10000 : debtSpreadPct(a) / 100
	const monthlyRate = (eiborPa + conSpreadPa) / 12
	return round(devDebtBalance * monthlyRate * (stabilizationYear - 1) * 12)
}

function computeBtrPermDebt(
	a: FeasibilityAssumptions,
	stabilizedNoiAed: number,
	devDebtBalance: number,
	holdYears: number,
	stabilizationYear: number
): BtrPermDebtOutputs {
	const ltvPct = btr(a, 'btrPermDebtLtvPct') / 100
	const permSpreadBps = btr(a, 'btrPermDebtSpreadBps')
	const explicitPermRate = (a.btrPermDebtRatePct ?? 0) > 0 && permSpreadBps <= 0
	const allInRate = explicitPermRate
		? (a.btrPermDebtRatePct ?? 0) / 100
		: ((a.eiborRatePct ?? 4.85) + permSpreadBps / 100) / 100
	const amortYears = btr(a, 'btrPermDebtAmortYears')
	const dscrMin = btr(a, 'btrDscrMinimum')
	const pointsPct = btr(a, 'btrPermDebtPointsPct') / 100
	const refiCapRate = btr(a, 'btrRefiCapRatePct') / 100

	// Stabilized value at refi (may use different cap rate than exit)
	const stabilizedValue = refiCapRate > 0 ? round(stabilizedNoiAed / refiCapRate) : 0
	const ltvMaxDebt = round(stabilizedValue * ltvPct)

	// Annual debt service for a given loan amount (constant payment mortgage)
	function annualDS(principal: number): number {
		if (principal <= 0 || amortYears <= 0) return 0
		if (allInRate === 0) return principal / amortYears
		const monthlyRate = allInRate / 12
		const n = amortYears * 12
		const monthlyPayment =
			(principal * (monthlyRate * (1 + monthlyRate) ** n)) / ((1 + monthlyRate) ** n - 1)
		return round(monthlyPayment * 12)
	}

	// DSCR-constrained max debt
	const annuityConstant = ltvMaxDebt > 0 ? annualDS(ltvMaxDebt) / ltvMaxDebt : 0
	const dscrMaxDebt =
		annuityConstant > 0 ? round(stabilizedNoiAed / (dscrMin * annuityConstant)) : 0

	const dscrConstrained = dscrMaxDebt < ltvMaxDebt
	const actualDebt = round(Math.min(ltvMaxDebt, dscrMaxDebt))
	const piDebtService = annualDS(actualDebt)
	const ioDebtService = round(actualDebt * allInRate) // interest-only payment
	const dscr = piDebtService > 0 ? round(stabilizedNoiAed / piDebtService, 2) : 0
	const debtYield = actualDebt > 0 ? round((stabilizedNoiAed / actualDebt) * 100, 2) : 0

	// Loan payoff at exit: during IO period, principal is unchanged;
	// after IO, standard amortization on original principal for amortYears
	const ioYears = btr(a, 'btrPermDebtIoYears')
	const yearsAfterRefiAtExit = Math.max(0, holdYears - stabilizationYear + 1)
	const piYearsElapsed = Math.max(0, yearsAfterRefiAtExit - ioYears)
	const loanPayoff = round(remainingLoanBalance(actualDebt, allInRate, amortYears, piYearsElapsed))

	// Refi event: perm loan proceeds minus dev debt payoff minus points
	const refiPoints = round(actualDebt * pointsPct)
	const refiProceeds = round(actualDebt - devDebtBalance - refiPoints)

	return {
		stabilizedValueAed: stabilizedValue,
		maxPermDebtAed: ltvMaxDebt,
		dscrConstrained,
		actualPermDebtAed: actualDebt,
		ioDebtServiceAed: ioDebtService,
		annualDebtServiceAed: piDebtService,
		dscrAtOrigination: dscr,
		debtYieldPct: debtYield,
		loanPayoffAed: loanPayoff,
		refiProceedsAed: refiProceeds,
		refiPointsCostAed: refiPoints
	}
}

/** Outstanding balance on an amortizing loan after `elapsedYears` of payments. */
export function remainingLoanBalance(
	principal: number,
	annualRate: number,
	amortYears: number,
	elapsedYears: number
): number {
	if (principal <= 0 || elapsedYears >= amortYears) return 0
	if (annualRate === 0) return principal * Math.max(0, 1 - elapsedYears / amortYears)
	const monthlyRate = annualRate / 12
	const n = amortYears * 12
	const t = elapsedYears * 12
	return (
		(principal * ((1 + monthlyRate) ** n - (1 + monthlyRate) ** t)) / ((1 + monthlyRate) ** n - 1)
	)
}

/** Annual IRR — delegates to the existing periodicIrr with periodsPerYear=1 */
function computeAnnualIrr(cashFlows: number[]): number | null {
	return periodicIrr(cashFlows, 1)
}

// ── BTR Sources & Uses ───────────────────────────────────────────────────────

function computeBtrSourcesUses(
	devCosts: BtrDevCostOutputs,
	devCf: { periods: BtrDevPeriod[]; totalDevInterest: number }
): BtrSourcesUses {
	const periods = devCf.periods

	// Uses
	const totalDevCostExclVat = devCosts.totalDevCostExclVatAed
	const totalVat = devCosts.totalVatAed
	const devFinancingCosts = devCf.totalDevInterest
	const totalUses = round(totalDevCostExclVat + totalVat + devFinancingCosts)

	// Sources — peak balances (not cumulative draws, which overstate if same-period repayments)
	const peakAcqDebt = Math.max(0, ...periods.map((p) => p.acqDebtBalanceAed))
	const peakConDebt = Math.max(0, ...periods.map((p) => p.conDebtBalanceAed))
	const actualEquity = round(periods.reduce((s, p) => s + p.equityContributionAed, 0))
	const vatRefunds = round(periods.reduce((s, p) => s + p.vatRefundAed, 0))
	const totalSources = round(peakAcqDebt + peakConDebt + actualEquity + vatRefunds)

	return {
		totalDevCostExclVatAed: totalDevCostExclVat,
		totalVatAed: totalVat,
		devFinancingCostsAed: devFinancingCosts,
		totalUsesAed: totalUses,
		peakAcqDebtAed: round(peakAcqDebt),
		peakConDebtAed: round(peakConDebt),
		actualEquityAed: actualEquity,
		vatRefundsAed: vatRefunds,
		totalSourcesAed: totalSources
	}
}

// ── BTR Annual Cash Flow (dev + ops + exit in one timeline) ─────────────────

function computeBtrAnnualCashFlow(
	devCf: {
		periods: BtrDevPeriod[]
		totalDevDebt: number
		totalDevEquity: number
		totalDevInterest: number
		constructionMonths: number
	},
	operatingYears: BtrOperatingYear[],
	exit: BtrExitOutputs,
	permDebt: BtrPermDebtOutputs,
	stabilizationYear: number,
	devDebtCarryToRefiAed: number
): BtrAnnualCashFlowRow[] {
	const rows: BtrAnnualCashFlowRow[] = []

	// Year 0: Development phase (all months aggregated)
	const devCosts = round(
		devCf.periods.reduce((s, p) => s + p.costOutflowAed + p.vatPaidAed - p.vatRefundAed, 0)
	)
	const devDebt = round(devCf.periods.reduce((s, p) => s + p.devDebtDrawAed, 0))
	const devDebtBalanceAtHandover = round(devCf.periods.at(-1)?.devDebtBalanceAed ?? devDebt)
	const devEquity = round(devCf.periods.reduce((s, p) => s + p.equityContributionAed, 0))
	const devInterest = devCf.totalDevInterest

	rows.push({
		yearLabel: 'Development',
		yearIndex: 0,
		devCostsAed: -devCosts,
		devDebtDrawAed: devDebt,
		devDebtRepaymentAed: 0,
		devInterestAed: -devInterest,
		devEquityAed: -devEquity,
		cfoAed: 0,
		permDebtProceedsAed: 0,
		permDebtServiceAed: 0,
		permLoanPayoffAed: 0,
		salePriceAed: 0,
		saleExpensesAed: 0,
		unleveredCfAed: round(-devCosts - devInterest),
		leveredCfAed: round(-devEquity)
	})

	// Operating years
	const holdYears = operatingYears.length

	for (let i = 0; i < holdYears; i++) {
		const yr = operatingYears[i]
		const isRefiYear = i + 1 === stabilizationYear
		const isExitYear = i === holdYears - 1

		// Refi event: perm loan comes in, dev debt goes out
		const permProceeds = isRefiYear ? permDebt.actualPermDebtAed : 0
		const devDebtRepay = isRefiYear ? round(devDebtBalanceAtHandover + devDebtCarryToRefiAed) : 0
		const refiPoints = isRefiYear ? permDebt.refiPointsCostAed : 0

		// Disposition
		const salePrice = isExitYear ? exit.grossSalePriceAed : 0
		const saleExpenses = isExitYear ? exit.exitCostsAed : 0
		const loanPayoff = isExitYear ? permDebt.loanPayoffAed : 0

		const unleveredCf = round(yr.cfoAed + (isExitYear ? exit.netSaleProceedsAed : 0))
		// refiProceedsAed is already net of devDebtBalance and refiPointsCostAed,
		// so do NOT deduct refiPoints again here
		const leveredCf = round(
			yr.cfafAed +
				(isRefiYear ? permDebt.refiProceedsAed : 0) +
				(isExitYear ? exit.netSaleProceedsAed - loanPayoff : 0)
		)

		rows.push({
			yearLabel: yr.yearLabel,
			yearIndex: i + 1,
			devCostsAed: 0,
			devDebtDrawAed: 0,
			devDebtRepaymentAed: isRefiYear ? -devDebtRepay : 0,
			devInterestAed: isRefiYear ? -refiPoints : 0,
			devEquityAed: 0,
			cfoAed: yr.cfoAed,
			permDebtProceedsAed: permProceeds,
			permDebtServiceAed: -yr.debtServiceAed,
			permLoanPayoffAed: isExitYear ? -loanPayoff : 0,
			salePriceAed: salePrice,
			saleExpensesAed: isExitYear ? -saleExpenses : 0,
			unleveredCfAed: unleveredCf,
			leveredCfAed: leveredCf
		})
	}

	return rows
}

// ── BTR Returns (standalone, no BTS dependencies) ───────────────────────────

function computeBtrReturns(
	_a: FeasibilityAssumptions,
	devCosts: BtrDevCostOutputs,
	devCf: {
		periods: BtrDevPeriod[]
		totalDevDebt: number
		totalDevEquity: number
		totalDevInterest: number
	},
	operatingMonths: BtrOperatingMonth[],
	operatingYears: BtrOperatingYear[],
	exit: BtrExitOutputs,
	permDebt: BtrPermDebtOutputs,
	stabilizationYear: number,
	devDebtCarryToRefiAed: number
): BtrReturnsOutputs {
	const totalDevCost = devCosts.totalDevCostInclVatAed
	const totalDevFinancing = devCf.totalDevInterest
	const totalProjectCost = round(
		totalDevCost + totalDevFinancing + devDebtCarryToRefiAed + permDebt.refiPointsCostAed
	)

	const stabilizedYear = operatingYears.find((y) => !y.isLeaseUp)
	const stabilizedNoi = stabilizedYear?.noiAed ?? 0
	const yieldOnCost = totalDevCost > 0 ? round((stabilizedNoi / totalDevCost) * 100, 2) : 0

	// ── Unlevered IRR: dev costs out, CFO in, exit at end ──
	const unleveredCfs: number[] = []
	unleveredCfs.push(round(-(totalDevCost + totalDevFinancing + devDebtCarryToRefiAed)))
	for (let i = 0; i < operatingYears.length; i++) {
		let cf = operatingYears[i].cfoAed
		if (i === operatingYears.length - 1) cf += exit.netSaleProceedsAed
		unleveredCfs.push(cf)
	}

	// ── Levered IRR: equity in during dev, refi proceeds at stabilization,
	//    CFAF during ops, exit net of loan payoff at end ──
	const leveredCfs: number[] = []
	leveredCfs.push(round(-devCf.totalDevEquity))
	for (let i = 0; i < operatingYears.length; i++) {
		let cf = operatingYears[i].cfafAed
		// Refi event in stabilization year
		if (i + 1 === stabilizationYear) {
			cf += permDebt.refiProceedsAed
		}
		// Exit in final year
		if (i === operatingYears.length - 1) {
			cf += exit.netSaleProceedsAed - permDebt.loanPayoffAed
		}
		leveredCfs.push(cf)
	}

	const unleveredIrr = computeAnnualIrr(unleveredCfs)
	const leveredIrr = computeAnnualIrr(leveredCfs)

	const periodEndDate = (periodLabel: string) => {
		const [year, month] = periodLabel.split('-').map((part) => Number(part))
		return endOfMonth(new Date(Date.UTC(year, month - 1, 1)))
	}
	const unleveredXirrCashFlows: Array<{ date: Date; amount: number }> = devCf.periods.map(
		(period) => ({
			date: periodEndDate(period.periodLabel),
			amount: round(
				-(
					period.costOutflowAed +
					period.vatPaidAed +
					period.interestAed +
					period.financingFeeAed +
					period.exitFeeAed -
					period.vatRefundAed
				)
			)
		})
	)
	const leveredXirrCashFlows: Array<{ date: Date; amount: number }> = devCf.periods.map(
		(period) => ({
			date: periodEndDate(period.periodLabel),
			amount: -period.equityContributionAed
		})
	)
	for (const month of operatingMonths) {
		const isRefiMonth = month.year === stabilizationYear && month.month % 12 === 1
		const isExitMonth = month.month === operatingMonths.length
		unleveredXirrCashFlows.push({
			date: periodEndDate(month.periodLabel),
			amount: round(month.cfoAed + (isExitMonth ? exit.netSaleProceedsAed : 0))
		})
		leveredXirrCashFlows.push({
			date: periodEndDate(month.periodLabel),
			amount: round(
				month.cfafAed +
					(isRefiMonth ? permDebt.refiProceedsAed : 0) +
					(isExitMonth ? exit.netSaleProceedsAed - permDebt.loanPayoffAed : 0)
			)
		})
	}
	const unleveredXirr = computeXirr(unleveredXirrCashFlows)
	const leveredXirr = computeXirr(leveredXirrCashFlows)

	const totalUnleveredCf = unleveredCfs.reduce((s, v) => s + v, 0)
	const unleveredMoic =
		totalDevCost > 0 ? round((totalDevCost + totalUnleveredCf) / totalDevCost, 3) : 0

	const totalLeveredCf = leveredCfs.reduce((s, v) => s + v, 0)
	const leveredMoic =
		devCf.totalDevEquity > 0
			? round((devCf.totalDevEquity + totalLeveredCf) / devCf.totalDevEquity, 3)
			: 0

	// Peak equity = dev equity (before refi proceeds)
	let peakEquity = 0
	let runningEquity = 0
	// Dev phase
	for (const p of devCf.periods) {
		runningEquity += p.equityContributionAed
		peakEquity = Math.max(peakEquity, runningEquity)
	}

	return {
		totalDevCostAed: totalDevCost,
		totalDevFinancingCostsAed: totalDevFinancing,
		totalProjectCostAed: totalProjectCost,
		stabilizedNoiAed: stabilizedNoi,
		stabilizedYieldOnCostPct: yieldOnCost,
		unleveredIrrPct: unleveredIrr !== null ? round(unleveredIrr, 2) : null,
		unleveredXirrPct: unleveredXirr !== null ? round(unleveredXirr, 2) : null,
		unleveredMoic,
		leveredIrrPct: leveredIrr !== null ? round(leveredIrr, 2) : null,
		leveredXirrPct: leveredXirr !== null ? round(leveredXirr, 2) : null,
		leveredMoic,
		totalProfitAed: round(totalLeveredCf),
		totalEquityInvestedAed: round(devCf.totalDevEquity),
		peakEquityAed: round(peakEquity),
		devDebtFundedAed: devCf.totalDevDebt,
		devEquityFundedAed: devCf.totalDevEquity,
		devInterestReserveAed: round(devCf.totalDevInterest + devDebtCarryToRefiAed),
		devDebtCarryToRefiAed
	}
}

function emptyBtrSensitivities(): BtrSensitivityOutputs {
	return {
		exitCapRate: [],
		rentGrowth: [],
		hardCost: [],
		occupancy: [],
		permDebtLtv: []
	}
}

function computeBtrSensitivities(
	a: FeasibilityAssumptions,
	area: AreaBridgeOutputs
): BtrSensitivityOutputs {
	const baseExitCap = btr(a, 'btrExitCapRatePct')
	const baseRentGrowth = btr(a, 'btrMarketRentGrowthPct') || btr(a, 'btrAnnualRentGrowthPct')
	const baseHardCost =
		positiveOverride(a.constructionCostOverrideAed) ??
		area.totalCostableBua * a.constructionCostPsqmBua
	const baseOccupancy = btr(a, 'btrStabilizedOccupancyPct')
	const basePermLtv = btr(a, 'btrPermDebtLtvPct')

	const summarize = (label: string, patch: Partial<FeasibilityAssumptions>): BtrSensitivityCase => {
		const out = computeBtr({ ...a, ...patch }, area, false)
		return {
			label,
			exitCapRatePct: out.exit.exitCapRatePct,
			rentGrowthPct:
				btr({ ...a, ...patch }, 'btrMarketRentGrowthPct') ||
				btr({ ...a, ...patch }, 'btrAnnualRentGrowthPct'),
			stabilizedYieldOnCostPct: out.returns.stabilizedYieldOnCostPct,
			unleveredIrrPct: out.returns.unleveredXirrPct ?? out.returns.unleveredIrrPct,
			leveredIrrPct: out.returns.leveredXirrPct ?? out.returns.leveredIrrPct,
			leveredMoic: out.returns.leveredMoic,
			grossSalePriceAed: out.exit.grossSalePriceAed,
			totalProfitAed: out.returns.totalProfitAed
		}
	}

	return {
		exitCapRate: [-1, -0.5, 0, 0.5, 1].map((delta) =>
			summarize(`${delta > 0 ? '+' : ''}${delta.toFixed(1)}% exit cap`, {
				btrExitCapRatePct: Math.max(0.1, baseExitCap + delta)
			})
		),
		rentGrowth: [-2, -1, 0, 1, 2].map((delta) =>
			summarize(`${delta > 0 ? '+' : ''}${delta.toFixed(1)}% rent growth`, {
				btrMarketRentGrowthPct: Math.max(-10, baseRentGrowth + delta)
			})
		),
		hardCost: [-10, -5, 0, 5, 10].map((delta) =>
			summarize(`${delta > 0 ? '+' : ''}${delta}% hard cost`, {
				constructionCostOverrideAed: round(baseHardCost * (1 + delta / 100))
			})
		),
		occupancy: [-5, -2.5, 0, 2.5, 5].map((delta) =>
			summarize(`${delta > 0 ? '+' : ''}${delta.toFixed(1)}% occupancy`, {
				btrStabilizedOccupancyPct: Math.min(100, Math.max(1, baseOccupancy + delta))
			})
		),
		permDebtLtv: [-15, -7.5, 0, 7.5, 15].map((delta) =>
			summarize(`${delta > 0 ? '+' : ''}${delta.toFixed(1)}% perm LTV`, {
				btrPermDebtLtvPct: Math.min(95, Math.max(0, basePermLtv + delta))
			})
		)
	}
}

function computeBtrWaterfall(
	a: FeasibilityAssumptions,
	annualCashFlow: BtrAnnualCashFlowRow[],
	totalEquityInvestedAed: number
): BtrWaterfallOutputs {
	const preferredReturnPct = d(a, 'preferredReturnPa') * 100
	const sponsorPromotePct = d(a, 'sponsorPromotePct') * 100
	const promoteShare = sponsorPromotePct / 100
	let unreturnedCapital = totalEquityInvestedAed
	let accruedPref = 0
	const years: BtrWaterfallYear[] = []

	for (const row of annualCashFlow) {
		if (row.yearIndex > 0 && unreturnedCapital > 0) {
			accruedPref = round(accruedPref + unreturnedCapital * d(a, 'preferredReturnPa'))
		}
		let distributable = Math.max(row.leveredCfAed, 0)
		const returnOfCapital = Math.min(distributable, unreturnedCapital)
		distributable = round(distributable - returnOfCapital)
		unreturnedCapital = round(unreturnedCapital - returnOfCapital)

		const preferredReturn = Math.min(distributable, accruedPref)
		distributable = round(distributable - preferredReturn)
		accruedPref = round(accruedPref - preferredReturn)

		const gpDistribution = round(distributable * promoteShare)
		const lpResidualDistribution = round(distributable - gpDistribution)
		const lpDistribution = round(returnOfCapital + preferredReturn + lpResidualDistribution)

		years.push({
			yearLabel: row.yearLabel,
			distributableCashFlowAed: Math.max(row.leveredCfAed, 0),
			returnOfCapitalAed: returnOfCapital,
			preferredReturnAed: preferredReturn,
			lpDistributionAed: lpDistribution,
			gpDistributionAed: gpDistribution,
			endingUnreturnedCapitalAed: unreturnedCapital,
			endingAccruedPrefAed: accruedPref
		})
	}

	const total = (field: keyof BtrWaterfallYear) =>
		round(
			years.reduce(
				(sum, row) => sum + (typeof row[field] === 'number' ? (row[field] as number) : 0),
				0
			)
		)

	return {
		preferredReturnPct,
		sponsorPromotePct,
		totalDistributableCashFlowAed: total('distributableCashFlowAed'),
		totalReturnOfCapitalAed: total('returnOfCapitalAed'),
		totalPreferredReturnAed: total('preferredReturnAed'),
		totalLpDistributionAed: total('lpDistributionAed'),
		totalGpDistributionAed: total('gpDistributionAed'),
		endingUnreturnedCapitalAed: unreturnedCapital,
		endingAccruedPrefAed: accruedPref,
		years
	}
}

// ── BTR Orchestrator ────────────────────────────────────────────────────────

function computeBtr(
	a: FeasibilityAssumptions,
	area: AreaBridgeOutputs,
	includeExtras = true
): BtrOutputs {
	const program = computeBtrProgram(a)
	const devCosts = computeBtrDevCosts(a, area)
	const devCf = computeBtrDevCashFlow(a, devCosts)

	// Determine stabilization year (first year NOT in lease-up)
	const totalUnits = program.totalUnits
	const leaseUpPace = btr(a, 'btrLeaseUpPaceUnitsPerMonth')
	const stabilizedOccPct = btr(a, 'btrStabilizedOccupancyPct') / 100
	const unitsToLeaseUp = Math.ceil(totalUnits * stabilizedOccPct)
	const leaseUpMonths = leaseUpPace > 0 ? Math.ceil(unitsToLeaseUp / leaseUpPace) : 12
	const stabilizationYear = Math.max(1, Math.floor(Math.max(leaseUpMonths - 1, 0) / 12) + 2)

	// Need permDebt before operating (for debt service)
	// Compute a preliminary operating to get stabilized NOI
	const dummyPermDebt: BtrPermDebtOutputs = {
		stabilizedValueAed: 0,
		maxPermDebtAed: 0,
		dscrConstrained: false,
		actualPermDebtAed: 0,
		ioDebtServiceAed: 0,
		annualDebtServiceAed: 0,
		dscrAtOrigination: 0,
		debtYieldPct: 0,
		loanPayoffAed: 0,
		refiProceedsAed: 0,
		refiPointsCostAed: 0
	}
	const prelimOpsMonths = computeBtrOperatingMonths(a, program, dummyPermDebt, stabilizationYear, 0)
	const prelimOps = aggregateBtrOperatingYears(prelimOpsMonths)
	const stabilizedYear = prelimOps.find((y) => !y.isLeaseUp)
	const stabilizedNoi = stabilizedYear?.noiAed ?? 0

	// Compute perm debt using stabilized NOI and dev debt balance
	const devDebtBalance =
		devCf.periods.length > 0 ? devCf.periods[devCf.periods.length - 1].devDebtBalanceAed : 0
	const devDebtCarryToRefi = computeBtrDevDebtCarryToRefi(a, devDebtBalance, stabilizationYear)
	const devDebtBalanceAtRefi = round(devDebtBalance + devDebtCarryToRefi)
	const holdYears = btr(a, 'btrHoldPeriodYears')
	const permDebt = computeBtrPermDebt(
		a,
		stabilizedNoi,
		devDebtBalanceAtRefi,
		holdYears,
		stabilizationYear
	)

	// Now compute operating with real debt service. Monthly is source-of-truth; annual is a roll-up.
	const operatingMonths = computeBtrOperatingMonths(
		a,
		program,
		permDebt,
		stabilizationYear,
		devDebtBalance
	)
	const operatingYears = aggregateBtrOperatingYears(operatingMonths)
	const exit = computeBtrExit(a, operatingYears, devCosts.totalDevCostInclVatAed)
	const returns = computeBtrReturns(
		a,
		devCosts,
		devCf,
		operatingMonths,
		operatingYears,
		exit,
		permDebt,
		stabilizationYear,
		devDebtCarryToRefi
	)
	const annualCashFlow = computeBtrAnnualCashFlow(
		devCf,
		operatingYears,
		exit,
		permDebt,
		stabilizationYear,
		devDebtCarryToRefi
	)
	const sourcesUses = computeBtrSourcesUses(devCosts, devCf)
	const sensitivities = includeExtras ? computeBtrSensitivities(a, area) : emptyBtrSensitivities()
	const waterfall = computeBtrWaterfall(a, annualCashFlow, returns.totalEquityInvestedAed)

	return {
		program,
		devCosts,
		devCashFlow: devCf.periods,
		operatingMonths,
		operatingYears,
		exit,
		permDebt,
		returns,
		annualCashFlow,
		sourcesUses,
		sensitivities,
		waterfall,
		stabilizationYear,
		leaseUpMonths
	}
}

export function computeWorkbook(assumptions: FeasibilityAssumptions): WorkbookOutputs {
	// ── Step 1: Static derivations (no dependencies between them) ──
	const area = computeArea(assumptions)
	const siteMassing = computeSiteMassing(assumptions, area)
	const program = computeProgram(assumptions)
	const costs = computeCosts(assumptions, area, program)

	// ── Step 2: Monthly cash flow — THE core engine ──
	// This is where all the action happens: costs go out per S-curve,
	// collections come in per payment plan, debt fills the gap (up to
	// LTV/LTC), equity fills the residual. Interest accrues on balances.
	const cashFlow = computeCashFlow(assumptions, costs, program)
	const periods = cashFlow.periods

	// ── Step 3: Everything downstream derives from the CF periods ──
	const funding = deriveFunding(assumptions, costs, periods)
	const financing = computeFinancing(assumptions, costs, program, periods)
	const returns = computeReturns(assumptions, program, costs, area, periods)
	const budgetTiming = computeBudgetTiming(periods)
	const sourcesUses = computeSourcesUses(costs, periods)
	const waterfall = computeWaterfall(assumptions, periods)
	const vatBridge = computeVatBridge(costs, periods)
	const milestones = computeMilestones(assumptions)
	const annualCashFlow = computeAnnualCashFlow(periods)

	// ── BTR computation (only for build_to_rent_residential) ──
	// BTR is a standalone model: its own dev costs, dev CF, operating CF, refi, exit.
	// It does NOT use BTS sale proceeds, marketing/sales-admin costs, or BTS cash flow.
	const btrOutputs =
		assumptions.developmentModel === 'build_to_rent_residential'
			? computeBtr(assumptions, area)
			: undefined

	return {
		area,
		siteMassing,
		program,
		costs,
		funding,
		cashFlow,
		returns,
		financing,
		budgetTiming,
		sourcesUses,
		waterfall,
		vatBridge,
		milestones,
		annualCashFlow,
		btr: btrOutputs
	}
}
