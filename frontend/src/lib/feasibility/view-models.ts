import type {
	PlotResearchOutput as PlotResearch,
	StudyContext
} from '$lib/api/generated/hey-api/types.gen'
import { monthsBetween } from '$lib/feasibility/format'
import type { CashFlowPeriod, WorkbookOutputs } from '$lib/feasibility/workbook/engine'
import type { FeasibilityAssumptions, PlotDetails } from '$lib/feasibility/workbook/models'
import type { ValidationResult } from '$lib/feasibility/workbook/validation'

export interface PricingEvidenceStudyViewModel {
	market_area: string
	usage: string
	headline: string
	off_plan_unit_benchmarks: PlotResearch['off_plan_unit_benchmarks']
	market_pricing: PlotResearch['market_pricing']
	pricing_evidence: PlotResearch['pricing_evidence']
	competition_evidence: PlotResearch['competition_evidence']
	land_sales_evidence: PlotResearch['land_sales_evidence']
}

export interface StudyContextCardViewModel {
	headline: string
	positioning: string
	marketSummary: string
	summaryPoints: string[]
	community: string
	projectTier: string
	plotAreaSqm: number | null
	maxGfaSqm: number | null
}

export interface ResearchSnapshotViewModel {
	landCostMidEstimateAed: number | null
	pricingComparables: number
	landSalesComparables: number
}

export type CheckStatus = 'within_range' | 'warning' | 'outlier' | 'missing'

export interface ModelCheckViewModel {
	label: string
	value: string
	status: CheckStatus
	note: string
}

export interface ValidationSummaryViewModel {
	status: ValidationResult['status']
	hardFailures: number
	warnings: number
	missingEvidence: number
}

export interface AnnualCashFlowRow {
	year: number
	revenueInflowsAed: number
	depositInflowsAed: number
	preHandoverInflowsAed: number
	handoverInflowsAed: number
	operatingOutflowsAed: number
	costLandAed: number
	costConstructionAed: number
	costProfessionalFeesAed: number
	costMarketingAed: number
	costSalesAgentAed: number
	costInfrastructureAed: number
	costAuthorityFeesAed: number
	costCommunityFeesAed: number
	costContingencyAed: number
	costVatAed: number
	unleveredNetCashFlowAed: number
	debtDrawAed: number
	debtRepaymentAed: number
	interestPaidAed: number
	commitmentFeePaidAed: number
	equityContributionAed: number
	equityDistributionAed: number
	leveredNetCashFlowAed: number
	landDrawAed: number
	constructionDrawAed: number
	costPaidFromEscrowAed: number
	vatRefundInflowsAed: number
	debtBalanceAed: number
	landLoanBalanceAed: number
	constructionLoanBalanceAed: number
	escrowBalanceAed: number
}

export function buildPricingEvidenceStudy(
	research: PlotResearch | null,
	studyContext: StudyContext | null
): PricingEvidenceStudyViewModel | null {
	if (!research) return null
	return {
		market_area: research.market_area,
		usage: research.usage,
		headline: studyContext?.headline || research.headline,
		off_plan_unit_benchmarks: research.off_plan_unit_benchmarks,
		market_pricing: research.market_pricing,
		pricing_evidence: research.pricing_evidence,
		competition_evidence: research.competition_evidence,
		land_sales_evidence: research.land_sales_evidence
	}
}

export function buildStudyContextCard(
	plotData: PlotDetails | null,
	studyContext: StudyContext | null
): StudyContextCardViewModel {
	return {
		headline: studyContext?.headline ?? '—',
		positioning: studyContext?.positioning ?? '—',
		marketSummary: studyContext?.market_summary ?? '—',
		summaryPoints: studyContext?.summary_points ?? [],
		community: plotData?.community_name ?? '—',
		projectTier: studyContext?.project_tier ?? 'unknown',
		plotAreaSqm: plotData?.plot_area_sqm ?? null,
		maxGfaSqm: plotData?.max_gfa_sqm ?? null
	}
}

export function buildResearchSnapshot(research: PlotResearch | null): ResearchSnapshotViewModel {
	return {
		landCostMidEstimateAed: research?.land_cost_estimate_aed_mid ?? null,
		pricingComparables: research?.pricing_evidence?.length ?? 0,
		landSalesComparables: research?.land_sales_evidence?.length ?? 0
	}
}

