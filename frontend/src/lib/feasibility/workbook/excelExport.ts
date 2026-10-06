import * as XLSX from 'xlsx'
import type {
	PlotResearchOutput as PlotResearch,
	StudyContext
} from '$lib/api/generated/hey-api/types.gen'
import { SQM_TO_SQFT } from '$lib/utils/units'
import type { WorkbookOutputs } from './engine'
import type { FeasibilityAssumptions } from './models'
import type { ValidationResult } from './validation'

type CellValue = string | number | boolean | null
type SheetRow = CellValue[]

interface SheetSpec {
	name: string
	rows: SheetRow[]
	widths?: number[]
	formulaCells?: Array<{ cell: string; formula: string }>
}

export interface FeasibilityWorkbookExportInput {
	assumptions: FeasibilityAssumptions
	outputs: WorkbookOutputs
	research?: PlotResearch | null
	studyContext?: StudyContext | null
	validation?: ValidationResult | null
	generatedAt?: Date
}

function round(value: number | null | undefined, digits = 0): number | null {
	if (value === null || value === undefined || !Number.isFinite(value)) return null
	const factor = 10 ** digits
	return Math.round(value * factor) / factor
}

function pct(value: number | null | undefined, digits = 2): number | null {
	return round(value, digits)
}

function cleanSheetName(name: string): string {
	return name.replaceAll(/[\\/?*[\]:]/g, ' ').slice(0, 31)
}

function safeFilePart(value: string | null | undefined): string {
	return (value || 'feasibility')
		.trim()
		.toLowerCase()
		.replaceAll(/[^a-z0-9]+/g, '-')
		.replaceAll(/(^-|-$)/g, '')
		.slice(0, 60)
}

function appendSheet(workbook: XLSX.WorkBook, spec: SheetSpec): void {
	const worksheet = XLSX.utils.aoa_to_sheet(spec.rows)
	for (const formulaCell of spec.formulaCells ?? []) {
		worksheet[formulaCell.cell] = { t: 'n', f: formulaCell.formula }
	}
	if (spec.widths) {
		worksheet['!cols'] = spec.widths.map((wch) => ({ wch }))
	}
	XLSX.utils.book_append_sheet(workbook, worksheet, cleanSheetName(spec.name))
}

function section(rows: SheetRow[], title: string): void {
	rows.push([])
	rows.push([title])
}

function row(label: string, value: CellValue, unit = '', basis = ''): SheetRow {
	return [label, value, unit, basis]
}

function sum(values: number[]): number {
	return round(values.reduce((total, value) => total + value, 0)) ?? 0
}

function btrRequired(input: FeasibilityWorkbookExportInput) {
	if (!input.outputs.btr) {
		throw new Error('BTR Excel export requires build-to-rent outputs.')
	}
	return input.outputs.btr
}

function buildSummarySheet(input: FeasibilityWorkbookExportInput): SheetSpec {
	const btr = btrRequired(input)
	const a = input.assumptions
	const rows: SheetRow[] = [
		['BTR EXECUTIVE SUMMARY'],
		['Generated At', (input.generatedAt ?? new Date()).toISOString()],
		[],
		['Project Information'],
		['Plot Number', a.plotNumber ?? ''],
		['Community', a.communityName ?? input.research?.market_area ?? ''],
		['Project', a.projectName ?? input.studyContext?.headline ?? input.research?.headline ?? ''],
		['Usage', a.usage],
		['Development Model', 'Build-to-Rent Residential'],
		['Handover', a.handoverDate],
		['Hold Period', btr.operatingYears.length, 'years']
	]

	section(rows, 'Key Performance Indicators')
	rows.push(['Metric', 'Value', 'Unit', 'Basis'])
	rows.push(row('Stabilized NOI', round(btr.returns.stabilizedNoiAed), 'AED/yr'))
	rows.push(row('Yield on Cost', pct(btr.exit.devYieldPct), '%', 'Stabilized NOI / total dev cost'))
	rows.push(row('Gross Yield', pct(btr.exit.grossYieldPct), '%'))
	rows.push(row('Net Yield', pct(btr.exit.netYieldPct), '%'))
	rows.push(row('Unlevered IRR', pct(btr.returns.unleveredIrrPct), '%'))
	rows.push(row('Levered IRR', pct(btr.returns.leveredIrrPct), '%'))
	rows.push(row('Levered MOIC', round(btr.returns.leveredMoic, 2), 'x'))
	rows.push(row('Unlevered MOIC', round(btr.returns.unleveredMoic, 2), 'x'))
	rows.push(row('Total Development Cost', round(btr.devCosts.totalDevCostInclVatAed), 'AED'))
	rows.push(row('Total Project Cost', round(btr.returns.totalProjectCostAed), 'AED'))
	rows.push(row('Development Debt Funded', round(btr.returns.devDebtFundedAed), 'AED'))
	rows.push(row('Development Equity Required', round(btr.returns.devEquityFundedAed), 'AED'))
	rows.push(row('Dev Debt Carry to Refi', round(btr.returns.devDebtCarryToRefiAed), 'AED'))
	rows.push(row('Permanent Debt', round(btr.permDebt.actualPermDebtAed), 'AED'))
	rows.push(row('DSCR at Origination', round(btr.permDebt.dscrAtOrigination, 2), 'x'))
	rows.push(row('Debt Yield', pct(btr.permDebt.debtYieldPct), '%'))
	rows.push(row('Exit Cap Rate', pct(btr.exit.exitCapRatePct), '%'))
	rows.push(row('Gross Sale Price', round(btr.exit.grossSalePriceAed), 'AED'))
	rows.push(row('Total Profit', round(btr.returns.totalProfitAed), 'AED'))
	rows.push(row('Total Units', btr.program.totalUnits, 'units'))
	rows.push(row('Total Leasable Area', round(btr.program.totalAreaSqm), 'sqm'))

	section(rows, 'Readiness Note')
	rows.push([
		'This export includes BTR values, monthly operating detail, XIRR outputs, sensitivities, waterfall, model map, named ranges, and a formula audit sheet. Formula depth is focused on audit/export integrity; the web engine remains the calculation source of truth.'
	])

	return { name: 'Executive Summary', rows, widths: [34, 18, 12, 48] }
}

