<script lang="ts">
import type { BtrOperatingYear } from '$lib/feasibility/workbook/engine'
import { workbookStore } from '$lib/feasibility/workbook/store.svelte'

function fmt(value: number | null | undefined, digits = 0) {
	if (value === null || value === undefined || !Number.isFinite(value)) return '—'
	return value.toLocaleString('en-AE', {
		minimumFractionDigits: digits,
		maximumFractionDigits: digits
	})
}

function fmtPct(value: number | null | undefined, digits = 1) {
	if (value === null || value === undefined || !Number.isFinite(value)) return '—'
	return `${fmt(value, digits)}%`
}

function fmtK(value: number | null | undefined) {
	if (value === null || value === undefined || !Number.isFinite(value)) return '—'
	return fmt(Math.round(value / 1000))
}

function fmtNeg(value: number | null | undefined) {
	if (value === null || value === undefined || !Number.isFinite(value)) return '—'
	const abs = Math.abs(value)
	return value < 0 ? `(${fmtK(abs)})` : fmtK(value)
}

type RevKey =
	| 'grossPotentialRentAed'
	| 'modelUnitDeductionAed'
	| 'concessionsAed'
	| 'effectiveRentalIncomeAed'
	| 'otherIncomeAed'
	| 'totalPotentialIncomeAed'
	| 'vacancyAed'
	| 'creditLossAed'
	| 'effectiveGrossRevenueAed'
type ExpKey =
	| 'propertyManagementAed'
	| 'repairsMaintenanceAed'
	| 'payrollAed'
	| 'generalAdminAed'
	| 'contractServicesAed'
	| 'insuranceAed'
	| 'serviceChargeAed'
	| 'utilitiesAed'
	| 'marketingLeasingAed'
	| 'totalOpExAed'

const revenueRowDefs: { label: string; key: RevKey; isTotal?: boolean; isNeg?: boolean }[] = [
	{ label: 'Gross Potential Rent', key: 'grossPotentialRentAed' },
	{ label: 'Less: Non-Revenue Units', key: 'modelUnitDeductionAed', isNeg: true },
	{ label: 'Less: Concessions', key: 'concessionsAed', isNeg: true },
	{ label: 'Effective Rental Income', key: 'effectiveRentalIncomeAed' },
	{ label: 'Other Income', key: 'otherIncomeAed' },
	{ label: 'Total Potential Income', key: 'totalPotentialIncomeAed' },
	{ label: 'Less: General Vacancy', key: 'vacancyAed', isNeg: true },
	{ label: 'Less: Credit Loss', key: 'creditLossAed', isNeg: true },
	{ label: 'Effective Gross Revenue', key: 'effectiveGrossRevenueAed', isTotal: true }
]

const expenseRowDefs: { label: string; key: ExpKey; isTotal?: boolean }[] = [
	{ label: 'Property Management', key: 'propertyManagementAed' },
	{ label: 'Repairs & Maintenance', key: 'repairsMaintenanceAed' },
	{ label: 'Payroll & Staffing', key: 'payrollAed' },
	{ label: 'General & Administrative', key: 'generalAdminAed' },
	{ label: 'Contract Services', key: 'contractServicesAed' },
	{ label: 'Insurance', key: 'insuranceAed' },
	{ label: 'Service Charge', key: 'serviceChargeAed' },
	{ label: 'Utilities', key: 'utilitiesAed' },
	{ label: 'Marketing & Leasing', key: 'marketingLeasingAed' },
	{ label: 'Total OpEx', key: 'totalOpExAed', isTotal: true }
]

const outputs = $derived(workbookStore.outputs)
const btr = $derived(outputs?.btr)
const assumptions = $derived(workbookStore.assumptions)
const permDebtAllInRate = $derived(
	(assumptions?.eiborRatePct ?? 0) + (assumptions?.btrPermDebtSpreadBps ?? 165) / 100
)

