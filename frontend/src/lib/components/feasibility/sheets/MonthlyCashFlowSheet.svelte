<script lang="ts">
import type {
	BtrAnnualCashFlowRow,
	BtrDevPeriod,
	CashFlowPeriod
} from '$lib/feasibility/workbook/engine'
import { workbookStore } from '$lib/feasibility/workbook/store.svelte'

const isBtr = $derived(workbookStore.assumptions?.developmentModel === 'build_to_rent_residential')
const btrDevPeriods = $derived(workbookStore.workbook?.btr?.devCashFlow ?? ([] as BtrDevPeriod[]))
const btrAnnualRows = $derived(
	workbookStore.workbook?.btr?.annualCashFlow ?? ([] as BtrAnnualCashFlowRow[])
)
const btrOperatingYears = $derived(workbookStore.workbook?.btr?.operatingYears ?? [])
const periods = $derived(workbookStore.workbook?.cashFlow?.periods ?? ([] as CashFlowPeriod[]))

type NumericPeriodField =
	| 'revenueInflowsAed'
	| 'operatingOutflowsAed'
	| 'debtDrawAed'
	| 'debtRepaymentAed'
	| 'interestPaidAed'
	| 'commitmentFeePaidAed'
	| 'equityContributionAed'
	| 'equityDistributionAed'
	| 'debtBalanceAed'
	| 'landLoanBalanceAed'
	| 'constructionLoanBalanceAed'
	| 'escrowBalanceAed'
	| 'unleveredNetCashFlowAed'
	| 'leveredNetCashFlowAed'
	| 'depositInflowsAed'
	| 'preHandoverInflowsAed'
	| 'handoverInflowsAed'
	| 'costLandAed'
	| 'costLandFeesAed'
	| 'costPermitFeesAed'
	| 'costHardAed'
	| 'costSoftAed'
	| 'costConstructionAed'
	| 'costProfessionalFeesAed'
	| 'costMarketingAed'
	| 'costSalesAdminAed'
	| 'costSalesAgentAed'
	| 'costInfrastructureAed'
	| 'costAuthorityFeesAed'
	| 'costCommunityFeesAed'
	| 'costContingencyAed'
	| 'costVatAed'
	| 'vatPaidAed'
	| 'vatRefundInflowsAed'
	| 'financingFeeAed'
	| 'exitFeeAed'
	| 'interestAcqAed'
	| 'interestConAed'
	| 'acqDebtDrawAed'
	| 'acqDebtRepaymentAed'
	| 'closingAcqDebtAed'
	| 'conDebtDrawAed'
	| 'conDebtRepaymentAed'
	| 'closingConDebtAed'
	| 'contractedRevenueAed'
	| 'netCfBeforeDebtAed'
	| 'totalUsesAed'
	| 'constructionCurvePct'
	| 'salesCurvePct'

type CostBreakdownRow = { field: NumericPeriodField; label: string }
type FinancingRow = { field: NumericPeriodField; label: string; isOut: boolean }
type BalanceRow = { field: NumericPeriodField; label: string }

function fmt(v: number): string {
	if (v === 0) return '—'
	return Math.abs(Math.round(v)).toLocaleString('en-AE')
}

function fmtOut(v: number): string {
	if (v === 0) return '—'
	return `(${Math.round(v).toLocaleString('en-AE')})`
}

function periodValue(period: CashFlowPeriod, field: NumericPeriodField): number {
	return Number(period[field] ?? 0)
}

function sum(field: NumericPeriodField): number {
	return periods.reduce((s, p) => s + periodValue(p, field), 0)
}

function hasPositive(field: NumericPeriodField): boolean {
	return periods.some((p) => periodValue(p, field) > 0)
}

const TH =
	'px-2 py-[4px] text-right text-[9px] font-semibold text-slate-500 whitespace-nowrap min-w-[70px]'
const TH_L =
	'px-2 py-[4px] text-left text-[9px] font-semibold text-slate-600 sticky left-0 bg-white z-20 min-w-[160px] whitespace-nowrap border-r border-slate-200'
const TH_TOT =
	'px-2 py-[4px] text-right text-[9px] font-semibold text-slate-700 bg-slate-100 whitespace-nowrap border-r border-slate-300 min-w-[80px]'
const TD = 'px-2 py-[3px] text-right text-[10px] tabular-nums text-slate-600 whitespace-nowrap'
const TD_OUT = 'px-2 py-[3px] text-right text-[10px] tabular-nums text-slate-900 whitespace-nowrap'
const TD_NET = 'px-2 py-[3px] text-right text-[10px] tabular-nums font-semibold whitespace-nowrap'
const TD_TOT =
	'px-2 py-[3px] text-right text-[10px] tabular-nums font-semibold text-slate-800 bg-slate-50 whitespace-nowrap border-r border-slate-200'
const TD_L =
	'px-2 py-[3px] text-left text-[10px] text-slate-700 sticky left-0 bg-white z-10 border-r border-slate-200 whitespace-nowrap'
const TD_L_SUB =
	'pl-5 pr-2 py-[2px] text-left text-[9px] text-slate-400 sticky left-0 bg-white z-10 border-r border-slate-200 whitespace-nowrap italic'
const TD_L_HDR =
	'px-2 py-[4px] text-left text-[10px] font-bold text-white sticky left-0 z-10 border-r border-slate-200 whitespace-nowrap'
const HDR_ROW = 'bg-[#1F3864]'
const SUB_ROW = 'border-t border-slate-100 bg-slate-50/40'
const DATA_ROW = 'border-t border-slate-100 hover:bg-slate-50/60'
const TOTAL_ROW = 'border-t-2 border-[#1F3864] border-b border-slate-200'