export function buildValidationSummary(
	validation: ValidationResult | null
): ValidationSummaryViewModel | null {
	if (!validation) return null
	return {
		status: validation.status,
		hardFailures: validation.hardFailures,
		warnings: validation.warnings,
		missingEvidence: validation.missingEvidence
	}
}

export function buildChecksModel(
	outputs: WorkbookOutputs | null,
	validation: ValidationResult | null,
	fmt: (value: number | null | undefined, digits?: number) => string
): ModelCheckViewModel[] {
	const hasIssue = (code: string) => (validation?.issues ?? []).some((issue) => issue.code === code)
	return [
		{
			label: 'Sources vs uses',
			value: outputs ? `Gap AED ${fmt(outputs.sourcesUses.gapAed)}` : 'N/A',
			status: !outputs ? 'missing' : hasIssue('funding_gap') ? 'warning' : 'within_range',
			note: 'Model should reconcile tightly before sign-off across funding and uses summaries'
		},
		{
			label: 'Total costs',
			value: outputs ? `AED ${fmt(outputs.costs.totalCostsInclVatAed)}` : 'N/A',
			status: !outputs ? 'missing' : 'within_range',
			note: 'Total project costs including VAT'
		},
		{
			label: 'Gross margin',
			value: outputs ? `${fmt(outputs.returns.grossMarginPct, 1)}%` : 'N/A',
			status: !outputs
				? 'missing'
				: outputs.returns.grossMarginPct < 0
					? 'outlier'
					: outputs.returns.grossMarginPct < 10
						? 'warning'
						: 'within_range',
			note: 'Gross margin should be positive and reasonable'
		},
		{
			label: 'Project IRR',
			value:
				outputs?.returns?.projectIrrPct != null
					? `${fmt(outputs.returns.projectIrrPct, 1)}%`
					: 'N/A',
			status:
				outputs?.returns?.projectIrrPct == null
					? 'missing'
					: outputs.returns.projectIrrPct < 0
						? 'outlier'
						: outputs.returns.projectIrrPct > 30
							? 'warning'
							: 'within_range',
			note: 'Check for implausible or broken timed cash flows'
		},
		{
			label: 'Unit count',
			value: outputs ? `${fmt(outputs.program.totalUnits)} units` : 'N/A',
			status: !outputs ? 'missing' : outputs.program.totalUnits === 0 ? 'warning' : 'within_range',
			note: 'At least one unit type should be configured'
		}
	]
}

function createEmptyAnnualCashFlowRow(year: number): AnnualCashFlowRow {
	return {
		year,
		revenueInflowsAed: 0,
		depositInflowsAed: 0,
		preHandoverInflowsAed: 0,
		handoverInflowsAed: 0,
		operatingOutflowsAed: 0,
		costLandAed: 0,
		costConstructionAed: 0,
		costProfessionalFeesAed: 0,
		costMarketingAed: 0,
		costSalesAgentAed: 0,
		costInfrastructureAed: 0,
		costAuthorityFeesAed: 0,
		costCommunityFeesAed: 0,
		costContingencyAed: 0,
		costVatAed: 0,
		unleveredNetCashFlowAed: 0,
		debtDrawAed: 0,
		debtRepaymentAed: 0,
		interestPaidAed: 0,
		commitmentFeePaidAed: 0,
		equityContributionAed: 0,
		equityDistributionAed: 0,
		leveredNetCashFlowAed: 0,
		landDrawAed: 0,
		constructionDrawAed: 0,
		costPaidFromEscrowAed: 0,
		vatRefundInflowsAed: 0,
		debtBalanceAed: 0,
		landLoanBalanceAed: 0,
		constructionLoanBalanceAed: 0,
		escrowBalanceAed: 0
	}
}