function buildAssumptionsSheet(input: FeasibilityWorkbookExportInput): SheetSpec {
	const btr = btrRequired(input)
	const a = input.assumptions
	const rows: SheetRow[] = [['BTR KEY ASSUMPTIONS'], ['Line Item', 'Value', 'Unit', 'Basis']]

	section(rows, 'Area and Program')
	rows.push(row('Plot Area', round(a.plotAreaSqm), 'sqm'))
	rows.push(row('Maximum GFA', round(a.maxGfaSqm), 'sqm'))
	rows.push(row('Costable BUA', round(input.outputs.area.totalCostableBua), 'sqm'))
	rows.push(row('Total Rental Units', btr.program.totalUnits, 'units'))
	rows.push(row('Total Leasable Area', round(btr.program.totalAreaSqm), 'sqm'))
	rows.push(row('Weighted Avg Rent', round(btr.program.weightedAvgRentPsqmMonth, 2), 'AED/sqm/mo'))

	section(rows, 'Rental Unit Mix')
	rows.push([
		'Unit Type',
		'Units',
		'Avg Size (sqm)',
		'Monthly Rent (AED)',
		'Annual Rent (AED)',
		'Parking Spaces'
	])
	for (const unit of btr.program.rows) {
		rows.push([
			unit.label,
			unit.units,
			round(unit.avgSizeSqm),
			round(unit.monthlyRentAed),
			round(unit.annualRentAed),
			unit.parkingSpaces
		])
	}

	section(rows, 'Growth and Inflation')
	rows.push(
		row('Market Rent Growth', pct(a.btrMarketRentGrowthPct ?? a.btrAnnualRentGrowthPct), '% p.a.')
	)
	rows.push(row('Renewal Rent Growth', pct(a.btrRenewalRentGrowthPct), '% p.a.'))
	rows.push(row('Other Income Growth', pct(a.btrAncillaryGrowthPct), '% p.a.'))
	rows.push(row('OpEx Escalation / Inflation', pct(a.btrOpExGrowthPct), '% p.a.'))
	rows.push(row('Development Cost Escalation', pct(a.btrDevCostEscalationPct), '% p.a.'))
	rows.push(row('Terminal NOI Growth', pct(a.btrTerminalGrowthPct), '% p.a.'))

	section(rows, 'Operating Assumptions')
	rows.push(row('Lease-Up Pace', round(a.btrLeaseUpPaceUnitsPerMonth), 'units/mo'))
	rows.push(row('Stabilized Occupancy', pct(a.btrStabilizedOccupancyPct), '%'))
	rows.push(row('Free Rent Concession', round(a.btrFreeRentMonths, 1), 'months'))
	rows.push(row('General Vacancy', pct(a.btrGeneralVacancyPct), '%'))
	rows.push(row('Credit Loss', pct(a.btrCreditLossPct), '%'))
	rows.push(row('Property Management', pct(a.btrPropertyManagementPct), '% of EGR'))
	rows.push(row('Repairs and Maintenance', round(a.btrRepairsMaintenancePsqm), 'AED/sqm/yr'))
	rows.push(row('Payroll and Staffing', round(a.btrPayrollPsqm), 'AED/sqm/yr'))
	rows.push(row('General and Administrative', pct(a.btrGeneralAdminPct), '% of EGR'))
	rows.push(row('Contract Services', round(a.btrContractServicesPsqm), 'AED/sqm/yr'))
	rows.push(row('Insurance', round(a.btrInsurancePsqm), 'AED/sqm/yr'))
	rows.push(row('Service Charge', round(a.btrServiceChargePsqm), 'AED/sqm/yr'))
	rows.push(row('Utilities', round(a.btrUtilitiesPsqm), 'AED/sqm/yr'))
	rows.push(row('Marketing and Leasing', pct(a.btrMarketingLeasingPct), '% of EGR'))
	rows.push(row('CapEx Reserve', pct(a.btrCapexReservePct), '% of NOI'))

	section(rows, 'Debt and Exit')
	rows.push(row('Acquisition LTV', pct((a.acquisitionDebtLtv ?? 0) * 100), '%'))
	rows.push(row('Construction LTC', pct((a.constructionDebtLtc ?? 0) * 100), '%'))
	rows.push(row('EIBOR Base Rate', pct(a.eiborRatePct), '%'))
	rows.push(row('Land Loan Spread', round(a.landLoanSpreadBps), 'bps'))
	rows.push(row('Construction Loan Spread', round(a.constructionLoanSpreadBps), 'bps'))
	rows.push(row('Permanent Debt LTV', pct(a.btrPermDebtLtvPct), '%'))
	rows.push(row('Permanent Debt Spread', round(a.btrPermDebtSpreadBps), 'bps'))
	rows.push(row('Permanent Debt Amortization', round(a.btrPermDebtAmortYears), 'years'))
	rows.push(row('Minimum DSCR', round(a.btrDscrMinimum, 2), 'x'))
	rows.push(row('Refi Cap Rate', pct(a.btrRefiCapRatePct), '%'))
	rows.push(row('Exit Cap Rate', pct(a.btrExitCapRatePct), '%'))
	rows.push(row('Exit Costs', pct(a.btrExitCostPct), '% of sale price'))

	return { name: 'Key Assumptions', rows, widths: [34, 18, 18, 18, 18, 18] }
}