const exitRows = $derived(
	btr
		? [
				{
					label: 'Exit Year',
					value: `Year ${btr.exit.exitYear}`,
					note: `Hold period: ${assumptions?.btrHoldPeriodYears ?? 10} years`,
					highlight: false
				},
				{
					label: 'Terminal NOI',
					value: `AED ${fmt(btr.exit.terminalNoiAed)}`,
					note: 'Forward NOI using rent growth and OpEx escalation',
					highlight: false
				},
				{
					label: 'Exit Cap Rate',
					value: fmtPct(btr.exit.exitCapRatePct),
					note: 'Applied to terminal NOI',
					highlight: false
				},
				{
					label: 'Terminal Sale Value',
					value: `AED ${fmt(btr.exit.grossSalePriceAed)}`,
					note: 'Terminal NOI / Exit Cap Rate',
					highlight: true
				},
				{
					label: 'Exit Costs',
					value: `AED ${fmt(btr.exit.exitCostsAed)}`,
					note: `${fmtPct(assumptions?.btrExitCostPct ?? 2)} brokerage + legal`,
					highlight: false
				},
				{
					label: 'Net Sale Proceeds',
					value: `AED ${fmt(btr.exit.netSaleProceedsAed)}`,
					note: 'Gross less exit costs',
					highlight: true
				},
				{
					label: 'Development Yield',
					value: fmtPct(btr.exit.devYieldPct),
					note: 'Stabilized NOI / Total Dev Cost',
					highlight: false
				},
				{
					label: 'Development Spread',
					value: `${btr.exit.developmentSpreadBps} bps`,
					note: 'Dev yield minus exit cap rate',
					highlight: false
				}
			]
		: []
)

const debtRows = $derived(
	btr
		? [
				{
					label: 'Stabilized Value',
					value: `AED ${fmt(btr.permDebt.stabilizedValueAed)}`,
					note: 'Stabilized NOI / Refi Cap Rate'
				},
				{
					label: 'Max Perm Debt (LTV)',
					value: `AED ${fmt(btr.permDebt.maxPermDebtAed)}`,
					note: `${fmtPct(assumptions?.btrPermDebtLtvPct ?? 65)} LTV`
				},
				{
					label: 'Actual Perm Debt',
					value: `AED ${fmt(btr.permDebt.actualPermDebtAed)}`,
					note: btr.permDebt.dscrConstrained ? 'DSCR constrained' : 'LTV constrained'
				},
				{
					label: 'IO Debt Service',
					value: `AED ${fmt(btr.permDebt.ioDebtServiceAed)}`,
					note: `Interest-only for ${assumptions?.btrPermDebtIoYears ?? 1}yr(s) after refi`
				},
				{
					label: 'P&I Debt Service',
					value: `AED ${fmt(btr.permDebt.annualDebtServiceAed)}`,
					note: `${fmtPct(permDebtAllInRate)} all-in, ${assumptions?.btrPermDebtAmortYears ?? 25}yr amort`
				},
				{
					label: 'DSCR at Origination',
					value: `${fmt(btr.permDebt.dscrAtOrigination, 2)}x`,
					note: `Min: ${fmt(assumptions?.btrDscrMinimum ?? 1.25, 2)}x`
				},
				{
					label: 'Debt Yield',
					value: fmtPct(btr.permDebt.debtYieldPct),
					note: 'Stabilized NOI / Perm Debt'
				}
			]
		: []
)

const returnRows = $derived(
	btr
		? [
				{
					label: 'Total Dev Cost',
					value: `AED ${fmt(btr.returns.totalDevCostAed)}`,
					note: 'All development costs incl. VAT',
					highlight: false
				},
				{
					label: 'Total Project Cost',
					value: `AED ${fmt(btr.returns.totalProjectCostAed)}`,
					note: 'Dev cost + financing costs',
					highlight: false
				},
				{
					label: 'Total Equity Invested',
					value: `AED ${fmt(btr.returns.totalEquityInvestedAed)}`,
					note: 'Equity contributions during dev phase',
					highlight: false
				},
				{
					label: 'Peak Equity',
					value: `AED ${fmt(btr.returns.peakEquityAed)}`,
					note: 'Maximum cumulative equity draw',
					highlight: false
				},
				{
					label: 'Total Profit',
					value: `AED ${fmt(btr.returns.totalProfitAed)}`,
					note: 'Net exit proceeds + operating CF - dev cost',
					highlight: false
				},
				{
					label: 'Stabilized Yield on Cost',
					value: fmtPct(btr.returns.stabilizedYieldOnCostPct),
					note: 'Stabilized NOI / Total Dev Cost',
					highlight: false
				},
				{
					label: 'Unlevered IRR',
					value: btr.returns.unleveredIrrPct != null ? fmtPct(btr.returns.unleveredIrrPct) : 'N/A',
					note: 'All-cash returns including exit',
					highlight: true
				},
				{
					label: 'Unlevered MOIC',
					value: `${fmt(btr.returns.unleveredMoic, 2)}x`,
					note: 'Total distributions / total investment',
					highlight: true
				},
				{
					label: 'Levered IRR',
					value: btr.returns.leveredIrrPct != null ? fmtPct(btr.returns.leveredIrrPct) : 'N/A',
					note: 'Equity returns after debt service',
					highlight: true
				},
				{
					label: 'Levered MOIC',
					value: `${fmt(btr.returns.leveredMoic, 2)}x`,
					note: 'Equity distributions / equity invested',
					highlight: true
				}
			]
		: []
)