export function buildAnnualCashFlowRows(periods: CashFlowPeriod[]): AnnualCashFlowRow[] {
	const byYear = new Map<number, AnnualCashFlowRow>()
	for (const period of periods) {
		const year = Number.parseInt(period.periodEndDate.slice(0, 4), 10)
		const row = byYear.get(year) ?? createEmptyAnnualCashFlowRow(year)
		row.revenueInflowsAed += period.revenueInflowsAed
		row.depositInflowsAed += period.depositInflowsAed
		row.preHandoverInflowsAed += period.preHandoverInflowsAed
		row.handoverInflowsAed += period.handoverInflowsAed
		row.operatingOutflowsAed += period.operatingOutflowsAed
		row.costLandAed += period.costLandAed
		row.costConstructionAed += period.costConstructionAed
		row.costProfessionalFeesAed += period.costProfessionalFeesAed
		row.costMarketingAed += period.costMarketingAed
		row.costSalesAgentAed += period.costSalesAgentAed
		row.costInfrastructureAed += period.costInfrastructureAed
		row.costAuthorityFeesAed += period.costAuthorityFeesAed
		row.costCommunityFeesAed += period.costCommunityFeesAed
		row.costContingencyAed += period.costContingencyAed
		row.costVatAed += period.costVatAed
		row.unleveredNetCashFlowAed += period.unleveredNetCashFlowAed
		row.debtDrawAed += period.debtDrawAed
		row.debtRepaymentAed += period.debtRepaymentAed
		row.interestPaidAed += period.interestPaidAed
		row.commitmentFeePaidAed += period.commitmentFeePaidAed
		row.equityContributionAed += period.equityContributionAed
		row.equityDistributionAed += period.equityDistributionAed
		row.leveredNetCashFlowAed += period.leveredNetCashFlowAed
		row.landDrawAed += period.landDrawAed
		row.constructionDrawAed += period.constructionDrawAed
		row.costPaidFromEscrowAed += period.costPaidFromEscrowAed ?? 0
		row.vatRefundInflowsAed += period.vatRefundInflowsAed ?? 0
		row.debtBalanceAed = period.debtBalanceAed
		row.landLoanBalanceAed = period.landLoanBalanceAed
		row.constructionLoanBalanceAed = period.constructionLoanBalanceAed
		row.escrowBalanceAed = period.escrowBalanceAed
		byYear.set(year, row)
	}
	return Array.from(byYear.values()).sort((a, b) => a.year - b.year)
}

export function sumAnnualCashFlowRows(rows: AnnualCashFlowRow[]): AnnualCashFlowRow {
	const last = rows.at(-1)
	return {
		year: 0,
		revenueInflowsAed: rows.reduce((sum, row) => sum + row.revenueInflowsAed, 0),
		depositInflowsAed: rows.reduce((sum, row) => sum + row.depositInflowsAed, 0),
		preHandoverInflowsAed: rows.reduce((sum, row) => sum + row.preHandoverInflowsAed, 0),
		handoverInflowsAed: rows.reduce((sum, row) => sum + row.handoverInflowsAed, 0),
		operatingOutflowsAed: rows.reduce((sum, row) => sum + row.operatingOutflowsAed, 0),
		costLandAed: rows.reduce((sum, row) => sum + row.costLandAed, 0),
		costConstructionAed: rows.reduce((sum, row) => sum + row.costConstructionAed, 0),
		costProfessionalFeesAed: rows.reduce((sum, row) => sum + row.costProfessionalFeesAed, 0),
		costMarketingAed: rows.reduce((sum, row) => sum + row.costMarketingAed, 0),
		costSalesAgentAed: rows.reduce((sum, row) => sum + row.costSalesAgentAed, 0),
		costInfrastructureAed: rows.reduce((sum, row) => sum + row.costInfrastructureAed, 0),
		costAuthorityFeesAed: rows.reduce((sum, row) => sum + row.costAuthorityFeesAed, 0),
		costCommunityFeesAed: rows.reduce((sum, row) => sum + row.costCommunityFeesAed, 0),
		costContingencyAed: rows.reduce((sum, row) => sum + row.costContingencyAed, 0),
		costVatAed: rows.reduce((sum, row) => sum + row.costVatAed, 0),
		unleveredNetCashFlowAed: rows.reduce((sum, row) => sum + row.unleveredNetCashFlowAed, 0),
		debtDrawAed: rows.reduce((sum, row) => sum + row.debtDrawAed, 0),
		debtRepaymentAed: rows.reduce((sum, row) => sum + row.debtRepaymentAed, 0),
		interestPaidAed: rows.reduce((sum, row) => sum + row.interestPaidAed, 0),
		commitmentFeePaidAed: rows.reduce((sum, row) => sum + row.commitmentFeePaidAed, 0),
		equityContributionAed: rows.reduce((sum, row) => sum + row.equityContributionAed, 0),
		equityDistributionAed: rows.reduce((sum, row) => sum + row.equityDistributionAed, 0),
		leveredNetCashFlowAed: rows.reduce((sum, row) => sum + row.leveredNetCashFlowAed, 0),
		landDrawAed: rows.reduce((sum, row) => sum + row.landDrawAed, 0),
		constructionDrawAed: rows.reduce((sum, row) => sum + row.constructionDrawAed, 0),
		costPaidFromEscrowAed: rows.reduce((sum, row) => sum + row.costPaidFromEscrowAed, 0),
		vatRefundInflowsAed: rows.reduce((sum, row) => sum + row.vatRefundInflowsAed, 0),
		debtBalanceAed: last?.debtBalanceAed ?? 0,
		landLoanBalanceAed: last?.landLoanBalanceAed ?? 0,
		constructionLoanBalanceAed: last?.constructionLoanBalanceAed ?? 0,
		escrowBalanceAed: last?.escrowBalanceAed ?? 0
	}
}