function buildSiteMassingSheet(input: FeasibilityWorkbookExportInput): SheetSpec {
	const m = input.outputs.siteMassing
	const a = input.assumptions
	const rows: SheetRow[] = [
		['SITE MASSING TEST-FIT'],
		['Physical capacity view for coverage, floorplate, height, and unit capacity'],
		[],
		['Metric', 'Value', 'Unit', 'Basis']
	]

	rows.push(row('Building form', m.buildingForm, '', 'Classified from max storeys'))
	rows.push(row('Plot area', round(m.plotAreaSqm), 'sqm'))
	rows.push(row('Maximum GFA', round(m.maxGfaSqm), 'sqm'))
	rows.push(row('GIS max coverage', pct(a.maxCoveragePct), '%'))
	rows.push(row('Target coverage', pct(a.targetCoveragePct), '%'))
	rows.push(row('Applied coverage', pct(m.appliedCoveragePct), '%'))
	rows.push(row('Covered footprint', round(m.coveredFootprintSqm), 'sqm'))
	rows.push(row('Total modelled footprint', round(m.totalFootprintSqm), 'sqm'))
	rows.push(row('Coverage utilization', pct(m.coverageUtilizationPct), '%'))
	rows.push(row('Building count', m.buildingCount, 'buildings'))
	rows.push(row('Typical gross floorplate', round(m.typicalGrossFloorplateSqm), 'sqm'))
	rows.push(row('Weighted average unit size', round(m.weightedAvgUnitSizeSqm, 1), 'sqm'))
	rows.push(row('Target unit count', m.targetUnitCount, 'units'))
	rows.push(row('Physical unit capacity', m.totalPhysicalUnitCapacity, 'units'))
	rows.push(row('Allocated GFA', round(m.totalAllocatedGfaSqm), 'sqm'))
	rows.push(row('GFA utilization', pct(m.gfaUtilizationPct), '%'))
	rows.push(row('Estimated maximum height', round(m.estimatedMaxHeightM, 1), 'm'))

	section(rows, 'Massing Controls')
	rows.push(['Input', 'Value', 'Unit', 'Basis'])
	rows.push(
		row('Target building count', a.targetBuildingCount ?? null, 'buildings', 'Blank = auto-size')
	)
	rows.push(
		row(
			'Max efficient tower floorplate',
			round(a.maxEfficientTowerFloorplateSqm),
			'sqm',
			'Blank = benchmark'
		)
	)
	rows.push(
		row(
			'Min efficient tower floorplate',
			round(a.minEfficientTowerFloorplateSqm),
			'sqm',
			'Blank = benchmark'
		)
	)
	rows.push(row('Residential floor-to-floor height', round(a.floorToFloorHeightM ?? 3.2, 1), 'm'))
	rows.push(row('Podium floor-to-floor height', round(a.podiumFloorToFloorHeightM ?? 4, 1), 'm'))
	rows.push(row('Ground floor height', round(a.groundFloorHeightM ?? 5, 1), 'm'))
	rows.push(row('Roof plant allowance', round(a.roofPlantAllowanceM ?? 6, 1), 'm'))

	section(rows, 'Building Schedule')
	rows.push([
		'Building',
		'Type',
		'Footprint sqm',
		'Gross floorplate sqm',
		'Net floorplate sqm',
		'Allocated GFA sqm',
		'Residential floors',
		'Podium floors',
		'Amenity floors',
		'Total floors',
		'Estimated height m',
		'Units / floor',
		'Total units'
	])
	for (const building of m.buildings) {
		rows.push([
			building.label,
			building.buildingType,
			round(building.footprintSqm),
			round(building.grossFloorplateSqm),
			round(building.netFloorplateSqm),
			round(building.allocatedGfaSqm),
			building.residentialFloors,
			building.podiumFloors,
			building.amenityFloors,
			building.totalFloors,
			round(building.estimatedHeightM, 1),
			building.unitsPerTypicalFloor,
			building.totalUnits
		])
	}

	if (m.warnings.length) {
		section(rows, 'Review Flags')
		rows.push(['Warning'])
		for (const warning of m.warnings) rows.push([warning])
	}

	return {
		name: 'Site Massing',
		rows,
		widths: [30, 18, 16, 24, 20, 20, 16, 16, 16, 16, 18, 16, 16]
	}
}

function buildBudgetSheet(input: FeasibilityWorkbookExportInput): SheetSpec {
	const btr = btrRequired(input)
	const a = input.assumptions
	const d = btr.devCosts
	const total = d.totalDevCostInclVatAed || 1
	const rows: SheetRow[] = [
		['BTR DEVELOPMENT BUDGET'],
		['Line Item', 'Amount (AED)', 'Input / Basis', '% of Dev Cost']
	]
	const budgetRow = (label: string, amount: number, basis = '') =>
		rows.push([label, round(amount), basis, round((amount / total) * 100, 2)])

	section(rows, 'Land Acquisition')
	budgetRow('Land acquisition', d.landAcquisitionAed, `${round(a.landPricePsqm)} AED/sqm plot`)
	budgetRow(
		'Land transfer fee',
		d.landTransferFeeAed,
		`${pct((a.landTransferFeePct ?? 0) * 100)}% of land`
	)
	budgetRow('Brokerage', d.brokerageFeeAed, `${pct((a.brokeragePct ?? 0) * 100)}% of land`)
	budgetRow('Legal / due diligence', d.legalDdCostAed, `${pct((a.legalDdPct ?? 0) * 100)}% of land`)
	budgetRow('Total land cost', d.totalLandCostAed)

	section(rows, 'Construction')
	budgetRow(
		'Hard cost',
		d.hardCostAed,
		`${round(a.constructionCostPsqmBua)} AED/sqm BUA, escalated`
	)
	budgetRow('Permit fees', d.permitFeesAed, `${pct((a.permitFeesPct ?? 0) * 100)}% of hard cost`)
	budgetRow('Soft cost / design', d.softCostAed, `${pct((a.softCostPct ?? 0) * 100)}% of hard cost`)
	budgetRow('Contingency', d.contingencyCostAed, `${pct(a.contingencyPct)}% of hard cost`)
	budgetRow('Total construction cost', d.totalConstructionCostAed)

	section(rows, 'Statutory and Development')
	budgetRow('Infrastructure and utilities', d.infrastructureCostAed)
	budgetRow('Authority / government fees', d.governmentFeesAed)
	budgetRow('Master community fees', d.masterCommunityFeesAed)
	budgetRow('FFE / OS&E / pre-opening', d.ffeOsePreopeningCostAed)
	budgetRow('Demolition / enabling works', d.demolitionCostAed)
	budgetRow('Lease-up marketing', d.leaseUpMarketingAed)
	budgetRow('VAT', d.totalVatAed, `${pct(a.vatPct)}% where applicable`)
	budgetRow('Total development cost', d.totalDevCostInclVatAed)

	return { name: 'Development Budget', rows, widths: [34, 18, 28, 16] }
}

