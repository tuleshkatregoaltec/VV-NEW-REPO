import type {
	DevelopmentModel,
	FeasibilityAssumptions,
	PlotDetails,
	UsageType,
	VatApplicability
} from './models'

export type AssumptionHydrationMode = 'saved' | 'generated'

interface DefaultOptions {
	asOfDate?: Date | string
	developmentModel?: DevelopmentModel
}

interface HydrateOptions extends DefaultOptions {
	mode?: AssumptionHydrationMode
}

const MONTH_OFFSETS = {
	demolition: 1,
	sales: 3,
	construction: 4,
	preHandover: 28,
	handover: 34
} as const

export const WORKBOOK_OPTION_DEFAULTS = {
	basementParkingFloors: 4,
	podiumFloors: 5,
	residentialFloors: 30,
	amenityRoofFloors: 1,
	parkingAreaPerSpaceSqm: 30,
	aboveGradeBuaFactor: 1.1,
	serviceBohPlantPct: 0.03,
	podiumParkingFloorsOutsideGfa: 0,
	floorToFloorHeightM: 3.2,
	podiumFloorToFloorHeightM: 4,
	groundFloorHeightM: 5,
	roofPlantAllowanceM: 6,
	landTransferFeePct: 0.04,
	brokeragePct: 0.01,
	legalDdPct: 0.005,
	permitFeesPct: 0.02,
	softCostPct: 0.15,
	acquisitionDebtLtv: 0.7,
	constructionDebtLtc: 0.7,
	debtSpreadPa: 0.02,
	financingFeePct: 0.01,
	exitFeePct: 0.01,
	preferredReturnPa: 0.08,
	sponsorPromotePct: 0.2,
	projectYears: 5,
	constructionCurveSteepness: 8,
	salesCurveSteepness: 8,
	vatAppliesTo: {
		land: true,
		hardCosts: true,
		softCosts: true,
		permitFees: true,
		contingency: true,
		marketing: true,
		salesAdmin: true
	} satisfies VatApplicability,
	vatRefundLagMonths: 6
} as const

export const BTR_WORKBOOK_DEFAULTS = {
	btrHoldPeriodYears: 10,
	btrLeaseUpPaceUnitsPerMonth: 20,
	btrStabilizedOccupancyPct: 97,
	btrFreeRentMonths: 0,
	btrAnnualRentGrowthPct: 5,
	btrMarketRentGrowthPct: 5,
	btrRenewalRentGrowthPct: 5,
	btrGeneralVacancyPct: 5,
	btrPropertyManagementPct: 5,
	btrRepairsMaintenancePsqm: 50,
	btrInsurancePsqm: 10,
	btrServiceChargePsqm: 80,
	btrUtilitiesPsqm: 30,
	btrMarketingLeasingPct: 2,
	btrCapexReservePct: 5,
	btrParkingIncomeAed: 0,
	btrAncillaryIncomeAed: 0,
	btrAncillaryGrowthPct: 3,
	btrStabilizedFreeRentMonths: 0,
	btrOpExGrowthPct: 3,
	btrDevCostEscalationPct: 4,
	btrTerminalGrowthPct: 4,
	btrLeaseUpMarketingAed: 0,
	btrCreditLossPct: 1,
	btrPayrollPsqm: 40,
	btrGeneralAdminPct: 1,
	btrContractServicesPsqm: 25,
	btrModelUnits: 1,
	btrExitCapRatePct: 5.5,
	btrExitCostPct: 6,
	btrPermDebtLtvPct: 65,
	btrPermDebtRatePct: 6,
	btrPermDebtSpreadBps: 165,
	btrPermDebtAmortYears: 25,
	btrPermDebtPointsPct: 1,
	btrPermDebtIoYears: 1,
	btrDscrMinimum: 1.25,
	btrRefiCapRatePct: 5.5
} as const