export interface BudgetSummaryViewModel {
	constructionMonths: number
	totalInterestPaid: number
	totalCommitmentFees: number
	arrangementFee: number
	totalFinanceCosts: number
	preFinanceCosts: number
	costPerUnitAed: number
	costPerSqftBua: number
	revenuePerUnitAed: number
	profitPerUnitAed: number
	grossMarginPct: number
	allInProfit: number
	allInMarginPct: number
	equityIrrPct: number | null
	projectIrrPct: number | null
}

export function buildBudgetSummary(
	assumptions: FeasibilityAssumptions,
	outputs: WorkbookOutputs | null,
	model: {
		totalLandCostAed: number
		constructionCostInclInflation: number
		designSupervisionCost: number
		marketingCost: number
		salesAgentFees: number
		demolitionCost: number
		contingencyCost: number
		totalDebtCapacity: number
		totalUnits: number
		modelTotalCostsInclVat: number
		totalBuaSqm: number
		totalConfiguredRevenue: number
		projectIrrPct: number | null
	}
): BudgetSummaryViewModel {
	const constructionMonths =
		monthsBetween(assumptions.constructionDate, assumptions.handoverDate) ?? 0
	const totalInterestPaid = outputs?.returns?.totalInterestPaidAed ?? 0
	const totalCommitmentFees = outputs?.returns?.totalCommitmentFeesAed ?? 0
	const arrangementFee =
		outputs?.financing?.arrangementFeeAed ??
		model.totalDebtCapacity * (assumptions.arrangementFeePct / 100)
	const totalFinanceCosts = totalInterestPaid + totalCommitmentFees + arrangementFee
	const preFinanceCosts =
		model.totalLandCostAed +
		model.constructionCostInclInflation +
		model.designSupervisionCost +
		model.marketingCost +
		model.salesAgentFees +
		assumptions.infrastructureCostAed +
		assumptions.governmentFeesAed +
		assumptions.masterCommunityFeesAed +
		(assumptions.demolitionEnabled ? model.demolitionCost : 0) +
		assumptions.ffeOsePreopeningCostAed +
		model.contingencyCost
	const costPerUnitAed = model.totalUnits > 0 ? model.modelTotalCostsInclVat / model.totalUnits : 0
	const costPerSqftBua =
		model.totalBuaSqm > 0 ? model.modelTotalCostsInclVat / (model.totalBuaSqm / 0.092903) : 0
	const revenuePerUnitAed =
		model.totalUnits > 0 ? model.totalConfiguredRevenue / model.totalUnits : 0
	const profitPerUnitAed = revenuePerUnitAed - costPerUnitAed
	const grossMarginPct =
		model.totalConfiguredRevenue > 0
			? ((model.totalConfiguredRevenue - model.modelTotalCostsInclVat) /
					model.totalConfiguredRevenue) *
				100
			: 0
	const allInProfit =
		outputs?.returns?.allInProjectProfitAed ??
		model.totalConfiguredRevenue - model.modelTotalCostsInclVat - totalFinanceCosts
	const allInMarginPct =
		outputs?.returns?.allInMarginPct ??
		(model.totalConfiguredRevenue > 0 ? (allInProfit / model.totalConfiguredRevenue) * 100 : 0)
	return {
		constructionMonths,
		totalInterestPaid,
		totalCommitmentFees,
		arrangementFee,
		totalFinanceCosts,
		preFinanceCosts,
		costPerUnitAed,
		costPerSqftBua,
		revenuePerUnitAed,
		profitPerUnitAed,
		grossMarginPct,
		allInProfit,
		allInMarginPct,
		equityIrrPct: outputs?.returns?.equityIrrPct ?? null,
		projectIrrPct: model.projectIrrPct
	}
}