function buildMonthlyDevCashFlowSheet(input: FeasibilityWorkbookExportInput): SheetSpec {
	const btr = btrRequired(input)
	const periods = btr.devCashFlow
	const labels = periods.map((p) => p.periodLabel)
	const rows: SheetRow[] = [
		['BTR MONTHLY DEVELOPMENT CASH FLOW'],
		['Line Item', ...labels, 'Total']
	]
	const line = (label: string, values: number[]) =>
		rows.push([label, ...values.map((v) => round(v)), round(sum(values))])

	line(
		'Development cost outflows',
		periods.map((p) => -p.costOutflowAed)
	)
	line(
		'VAT paid',
		periods.map((p) => -p.vatPaidAed)
	)
	line(
		'VAT refund received',
		periods.map((p) => p.vatRefundAed)
	)
	line(
		'Capitalized interest',
		periods.map((p) => -p.interestAed)
	)
	line(
		'Financing / exit fees',
		periods.map((p) => -(p.financingFeeAed + p.exitFeeAed))
	)
	line(
		'Total uses',
		periods.map((p) => -p.totalUsesAed)
	)
	line(
		'Acquisition debt draw',
		periods.map((p) => p.acqDebtDrawAed)
	)
	line(
		'Construction debt draw',
		periods.map((p) => p.conDebtDrawAed)
	)
	line(
		'Equity contribution',
		periods.map((p) => p.equityContributionAed)
	)
	line(
		'Acquisition debt balance',
		periods.map((p) => p.acqDebtBalanceAed)
	)
	line(
		'Construction debt balance',
		periods.map((p) => p.conDebtBalanceAed)
	)
	line(
		'Total development debt balance',
		periods.map((p) => p.devDebtBalanceAed)
	)

	return { name: 'Monthly Dev CF', rows, widths: [28, ...labels.map(() => 14), 16] }
}

function buildOperatingSheet(input: FeasibilityWorkbookExportInput): SheetSpec {
	const btr = btrRequired(input)
	const years = btr.operatingYears
	const labels = years.map((y) => y.yearLabel)
	const rows: SheetRow[] = [['BTR OPERATING MODEL'], ['Line Item', ...labels]]
	const line = (label: string, values: number[]) =>
		rows.push([label, ...values.map((v) => round(v))])

	section(rows, 'Revenue')
	line(
		'Gross Potential Rent',
		years.map((y) => y.grossPotentialRentAed)
	)
	line(
		'Less: Non-Revenue / Model Units',
		years.map((y) => -y.modelUnitDeductionAed)
	)
	line(
		'Less: Concessions',
		years.map((y) => -y.concessionsAed)
	)
	line(
		'Effective Rental Income',
		years.map((y) => y.effectiveRentalIncomeAed)
	)
	line(
		'Other Income',
		years.map((y) => y.otherIncomeAed)
	)
	line(
		'Total Potential Income',
		years.map((y) => y.totalPotentialIncomeAed)
	)
	line(
		'Less: General Vacancy',
		years.map((y) => -y.vacancyAed)
	)
	line(
		'Less: Credit Loss',
		years.map((y) => -y.creditLossAed)
	)
	line(
		'Effective Gross Revenue',
		years.map((y) => y.effectiveGrossRevenueAed)
	)

	section(rows, 'Operating Expenses')
	line(
		'Property Management',
		years.map((y) => -y.propertyManagementAed)
	)
	line(
		'Repairs and Maintenance',
		years.map((y) => -y.repairsMaintenanceAed)
	)
	line(
		'Payroll and Staffing',
		years.map((y) => -y.payrollAed)
	)
	line(
		'General and Administrative',
		years.map((y) => -y.generalAdminAed)
	)
	line(
		'Contract Services',
		years.map((y) => -y.contractServicesAed)
	)
	line(
		'Insurance',
		years.map((y) => -y.insuranceAed)
	)
	line(
		'Service Charge',
		years.map((y) => -y.serviceChargeAed)
	)
	line(
		'Utilities',
		years.map((y) => -y.utilitiesAed)
	)
	line(
		'Marketing and Leasing',
		years.map((y) => -y.marketingLeasingAed)
	)
	line(
		'Total OpEx',
		years.map((y) => -y.totalOpExAed)
	)

	section(rows, 'NOI and Debt Service')
	line(
		'Net Operating Income',
		years.map((y) => y.noiAed)
	)
	line(
		'Less: CapEx Reserve',
		years.map((y) => -y.capexReserveAed)
	)
	line(
		'Cash Flow from Operations',
		years.map((y) => y.cfoAed)
	)
	line(
		'Less: Permanent Debt Service',
		years.map((y) => -y.debtServiceAed)
	)
	line(
		'Cash Flow After Financing',
		years.map((y) => y.cfafAed)
	)

	section(rows, 'Operating Metrics')
	line(
		'Occupancy',
		years.map((y) => y.occupancyPct)
	)
	line(
		'OpEx Ratio',
		years.map((y) => round(y.opExRatio * 100, 2) ?? 0)
	)
	line(
		'NOI Margin',
		years.map((y) =>
			y.effectiveGrossRevenueAed > 0
				? (round((y.noiAed / y.effectiveGrossRevenueAed) * 100, 2) ?? 0)
				: 0
		)
	)

	return { name: 'Operating Model', rows, widths: [30, ...labels.map(() => 14)] }
}

function buildSourcesUsesSheet(input: FeasibilityWorkbookExportInput): SheetSpec {
	const btr = btrRequired(input)
	const su = btr.sourcesUses
	const gap = su.totalSourcesAed - su.totalUsesAed
	const rows: SheetRow[] = [
		['BTR SOURCES AND USES'],
		['Line Item', 'Amount (AED)', 'Basis'],
		[],
		['Uses'],
		[
			'Development cost excl. VAT',
			round(su.totalDevCostExclVatAed),
			'Land + construction + statutory + lease-up'
		],
		['VAT paid', round(su.totalVatAed), 'Gross VAT paid before refunds'],
		[
			'Development financing costs',
			round(su.devFinancingCostsAed),
			'Interest + financing / exit fees'
		],
		['Total Uses', round(su.totalUsesAed), ''],
		[],
		['Sources'],
		['Acquisition debt', round(su.peakAcqDebtAed), 'Peak acquisition debt balance'],
		['Construction debt', round(su.peakConDebtAed), 'Peak construction debt balance'],
		['Sponsor equity', round(su.actualEquityAed), 'Actual monthly equity contributions'],
		[
			'VAT refunds received',
			round(su.vatRefundsAed),
			'Input VAT recovered during development tail'
		],
		['Total Sources', round(su.totalSourcesAed), ''],
		[],
		[
			'Sources - Uses Check',
			round(gap),
			Math.abs(gap) <= 1000 ? 'OK' : 'Mismatch - review capital structure'
		]
	]

	return { name: 'Sources Uses', rows, widths: [34, 18, 54] }
}