const GENERATED_DETERMINISTIC_KEYS: Array<keyof FeasibilityAssumptions> = [
	'buaMultiplier',
	'nsaEfficiencyPct',
	'standardParkingRatio',
	'largeUnitThresholdSqm',
	'largeUnitParkingRatio',
	'designSupervisionPct',
	'designSupervisionCostOverrideAed',
	'constructionCostOverrideAed',
	'marketingCostPct',
	'marketingCostOverrideAed',
	'salesAgentFeePct',
	'salesAgentFeesOverrideAed',
	'contingencyPct',
	'contingencyCostOverrideAed',
	'infrastructureCostAed',
	'governmentFeesAed',
	'masterCommunityFeesAed',
	'ffeOsePreopeningCostAed',
	'demolitionEnabled',
	'demolitionCostAed',
	'midPointInflationPct',
	'vatPct',
	'financeRatePct',
	'arrangementFeePct',
	'commitmentFeePct',
	'debtToCostRatio',
	'presaleThresholdPct',
	'escrowRetentionPct',
	'landLoanLtvPct',
	'eiborRatePct',
	'landLoanSpreadBps',
	'constructionLoanSpreadBps',
	'debtFundingAed',
	'equityFundingAed',
	'debtRepaymentMode',
	'landAcquisitionDate',
	'demolitionEnablingDate',
	'salesCommencementDate',
	'salesPeriodMonths',
	'constructionDate',
	'handoverDate',
	'preHandoverMilestoneDate',
	'basementParkingFloors',
	'parkingAreaPerSpaceSqm',
	'aboveGradeBuaFactor',
	'serviceBohPlantPct',
	'podiumParkingFloorsOutsideGfa',
	'floorToFloorHeightM',
	'podiumFloorToFloorHeightM',
	'groundFloorHeightM',
	'roofPlantAllowanceM',
	'landTransferFeePct',
	'brokeragePct',
	'legalDdPct',
	'permitFeesPct',
	'softCostPct',
	'acquisitionDebtLtv',
	'constructionDebtLtc',
	'debtSpreadPa',
	'financingFeePct',
	'exitFeePct',
	'preferredReturnPa',
	'sponsorPromotePct',
	'projectYears',
	'constructionCurveSteepness',
	'salesCurveSteepness',
	'vatRefundLagMonths',
	'selectedScenario'
]

const OPTIONAL_DEFAULT_KEYS = [
	...Object.keys(WORKBOOK_OPTION_DEFAULTS),
	...Object.keys(BTR_WORKBOOK_DEFAULTS)
] as Array<keyof FeasibilityAssumptions>

function coerceDate(raw: Date | string | undefined): Date {
	if (raw instanceof Date) {
		return Number.isNaN(raw.getTime()) ? new Date() : raw
	}
	if (typeof raw === 'string') {
		const parsed = new Date(`${raw}T00:00:00.000Z`)
		return Number.isNaN(parsed.getTime()) ? new Date() : parsed
	}
	return new Date()
}

function isoDate(date: Date): string {
	return date.toISOString().slice(0, 10)
}

function addMonths(date: Date, months: number): Date {
	const year = date.getUTCFullYear()
	const month = date.getUTCMonth() + months
	const day = date.getUTCDate()
	const endOfTargetMonth = new Date(Date.UTC(year, month + 1, 0)).getUTCDate()
	return new Date(Date.UTC(year, month, Math.min(day, endOfTargetMonth)))
}

function defaultSchedule(asOfDate: Date | string | undefined) {
	const base = coerceDate(asOfDate)
	return {
		landAcquisitionDate: isoDate(base),
		demolitionEnablingDate: isoDate(addMonths(base, MONTH_OFFSETS.demolition)),
		salesCommencementDate: isoDate(addMonths(base, MONTH_OFFSETS.sales)),
		constructionDate: isoDate(addMonths(base, MONTH_OFFSETS.construction)),
		preHandoverMilestoneDate: isoDate(addMonths(base, MONTH_OFFSETS.preHandover)),
		handoverDate: isoDate(addMonths(base, MONTH_OFFSETS.handover))
	}
}

export function parseMaxStoreys(maxHeight: string | null | undefined): number | null {
	if (!maxHeight) return null
	const matches = maxHeight.match(/(\d+)/g)
	if (!matches?.length) return null
	const storeys = Number(matches[matches.length - 1])
	return Number.isFinite(storeys) && storeys > 0 ? storeys : null
}

export function parseMaxCoverage(maxCoverage: string | null | undefined): number | null {
	if (!maxCoverage) return null
	const match = maxCoverage.match(/(\d+(?:\.\d+)?)/)
	if (!match) return null
	const value = Number(match[1])
	return Number.isFinite(value) ? value : null
}

export function defaultDevelopmentModel(usage: UsageType): DevelopmentModel | undefined {
	return usage === 'residential' || usage === 'mixed_use' ? 'build_to_sell_residential' : undefined
}

export function defaultVatApplicability(): VatApplicability {
	return { ...WORKBOOK_OPTION_DEFAULTS.vatAppliesTo }
}