const totUnlevered = $derived(sum('unleveredNetCashFlowAed'))
const totLevered = $derived(sum('leveredNetCashFlowAed'))
const costBreakdownRows: CostBreakdownRow[] = [
	{ field: 'costLandAed', label: 'Land acquisition' },
	{ field: 'costLandFeesAed', label: 'Land fees (transfer/brokerage/legal)' },
	{ field: 'costPermitFeesAed', label: 'Permit / authority fees' },
	{ field: 'costHardAed', label: 'Hard cost (construction)' },
	{ field: 'costSoftAed', label: 'Soft cost (professional fees)' },
	{ field: 'costContingencyAed', label: 'Contingency' },
	{ field: 'costInfrastructureAed', label: 'Infrastructure & utilities' },
	{ field: 'costAuthorityFeesAed', label: 'Authority & connection fees' },
	{ field: 'costCommunityFeesAed', label: 'Community fees / demolition / FFE' },
	{ field: 'costMarketingAed', label: 'Marketing' },
	{ field: 'costSalesAdminAed', label: 'Sales admin' },
	{ field: 'vatPaidAed', label: 'VAT paid' }
]
const financingRows: FinancingRow[] = [
	{ field: 'financingFeeAed', label: 'Financing fee', isOut: true },
	{ field: 'acqDebtDrawAed', label: 'Acquisition debt draw', isOut: false },
	{ field: 'conDebtDrawAed', label: 'Construction debt draw', isOut: false },
	{ field: 'interestAcqAed', label: 'Interest — acquisition', isOut: true },
	{ field: 'interestConAed', label: 'Interest — construction', isOut: true },
	{ field: 'acqDebtRepaymentAed', label: 'Acquisition debt repayment', isOut: true },
	{ field: 'conDebtRepaymentAed', label: 'Construction debt repayment', isOut: true },
	{ field: 'exitFeeAed', label: 'Exit fee', isOut: true },
	{ field: 'equityContributionAed', label: 'Equity contribution', isOut: true },
	{ field: 'equityDistributionAed', label: 'Equity distribution', isOut: false }
]
const balanceRows: BalanceRow[] = [
	{ field: 'debtBalanceAed', label: 'Total debt balance' },
	{ field: 'closingAcqDebtAed', label: 'Acquisition tranche balance' },
	{ field: 'closingConDebtAed', label: 'Construction tranche balance' }
]

function sumBtr(field: keyof BtrDevPeriod): number {
	return btrDevPeriods.reduce((sum, period) => sum + Number(period[field] ?? 0), 0)
}

function sumBtrAnnual(field: keyof BtrAnnualCashFlowRow): number {
	return btrAnnualRows.reduce((sum, row) => sum + Number(row[field] ?? 0), 0)
}

function fmtSigned(v: number): string {
	if (v === 0) return '—'
	return v < 0 ? fmtOut(Math.abs(v)) : fmt(v)
}

// Sources per period: proceeds + VAT refunds + debt draws + equity in
function periodSources(p: CashFlowPeriod): number {
	return round(
		p.revenueInflowsAed +
			(p.vatRefundInflowsAed ?? 0) +
			p.acqDebtDrawAed +
			p.conDebtDrawAed +
			p.equityContributionAed
	)
}

// Uses per period: costs + VAT paid + interest + fees + debt repayments + equity out
function periodUses(p: CashFlowPeriod): number {
	return round(
		p.totalUsesAed + p.acqDebtRepaymentAed + p.conDebtRepaymentAed + p.equityDistributionAed
	)
}

// ── Monthly source allocation (waterfall per period) ─────────────────────────
// For each period, allocate total outflows to sources in priority order:
// 1. Off-plan proceeds + VAT refunds (buyer cash reduces equity need first)
// 2. Acquisition debt drawn
// 3. Construction debt drawn
// 4. Equity (residual — always non-zero when equity was deployed)
interface PeriodAlloc {
	totalOutflow: number
	proceedsAlloc: number
	acqDebtAlloc: number
	conDebtAlloc: number
	equityAlloc: number
}

function computeAlloc(p: CashFlowPeriod): PeriodAlloc {
	// Total outflow = all cost outflows: operating costs + VAT + interest + fees (totalUsesAed).
	// Debt repayments and equity distributions are excluded — they are capital recycling
	// (balance sheet movements), not new project cost outflows. This makes the waterfall
	// totals reconcile with the S&U total uses.
	const totalOutflow = p.totalUsesAed
	let remaining = totalOutflow

	// Priority 1: proceeds + VAT refunds
	const availableProceeds = p.revenueInflowsAed + (p.vatRefundInflowsAed ?? 0)
	const proceedsAlloc = round(Math.min(availableProceeds, remaining))
	remaining = round(remaining - proceedsAlloc)

	// Priority 2: acquisition debt
	const acqDebtAlloc = round(Math.min(p.acqDebtDrawAed, remaining))
	remaining = round(remaining - acqDebtAlloc)

	// Priority 3: construction debt
	const conDebtAlloc = round(Math.min(p.conDebtDrawAed, remaining))
	remaining = round(remaining - conDebtAlloc)

	// Priority 4: equity (residual)
	const equityAlloc = round(Math.max(remaining, 0))

	return { totalOutflow, proceedsAlloc, acqDebtAlloc, conDebtAlloc, equityAlloc }
}

const periodAllocs = $derived(periods.map(computeAlloc))

// Precompute cumulative running totals for balance section
// Now tracks cumulative allocated amounts from waterfall (not just raw draws)
const cumulativeProceeds = $derived(
	periodAllocs.reduce<number[]>((acc, a) => {
		acc.push(round((acc[acc.length - 1] ?? 0) + a.proceedsAlloc))
		return acc
	}, [])
)
const cumulativeEquity = $derived(
	periodAllocs.reduce<number[]>((acc, a) => {
		acc.push(round((acc[acc.length - 1] ?? 0) + a.equityAlloc))
		return acc
	}, [])
)
const cumulativeAcqDebt = $derived(
	periodAllocs.reduce<number[]>((acc, a) => {
		acc.push(round((acc[acc.length - 1] ?? 0) + a.acqDebtAlloc))
		return acc
	}, [])
)
const cumulativeConDebt = $derived(
	periodAllocs.reduce<number[]>((acc, a) => {
		acc.push(round((acc[acc.length - 1] ?? 0) + a.conDebtAlloc))
		return acc
	}, [])
)