function buildDebtReturnsSheet(input: FeasibilityWorkbookExportInput): SheetSpec {
	const btr = btrRequired(input)
	const rows: SheetRow[] = [['BTR DEBT AND RETURNS'], ['Line Item', 'Value', 'Unit', 'Basis']]

	section(rows, 'Permanent Debt')
	rows.push(
		row(
			'Stabilized Value',
			round(btr.permDebt.stabilizedValueAed),
			'AED',
			'Stabilized NOI / refi cap rate'
		)
	)
	rows.push(row('Maximum Perm Debt', round(btr.permDebt.maxPermDebtAed), 'AED', 'LTV constrained'))
	rows.push(
		row(
			'Actual Perm Debt',
			round(btr.permDebt.actualPermDebtAed),
			'AED',
			btr.permDebt.dscrConstrained ? 'DSCR constrained' : 'LTV constrained'
		)
	)
	rows.push(row('Annual Debt Service', round(btr.permDebt.annualDebtServiceAed), 'AED/yr'))
	rows.push(row('IO Debt Service', round(btr.permDebt.ioDebtServiceAed), 'AED/yr'))
	rows.push(row('DSCR at Origination', round(btr.permDebt.dscrAtOrigination, 2), 'x'))
	rows.push(row('Debt Yield', pct(btr.permDebt.debtYieldPct), '%'))
	rows.push(row('Refi Points / Fees', round(btr.permDebt.refiPointsCostAed), 'AED'))
	rows.push(row('Net Refi Proceeds', round(btr.permDebt.refiProceedsAed), 'AED'))
	rows.push(row('Loan Payoff at Exit', round(btr.permDebt.loanPayoffAed), 'AED'))

	section(rows, 'Exit and Valuation')
	rows.push(row('Exit Year', btr.exit.exitYear, 'year'))
	rows.push(row('Terminal NOI', round(btr.exit.terminalNoiAed), 'AED/yr'))
	rows.push(row('Exit Cap Rate', pct(btr.exit.exitCapRatePct), '%'))
	rows.push(row('Gross Sale Price', round(btr.exit.grossSalePriceAed), 'AED'))
	rows.push(row('Exit Costs', round(btr.exit.exitCostsAed), 'AED'))
	rows.push(row('Net Sale Proceeds', round(btr.exit.netSaleProceedsAed), 'AED'))
	rows.push(row('Development Yield', pct(btr.exit.devYieldPct), '%'))
	rows.push(row('Development Spread', round(btr.exit.developmentSpreadBps), 'bps'))

	section(rows, 'Full-Cycle Returns')
	rows.push(row('Total Development Cost', round(btr.returns.totalDevCostAed), 'AED'))
	rows.push(row('Total Project Cost', round(btr.returns.totalProjectCostAed), 'AED'))
	rows.push(row('Total Equity Invested', round(btr.returns.totalEquityInvestedAed), 'AED'))
	rows.push(row('Peak Equity', round(btr.returns.peakEquityAed), 'AED'))
	rows.push(row('Dev Debt Carry to Refi', round(btr.returns.devDebtCarryToRefiAed), 'AED'))
	rows.push(row('Total Profit', round(btr.returns.totalProfitAed), 'AED'))
	rows.push(row('Stabilized Yield on Cost', pct(btr.returns.stabilizedYieldOnCostPct), '%'))
	rows.push(row('Unlevered IRR', pct(btr.returns.unleveredIrrPct), '%'))
	rows.push(
		row('Unlevered XIRR', pct(btr.returns.unleveredXirrPct), '%', 'Date-based monthly cash flows')
	)
	rows.push(row('Unlevered MOIC', round(btr.returns.unleveredMoic, 2), 'x'))
	rows.push(row('Levered IRR', pct(btr.returns.leveredIrrPct), '%'))
	rows.push(
		row('Levered XIRR', pct(btr.returns.leveredXirrPct), '%', 'Date-based monthly cash flows')
	)
	rows.push(row('Levered MOIC', round(btr.returns.leveredMoic, 2), 'x'))

	section(rows, 'Annual Full-Cycle Cash Flow')
	rows.push(['Line Item', ...btr.annualCashFlow.map((r) => r.yearLabel)])
	const annual = (label: string, values: number[]) =>
		rows.push([label, ...values.map((v) => round(v))])
	annual(
		'Development Costs',
		btr.annualCashFlow.map((r) => r.devCostsAed)
	)
	annual(
		'Development Debt Draw',
		btr.annualCashFlow.map((r) => r.devDebtDrawAed)
	)
	annual(
		'Development Debt Repayment',
		btr.annualCashFlow.map((r) => r.devDebtRepaymentAed)
	)
	annual(
		'Development Interest / Fees',
		btr.annualCashFlow.map((r) => r.devInterestAed)
	)
	annual(
		'Operating CFO',
		btr.annualCashFlow.map((r) => r.cfoAed)
	)
	annual(
		'Permanent Debt Proceeds',
		btr.annualCashFlow.map((r) => r.permDebtProceedsAed)
	)
	annual(
		'Permanent Debt Service',
		btr.annualCashFlow.map((r) => r.permDebtServiceAed)
	)
	annual(
		'Sale Price',
		btr.annualCashFlow.map((r) => r.salePriceAed)
	)
	annual(
		'Sale Expenses',
		btr.annualCashFlow.map((r) => r.saleExpensesAed)
	)
	annual(
		'Loan Payoff',
		btr.annualCashFlow.map((r) => r.permLoanPayoffAed)
	)
	annual(
		'Unlevered Cash Flow',
		btr.annualCashFlow.map((r) => r.unleveredCfAed)
	)
	annual(
		'Levered Cash Flow',
		btr.annualCashFlow.map((r) => r.leveredCfAed)
	)

	return {
		name: 'Debt Returns',
		rows,
		widths: [34, 18, 12, 42, ...btr.annualCashFlow.map(() => 14)]
	}
}