export function createDefaultAssumptions(options: DefaultOptions = {}): FeasibilityAssumptions {
	const schedule = defaultSchedule(options.asOfDate)
	return {
		usage: 'unknown',
		plotAreaSqm: 0,
		maxGfaSqm: 0,
		maxCoveragePct: null,
		maxStoreys: null,
		maxFar: 0,
		buaMultiplier: 1.5,
		nsaEfficiencyPct: 80,
		numberOfTowers: 1,
		numberOfFloors: 1,
		unitConfigs: [],
		btrUnitConfigs: [],
		paymentPlan: { depositPct: 10, constructionPct: 30, handoverPct: 60 },
		standardParkingRatio: 1,
		largeUnitThresholdSqm: 140,
		largeUnitParkingRatio: 2,
		landPricePsqm: 0,
		landAcquisitionCostOverrideAed: null,
		brokerageFeeAed: 0,
		legalDdCostAed: 0,
		constructionCostPsqmBua: 0,
		constructionCostOverrideAed: null,
		midPointInflationPct: 4,
		designSupervisionPct: 6,
		designSupervisionCostOverrideAed: null,
		marketingCostPct: 1,
		marketingCostOverrideAed: null,
		salesAgentFeePct: 5,
		salesAgentFeesOverrideAed: null,
		infrastructureCostAed: 8_000_000,
		governmentFeesAed: 5_000_000,
		masterCommunityFeesAed: 3_500_000,
		ffeOsePreopeningCostAed: 0,
		contingencyPct: 5,
		contingencyCostOverrideAed: null,
		demolitionEnabled: false,
		demolitionCostAed: 0,
		vatPct: 5,
		debtToCostRatio: 0,
		landLoanLtvPct: 70,
		eiborRatePct: 4.85,
		landLoanSpreadBps: 200,
		constructionLoanSpreadBps: 200,
		arrangementFeePct: 1,
		commitmentFeePct: 0.5,
		presaleThresholdPct: 35,
		escrowRetentionPct: 5,
		debtRepaymentMode: 'bullet_at_handover',
		debtFundingAed: 0,
		equityFundingAed: 0,
		financeRatePct: 0,
		salesPeriodMonths: 24,
		...schedule,
		...WORKBOOK_OPTION_DEFAULTS,
		vatAppliesTo: defaultVatApplicability(),
		selectedScenario: 'base',
		developmentModel: options.developmentModel ?? 'build_to_sell_residential',
		...BTR_WORKBOOK_DEFAULTS
	}
}

export function createAssumptionsFromPlot(
	plotData: PlotDetails,
	options: DefaultOptions = {}
): FeasibilityAssumptions {
	const usage = plotData.inferred_usage ?? 'unknown'
	const developmentModel =
		options.developmentModel ?? defaultDevelopmentModel(usage) ?? 'build_to_sell_residential'
	const base = createDefaultAssumptions({ ...options, developmentModel })
	return normalizeAssumptions(
		{
			...base,
			usage,
			plotAreaSqm: plotData.plot_area_sqm,
			maxGfaSqm: plotData.max_gfa_sqm ?? 0,
			maxCoveragePct: parseMaxCoverage(plotData.max_coverage),
			maxStoreys: parseMaxStoreys(plotData.max_height),
			maxFar: plotData.far ?? 0,
			plotNumber: plotData.plot_number,
			communityName: plotData.community_name,
			projectName: plotData.project_name,
			gfaType: plotData.gfa_type,
			sitePlanIssueDate: plotData.site_plan_issue_date,
			sitePlanExpiryDate: plotData.site_plan_expiry_date,
			plotWarnings: [...(plotData.warnings ?? [])],
			developmentModel
		},
		options
	)
}

function fillMissingOptionalDefaults(
	assumptions: FeasibilityAssumptions,
	defaults: FeasibilityAssumptions
): void {
	const target = assumptions as unknown as Record<string, unknown>
	const source = defaults as unknown as Record<string, unknown>
	for (const key of OPTIONAL_DEFAULT_KEYS) {
		if (target[key] === undefined || target[key] === null) {
			target[key] = source[key]
		}
	}
}

function applyGeneratedDeterministicDefaults(
	assumptions: FeasibilityAssumptions,
	defaults: FeasibilityAssumptions
): void {
	const target = assumptions as unknown as Record<string, unknown>
	const source = defaults as unknown as Record<string, unknown>
	for (const key of GENERATED_DETERMINISTIC_KEYS) {
		target[key] = source[key]
	}
	assumptions.paymentPlan = { ...defaults.paymentPlan }
	assumptions.vatAppliesTo = { ...defaults.vatAppliesTo } as VatApplicability
	for (const key of Object.keys(BTR_WORKBOOK_DEFAULTS) as Array<keyof FeasibilityAssumptions>) {
		target[key] = source[key]
	}
}

function mirrorBtrToUnitConfigs(assumptions: FeasibilityAssumptions): void {
	if (
		assumptions.developmentModel !== 'build_to_rent_residential' ||
		!assumptions.btrUnitConfigs?.length
	) {
		return
	}
	assumptions.unitConfigs = assumptions.btrUnitConfigs.map((cfg, index) => ({
		id: cfg.id || `btr-${index + 1}`,
		label: cfg.label || `Rental ${index + 1}`,
		units: cfg.units,
		avgSizeSqm: cfg.avgSizeSqm,
		sellingRatePsqm: 0,
		parkingRatio: cfg.parkingRatio
	}))
	assumptions.marketingCostPct = 0
	assumptions.salesAgentFeePct = 0
	assumptions.marketingCostOverrideAed = 0
	assumptions.salesAgentFeesOverrideAed = 0
}