function getVal(yr: BtrOperatingYear, key: RevKey): number {
	return yr[key]
}
function getExpVal(yr: BtrOperatingYear, key: ExpKey): number {
	return yr[key]
}
function noiMargin(yr: BtrOperatingYear): number {
	return yr.effectiveGrossRevenueAed > 0 ? (yr.noiAed / yr.effectiveGrossRevenueAed) * 100 : 0
}
</script>

{#if !btr}
<div class="h-full flex items-center justify-center px-6 text-sm text-slate-400">
	{#if assumptions?.developmentModel !== 'build_to_rent_residential'}
		Select "Build-to-Rent Residential" as the development model to view BTR analysis.
	{:else}
		Generate an HBU study to view the BTR operating model.
	{/if}
</div>
{:else}
<div class="overflow-auto flex-1 bg-white text-[11px] font-[Calibri,'Segoe_UI',Arial,sans-serif] select-none">

	<!-- Title bar -->
	<div class="bg-[#1F3864] border-b-2 border-[#1F3864] text-white px-4 py-2.5 flex items-center justify-between gap-4">
		<div class="text-[13px] font-bold tracking-wide">BUILD-TO-RENT OPERATING MODEL</div>
		<div class="text-[10px] text-blue-200 shrink-0">AED 000s unless stated</div>
	</div>

	<!-- KPI Summary bar -->
	<div class="flex border-b border-[#B8C4CE] bg-[#EEF2F7] divide-x divide-[#D9D9D9]">
		<div class="px-2 py-1.5 flex-1">
			<div class="text-[9px] uppercase tracking-wider text-slate-500 font-semibold">Stabilized NOI</div>
			<div class="text-[11px] font-bold text-slate-900 tabular-nums">AED {fmtK(btr.returns.stabilizedNoiAed)}K</div>
		</div>
		<div class="px-2 py-1.5 flex-1">
			<div class="text-[9px] uppercase tracking-wider text-slate-500 font-semibold">Yield on Cost</div>
			<div class="text-[11px] font-bold text-slate-900 tabular-nums">{fmtPct(btr.returns.stabilizedYieldOnCostPct)}</div>
		</div>
		<div class="px-2 py-1.5 flex-1">
			<div class="text-[9px] uppercase tracking-wider text-slate-500 font-semibold">Unlevered IRR</div>
			<div class="text-[11px] font-bold text-slate-900 tabular-nums">{btr.returns.unleveredIrrPct != null ? fmtPct(btr.returns.unleveredIrrPct) : 'N/A'}</div>
		</div>
		<div class="px-2 py-1.5 flex-1">
			<div class="text-[9px] uppercase tracking-wider text-slate-500 font-semibold">Levered IRR</div>
			<div class="text-[11px] font-bold text-slate-900 tabular-nums">{btr.returns.leveredIrrPct != null ? fmtPct(btr.returns.leveredIrrPct) : 'N/A'}</div>
		</div>
		<div class="px-2 py-1.5 flex-1">
			<div class="text-[9px] uppercase tracking-wider text-slate-500 font-semibold">Equity MOIC</div>
			<div class="text-[11px] font-bold text-slate-900 tabular-nums">{fmt(btr.returns.leveredMoic, 2)}x</div>
		</div>
	</div>

	<!-- Section A: Unit Mix -->
	<table class="w-full border-collapse" style="border-spacing:0">
		<tbody>
		<tr class="bg-[#1F3864]">
			<td colspan="7" class="px-2 py-[4px] text-white font-bold text-[11px] tracking-wide">A.&nbsp;&nbsp;RENTAL UNIT MIX</td>
		</tr>
		<tr class="bg-[#D6DCE4] border-b border-[#B8C4CE]">
			<th class="px-2 py-[4px] text-left text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Type</th>
			<th class="px-2 py-[4px] text-right text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Units</th>
			<th class="px-2 py-[4px] text-right text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Avg Size (sqm)</th>
			<th class="px-2 py-[4px] text-right text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Total Area (sqm)</th>
			<th class="px-2 py-[4px] text-right text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Monthly Rent</th>
			<th class="px-2 py-[4px] text-right text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Annual Rent</th>
			<th class="px-2 py-[4px] text-right text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Parking</th>
		</tr>
		{#each btr.program.rows as row (row.id)}
			<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
				<td class="px-2 py-[3px] text-left text-[10px] text-slate-800">{row.label}</td>
				<td class="px-2 py-[3px] text-right tabular-nums text-slate-900">{row.units}</td>
				<td class="px-2 py-[3px] text-right tabular-nums text-slate-900">{fmt(row.avgSizeSqm, 0)}</td>
				<td class="px-2 py-[3px] text-right tabular-nums text-slate-900">{fmt(row.totalAreaSqm, 0)}</td>
				<td class="px-2 py-[3px] text-right tabular-nums text-[#1565C0]">{fmt(row.monthlyRentAed, 0)}</td>
				<td class="px-2 py-[3px] text-right tabular-nums text-slate-900">{fmt(row.annualRentAed, 0)}</td>
				<td class="px-2 py-[3px] text-right tabular-nums text-slate-900">{row.parkingSpaces}</td>
			</tr>
		{/each}
		<tr class="border-t-2 border-[#B8C4CE] bg-[#EEF2F7] font-semibold">
			<td class="px-2 py-[4px] text-left text-[10px] text-slate-900">Total</td>
			<td class="px-2 py-[4px] text-right tabular-nums text-slate-900">{btr.program.totalUnits}</td>
			<td class="px-2 py-[4px] text-right tabular-nums text-slate-500">—</td>
			<td class="px-2 py-[4px] text-right tabular-nums text-slate-900">{fmt(btr.program.totalAreaSqm, 0)}</td>
			<td class="px-2 py-[4px] text-right tabular-nums text-slate-500">—</td>
			<td class="px-2 py-[4px] text-right tabular-nums text-slate-900">{fmt(btr.program.grossPotentialRentAed, 0)}</td>
			<td class="px-2 py-[4px] text-right tabular-nums text-slate-900">{btr.program.totalParkingSpaces}</td>
		</tr>
		</tbody>
	</table>

	<!-- Section B: Annual Operating P&L -->
	<div class="overflow-x-auto">
	<table class="w-full border-collapse" style="border-spacing:0; min-width: max-content">
		<tbody>
		<tr class="bg-[#1F3864]">
			<td colspan={btr.operatingYears.length + 1} class="px-2 py-[4px] text-white font-bold text-[11px] tracking-wide">B.&nbsp;&nbsp;ANNUAL OPERATING P&L (AED 000s)</td>
		</tr>
		<tr class="bg-[#D6DCE4] border-b border-[#B8C4CE]">
			<th class="px-2 py-[4px] text-left text-[9px] font-semibold text-slate-600 uppercase tracking-wider sticky left-0 bg-[#D6DCE4] z-10 min-w-[180px]">Line Item</th>
			{#each btr.operatingYears as yr (yr.year)}
				<th class="px-2 py-[4px] text-right text-[9px] font-semibold text-slate-600 uppercase tracking-wider min-w-[80px]">
					{yr.yearLabel}
					{#if yr.isLeaseUp}<br/><span class="text-amber-600 normal-case">Lease-up</span>{/if}
				</th>
			{/each}
		</tr>

		<!-- Revenue section -->
		<tr class="bg-slate-50/80 border-b border-[#D9D9D9]">
			<td class="px-2 py-[3px] text-left text-[10px] text-slate-900 font-semibold sticky left-0 bg-slate-50/80 z-10" colspan={btr.operatingYears.length + 1}>Revenue</td>
		</tr>
		{#each revenueRowDefs as row (row.label)}
			<tr class="border-b border-[#D9D9D9] {row.isTotal ? 'bg-[#EEF2F7] font-semibold' : ''} hover:bg-slate-50/60">
				<td class="px-2 py-[3px] text-left text-[10px] text-slate-800 sticky left-0 {row.isTotal ? 'bg-[#EEF2F7]' : 'bg-white'} z-10 {row.isNeg ? 'pl-6' : ''}">{row.label}</td>
				{#each btr.operatingYears as yr (yr.year)}
					<td class="px-2 py-[3px] text-right tabular-nums text-[10px] text-slate-900">
						{row.isNeg ? fmtNeg(getVal(yr, row.key)) : fmtK(getVal(yr, row.key))}
					</td>
				{/each}
			</tr>
		{/each}

		<!-- Expenses section -->
		<tr class="bg-slate-50/80 border-b border-[#D9D9D9]">
			<td class="px-2 py-[3px] text-left text-[10px] text-slate-900 font-semibold sticky left-0 bg-slate-50/80 z-10" colspan={btr.operatingYears.length + 1}>Operating Expenses</td>
		</tr>
		{#each expenseRowDefs as row (row.label)}
			<tr class="border-b border-[#D9D9D9] {row.isTotal ? 'bg-[#EEF2F7] font-semibold' : ''} hover:bg-slate-50/60">
				<td class="px-2 py-[3px] text-left text-[10px] text-slate-800 sticky left-0 {row.isTotal ? 'bg-[#EEF2F7]' : 'bg-white'} z-10 {!row.isTotal ? 'pl-6' : ''}">{row.label}</td>
				{#each btr.operatingYears as yr (yr.year)}
					<td class="px-2 py-[3px] text-right tabular-nums text-[10px] text-slate-900">
						({fmtK(Math.abs(getExpVal(yr, row.key)))})
					</td>
				{/each}
			</tr>
		{/each}

		<!-- NOI row -->
		<tr class="border-t-2 border-[#B8C4CE] bg-[#EEF2F7] font-bold">
			<td class="px-2 py-[4px] text-left text-[10px] text-slate-900 sticky left-0 bg-[#EEF2F7] z-10">Net Operating Income (NOI)</td>
			{#each btr.operatingYears as yr (yr.year)}
				<td class="px-2 py-[4px] text-right tabular-nums text-[10px] text-slate-900">
					{fmtNeg(yr.noiAed)}
				</td>
			{/each}
		</tr>

		<!-- CapEx and CFO -->
		<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
			<td class="px-2 py-[3px] text-left text-[10px] text-slate-800 pl-6 sticky left-0 bg-white z-10">Less: CapEx Reserve</td>
			{#each btr.operatingYears as yr (yr.year)}
				<td class="px-2 py-[3px] text-right tabular-nums text-[10px] text-slate-900">
					({fmtK(Math.abs(yr.capexReserveAed))})
				</td>
			{/each}
		</tr>
		<tr class="border-t-2 border-[#B8C4CE] bg-[#EEF2F7] font-bold">
			<td class="px-2 py-[4px] text-left text-[10px] text-slate-900 sticky left-0 bg-[#EEF2F7] z-10">Cash Flow from Operations (CFO)</td>
			{#each btr.operatingYears as yr (yr.year)}
				<td class="px-2 py-[4px] text-right tabular-nums text-[10px] text-slate-900">
					{fmtNeg(yr.cfoAed)}
				</td>
			{/each}
		</tr>

		<!-- Debt Service & CFAF -->
		<tr class="bg-slate-50/80 border-b border-[#D9D9D9]">
			<td class="px-2 py-[3px] text-left text-[10px] text-slate-900 font-semibold sticky left-0 bg-slate-50/80 z-10" colspan={btr.operatingYears.length + 1}>Permanent Debt Service</td>
		</tr>
		<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
			<td class="px-2 py-[3px] text-left text-[10px] text-slate-800 pl-6 sticky left-0 bg-white z-10">Less: Debt Service</td>
			{#each btr.operatingYears as yr (yr.year)}
				<td class="px-2 py-[3px] text-right tabular-nums text-[10px] {yr.debtServiceAed > 0 ? 'text-slate-900' : 'text-slate-400'}">
					{yr.debtServiceAed > 0 ? `(${fmtK(yr.debtServiceAed)})` : '—'}
				</td>
			{/each}
		</tr>
		<tr class="border-t-2 border-[#B8C4CE] bg-[#EEF2F7] font-bold">
			<td class="px-2 py-[4px] text-left text-[10px] text-slate-900 sticky left-0 bg-[#EEF2F7] z-10">Cash Flow After Financing (CFAF)</td>
			{#each btr.operatingYears as yr (yr.year)}
				<td class="px-2 py-[4px] text-right tabular-nums text-[10px] text-slate-900">
					{fmtNeg(yr.cfafAed)}
				</td>
			{/each}
		</tr>

		<!-- Operating metrics -->
		<tr class="bg-slate-50/80 border-b border-[#D9D9D9]">
			<td class="px-2 py-[3px] text-left text-[10px] text-slate-900 font-semibold sticky left-0 bg-slate-50/80 z-10" colspan={btr.operatingYears.length + 1}>Key Metrics</td>
		</tr>
		<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
			<td class="px-2 py-[3px] text-left text-[10px] text-slate-800 sticky left-0 bg-white z-10">Occupancy</td>
			{#each btr.operatingYears as yr (yr.year)}
				<td class="px-2 py-[3px] text-right tabular-nums text-[10px] text-slate-900">{fmtPct(yr.occupancyPct)}</td>
			{/each}
		</tr>
		<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
			<td class="px-2 py-[3px] text-left text-[10px] text-slate-800 sticky left-0 bg-white z-10">OpEx Ratio</td>
			{#each btr.operatingYears as yr (yr.year)}
				<td class="px-2 py-[3px] text-right tabular-nums text-[10px] text-slate-900">{fmtPct(yr.opExRatio * 100)}</td>
			{/each}
		</tr>
		<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
			<td class="px-2 py-[3px] text-left text-[10px] text-slate-800 sticky left-0 bg-white z-10">NOI Margin</td>
			{#each btr.operatingYears as yr (yr.year)}
				<td class="px-2 py-[3px] text-right tabular-nums text-[10px] text-slate-900">{fmtPct(noiMargin(yr))}</td>
			{/each}
		</tr>
		</tbody>
	</table>
	</div>

	<!-- Section C: Exit & Valuation -->
	<table class="w-full border-collapse" style="border-spacing:0">
		<tbody>
		<tr class="bg-[#1F3864]">
			<td colspan="3" class="px-2 py-[4px] text-white font-bold text-[11px] tracking-wide">C.&nbsp;&nbsp;EXIT &amp; VALUATION</td>
		</tr>
		<tr class="bg-[#D6DCE4] border-b border-[#B8C4CE]">
			<th class="px-2 py-[4px] text-left text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Metric</th>
			<th class="px-2 py-[4px] text-right text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Value</th>
			<th class="px-2 py-[4px] text-left text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Note</th>
		</tr>
		{#each exitRows as row (row.label)}
			<tr class="border-b border-[#D9D9D9] {row.highlight ? 'bg-[#EEF2F7] font-semibold' : ''} hover:bg-slate-50/60">
				<td class="px-2 py-[3px] text-left text-[10px] text-slate-800">{row.label}</td>
				<td class="px-2 py-[3px] text-right tabular-nums text-[10px] text-slate-900 font-medium">{row.value}</td>
				<td class="px-2 py-[3px] text-left text-[9px] text-slate-500">{row.note}</td>
			</tr>
		{/each}
		</tbody>
	</table>

	<!-- Section D: Permanent Debt -->
	<table class="w-full border-collapse" style="border-spacing:0">
		<tbody>
		<tr class="bg-[#1F3864]">
			<td colspan="3" class="px-2 py-[4px] text-white font-bold text-[11px] tracking-wide">D.&nbsp;&nbsp;PERMANENT DEBT (REFINANCE AT STABILIZATION)</td>
		</tr>
		<tr class="bg-[#D6DCE4] border-b border-[#B8C4CE]">
			<th class="px-2 py-[4px] text-left text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Metric</th>
			<th class="px-2 py-[4px] text-right text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Value</th>
			<th class="px-2 py-[4px] text-left text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Note</th>
		</tr>
		{#each debtRows as row (row.label)}
			<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
				<td class="px-2 py-[3px] text-left text-[10px] text-slate-800">{row.label}</td>
				<td class="px-2 py-[3px] text-right tabular-nums text-[10px] font-medium {row.label === 'DSCR at Origination' && btr ? (btr.permDebt.dscrAtOrigination >= (assumptions?.btrDscrMinimum ?? 1.25) ? 'text-slate-900' : 'text-amber-700') : 'text-slate-900'}">{row.value}</td>
				<td class="px-2 py-[3px] text-left text-[9px] text-slate-500">{row.note}</td>
			</tr>
		{/each}
		</tbody>
	</table>

	<!-- Section E: Full-Cycle Returns -->
	<table class="w-full border-collapse" style="border-spacing:0">
		<tbody>
		<tr class="bg-[#1F3864]">
			<td colspan="3" class="px-2 py-[4px] text-white font-bold text-[11px] tracking-wide">E.&nbsp;&nbsp;FULL-CYCLE RETURNS</td>
		</tr>
		<tr class="bg-[#D6DCE4] border-b border-[#B8C4CE]">
			<th class="px-2 py-[4px] text-left text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Metric</th>
			<th class="px-2 py-[4px] text-right text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Value</th>
			<th class="px-2 py-[4px] text-left text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Note</th>
		</tr>
		{#each returnRows as row (row.label)}
			<tr class="border-b border-[#D9D9D9] {row.highlight ? 'font-semibold' : ''} hover:bg-slate-50/60">
				<td class="px-2 py-[3px] text-left text-[10px] text-slate-800">{row.label}</td>
				<td class="px-2 py-[3px] text-right tabular-nums text-[10px] {row.highlight ? 'text-emerald-700' : 'text-slate-900'} font-medium">{row.value}</td>
				<td class="px-2 py-[3px] text-left text-[9px] text-slate-500">{row.note}</td>
			</tr>
		{/each}
		</tbody>
	</table>

	<!-- Section F: Annual Cash Flow (Full Cycle) -->
	{#if btr.annualCashFlow.length > 0}
	<div class="overflow-x-auto">
	<table class="w-full border-collapse" style="border-spacing:0; min-width: max-content">
		<tbody>
		<tr class="bg-[#1F3864]">
			<td colspan={btr.annualCashFlow.length + 1} class="px-2 py-[4px] text-white font-bold text-[11px] tracking-wide">F.&nbsp;&nbsp;ANNUAL CASH FLOW — FULL CYCLE (AED 000s)</td>
		</tr>
		<tr class="bg-[#D6DCE4] border-b border-[#B8C4CE]">
			<th class="px-2 py-[4px] text-left text-[9px] font-semibold text-slate-600 uppercase tracking-wider sticky left-0 bg-[#D6DCE4] z-10 min-w-[180px]">Line Item</th>
			{#each btr.annualCashFlow as yr (yr.yearLabel)}
				<th class="px-2 py-[4px] text-right text-[9px] font-semibold text-slate-600 uppercase tracking-wider min-w-[80px]">{yr.yearLabel}</th>
			{/each}
		</tr>
		<!-- Dev costs -->
		<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
			<td class="px-2 py-[3px] text-left text-[10px] text-slate-800 sticky left-0 bg-white z-10">Dev Costs</td>
			{#each btr.annualCashFlow as yr (yr.yearLabel)}
				<td class="px-2 py-[3px] text-right tabular-nums text-[10px] {yr.devCostsAed !== 0 ? 'text-slate-900' : 'text-slate-400'}">{yr.devCostsAed !== 0 ? fmtNeg(yr.devCostsAed) : '—'}</td>
			{/each}
		</tr>
		<!-- Dev debt -->
		<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
			<td class="px-2 py-[3px] text-left text-[10px] text-slate-800 pl-6 sticky left-0 bg-white z-10">Dev Debt Draw</td>
			{#each btr.annualCashFlow as yr (yr.yearLabel)}
				<td class="px-2 py-[3px] text-right tabular-nums text-[10px] text-slate-900">{yr.devDebtDrawAed !== 0 ? fmtK(yr.devDebtDrawAed) : '—'}</td>
			{/each}
		</tr>
		<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
			<td class="px-2 py-[3px] text-left text-[10px] text-slate-800 pl-6 sticky left-0 bg-white z-10">Dev Debt Repayment</td>
			{#each btr.annualCashFlow as yr (yr.yearLabel)}
				<td class="px-2 py-[3px] text-right tabular-nums text-[10px] {yr.devDebtRepaymentAed !== 0 ? 'text-slate-900' : 'text-slate-400'}">{yr.devDebtRepaymentAed !== 0 ? fmtNeg(yr.devDebtRepaymentAed) : '—'}</td>
			{/each}
		</tr>
		<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
			<td class="px-2 py-[3px] text-left text-[10px] text-slate-800 pl-6 sticky left-0 bg-white z-10">Dev Interest</td>
			{#each btr.annualCashFlow as yr (yr.yearLabel)}
				<td class="px-2 py-[3px] text-right tabular-nums text-[10px] {yr.devInterestAed !== 0 ? 'text-slate-900' : 'text-slate-400'}">{yr.devInterestAed !== 0 ? fmtNeg(yr.devInterestAed) : '—'}</td>
			{/each}
		</tr>
		<!-- Operating CFO -->
		<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
			<td class="px-2 py-[3px] text-left text-[10px] text-slate-800 sticky left-0 bg-white z-10">Operating CFO</td>
			{#each btr.annualCashFlow as yr (yr.yearLabel)}
				<td class="px-2 py-[3px] text-right tabular-nums text-[10px] {yr.cfoAed !== 0 ? 'text-slate-900' : 'text-slate-400'}">{yr.cfoAed !== 0 ? fmtNeg(yr.cfoAed) : '—'}</td>
			{/each}
		</tr>
		<!-- Perm debt -->
		<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
			<td class="px-2 py-[3px] text-left text-[10px] text-slate-800 pl-6 sticky left-0 bg-white z-10">Perm Debt Proceeds (Refi)</td>
			{#each btr.annualCashFlow as yr (yr.yearLabel)}
				<td class="px-2 py-[3px] text-right tabular-nums text-[10px] text-slate-900">{yr.permDebtProceedsAed !== 0 ? fmtK(yr.permDebtProceedsAed) : '—'}</td>
			{/each}
		</tr>
		<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
			<td class="px-2 py-[3px] text-left text-[10px] text-slate-800 pl-6 sticky left-0 bg-white z-10">Perm Debt Service</td>
			{#each btr.annualCashFlow as yr (yr.yearLabel)}
				<td class="px-2 py-[3px] text-right tabular-nums text-[10px] {yr.permDebtServiceAed !== 0 ? 'text-slate-900' : 'text-slate-400'}">{yr.permDebtServiceAed !== 0 ? fmtNeg(yr.permDebtServiceAed) : '—'}</td>
			{/each}
		</tr>
		<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
			<td class="px-2 py-[3px] text-left text-[10px] text-slate-800 pl-6 sticky left-0 bg-white z-10">Loan Payoff at Exit</td>
			{#each btr.annualCashFlow as yr (yr.yearLabel)}
				<td class="px-2 py-[3px] text-right tabular-nums text-[10px] {yr.permLoanPayoffAed !== 0 ? 'text-slate-900' : 'text-slate-400'}">{yr.permLoanPayoffAed !== 0 ? fmtNeg(yr.permLoanPayoffAed) : '—'}</td>
			{/each}
		</tr>
		<!-- Disposition -->
		<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
			<td class="px-2 py-[3px] text-left text-[10px] text-slate-800 sticky left-0 bg-white z-10">Terminal Sale Value</td>
			{#each btr.annualCashFlow as yr (yr.yearLabel)}
				<td class="px-2 py-[3px] text-right tabular-nums text-[10px] text-slate-900">{yr.salePriceAed !== 0 ? fmtK(yr.salePriceAed) : '—'}</td>
			{/each}
		</tr>
		<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
			<td class="px-2 py-[3px] text-left text-[10px] text-slate-800 pl-6 sticky left-0 bg-white z-10">Sale Expenses</td>
			{#each btr.annualCashFlow as yr (yr.yearLabel)}
				<td class="px-2 py-[3px] text-right tabular-nums text-[10px] text-slate-900">{yr.saleExpensesAed !== 0 ? fmtNeg(yr.saleExpensesAed) : '—'}</td>
			{/each}
		</tr>
		<!-- Net flows -->
		<tr class="border-t-2 border-[#B8C4CE] bg-[#EEF2F7] font-bold">
			<td class="px-2 py-[4px] text-left text-[10px] text-slate-900 sticky left-0 bg-[#EEF2F7] z-10">Unlevered Cash Flow</td>
			{#each btr.annualCashFlow as yr (yr.yearLabel)}
				<td class="px-2 py-[4px] text-right tabular-nums text-[10px] text-slate-900">{fmtNeg(yr.unleveredCfAed)}</td>
			{/each}
		</tr>
		<tr class="border-t-2 border-[#B8C4CE] bg-[#EEF2F7] font-bold">
			<td class="px-2 py-[4px] text-left text-[10px] text-slate-900 sticky left-0 bg-[#EEF2F7] z-10">Levered Cash Flow</td>
			{#each btr.annualCashFlow as yr (yr.yearLabel)}
				<td class="px-2 py-[4px] text-right tabular-nums text-[10px] text-slate-900">{fmtNeg(yr.leveredCfAed)}</td>
			{/each}
		</tr>
		</tbody>
	</table>
	</div>
	{/if}

	<div class="py-3"></div>
</div>
{/if}