function buildMonthlyOperatingSheet(input: FeasibilityWorkbookExportInput): SheetSpec {
	const btr = btrRequired(input)
	const months = btr.operatingMonths
	const labels = months.map((m) => m.periodLabel)
	const rows: SheetRow[] = [['BTR MONTHLY OPERATING CASH FLOW'], ['Line Item', ...labels, 'Total']]
	const line = (label: string, values: number[]) =>
		rows.push([label, ...values.map((v) => round(v)), round(sum(values))])

	line(
		'Gross Potential Rent',
		months.map((m) => m.grossPotentialRentAed)
	)
	line(
		'Less: Non-Revenue / Model Units',
		months.map((m) => -m.modelUnitDeductionAed)
	)
	line(
		'Less: Concessions',
		months.map((m) => -m.concessionsAed)
	)
	line(
		'Effective Rental Income',
		months.map((m) => m.effectiveRentalIncomeAed)
	)
	line(
		'Other Income',
		months.map((m) => m.otherIncomeAed)
	)
	line(
		'Total Potential Income',
		months.map((m) => m.totalPotentialIncomeAed)
	)
	line(
		'Less: General Vacancy',
		months.map((m) => -m.vacancyAed)
	)
	line(
		'Less: Credit Loss',
		months.map((m) => -m.creditLossAed)
	)
	line(
		'Effective Gross Revenue',
		months.map((m) => m.effectiveGrossRevenueAed)
	)
	line(
		'Total OpEx',
		months.map((m) => -m.totalOpExAed)
	)
	line(
		'NOI',
		months.map((m) => m.noiAed)
	)
	line(
		'CapEx Reserve',
		months.map((m) => -m.capexReserveAed)
	)
	line(
		'CFO',
		months.map((m) => m.cfoAed)
	)
	line(
		'Debt Service',
		months.map((m) => -m.debtServiceAed)
	)
	line(
		'CFAF',
		months.map((m) => m.cfafAed)
	)
	line(
		'Occupancy %',
		months.map((m) => m.occupancyPct)
	)

	section(rows, 'Per-Unit-Type Gross Rent')
	for (const unit of btr.program.rows) {
		line(
			`${unit.label} GPR`,
			months.map(
				(m) => m.unitTypeIncomes.find((income) => income.id === unit.id)?.grossPotentialRentAed ?? 0
			)
		)
	}

	return { name: 'Monthly Ops CF', rows, widths: [30, ...labels.map(() => 13), 16] }
}

function buildSensitivitiesSheet(input: FeasibilityWorkbookExportInput): SheetSpec {
	const btr = btrRequired(input)
	const rows: SheetRow[] = [['BTR SENSITIVITIES']]
	const addTable = (title: string, cases: typeof btr.sensitivities.exitCapRate) => {
		section(rows, title)
		rows.push([
			'Scenario',
			'Exit Cap %',
			'Rent Growth %',
			'YOC %',
			'Unlevered IRR/XIRR %',
			'Levered IRR/XIRR %',
			'Levered MOIC',
			'Gross Sale Price',
			'Total Profit'
		])
		for (const item of cases) {
			rows.push([
				item.label,
				round(item.exitCapRatePct, 2),
				round(item.rentGrowthPct, 2),
				round(item.stabilizedYieldOnCostPct, 2),
				round(item.unleveredIrrPct, 2),
				round(item.leveredIrrPct, 2),
				round(item.leveredMoic, 2),
				round(item.grossSalePriceAed),
				round(item.totalProfitAed)
			])
		}
	}

	addTable('Exit Cap Rate', btr.sensitivities.exitCapRate)
	addTable('Rent Growth', btr.sensitivities.rentGrowth)
	addTable('Hard Cost', btr.sensitivities.hardCost)
	addTable('Occupancy', btr.sensitivities.occupancy)
	addTable('Permanent Debt LTV', btr.sensitivities.permDebtLtv)

	return { name: 'Sensitivities', rows, widths: [26, 14, 16, 12, 18, 18, 14, 18, 18] }
}

function buildWaterfallSheet(input: FeasibilityWorkbookExportInput): SheetSpec {
	const btr = btrRequired(input)
	const waterfall = btr.waterfall
	const rows: SheetRow[] = [
		['BTR PARTNERSHIP WATERFALL'],
		['Preferred Return', round(waterfall.preferredReturnPct, 2), '%'],
		['Sponsor Promote', round(waterfall.sponsorPromotePct, 2), '%'],
		[],
		[
			'Year',
			'Distributable CF',
			'Return of Capital',
			'Preferred Return',
			'LP Distribution',
			'GP Distribution',
			'Ending Unreturned Capital',
			'Ending Accrued Pref'
		]
	]
	for (const year of waterfall.years) {
		rows.push([
			year.yearLabel,
			round(year.distributableCashFlowAed),
			round(year.returnOfCapitalAed),
			round(year.preferredReturnAed),
			round(year.lpDistributionAed),
			round(year.gpDistributionAed),
			round(year.endingUnreturnedCapitalAed),
			round(year.endingAccruedPrefAed)
		])
	}
	rows.push([])
	rows.push(['Total Distributable CF', round(waterfall.totalDistributableCashFlowAed)])
	rows.push(['Total Return of Capital', round(waterfall.totalReturnOfCapitalAed)])
	rows.push(['Total Preferred Return', round(waterfall.totalPreferredReturnAed)])
	rows.push(['Total LP Distribution', round(waterfall.totalLpDistributionAed)])
	rows.push(['Total GP Distribution', round(waterfall.totalGpDistributionAed)])

	return { name: 'Waterfall', rows, widths: [18, 18, 18, 18, 18, 18, 22, 20] }
}