function normalizeFinancingMirrors(assumptions: FeasibilityAssumptions): void {
	if (
		(assumptions.acquisitionDebtLtv === undefined || assumptions.acquisitionDebtLtv === null) &&
		Number.isFinite(assumptions.landLoanLtvPct)
	) {
		assumptions.acquisitionDebtLtv = assumptions.landLoanLtvPct / 100
	}

	if (Number.isFinite(assumptions.acquisitionDebtLtv)) {
		assumptions.landLoanLtvPct = Math.round((assumptions.acquisitionDebtLtv ?? 0) * 100)
	}

	if (
		(assumptions.debtSpreadPa === undefined || assumptions.debtSpreadPa === null) &&
		Number.isFinite(assumptions.constructionLoanSpreadBps)
	) {
		assumptions.debtSpreadPa = assumptions.constructionLoanSpreadBps / 10_000
	}

	if (
		(assumptions.landLoanSpreadBps === undefined || assumptions.landLoanSpreadBps === null) &&
		assumptions.debtSpreadPa !== undefined &&
		assumptions.debtSpreadPa !== null
	) {
		assumptions.landLoanSpreadBps = Math.round(assumptions.debtSpreadPa * 10_000)
	}

	if (
		(assumptions.constructionLoanSpreadBps === undefined ||
			assumptions.constructionLoanSpreadBps === null) &&
		assumptions.debtSpreadPa !== undefined &&
		assumptions.debtSpreadPa !== null
	) {
		assumptions.constructionLoanSpreadBps = Math.round(assumptions.debtSpreadPa * 10_000)
	}
}

export function normalizeAssumptions(
	raw: Partial<FeasibilityAssumptions> = {},
	options: HydrateOptions = {}
): FeasibilityAssumptions {
	const defaults = createDefaultAssumptions(options)
	const normalized: FeasibilityAssumptions = {
		...defaults,
		...raw,
		paymentPlan: {
			...defaults.paymentPlan,
			...(raw.paymentPlan ?? {})
		},
		vatAppliesTo: {
			...defaults.vatAppliesTo,
			...(raw.vatAppliesTo ?? {})
		} as VatApplicability,
		unitConfigs: raw.unitConfigs ?? defaults.unitConfigs,
		btrUnitConfigs: raw.btrUnitConfigs ?? defaults.btrUnitConfigs
	}

	fillMissingOptionalDefaults(normalized, defaults)
	if (options.mode === 'generated') {
		applyGeneratedDeterministicDefaults(normalized, defaults)
	}
	mirrorBtrToUnitConfigs(normalized)
	normalizeFinancingMirrors(normalized)

	return normalized
}

export function hydrateAssumptions(
	rawAssumptions: Partial<FeasibilityAssumptions> | undefined,
	plotData: PlotDetails,
	research?: {
		land_cost_estimate_aed_low?: number | null
		land_cost_estimate_aed_mid?: number | null
	},
	selectedDevelopmentModel?: DevelopmentModel,
	options: HydrateOptions = {}
): FeasibilityAssumptions {
	const base = createAssumptionsFromPlot(plotData, {
		...options,
		developmentModel: selectedDevelopmentModel
	})
	const developmentModel =
		rawAssumptions?.developmentModel ??
		selectedDevelopmentModel ??
		defaultDevelopmentModel(rawAssumptions?.usage ?? base.usage) ??
		base.developmentModel
	const hydrated = normalizeAssumptions(
		{
			...base,
			...(rawAssumptions ?? {}),
			plotNumber: plotData.plot_number,
			communityName: plotData.community_name,
			projectName: plotData.project_name,
			gfaType: plotData.gfa_type,
			sitePlanIssueDate: plotData.site_plan_issue_date,
			sitePlanExpiryDate: plotData.site_plan_expiry_date,
			plotWarnings: [...(plotData.warnings ?? [])],
			developmentModel
		},
		{ ...options, developmentModel }
	)

	if (options.mode !== 'generated') return hydrated

	const lowLandCost = research?.land_cost_estimate_aed_low ?? null
	const midLandCost = research?.land_cost_estimate_aed_mid ?? null
	const currentLandCost =
		hydrated.landAcquisitionCostOverrideAed ??
		(hydrated.plotAreaSqm > 0 ? hydrated.plotAreaSqm * hydrated.landPricePsqm : 0)

	if (midLandCost && lowLandCost && currentLandCost > 0 && currentLandCost < lowLandCost) {
		return {
			...hydrated,
			landAcquisitionCostOverrideAed: midLandCost,
			landPricePsqm: hydrated.plotAreaSqm > 0 ? midLandCost / hydrated.plotAreaSqm : 0
		}
	}

	return hydrated
}