// need round() from engine — use the same logic inline
function round(v: number): number {
	return Math.round(v * 100) / 100
}
</script>

{#if isBtr && btrDevPeriods.length > 0}
	<div class="h-full overflow-auto text-[10px] font-[Calibri,'Segoe_UI',Arial,sans-serif]">
		<table class="border-collapse min-w-full mb-4" style="border-spacing:0">
			<thead class="sticky top-0 z-30">
				<tr class="border-b-2 border-slate-300 bg-white shadow-sm">
					<th class="{TH_L} bg-slate-50">Line Item</th>
					{#each btrAnnualRows as row}
						<th class={TH}>{row.yearLabel}</th>
					{/each}
					<th class="px-2 py-[4px] text-right text-[9px] font-semibold text-slate-700 bg-slate-100 whitespace-nowrap sticky right-0 z-20 border-l border-slate-300">Total</th>
				</tr>
			</thead>
			<tbody>
				<tr class={HDR_ROW}>
					<td class="{TD_L_HDR} bg-[#1F3864]">BTR FULL-CYCLE CASH FLOW</td>
					{#each btrAnnualRows as _}<td class="bg-[#1F3864] min-w-[80px]"></td>{/each}
					<td class="bg-[#1F3864] sticky right-0 border-l border-[#2D4D7A] min-w-[80px]"></td>
				</tr>
				<tr class={DATA_ROW}>
					<td class={TD_L}>Development costs</td>
					{#each btrAnnualRows as row}<td class={TD_OUT}>{fmtSigned(row.devCostsAed)}</td>{/each}
					<td class="{TD_TOT} sticky right-0 border-l border-slate-300">{fmtSigned(sumBtrAnnual('devCostsAed'))}</td>
				</tr>
				<tr class={DATA_ROW}>
					<td class={TD_L}>Capitalized interest & financing fees</td>
					{#each btrAnnualRows as row}<td class={TD_OUT}>{fmtSigned(row.devInterestAed)}</td>{/each}
					<td class="{TD_TOT} sticky right-0 border-l border-slate-300">{fmtSigned(sumBtrAnnual('devInterestAed'))}</td>
				</tr>
				<tr class={DATA_ROW}>
					<td class={TD_L}>Operating CFO</td>
					{#each btrAnnualRows as row}<td class={row.cfoAed < 0 ? TD_OUT : TD}>{fmtSigned(row.cfoAed)}</td>{/each}
					<td class="{TD_TOT} sticky right-0 border-l border-slate-300">{fmtSigned(sumBtrAnnual('cfoAed'))}</td>
				</tr>
				<tr class={SUB_ROW}>
					<td class={TD_L_SUB}>↳ Occupancy</td>
					{#each btrAnnualRows as row, i}
						<td class="{TD} text-slate-400">{row.yearIndex > 0 && btrOperatingYears[i - 1] ? `${btrOperatingYears[i - 1].occupancyPct.toFixed(1)}%` : '—'}</td>
					{/each}
					<td class="{TD_TOT} sticky right-0 border-l border-slate-300">—</td>
				</tr>
				<tr class={SUB_ROW}>
					<td class={TD_L_SUB}>↳ NOI</td>
					{#each btrAnnualRows as row, i}
						<td class="{TD} text-slate-500">{row.yearIndex > 0 && btrOperatingYears[i - 1] ? fmtSigned(btrOperatingYears[i - 1].noiAed) : '—'}</td>
					{/each}
					<td class="{TD_TOT} sticky right-0 border-l border-slate-300">{fmtSigned(btrOperatingYears.reduce((s, y) => s + y.noiAed, 0))}</td>
				</tr>
				<tr class={DATA_ROW}>
					<td class={TD_L}>Permanent loan proceeds / refi</td>
					{#each btrAnnualRows as row}<td class={TD}>{fmtSigned(row.permDebtProceedsAed)}</td>{/each}
					<td class="{TD_TOT} sticky right-0 border-l border-slate-300">{fmtSigned(sumBtrAnnual('permDebtProceedsAed'))}</td>
				</tr>
				<tr class={DATA_ROW}>
					<td class={TD_L}>Development debt repayment</td>
					{#each btrAnnualRows as row}<td class={TD_OUT}>{fmtSigned(row.devDebtRepaymentAed)}</td>{/each}
					<td class="{TD_TOT} sticky right-0 border-l border-slate-300">{fmtSigned(sumBtrAnnual('devDebtRepaymentAed'))}</td>
				</tr>
				<tr class={DATA_ROW}>
					<td class={TD_L}>Permanent debt service</td>
					{#each btrAnnualRows as row}<td class={TD_OUT}>{fmtSigned(row.permDebtServiceAed)}</td>{/each}
					<td class="{TD_TOT} sticky right-0 border-l border-slate-300">{fmtSigned(sumBtrAnnual('permDebtServiceAed'))}</td>
				</tr>
				<tr class={DATA_ROW}>
					<td class={TD_L}>Terminal sale value</td>
					{#each btrAnnualRows as row}<td class={TD}>{fmtSigned(row.salePriceAed)}</td>{/each}
					<td class="{TD_TOT} sticky right-0 border-l border-slate-300">{fmtSigned(sumBtrAnnual('salePriceAed'))}</td>
				</tr>
				<tr class={DATA_ROW}>
					<td class={TD_L}>Sale expenses & loan payoff</td>
					{#each btrAnnualRows as row}<td class={TD_OUT}>{fmtSigned(row.saleExpensesAed + row.permLoanPayoffAed)}</td>{/each}
					<td class="{TD_TOT} sticky right-0 border-l border-slate-300">{fmtSigned(sumBtrAnnual('saleExpensesAed') + sumBtrAnnual('permLoanPayoffAed'))}</td>
				</tr>
				<tr class="border-t-2 border-[#1F3864] bg-[#E8F0FE]">
					<td class="px-2 py-[4px] text-left text-[10px] font-bold text-slate-900 sticky left-0 bg-[#E8F0FE] z-10 border-r border-slate-200 whitespace-nowrap">Unlevered Cash Flow</td>
					{#each btrAnnualRows as row}<td class="px-2 py-[4px] text-right text-[10px] tabular-nums font-semibold whitespace-nowrap text-slate-900">{fmtSigned(row.unleveredCfAed)}</td>{/each}
					<td class="px-2 py-[4px] text-right text-[10px] tabular-nums font-bold sticky right-0 border-l border-slate-300 bg-slate-100 text-slate-900">{fmtSigned(sumBtrAnnual('unleveredCfAed'))}</td>
				</tr>
				<tr class="border-t border-slate-300 bg-[#D6E4FF]">
					<td class="px-2 py-[4px] text-left text-[10px] font-bold text-slate-900 sticky left-0 bg-[#D6E4FF] z-10 border-r border-slate-200 whitespace-nowrap">Levered Equity Cash Flow</td>
					{#each btrAnnualRows as row}<td class="px-2 py-[4px] text-right text-[10px] tabular-nums font-semibold whitespace-nowrap text-slate-900">{fmtSigned(row.leveredCfAed)}</td>{/each}
					<td class="px-2 py-[4px] text-right text-[10px] tabular-nums font-bold sticky right-0 border-l border-slate-300 bg-slate-100 text-slate-900">{fmtSigned(sumBtrAnnual('leveredCfAed'))}</td>
				</tr>
			</tbody>
		</table>

		<table class="border-collapse min-w-full" style="border-spacing:0">
			<thead class="sticky top-0 z-30">
				<tr class="border-b-2 border-slate-300 bg-white shadow-sm">
					<th class="{TH_L} bg-slate-50">Line Item</th>
					{#each btrDevPeriods as period}
						<th class={TH}>{period.periodLabel}</th>
					{/each}
					<th class="px-2 py-[4px] text-right text-[9px] font-semibold text-slate-700 bg-slate-100 whitespace-nowrap sticky right-0 z-20 border-l border-slate-300">Total</th>
				</tr>
			</thead>
			<tbody>
				<!-- BTR DEVELOPMENT USES -->
				<tr class={HDR_ROW}>
					<td class="{TD_L_HDR} bg-[#1F3864]">BTR DEVELOPMENT USES</td>
					{#each btrDevPeriods as _}<td class="bg-[#1F3864] min-w-[70px]"></td>{/each}
					<td class="bg-[#1F3864] sticky right-0 border-l border-[#2D4D7A] min-w-[80px]"></td>
				</tr>
				<tr class={DATA_ROW}>
					<td class={TD_L}>Dev cost outflows (excl. VAT)</td>
					{#each btrDevPeriods as period}<td class={TD_OUT}>{period.costOutflowAed > 0 ? fmtOut(period.costOutflowAed) : '—'}</td>{/each}
					<td class="{TD_TOT} sticky right-0 border-l border-slate-300">{fmtOut(sumBtr('costOutflowAed'))}</td>
				</tr>
				<tr class={DATA_ROW}>
					<td class={TD_L}>VAT paid</td>
					{#each btrDevPeriods as period}<td class={TD_OUT}>{period.vatPaidAed > 0 ? fmtOut(period.vatPaidAed) : '—'}</td>{/each}
					<td class="{TD_TOT} sticky right-0 border-l border-slate-300">{fmtOut(sumBtr('vatPaidAed'))}</td>
				</tr>
				<tr class={DATA_ROW}>
					<td class={TD_L}>VAT refund received</td>
					{#each btrDevPeriods as period}<td class={TD}>{period.vatRefundAed > 0 ? fmt(period.vatRefundAed) : '—'}</td>{/each}
					<td class="{TD_TOT} sticky right-0 border-l border-slate-300">{fmt(sumBtr('vatRefundAed'))}</td>
				</tr>
				<tr class={DATA_ROW}>
					<td class={TD_L}>Capitalized interest</td>
					{#each btrDevPeriods as period}<td class={TD_OUT}>{period.interestAed > 0 ? fmtOut(period.interestAed) : '—'}</td>{/each}
					<td class="{TD_TOT} sticky right-0 border-l border-slate-300">{fmtOut(sumBtr('interestAed'))}</td>
				</tr>
				<tr class={DATA_ROW}>
					<td class={TD_L}>Financing / exit fees</td>
					{#each btrDevPeriods as period}<td class={TD_OUT}>{period.financingFeeAed + period.exitFeeAed > 0 ? fmtOut(period.financingFeeAed + period.exitFeeAed) : '—'}</td>{/each}
					<td class="{TD_TOT} sticky right-0 border-l border-slate-300">{fmtOut(sumBtr('financingFeeAed') + sumBtr('exitFeeAed'))}</td>
				</tr>
				<tr class="border-t-2 border-[#1F3864] bg-[#E8F0FE]">
					<td class="px-2 py-[4px] text-left text-[10px] font-bold text-slate-900 sticky left-0 bg-[#E8F0FE] z-10 border-r border-slate-200 whitespace-nowrap">TOTAL USES</td>
					{#each btrDevPeriods as period}
						<td class="px-2 py-[4px] text-right text-[10px] tabular-nums font-semibold whitespace-nowrap text-slate-900">
							{fmtOut(period.totalUsesAed)}
						</td>
					{/each}
					<td class="px-2 py-[4px] text-right text-[10px] tabular-nums font-bold sticky right-0 border-l border-slate-300 bg-slate-100 text-slate-900">
						{fmtOut(sumBtr('totalUsesAed'))}
					</td>
				</tr>

				<!-- BTR DEVELOPMENT SOURCES -->
				<tr class={HDR_ROW}>
					<td class="{TD_L_HDR} bg-[#1F3864]">BTR DEVELOPMENT SOURCES</td>
					{#each btrDevPeriods as _}<td class="bg-[#1F3864] min-w-[70px]"></td>{/each}
					<td class="bg-[#1F3864] sticky right-0 border-l border-[#2D4D7A] min-w-[80px]"></td>
				</tr>
				<tr class={DATA_ROW}>
					<td class={TD_L}>Acq. debt draw</td>
					{#each btrDevPeriods as period}<td class={TD}>{period.acqDebtDrawAed > 0 ? fmt(period.acqDebtDrawAed) : '—'}</td>{/each}
					<td class="{TD_TOT} sticky right-0 border-l border-slate-300">{fmt(sumBtr('acqDebtDrawAed'))}</td>
				</tr>
				<tr class={DATA_ROW}>
					<td class={TD_L}>Con. debt draw</td>
					{#each btrDevPeriods as period}<td class={TD}>{period.conDebtDrawAed > 0 ? fmt(period.conDebtDrawAed) : '—'}</td>{/each}
					<td class="{TD_TOT} sticky right-0 border-l border-slate-300">{fmt(sumBtr('conDebtDrawAed'))}</td>
				</tr>
				<tr class={DATA_ROW}>
					<td class={TD_L}>Equity contribution</td>
					{#each btrDevPeriods as period}<td class={TD}>{period.equityContributionAed > 0 ? fmt(period.equityContributionAed) : '—'}</td>{/each}
					<td class="{TD_TOT} sticky right-0 border-l border-slate-300">{fmt(sumBtr('equityContributionAed'))}</td>
				</tr>

				<!-- BTR DEVELOPMENT BALANCES -->
				<tr class={HDR_ROW}>
					<td class="{TD_L_HDR} bg-[#1F3864]">BTR DEVELOPMENT BALANCES</td>
					{#each btrDevPeriods as _}<td class="bg-[#1F3864] min-w-[70px]"></td>{/each}
					<td class="bg-[#1F3864] sticky right-0 border-l border-[#2D4D7A] min-w-[80px]"></td>
				</tr>
				<tr class={DATA_ROW}>
					<td class={TD_L}>Acq. debt balance</td>
					{#each btrDevPeriods as period}<td class={TD}>{period.acqDebtBalanceAed > 0 ? fmt(period.acqDebtBalanceAed) : '—'}</td>{/each}
					<td class="{TD_TOT} sticky right-0 border-l border-slate-300">
						{btrDevPeriods.length ? fmt(btrDevPeriods[btrDevPeriods.length - 1].acqDebtBalanceAed) : '—'}
					</td>
				</tr>
				<tr class={DATA_ROW}>
					<td class={TD_L}>Con. debt balance</td>
					{#each btrDevPeriods as period}<td class={TD}>{period.conDebtBalanceAed > 0 ? fmt(period.conDebtBalanceAed) : '—'}</td>{/each}
					<td class="{TD_TOT} sticky right-0 border-l border-slate-300">
						{btrDevPeriods.length ? fmt(btrDevPeriods[btrDevPeriods.length - 1].conDebtBalanceAed) : '—'}
					</td>
				</tr>
				<tr class="border-b border-[#D9D9D9] bg-slate-50/40">
					<td class={TD_L}>Total dev debt balance</td>
					{#each btrDevPeriods as period}<td class={TD}>{period.devDebtBalanceAed > 0 ? fmt(period.devDebtBalanceAed) : '—'}</td>{/each}
					<td class="{TD_TOT} sticky right-0 border-l border-slate-300">
						{btrDevPeriods.length ? fmt(btrDevPeriods[btrDevPeriods.length - 1].devDebtBalanceAed) : '—'}
					</td>
				</tr>
			</tbody>
		</table>
	</div>
{:else if periods.length === 0}
	<div class="h-full flex items-center justify-center text-sm text-slate-400">
		No cash flow data available.
	</div>
{:else}
	<div class="h-full overflow-auto text-[10px] font-[Calibri,'Segoe_UI',Arial,sans-serif]">
		<table class="border-collapse" style="border-spacing:0">
			<thead class="sticky top-0 z-30">
				<tr class="border-b-2 border-slate-300 bg-white shadow-sm">
					<th class="{TH_L} bg-slate-50">Line Item</th>
					<th class={TH_TOT}>Total</th>
					{#each periods as p}
						<th class={TH}>{p.periodLabel}</th>
					{/each}
				</tr>
			</thead>
			<tbody>

			<!-- REVENUE INFLOWS -->
			<tr class={HDR_ROW}>
				<td class="{TD_L_HDR} bg-[#1F3864]">REVENUE INFLOWS</td>
				<td class="bg-[#1F3864] min-w-[80px]"></td>
				{#each periods as _}<td class="bg-[#1F3864] min-w-[70px]"></td>{/each}
			</tr>
			<tr class={DATA_ROW}>
				<td class={TD_L}>Gross sales receipts</td>
				<td class={TD_TOT}>{fmt(sum('revenueInflowsAed'))}</td>
				{#each periods as p}<td class={TD}>{fmt(p.revenueInflowsAed)}</td>{/each}
			</tr>
			{#if periods.some(p => p.depositInflowsAed > 0)}
			<tr class={SUB_ROW}>
				<td class={TD_L_SUB}>↳ Deposits</td>
				<td class="px-2 py-[2px] text-right text-[9px] tabular-nums text-slate-400 bg-slate-50 border-r border-slate-200">{fmt(sum('depositInflowsAed'))}</td>
				{#each periods as p}<td class="{TD} text-slate-400">{fmt(p.depositInflowsAed)}</td>{/each}
			</tr>
			{/if}
			{#if periods.some(p => p.preHandoverInflowsAed > 0)}
			<tr class={SUB_ROW}>
				<td class={TD_L_SUB}>↳ Pre-handover</td>
				<td class="px-2 py-[2px] text-right text-[9px] tabular-nums text-slate-400 bg-slate-50 border-r border-slate-200">{fmt(sum('preHandoverInflowsAed'))}</td>
				{#each periods as p}<td class="{TD} text-slate-400">{fmt(p.preHandoverInflowsAed)}</td>{/each}
			</tr>
			{/if}
			{#if periods.some(p => p.handoverInflowsAed > 0)}
			<tr class={SUB_ROW}>
				<td class={TD_L_SUB}>↳ At handover</td>
				<td class="px-2 py-[2px] text-right text-[9px] tabular-nums text-slate-400 bg-slate-50 border-r border-slate-200">{fmt(sum('handoverInflowsAed'))}</td>
				{#each periods as p}<td class="{TD} text-slate-400">{fmt(p.handoverInflowsAed)}</td>{/each}
			</tr>
			{/if}
			{#if periods.some(p => (p.vatRefundInflowsAed ?? 0) > 0)}
			<tr class={DATA_ROW}>
				<td class={TD_L}>VAT refund</td>
				<td class={TD_TOT}>{fmt(sum('vatRefundInflowsAed'))}</td>
				{#each periods as p}<td class={TD}>{fmt(p.vatRefundInflowsAed ?? 0)}</td>{/each}
			</tr>
			{/if}
			<!-- Total inflows subtotal -->
			<tr class="border-t-2 border-[#1F3864] bg-[#E8F0FE]">
				<td class="px-2 py-[4px] text-left text-[10px] font-bold text-slate-900 sticky left-0 bg-[#E8F0FE] z-10 border-r border-slate-200 whitespace-nowrap">TOTAL INFLOWS</td>
				<td class="px-2 py-[4px] text-right text-[10px] tabular-nums font-bold text-slate-900 bg-slate-100 border-r border-slate-300 whitespace-nowrap">
					{fmt(sum('revenueInflowsAed') + sum('vatRefundInflowsAed'))}
				</td>
				{#each periods as p}
					<td class="px-2 py-[4px] text-right text-[10px] tabular-nums font-semibold whitespace-nowrap text-slate-900">
						{fmt(p.revenueInflowsAed + (p.vatRefundInflowsAed ?? 0))}
					</td>
				{/each}
			</tr>

			<!-- OPERATING OUTFLOWS -->
			<tr class={HDR_ROW}>
				<td class="{TD_L_HDR} bg-[#1F3864]">OPERATING OUTFLOWS</td>
				<td class="bg-[#1F3864] min-w-[80px]"></td>
				{#each periods as _}<td class="bg-[#1F3864] min-w-[70px]"></td>{/each}
			</tr>
			{#each costBreakdownRows as row (row.field)}
				{#if hasPositive(row.field)}
				<tr class={DATA_ROW}>
					<td class={TD_L}>{row.label}</td>
					<td class={TD_TOT}>{fmtOut(sum(row.field))}</td>
					{#each periods as p}<td class={TD_OUT}>{periodValue(p, row.field) > 0 ? fmtOut(periodValue(p, row.field)) : '—'}</td>{/each}
				</tr>
				{/if}
			{/each}
			<!-- Total outflows subtotal (operating costs + VAT paid — matches UNLEVERED NET CF) -->
			<tr class="border-t-2 border-[#1F3864] bg-[#E8F0FE]">
				<td class="px-2 py-[4px] text-left text-[10px] font-bold text-slate-900 sticky left-0 bg-[#E8F0FE] z-10 border-r border-slate-200 whitespace-nowrap">TOTAL OUTFLOWS</td>
				<td class="px-2 py-[4px] text-right text-[10px] tabular-nums font-bold text-slate-900 bg-slate-100 border-r border-slate-300 whitespace-nowrap">
					{fmtOut(sum('operatingOutflowsAed') + sum('vatPaidAed'))}
				</td>
				{#each periods as p}
					{@const tot = p.operatingOutflowsAed + p.vatPaidAed}
					<td class="px-2 py-[4px] text-right text-[10px] tabular-nums font-semibold whitespace-nowrap text-slate-900">
						{tot > 0 ? fmtOut(tot) : '—'}
					</td>
				{/each}
			</tr>

			<!-- UNLEVERED NET CF -->
			<tr class="border-t border-slate-300 bg-[#D6E4FF]">
				<td class="px-2 py-[4px] text-left text-[10px] font-bold text-slate-900 sticky left-0 bg-[#D6E4FF] z-10 border-r border-slate-200 whitespace-nowrap">UNLEVERED NET CASH FLOW</td>
				<td class="px-2 py-[4px] text-right text-[10px] tabular-nums font-bold bg-slate-100 border-r border-slate-300 whitespace-nowrap text-slate-900">
					{totUnlevered < 0 ? fmtOut(Math.abs(totUnlevered)) : fmt(totUnlevered)}
				</td>
				{#each periods as p}
					<td class="px-2 py-[4px] text-right text-[10px] tabular-nums font-semibold whitespace-nowrap text-slate-900">
						{p.unleveredNetCashFlowAed < 0 ? fmtOut(Math.abs(p.unleveredNetCashFlowAed)) : fmt(p.unleveredNetCashFlowAed)}
					</td>
				{/each}
			</tr>

			<!-- FINANCING -->
			<tr class={HDR_ROW}>
				<td class="{TD_L_HDR} bg-[#1F3864]">FINANCING</td>
				<td class="bg-[#1F3864] min-w-[80px]"></td>
				{#each periods as _}<td class="bg-[#1F3864] min-w-[70px]"></td>{/each}
			</tr>
			{#each financingRows as row (row.field)}
				{#if hasPositive(row.field)}
				<tr class={DATA_ROW}>
					<td class={TD_L}>{row.label}</td>
					<td class={TD_TOT}>{sum(row.field) > 0 ? (row.isOut ? fmtOut(sum(row.field)) : fmt(sum(row.field))) : '—'}</td>
					{#each periods as p}
						<td class={row.isOut ? TD_OUT : TD}>{periodValue(p, row.field) > 0 ? (row.isOut ? fmtOut(periodValue(p, row.field)) : fmt(periodValue(p, row.field))) : '—'}</td>
					{/each}
				</tr>
				{/if}
			{/each}
			<!-- Levered net CF -->
			<tr class="border-t border-slate-300 bg-[#D6E4FF]">
				<td class="px-2 py-[4px] text-left text-[10px] font-bold text-slate-900 sticky left-0 bg-[#D6E4FF] z-10 border-r border-slate-200 whitespace-nowrap">LEVERED (EQUITY) NET CASH FLOW</td>
				<td class="px-2 py-[4px] text-right text-[10px] tabular-nums font-bold bg-slate-100 border-r border-slate-300 whitespace-nowrap text-slate-900">
					{totLevered < 0 ? fmtOut(Math.abs(totLevered)) : fmt(totLevered)}
				</td>
				{#each periods as p}
					<td class="px-2 py-[4px] text-right text-[10px] tabular-nums font-semibold whitespace-nowrap text-slate-900">
						{p.leveredNetCashFlowAed < 0 ? fmtOut(Math.abs(p.leveredNetCashFlowAed)) : fmt(p.leveredNetCashFlowAed)}
					</td>
				{/each}
			</tr>

			<!-- CLOSING BALANCES -->
			<tr class={HDR_ROW}>
				<td class="{TD_L_HDR} bg-[#1F3864]">CLOSING BALANCES</td>
				<td class="bg-[#1F3864] min-w-[80px]"></td>
				{#each periods as _}<td class="bg-[#1F3864] min-w-[70px]"></td>{/each}
			</tr>
			{#each balanceRows as row (row.field)}
			<tr class={DATA_ROW}>
				<td class={TD_L}>{row.label}</td>
				<td class="px-2 py-[3px] text-right text-[9px] tabular-nums text-slate-400 bg-slate-50 border-r border-slate-200 whitespace-nowrap italic">closing</td>
				{#each periods as p}<td class={TD}>{fmt(periodValue(p, row.field))}</td>{/each}
			</tr>
			{/each}

			<!-- SOURCES OF FUNDS -->
			<tr class={HDR_ROW}>
				<td class="{TD_L_HDR} bg-[#1F3864]">SOURCES OF FUNDS</td>
				<td class="bg-[#1F3864] min-w-[80px]"></td>
				{#each periods as _}<td class="bg-[#1F3864] min-w-[70px]"></td>{/each}
			</tr>
			<tr class={DATA_ROW}>
				<td class={TD_L}>Off-plan proceeds</td>
				<td class={TD_TOT}>{fmt(sum('revenueInflowsAed'))}</td>
				{#each periods as p}<td class={TD}>{fmt(p.revenueInflowsAed)}</td>{/each}
			</tr>
			{#if hasPositive('vatRefundInflowsAed')}
			<tr class={DATA_ROW}>
				<td class={TD_L}>VAT refunds</td>
				<td class={TD_TOT}>{fmt(sum('vatRefundInflowsAed'))}</td>
				{#each periods as p}<td class={TD}>{fmt(p.vatRefundInflowsAed ?? 0)}</td>{/each}
			</tr>
			{/if}
			{#if hasPositive('acqDebtDrawAed')}
			<tr class={DATA_ROW}>
				<td class={TD_L}>Acquisition debt drawn</td>
				<td class={TD_TOT}>{fmt(sum('acqDebtDrawAed'))}</td>
				{#each periods as p}<td class={TD}>{fmt(p.acqDebtDrawAed)}</td>{/each}
			</tr>
			{/if}
			{#if hasPositive('conDebtDrawAed')}
			<tr class={DATA_ROW}>
				<td class={TD_L}>Construction debt drawn</td>
				<td class={TD_TOT}>{fmt(sum('conDebtDrawAed'))}</td>
				{#each periods as p}<td class={TD}>{fmt(p.conDebtDrawAed)}</td>{/each}
			</tr>
			{/if}
			<tr class={DATA_ROW}>
				<td class={TD_L}>Equity contributed</td>
				<td class={TD_TOT}>{fmt(sum('equityContributionAed'))}</td>
				{#each periods as p}<td class={TD}>{fmt(p.equityContributionAed)}</td>{/each}
			</tr>
			<!-- Total Sources -->
			<tr class="border-t-2 border-[#1F3864] bg-[#E8F0FE]">
				<td class="px-2 py-[4px] text-left text-[10px] font-bold text-slate-900 sticky left-0 bg-[#E8F0FE] z-10 border-r border-slate-200 whitespace-nowrap">Total Sources</td>
				<td class="px-2 py-[4px] text-right text-[10px] tabular-nums font-bold bg-slate-100 border-r border-slate-300 text-slate-900 whitespace-nowrap">
					{fmt(periods.reduce((s, p) => s + periodSources(p), 0))}
				</td>
				{#each periods as p}
					<td class="px-2 py-[4px] text-right text-[10px] tabular-nums font-semibold whitespace-nowrap text-slate-900">{fmt(periodSources(p))}</td>
				{/each}
			</tr>
			<!-- Total Uses -->
			<tr class="border-t border-slate-200 bg-slate-50/40">
				<td class="px-2 py-[3px] text-left text-[10px] italic text-slate-500 sticky left-0 bg-slate-50/40 z-10 border-r border-slate-200 whitespace-nowrap">Total Uses</td>
				<td class="px-2 py-[3px] text-right text-[9px] tabular-nums italic text-slate-500 bg-slate-50 border-r border-slate-200 whitespace-nowrap">
					{fmtOut(periods.reduce((s, p) => s + periodUses(p), 0))}
				</td>
				{#each periods as p}
					<td class="px-2 py-[3px] text-right text-[10px] tabular-nums italic text-slate-500 whitespace-nowrap">{periodUses(p) > 0 ? fmtOut(periodUses(p)) : '—'}</td>
				{/each}
			</tr>
			<!-- Funding gap -->
			<tr class="border-t border-slate-200">
				<td class="px-2 py-[3px] text-left text-[10px] font-semibold text-slate-700 sticky left-0 bg-white z-10 border-r border-slate-200 whitespace-nowrap">Funding Gap</td>
				<td class="px-2 py-[3px] text-right text-[9px] tabular-nums font-semibold bg-slate-50 border-r border-slate-200 text-slate-700 whitespace-nowrap">0</td>
				{#each periods as p}
					{@const bal = periodSources(p) - periodUses(p)}
					<td class="px-2 py-[3px] text-right text-[10px] tabular-nums font-semibold whitespace-nowrap {Math.abs(bal) < 1 ? 'text-slate-700' : 'text-rose-600'}">
						{Math.abs(bal) < 1 ? '—' : fmt(bal)}
					</td>
				{/each}
			</tr>

			<!-- MONTHLY SOURCE ALLOCATION -->
			<tr class={HDR_ROW}>
				<td class="{TD_L_HDR} bg-[#1F3864]">MONTHLY SOURCE ALLOCATION</td>
				<td class="bg-[#1F3864] min-w-[80px]"></td>
				{#each periods as _}<td class="bg-[#1F3864] min-w-[70px]"></td>{/each}
			</tr>
			<tr class={DATA_ROW}>
				<td class={TD_L}>Total outflows to fund</td>
				<td class={TD_TOT}>{fmtOut(periodAllocs.reduce((s, a) => s + a.totalOutflow, 0))}</td>
				{#each periodAllocs as a}<td class={TD_OUT}>{a.totalOutflow > 0 ? fmtOut(a.totalOutflow) : '—'}</td>{/each}
			</tr>
			<tr class={DATA_ROW}>
				<td class={TD_L}>Funded by: off-plan proceeds & VAT refund</td>
				<td class={TD_TOT}>{fmt(periodAllocs.reduce((s, a) => s + a.proceedsAlloc, 0))}</td>
				{#each periodAllocs as a}<td class={TD}>{a.proceedsAlloc > 0 ? fmt(a.proceedsAlloc) : '—'}</td>{/each}
			</tr>
			{#if periodAllocs.some(a => a.acqDebtAlloc > 0)}
			<tr class={DATA_ROW}>
				<td class={TD_L}>Funded by: acquisition debt</td>
				<td class={TD_TOT}>{fmt(periodAllocs.reduce((s, a) => s + a.acqDebtAlloc, 0))}</td>
				{#each periodAllocs as a}<td class={TD}>{a.acqDebtAlloc > 0 ? fmt(a.acqDebtAlloc) : '—'}</td>{/each}
			</tr>
			{/if}
			{#if periodAllocs.some(a => a.conDebtAlloc > 0)}
			<tr class={DATA_ROW}>
				<td class={TD_L}>Funded by: construction debt</td>
				<td class={TD_TOT}>{fmt(periodAllocs.reduce((s, a) => s + a.conDebtAlloc, 0))}</td>
				{#each periodAllocs as a}<td class={TD}>{a.conDebtAlloc > 0 ? fmt(a.conDebtAlloc) : '—'}</td>{/each}
			</tr>
			{/if}
			<tr class={DATA_ROW}>
				<td class={TD_L}>Funded by: sponsor equity</td>
				<td class={TD_TOT}>{fmt(periodAllocs.reduce((s, a) => s + a.equityAlloc, 0))}</td>
				{#each periodAllocs as a}<td class={TD}>{a.equityAlloc > 0 ? fmt(a.equityAlloc) : '—'}</td>{/each}
			</tr>
			<tr class="border-t border-slate-200">
				<td class="px-2 py-[3px] text-left text-[10px] font-semibold text-slate-700 sticky left-0 bg-white z-10 border-r border-slate-200 whitespace-nowrap">Allocation Gap</td>
				<td class="px-2 py-[3px] text-right text-[9px] tabular-nums font-semibold bg-slate-50 border-r border-slate-200 text-slate-700 whitespace-nowrap">0</td>
				{#each periodAllocs as a}
					{@const chk = round(a.proceedsAlloc + a.acqDebtAlloc + a.conDebtAlloc + a.equityAlloc - a.totalOutflow)}
					<td class="px-2 py-[3px] text-right text-[10px] tabular-nums font-semibold whitespace-nowrap {Math.abs(chk) < 1 ? 'text-slate-700' : 'text-rose-600'}">
						{Math.abs(chk) < 1 ? '—' : fmt(chk)}
					</td>
				{/each}
			</tr>

			<!-- CUMULATIVE SOURCE BALANCES -->
			<tr class={HDR_ROW}>
				<td class="{TD_L_HDR} bg-[#1F3864]">CUMULATIVE SOURCE BALANCES</td>
				<td class="bg-[#1F3864] min-w-[80px]"></td>
				{#each periods as _}<td class="bg-[#1F3864] min-w-[70px]"></td>{/each}
			</tr>
			<tr class={DATA_ROW}>
				<td class={TD_L}>Proceeds allocated (cumul.)</td>
				<td class={TD_TOT}>{fmt(cumulativeProceeds[cumulativeProceeds.length - 1] ?? 0)}</td>
				{#each periods as _, i}<td class={TD}>{fmt(cumulativeProceeds[i] ?? 0)}</td>{/each}
			</tr>
			{#if periodAllocs.some(a => a.acqDebtAlloc > 0)}
			<tr class={DATA_ROW}>
				<td class={TD_L}>Acq. debt allocated (cumul.)</td>
				<td class={TD_TOT}>{fmt(cumulativeAcqDebt[cumulativeAcqDebt.length - 1] ?? 0)}</td>
				{#each periods as _, i}<td class={TD}>{fmt(cumulativeAcqDebt[i] ?? 0)}</td>{/each}
			</tr>
			{/if}
			{#if periodAllocs.some(a => a.conDebtAlloc > 0)}
			<tr class={DATA_ROW}>
				<td class={TD_L}>Con. debt allocated (cumul.)</td>
				<td class={TD_TOT}>{fmt(cumulativeConDebt[cumulativeConDebt.length - 1] ?? 0)}</td>
				{#each periods as _, i}<td class={TD}>{fmt(cumulativeConDebt[i] ?? 0)}</td>{/each}
			</tr>
			{/if}
			<tr class={DATA_ROW}>
				<td class={TD_L}>Equity allocated (cumul.)</td>
				<td class={TD_TOT}>{fmt(cumulativeEquity[cumulativeEquity.length - 1] ?? 0)}</td>
				{#each periods as _, i}<td class={TD}>{fmt(cumulativeEquity[i] ?? 0)}</td>{/each}
			</tr>

			<tr><td colspan={periods.length + 2} class="py-3"></td></tr>
			</tbody>
		</table>
	</div>
{/if}