function buildFormulaAuditSheet(input: FeasibilityWorkbookExportInput): SheetSpec {
	const btr = btrRequired(input)
	const waterfallTotalRow = btr.waterfall.years.length + 7
	const waterfallLpRow = btr.waterfall.years.length + 10
	const waterfallGpRow = btr.waterfall.years.length + 11
	return {
		name: 'Formula Audit',
		rows: [
			['BTR FORMULA AUDIT'],
			['Check', 'Formula Result', 'Formula'],
			['Sources less Uses', null, "'Sources Uses'!B15-'Sources Uses'!B8"],
			['Total distributions', null, `Waterfall!B${waterfallTotalRow}`],
			['Waterfall LP + GP', null, `Waterfall!B${waterfallLpRow}+Waterfall!B${waterfallGpRow}`]
		],
		widths: [28, 18, 42],
		formulaCells: [
			{ cell: 'B3', formula: "'Sources Uses'!B15-'Sources Uses'!B8" },
			{ cell: 'B4', formula: `Waterfall!B${waterfallTotalRow}` },
			{ cell: 'B5', formula: `Waterfall!B${waterfallLpRow}+Waterfall!B${waterfallGpRow}` }
		]
	}
}

function buildModelMapSheet(input: FeasibilityWorkbookExportInput): SheetSpec {
	const rows: SheetRow[] = [
		['BTR MODEL MAP'],
		['Generated At', (input.generatedAt ?? new Date()).toISOString()],
		['Calculation Source', 'Frontend TypeScript feasibility engine'],
		['Export Type', 'Hybrid values + formula audit'],
		[],
		['Sheet', 'Purpose'],
		['Executive Summary', 'Project information and key investment metrics'],
		['Key Assumptions', 'Inputs, unit mix, growth, OpEx, debt, and exit assumptions'],
		['Site Massing', 'Coverage, building count, floorplate, height, and physical unit capacity'],
		['Development Budget', 'Land, construction, statutory, VAT, and lease-up costs'],
		['Monthly Dev CF', 'Monthly development uses, VAT, debt draws, balances, and equity'],
		['Operating Model', 'Annual operating P&L roll-up'],
		['Monthly Ops CF', 'Monthly operating P&L and debt service source schedule'],
		['Sources Uses', 'Development funding check'],
		['Debt Returns', 'Permanent debt, exit valuation, and return metrics'],
		['Sensitivities', 'Scenario outputs for key CRE underwriting drivers'],
		['Waterfall', 'LP/GP distribution waterfall based on levered cash flows'],
		['Model Checks', 'Hard checks and validation issues'],
		['Pricing Evidence', 'Rental comps, market evidence, and land evidence'],
		['Formula Audit', 'Formula-bearing audit checks and workbook references']
	]
	return { name: 'Model Map', rows, widths: [28, 80] }
}

function buildChecksSheet(input: FeasibilityWorkbookExportInput): SheetSpec {
	const btr = btrRequired(input)
	const validation = input.validation
	const gap = btr.sourcesUses.totalSourcesAed - btr.sourcesUses.totalUsesAed
	const rows: SheetRow[] = [
		['BTR MODEL CHECKS'],
		['Status', validation?.status ?? (Math.abs(gap) <= 1000 ? 'ready' : 'invalid')],
		['Hard Failures', validation?.hardFailures ?? null],
		['Warnings', validation?.warnings ?? null],
		['Missing Evidence', validation?.missingEvidence ?? null],
		[],
		['Check', 'Value', 'Status', 'Note']
	]

	const checkRow = (label: string, value: CellValue, ok: boolean, note: string) =>
		rows.push([label, value, ok ? 'OK' : 'REVIEW', note])

	checkRow(
		'Sources / Uses Gap',
		round(gap),
		Math.abs(gap) <= 1000,
		'Sources should equal uses within AED 1,000.'
	)
	checkRow(
		'Stabilized NOI',
		round(btr.returns.stabilizedNoiAed),
		btr.returns.stabilizedNoiAed > 0,
		'NOI should be positive.'
	)
	checkRow(
		'DSCR at Origination',
		round(btr.permDebt.dscrAtOrigination, 2),
		btr.permDebt.dscrAtOrigination >= (input.assumptions.btrDscrMinimum ?? 1.25),
		'Must meet minimum DSCR.'
	)
	checkRow(
		'Yield on Cost',
		pct(btr.exit.devYieldPct),
		btr.exit.devYieldPct > btr.exit.exitCapRatePct,
		'Development yield should generally exceed exit cap.'
	)
	checkRow(
		'Refi Proceeds',
		round(btr.permDebt.refiProceedsAed),
		btr.permDebt.refiProceedsAed >= 0,
		'Negative value means refi equity cure required.'
	)
	checkRow(
		'Levered MOIC',
		round(btr.returns.leveredMoic, 2),
		btr.returns.leveredMoic > 1,
		'Levered multiple should exceed 1.0x.'
	)
	checkRow(
		'Exit Cap Rate',
		pct(btr.exit.exitCapRatePct),
		btr.exit.exitCapRatePct > 0,
		'Exit cap must be positive.'
	)

	if (validation?.issues.length) {
		section(rows, 'Validation Issues')
		rows.push(['Severity', 'Code', 'Field', 'Message'])
		for (const issue of validation.issues) {
			rows.push([issue.severity, issue.code, issue.field ?? '', issue.message])
		}
	}

	return { name: 'Model Checks', rows, widths: [30, 18, 14, 70] }
}

function buildPricingEvidenceSheet(input: FeasibilityWorkbookExportInput): SheetSpec {
	const btr = btrRequired(input)
	const r = input.research
	const rows: SheetRow[] = [
		['BTR PRICING EVIDENCE'],
		['Market Area', r?.market_area ?? input.assumptions.communityName ?? ''],
		['Headline', input.studyContext?.headline ?? r?.headline ?? ''],
		['Total Units', btr.program.totalUnits],
		['Total Leasable Area', round(btr.program.totalAreaSqm), 'sqm'],
		['Gross Potential Rent', round(btr.program.grossPotentialRentAed), 'AED/yr']
	]

	if (r?.rental_rates_by_size_band?.length) {
		section(rows, 'Rental Rates by Unit Type')
		rows.push([
			'Unit Type',
			'Size Band',
			'Contracts',
			'Median AED/sqm/yr',
			'Median AED/sqft/mo',
			'Median Annual Rent'
		])
		for (const band of r.rental_rates_by_size_band) {
			rows.push([
				band.unit_type_proxy,
				band.size_band_label,
				band.contract_count,
				round(band.median_rent_psm_annual),
				round((band.median_rent_psm_annual * 0.092903) / 12, 2),
				round(band.median_annual_rent)
			])
		}
	}

	if (r?.rental_market_summary) {
		section(rows, 'Master Community Rental Averages')
		rows.push(['Metric', 'Value'])
		rows.push(['Rental contracts 12m', r.rental_market_summary.rental_contract_count_12m])
		rows.push(['Avg rent AED/sqm/yr', round(r.rental_market_summary.avg_rent_price_sqm_12m)])
		rows.push([
			'Avg rent AED/sqft/mo',
			r.rental_market_summary.avg_rent_price_sqm_12m
				? round((r.rental_market_summary.avg_rent_price_sqm_12m * 0.092903) / 12, 2)
				: null
		])
		rows.push(['Median annual rent', round(r.rental_market_summary.median_annual_rent)])
		rows.push(['Gross yield', pct(r.rental_market_summary.gross_yield_pct), '%'])
		rows.push([
			'Top developers',
			r.rental_market_summary.top_developers?.slice(0, 5).join(', ') ?? ''
		])
	}

	if (r?.rental_comparables?.length) {
		section(rows, 'Rental Comparable Projects')
		rows.push([
			'Project',
			'Area',
			'Similarity',
			'Rent AED/sqm/yr',
			'Rent AED/sqft/mo',
			'Median Annual Rent',
			'Yield'
		])
		for (const comp of r.rental_comparables.slice(0, 10)) {
			rows.push([
				comp.project_name,
				comp.area_name,
				round(comp.score, 1),
				round(comp.avg_rent_price_sqm_12m),
				comp.avg_rent_price_sqm_12m
					? round((comp.avg_rent_price_sqm_12m * 0.092903) / 12, 2)
					: null,
				round(comp.median_annual_rent),
				pct(comp.gross_yield_pct)
			])
		}
	}

	if (r?.land_sales_evidence?.length) {
		section(rows, 'Land Sales Evidence')
		rows.push([
			'Date',
			'Project',
			'Area',
			'Usage',
			'Plot Area sqm',
			'Price AED',
			'AED/plot sqm',
			'AED/GFA sqm'
		])
		for (const sale of r.land_sales_evidence.slice(0, 20)) {
			rows.push([
				sale.instance_date?.slice(0, 10) ?? '',
				sale.project_name || sale.procedure_name || '',
				sale.area_name,
				sale.property_usage,
				round(sale.plot_area_sqm),
				round(sale.price_aed),
				round(sale.price_sqm),
				round(sale.price_per_gfa_sqm)
			])
		}
	}

	rows.push([])
	rows.push(['Area Bridge'])
	rows.push(['Plot Area sqft', round(input.outputs.area.plotAreaSqm * SQM_TO_SQFT)])
	rows.push(['Max GFA sqft', round(input.outputs.area.maxGfaSqm * SQM_TO_SQFT)])
	rows.push(['Costable BUA sqft', round(input.outputs.area.totalCostableBua * SQM_TO_SQFT)])

	return { name: 'Pricing Evidence', rows, widths: [26, 26, 16, 18, 16, 18, 18, 18] }
}

export function buildFeasibilityWorkbook(input: FeasibilityWorkbookExportInput): XLSX.WorkBook {
	const workbook = XLSX.utils.book_new()
	if (!input.outputs.btr) {
		throw new Error('Only BTR feasibility Excel export is currently supported.')
	}

	const sheets = [
		buildSummarySheet(input),
		buildAssumptionsSheet(input),
		buildSiteMassingSheet(input),
		buildBudgetSheet(input),
		buildMonthlyDevCashFlowSheet(input),
		buildOperatingSheet(input),
		buildMonthlyOperatingSheet(input),
		buildSourcesUsesSheet(input),
		buildDebtReturnsSheet(input),
		buildSensitivitiesSheet(input),
		buildWaterfallSheet(input),
		buildChecksSheet(input),
		buildPricingEvidenceSheet(input),
		buildFormulaAuditSheet(input),
		buildModelMapSheet(input)
	]

	for (const sheet of sheets) appendSheet(workbook, sheet)
	workbook.Workbook = {
		...(workbook.Workbook ?? {}),
		Names: [
			{ Name: 'BTR_Stabilized_NOI', Ref: "'Executive Summary'!$B$15" },
			{ Name: 'BTR_Total_Dev_Cost', Ref: "'Executive Summary'!$B$23" },
			{ Name: 'BTR_Permanent_Debt', Ref: "'Executive Summary'!$B$28" },
			{ Name: 'BTR_Building_Count', Ref: "'Site Massing'!$B$14" },
			{ Name: 'BTR_Sources_Uses_Gap', Ref: "'Sources Uses'!$B$17" }
		]
	}
	workbook.Props = {
		Title: 'BTR Feasibility Model',
		Subject: 'Build-to-Rent feasibility export',
		Author: 'ViteVue Feasibility',
		CreatedDate: input.generatedAt ?? new Date()
	}
	return workbook
}

export function getFeasibilityWorkbookFileName(input: FeasibilityWorkbookExportInput): string {
	const a = input.assumptions
	const project = safeFilePart(
		a.projectName ?? input.studyContext?.headline ?? input.research?.headline
	)
	const plot = safeFilePart(a.plotNumber ?? input.research?.plot_number)
	const stamp = (input.generatedAt ?? new Date()).toISOString().slice(0, 10)
	return `btr-feasibility-${plot || project}-${stamp}.xlsx`
}

export function downloadFeasibilityWorkbook(input: FeasibilityWorkbookExportInput): void {
	const workbook = buildFeasibilityWorkbook(input)
	XLSX.writeFile(workbook, getFeasibilityWorkbookFileName(input), { compression: true })
}
