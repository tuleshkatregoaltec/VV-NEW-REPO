<script lang="ts">
import { workbookStore } from '$lib/feasibility/workbook/store.svelte'

function fmt(value: number | null | undefined, digits = 0) {
	if (value === null || value === undefined || !Number.isFinite(value)) return '0'
	return value.toLocaleString('en-AE', {
		minimumFractionDigits: digits,
		maximumFractionDigits: digits
	})
}

function fmtPct(value: number | null | undefined, digits = 1) {
	if (value === null || value === undefined || !Number.isFinite(value)) return '—'
	return `${fmt(value, digits)}%`
}

const workbook = $derived(workbookStore.workbook ?? null)
const assumptions = $derived(workbookStore.assumptions)
const isBtr = $derived(assumptions?.developmentModel === 'build_to_rent_residential')
const btr = $derived(workbook?.btr)
const btrPermDebtAllInRate = $derived(
	(assumptions?.eiborRatePct ?? 0) + (assumptions?.btrPermDebtSpreadBps ?? 165) / 100
)
const draftFinancing = $derived(workbook?.financing ?? null)
const sourcesUses = $derived(workbook?.sourcesUses ?? null)
const validation = $derived(workbookStore.validation ?? null)
const cashFlowPeriods = $derived(workbook?.cashFlow?.periods ?? [])

function issuePresent(code: string) {
	return (validation?.issues ?? []).some((issue) => issue.code === code)
}

type TestStatus = 'pass' | 'warning' | 'fail' | 'missing'

function pill(status: TestStatus) {
	if (status === 'fail') return 'bg-rose-100 text-rose-700'
	if (status === 'warning') return 'bg-amber-100 text-amber-700'
	if (status === 'missing') return 'bg-slate-200 text-slate-600'
	return 'bg-slate-100 text-slate-700'
}

function statusLabel(status: TestStatus) {
	if (status === 'fail') return 'Shortfall'
	if (status === 'warning') return 'Watch'
	if (status === 'missing') return '—'
	return 'Met'
}

const peakPeriod = $derived.by(() => {
	if (!cashFlowPeriods.length) return null
	return cashFlowPeriods.reduce((maxPeriod, period) =>
		period.debtBalanceAed > maxPeriod.debtBalanceAed ? period : maxPeriod
	)
})

const peakAcqPeriod = $derived.by(() => {
	if (!cashFlowPeriods.length) return null
	return cashFlowPeriods.reduce((max, p) =>
		(p.closingAcqDebtAed ?? 0) > (max.closingAcqDebtAed ?? 0) ? p : max
	)
})

const peakConPeriod = $derived.by(() => {
	if (!cashFlowPeriods.length) return null
	return cashFlowPeriods.reduce((max, p) =>
		(p.closingConDebtAed ?? 0) > (max.closingConDebtAed ?? 0) ? p : max
	)
})

const firstSweepPeriod = $derived.by(() => {
	return (
		cashFlowPeriods.find((period) => period.debtRepaymentAed > 0 && period.revenueInflowsAed > 0) ??
		null
	)
})

const facilityLines = $derived([
	{
		label: 'Acquisition tranche',
		source: sourcesUses?.sources.find((item) => item.code === 'land_loan') ?? null,
		peakBalance: peakAcqPeriod?.closingAcqDebtAed ?? 0,
		peakPeriodLabel: peakAcqPeriod?.periodLabel ?? '—',
		assumption: null
	},
	{
		label: 'Construction tranche',
		source: sourcesUses?.sources.find((item) => item.code === 'construction_loan') ?? null,
		peakBalance: peakConPeriod?.closingConDebtAed ?? 0,
		peakPeriodLabel: peakConPeriod?.periodLabel ?? '—',
		assumption: null
	}
])

const lenderTests = $derived([
	{
		label: 'Presale threshold',
		value: draftFinancing
			? `${fmt(draftFinancing.presaleCoveragePctAtConstruction, 1)}% covered`
			: '—',
		target: 'No threshold',
		status: !draftFinancing
			? 'missing'
			: draftFinancing.presaleCoveragePctAtConstruction < 100
				? 'warning'
				: 'pass',
		note: 'Presales at construction start.'
	},
	{
		label: 'Debt utilization',
		value: draftFinancing ? `${fmt(draftFinancing.debtCommitmentUtilizationPct, 1)}%` : '—',
		target: draftFinancing ? 'Within committed facilities' : '—',
		status: !draftFinancing
			? 'missing'
			: draftFinancing.debtCommitmentUtilizationPct > 100 ||
					issuePresent('peak_debt_exceeds_facility')
				? 'fail'
				: draftFinancing.debtCommitmentUtilizationPct > 95
					? 'warning'
					: 'pass',
		note: 'Peak debt / commitment.'
	},
	{
		label: 'Minimum debt headroom',
		value: draftFinancing ? `AED ${fmt(draftFinancing.minDebtHeadroomAed)}` : '—',
		target: 'Positive headroom through draw period',
		status: !draftFinancing
			? 'missing'
			: draftFinancing.minDebtHeadroomAed < 0 || issuePresent('peak_debt_exceeds_facility')
				? 'fail'
				: draftFinancing.minDebtHeadroomAed < 5_000_000
					? 'warning'
					: 'pass',
		note: 'Lowest residual facility capacity.'
	},
	{
		label: 'Completion reserve',
		value: draftFinancing ? `${fmt(draftFinancing.completionReserveCoveragePct, 1)}%` : '—',
		target: 'At least 100% covered before sponsor release',
		status: !draftFinancing
			? 'missing'
			: draftFinancing.completionReserveCoveragePct < 100 ||
					issuePresent('completion_reserve_underfunded')
				? 'fail'
				: draftFinancing.completionReserveCoveragePct < 110
					? 'warning'
					: 'pass',
		note: 'Terminal escrow / reserve requirement.'
	},
	{
		label: 'Terminal debt',
		value: draftFinancing ? `AED ${fmt(draftFinancing.closingDebtBalanceAed)}` : '—',
		target: 'Zero residual balance',
		status: !draftFinancing
			? 'missing'
			: draftFinancing.closingDebtBalanceAed > 0 || issuePresent('debt_balance_at_exit')
				? 'warning'
				: 'pass',
		note: 'Debt balance after handover.'
	},
	{
		label: 'Debt roll-forward',
		value: peakPeriod ? `Peak in ${peakPeriod.periodLabel}` : '—',
		target: 'Opening + draw + carry - repayment',
		status: !draftFinancing
			? 'missing'
			: issuePresent('debt_rollforward_mismatch')
				? 'fail'
				: 'pass',
		note: 'Draws, interest carry, and repayments.'
	}
] satisfies Array<{
	label: string
	value: string
	target: string
	status: TestStatus
	note: string
}>)
</script>

{#if isBtr && btr}
	<!-- ═══ BTR FINANCING VIEW ═══ -->
	<div class="overflow-auto flex-1 bg-white text-[11px] font-[Calibri,'Segoe_UI',Arial,sans-serif] select-none">

		<!-- Title bar -->
		<div class="bg-[#1F3864] border-b-2 border-[#1F3864] text-white px-4 py-2.5">
			<div class="text-[13px] font-bold tracking-wide">BTR FINANCING &amp; CAPITAL STRUCTURE</div>
		</div>

		<!-- Summary bar -->
		<div class="grid grid-cols-5 border-b border-[#B8C4CE] bg-[#EEF2F7]">
			<div class="px-3 py-2 border-r border-[#D9D9D9]">
				<div class="text-[9px] uppercase tracking-wider text-slate-500 font-semibold">Dev Debt</div>
				<div class="text-[13px] font-bold text-slate-900 tabular-nums mt-0.5">AED {fmt(btr.returns.devDebtFundedAed)}</div>
			</div>
			<div class="px-3 py-2 border-r border-[#D9D9D9]">
				<div class="text-[9px] uppercase tracking-wider text-slate-500 font-semibold">Dev Equity</div>
				<div class="text-[13px] font-bold text-slate-900 tabular-nums mt-0.5">AED {fmt(btr.returns.devEquityFundedAed)}</div>
			</div>
			<div class="px-3 py-2 border-r border-[#D9D9D9]">
				<div class="text-[9px] uppercase tracking-wider text-slate-500 font-semibold">Perm Loan (Refi)</div>
				<div class="text-[13px] font-bold text-slate-900 tabular-nums mt-0.5">AED {fmt(btr.permDebt.actualPermDebtAed)}</div>
			</div>
			<div class="px-3 py-2 border-r border-[#D9D9D9]">
				<div class="text-[9px] uppercase tracking-wider text-slate-500 font-semibold">DSCR</div>
				<div class="text-[13px] font-bold tabular-nums mt-0.5 {btr.permDebt.dscrAtOrigination >= (assumptions?.btrDscrMinimum ?? 1.25) ? 'text-slate-900' : 'text-amber-700'}">{fmt(btr.permDebt.dscrAtOrigination, 2)}x</div>
			</div>
			<div class="px-3 py-2">
				<div class="text-[9px] uppercase tracking-wider text-slate-500 font-semibold">Debt Yield</div>
				<div class="text-[13px] font-bold text-slate-900 tabular-nums mt-0.5">{fmtPct(btr.permDebt.debtYieldPct)}</div>
			</div>
		</div>

		<table class="w-full border-collapse" style="border-spacing:0">
			<tbody>

			<!-- Section A: Development Sources & Uses -->
			<tr class="bg-[#1F3864]">
				<td colspan="3" class="px-2 py-[4px] text-white font-bold text-[11px] tracking-wide">A.&nbsp;&nbsp;DEVELOPMENT SOURCES &amp; USES</td>
			</tr>
			<tr class="bg-[#D6DCE4] border-b border-[#B8C4CE]">
				<th class="px-2 py-[4px] text-left text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Line Item</th>
				<th class="px-2 py-[4px] text-right text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Amount (AED)</th>
				<th class="px-2 py-[4px] text-left text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Note</th>
			</tr>
			<!-- Uses -->
			<tr class="bg-slate-50/80 border-b border-[#D9D9D9]">
				<td class="px-2 py-[3px] text-left text-[10px] text-amber-700 font-semibold uppercase tracking-wider text-[9px]" colspan="3">Uses</td>
			</tr>
			{#each [
				{ label: 'Land Acquisition', amount: btr.devCosts.landAcquisitionAed },
				{ label: 'Land Transfer Fee', amount: btr.devCosts.landTransferFeeAed },
				{ label: 'Brokerage', amount: btr.devCosts.brokerageFeeAed },
				{ label: 'Legal / DD', amount: btr.devCosts.legalDdCostAed },
				{ label: 'Permit / Authority Fees', amount: btr.devCosts.permitFeesAed },
				{ label: 'Hard Costs (Construction)', amount: btr.devCosts.hardCostAed },
				{ label: 'Soft Costs', amount: btr.devCosts.softCostAed },
				{ label: 'Contingency', amount: btr.devCosts.contingencyCostAed },
				{ label: 'Lease-Up Marketing', amount: btr.devCosts.leaseUpMarketingAed },
				{ label: 'VAT', amount: btr.devCosts.totalVatAed },
			] as row (row.label)}
				<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
					<td class="px-2 py-[3px] text-left text-[10px] text-slate-800 pl-4">{row.label}</td>
					<td class="px-2 py-[3px] text-right tabular-nums text-[10px] text-slate-900">AED {fmt(row.amount)}</td>
					<td class="px-2 py-[3px]"></td>
				</tr>
			{/each}
			<tr class="border-t-2 border-[#B8C4CE] bg-[#EEF2F7] font-semibold">
				<td class="px-2 py-[4px] text-left text-[10px] text-slate-900">Total Development Cost</td>
				<td class="px-2 py-[4px] text-right tabular-nums text-[10px] text-slate-900 font-bold">AED {fmt(btr.devCosts.totalDevCostInclVatAed)}</td>
				<td class="px-2 py-[4px] text-left text-[9px] text-slate-500">Incl. VAT</td>
			</tr>
			<!-- Sources -->
			<tr class="bg-slate-50/80 border-b border-[#D9D9D9]">
				<td class="px-2 py-[3px] text-left text-[10px] text-slate-700 font-semibold uppercase tracking-wider text-[9px]" colspan="3">Sources</td>
			</tr>
			<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
				<td class="px-2 py-[3px] text-left text-[10px] text-slate-800 pl-4">Dev Debt (LTC-based)</td>
				<td class="px-2 py-[3px] text-right tabular-nums text-[10px] text-slate-900">AED {fmt(btr.returns.devDebtFundedAed)}</td>
				<td class="px-2 py-[3px] text-left text-[9px] text-slate-500">{fmtPct((assumptions?.constructionDebtLtc ?? 0.7) * 100, 0)} LTC</td>
			</tr>
			<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
				<td class="px-2 py-[3px] text-left text-[10px] text-slate-800 pl-4">Dev Equity</td>
				<td class="px-2 py-[3px] text-right tabular-nums text-[10px] text-slate-900">AED {fmt(btr.returns.devEquityFundedAed)}</td>
				<td class="px-2 py-[3px] text-left text-[9px] text-slate-500">Residual after debt</td>
			</tr>
			<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
				<td class="px-2 py-[3px] text-left text-[10px] text-slate-800 pl-4">Dev Interest Reserve</td>
				<td class="px-2 py-[3px] text-right tabular-nums text-[10px] text-slate-900">AED {fmt(btr.returns.devInterestReserveAed)}</td>
				<td class="px-2 py-[3px] text-left text-[9px] text-slate-500">Capitalized interest during construction</td>
			</tr>

			<!-- Section B: Refinance Event -->
			<tr class="bg-[#1F3864]">
				<td colspan="3" class="px-2 py-[4px] text-white font-bold text-[11px] tracking-wide">B.&nbsp;&nbsp;REFINANCE AT STABILIZATION (YEAR {btr.stabilizationYear})</td>
			</tr>
			<tr class="bg-[#D6DCE4] border-b border-[#B8C4CE]">
				<th class="px-2 py-[4px] text-left text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Line Item</th>
				<th class="px-2 py-[4px] text-right text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Amount (AED)</th>
				<th class="px-2 py-[4px] text-left text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Note</th>
			</tr>
			{#each [
				{ label: 'Stabilized Value', amount: btr.permDebt.stabilizedValueAed, note: 'Stabilized NOI / Cap Rate' },
				{ label: 'Max Perm Debt (LTV)', amount: btr.permDebt.maxPermDebtAed, note: `${fmtPct(assumptions?.btrPermDebtLtvPct ?? 65)} LTV` },
				{ label: 'Actual Perm Debt', amount: btr.permDebt.actualPermDebtAed, note: btr.permDebt.dscrConstrained ? 'DSCR constrained' : 'LTV constrained' },
				{ label: 'Refi Points / Fees', amount: -btr.permDebt.refiPointsCostAed, note: `${fmtPct(assumptions?.btrPermDebtPointsPct ?? 1)} of perm loan` },
				{ label: 'Dev Debt Payoff', amount: -btr.returns.devDebtFundedAed, note: 'Full repayment of dev facility' },
			] as row (row.label)}
				<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
					<td class="px-2 py-[3px] text-left text-[10px] text-slate-800">{row.label}</td>
					<td class="px-2 py-[3px] text-right tabular-nums text-[10px] text-slate-900 font-medium">AED {fmt(row.amount)}</td>
					<td class="px-2 py-[3px] text-left text-[9px] text-slate-500">{row.note}</td>
				</tr>
			{/each}
			<tr class="border-t-2 border-[#B8C4CE] bg-[#EEF2F7] font-semibold">
				<td class="px-2 py-[4px] text-left text-[10px] text-slate-900">Net Refi Proceeds</td>
				<td class="px-2 py-[4px] text-right tabular-nums text-[10px] font-bold {btr.permDebt.refiProceedsAed >= 0 ? 'text-slate-900' : 'text-amber-700'}">AED {fmt(btr.permDebt.refiProceedsAed)}</td>
				<td class="px-2 py-[4px] text-left text-[9px] text-slate-500">{btr.permDebt.refiProceedsAed >= 0 ? 'Distributed to equity' : 'Additional equity call required'}</td>
			</tr>

			<!-- Section C: Permanent Debt Service -->
			<tr class="bg-[#1F3864]">
				<td colspan="3" class="px-2 py-[4px] text-white font-bold text-[11px] tracking-wide">C.&nbsp;&nbsp;PERMANENT DEBT SERVICE</td>
			</tr>
			<tr class="bg-[#D6DCE4] border-b border-[#B8C4CE]">
				<th class="px-2 py-[4px] text-left text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Metric</th>
				<th class="px-2 py-[4px] text-right text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Value</th>
				<th class="px-2 py-[4px] text-left text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Note</th>
			</tr>
			{#each [
				{ label: 'All-In Rate', value: fmtPct(btrPermDebtAllInRate), note: `EIBOR + ${fmt(assumptions?.btrPermDebtSpreadBps ?? 165, 0)} bps perm spread` },
				{ label: 'Amortization', value: `${assumptions?.btrPermDebtAmortYears ?? 25} years`, note: `I/O period: ${assumptions?.btrPermDebtIoYears ?? 1} year(s)` },
				{ label: 'Annual Debt Service', value: `AED ${fmt(btr.permDebt.annualDebtServiceAed)}`, note: 'P&I payment' },
				{ label: 'DSCR at Origination', value: `${fmt(btr.permDebt.dscrAtOrigination, 2)}x`, note: `Min: ${fmt(assumptions?.btrDscrMinimum ?? 1.25, 2)}x` },
				{ label: 'Debt Yield', value: fmtPct(btr.permDebt.debtYieldPct), note: 'NOI / Perm Debt' },
				{ label: 'Loan Payoff at Exit', value: `AED ${fmt(btr.permDebt.loanPayoffAed)}`, note: `Remaining balance after ${assumptions?.btrHoldPeriodYears ?? 10} year hold` },
			] as row (row.label)}
				<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
					<td class="px-2 py-[3px] text-left text-[10px] text-slate-800">{row.label}</td>
					<td class="px-2 py-[3px] text-right tabular-nums text-[10px] font-medium {row.label === 'DSCR at Origination' ? (btr.permDebt.dscrAtOrigination >= (assumptions?.btrDscrMinimum ?? 1.25) ? 'text-slate-900' : 'text-amber-700') : 'text-slate-900'}">{row.value}</td>
					<td class="px-2 py-[3px] text-left text-[9px] text-slate-500">{row.note}</td>
				</tr>
			{/each}

			</tbody>
		</table>

		<div class="py-3"></div>
	</div>
{:else if !draftFinancing}
	<div class="h-full flex items-center justify-center text-sm text-slate-400">
		No financing data available.
	</div>
{:else}
	<div class="overflow-auto flex-1 bg-white text-[11px] font-[Calibri,'Segoe_UI',Arial,sans-serif] select-none">

		<!-- Title bar -->
		<div class="bg-[#1F3864] border-b-2 border-[#1F3864] text-white px-4 py-2.5">
			<div class="text-[13px] font-bold tracking-wide">FINANCING &amp; DEBT STRUCTURE</div>
		</div>

		<!-- Summary bar -->
		<div class="flex border-b border-[#B8C4CE] bg-[#EEF2F7] divide-x divide-[#D9D9D9]">
			<div class="px-2 py-1.5 flex-1">
				<div class="text-[9px] uppercase tracking-wider text-slate-500 font-semibold">Debt Commitment</div>
				<div class="text-[11px] font-bold text-slate-900 tabular-nums">{fmt(draftFinancing.debtCommitmentAed)} <span class="text-slate-400 font-normal">({fmt(draftFinancing.debtCommitmentUtilizationPct, 1)}% util.)</span></div>
			</div>
			<div class="px-2 py-1.5 flex-1">
				<div class="text-[9px] uppercase tracking-wider text-slate-500 font-semibold">Peak Debt</div>
				<div class="text-[11px] font-bold text-slate-900 tabular-nums">{fmt(draftFinancing.peakDebtAed)} <span class="text-slate-400 font-normal">{peakPeriod ? `M${peakPeriod.periodLabel}` : ''}</span></div>
			</div>
			<div class="px-2 py-1.5 flex-1">
				<div class="text-[9px] uppercase tracking-wider text-slate-500 font-semibold">Headroom / Terminal</div>
				<div class="text-[11px] font-bold text-slate-900 tabular-nums">{fmt(draftFinancing.minDebtHeadroomAed)} / {fmt(draftFinancing.closingDebtBalanceAed)}</div>
			</div>
			<div class="px-2 py-1.5 flex-1">
				<div class="text-[9px] uppercase tracking-wider text-slate-500 font-semibold">Completion Reserve</div>
				<div class="text-[11px] font-bold text-slate-900 tabular-nums">{fmt(draftFinancing.completionReserveCoveragePct, 1)}% <span class="text-slate-400 font-normal">Req. {fmt(draftFinancing.requiredCompletionReserveAed)}</span></div>
			</div>
		</div>

		<table class="w-full border-collapse" style="border-spacing:0">
			<tbody>

			<!-- Section A: Facility Structure -->
			<tr class="bg-[#1F3864]">
				<td colspan="5" class="px-2 py-[4px] text-white font-bold text-[11px] tracking-wide">A.&nbsp;&nbsp;FACILITY STRUCTURE</td>
			</tr>
			<tr class="bg-[#D6DCE4] border-b border-[#B8C4CE]">
				<th class="px-2 py-[4px] text-left text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Facility</th>
				<th class="px-2 py-[4px] text-right text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Commitment (AED)</th>
				<th class="px-2 py-[4px] text-right text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Peak Balance (AED)</th>
				<th class="px-2 py-[4px] text-right text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Peak Month</th>
				<th class="px-2 py-[4px] text-left text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Basis</th>
			</tr>
			{#each facilityLines as row (row.label)}
				<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
					<td class="px-2 py-[3px] text-left text-[10px] text-slate-800 font-semibold">{row.label}</td>
					<td class="px-2 py-[3px] text-right tabular-nums text-slate-900 text-[10px]">{row.source ? fmt(row.source.amountAed) : '—'}</td>
					<td class="px-2 py-[3px] text-right tabular-nums text-slate-900 text-[10px]">{fmt(row.peakBalance)}</td>
					<td class="px-2 py-[3px] text-right tabular-nums text-slate-500 text-[10px]">{row.peakPeriodLabel}</td>
					<td class="px-2 py-[3px] text-left text-[9px] text-slate-500">
						{row.source?.basis ?? '—'}
					</td>
				</tr>
			{/each}

			<!-- Section B: Credit Metrics -->
			<tr class="bg-[#1F3864]">
				<td colspan="5" class="px-2 py-[4px] text-white font-bold text-[11px] tracking-wide">B.&nbsp;&nbsp;CREDIT METRICS</td>
			</tr>
			<tr class="bg-[#D6DCE4] border-b border-[#B8C4CE]">
				<th class="px-1 py-[4px] text-center text-[9px] font-semibold text-slate-500 uppercase tracking-wider">#</th>
				<th class="px-2 py-[4px] text-left text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Test</th>
				<th class="px-2 py-[4px] text-right text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Current / Target</th>
				<th class="px-2 py-[4px] text-right text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Position</th>
				<th class="px-2 py-[4px] text-left text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Basis</th>
			</tr>
			{#each lenderTests as test, idx (test.label)}
				<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
					<td class="px-1 py-[3px] text-center text-[9px] text-slate-400">{idx + 1}</td>
					<td class="px-2 py-[3px] text-left text-[10px] text-slate-800">{test.label}</td>
					<td class="px-2 py-[3px] text-right tabular-nums text-[10px] text-slate-900">
						{test.value}<br /><span class="text-slate-400 text-[9px]">{test.target}</span>
					</td>
					<td class="px-2 py-[3px] text-right">
						<span class="inline-block px-2 py-0.5 text-[9px] font-semibold uppercase rounded-sm {pill(test.status)}">{statusLabel(test.status)}</span>
					</td>
					<td class="px-2 py-[3px] text-left text-[9px] text-slate-500">{test.note}</td>
				</tr>
			{/each}

			<!-- Section C: Financing Costs -->
			<tr class="bg-[#1F3864]">
				<td colspan="5" class="px-2 py-[4px] text-white font-bold text-[11px] tracking-wide">C.&nbsp;&nbsp;FINANCING COSTS</td>
			</tr>
			<tr class="bg-[#D6DCE4] border-b border-[#B8C4CE]">
				<th colspan="2" class="px-2 py-[4px] text-left text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Line Item</th>
				<th colspan="3" class="px-2 py-[4px] text-right text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Amount (AED)</th>
			</tr>
			{#each [
				{ label: 'Financing Fee', amount: workbook?.returns?.financingFeeAed ?? 0 },
				{ label: 'Exit Fee', amount: workbook?.returns?.exitFeeAed ?? 0 },
				{ label: 'Total Interest', amount: workbook?.returns?.totalInterestPaidAed ?? 0 },
				{ label: 'Total Financing Costs', amount: workbook?.returns?.totalFinancingCostsAed ?? 0 },
			] as row (row.label)}
				<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
					<td colspan="2" class="px-2 py-[3px] text-left text-[10px] text-slate-800">{row.label}</td>
					<td colspan="3" class="px-2 py-[3px] text-right tabular-nums text-slate-900 text-[10px]">AED {fmt(row.amount)}</td>
				</tr>
			{/each}

			<!-- Section D: Reserve & Release -->
			<tr class="bg-[#1F3864]">
				<td colspan="5" class="px-2 py-[4px] text-white font-bold text-[11px] tracking-wide">D.&nbsp;&nbsp;RESERVE &amp; RELEASE</td>
			</tr>
			<tr class="bg-[#D6DCE4] border-b border-[#B8C4CE]">
				<th class="px-1 py-[4px] text-center text-[9px] font-semibold text-slate-500 uppercase tracking-wider">#</th>
				<th colspan="2" class="px-2 py-[4px] text-left text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Line Item</th>
				<th class="px-2 py-[4px] text-right text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Amount (AED)</th>
				<th class="px-2 py-[4px] text-left text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Basis</th>
			</tr>
			{#each [
				{ label: 'Required completion reserve', amount: draftFinancing.requiredCompletionReserveAed, basis: 'Terminal reserve before sponsor release' },
				{ label: 'Sponsor release capacity', amount: draftFinancing.sponsorReleaseCapacityAed, basis: 'Escrow available above required reserve' },
				{ label: 'Closing escrow balance', amount: draftFinancing.closingEscrowBalanceAed, basis: 'Terminal escrow after debt and equity flows' },
			] as row, idx (row.label)}
				<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
					<td class="px-1 py-[3px] text-center text-[9px] text-slate-400">{idx + 1}</td>
					<td colspan="2" class="px-2 py-[3px] text-left text-[10px] text-slate-800">{row.label}</td>
					<td class="px-2 py-[3px] text-right tabular-nums text-slate-900 text-[10px]">AED {fmt(row.amount)}</td>
					<td class="px-2 py-[3px] text-left text-[9px] text-slate-500">{row.basis}</td>
				</tr>
			{/each}

			<!-- Section E: Repayment & Sweep -->
			<tr class="bg-[#1F3864]">
				<td colspan="5" class="px-2 py-[4px] text-white font-bold text-[11px] tracking-wide">E.&nbsp;&nbsp;REPAYMENT &amp; SWEEP</td>
			</tr>
			<tr class="bg-[#D6DCE4] border-b border-[#B8C4CE]">
				<th colspan="2" class="px-2 py-[4px] text-left text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Item</th>
				<th colspan="3" class="px-2 py-[4px] text-right text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Value</th>
			</tr>
			{#each [
				{ label: 'Repayment mode', value: workbookStore.inputs.debtRepaymentMode ?? 'bullet_at_handover' },
				{ label: 'First repayment period', value: firstSweepPeriod ? `${firstSweepPeriod.periodLabel} (AED ${fmt(firstSweepPeriod.debtRepaymentAed)})` : '—' },
				{ label: 'Total finance costs', value: 'AED ' + fmt(draftFinancing.totalFinanceCostsAed) },
				{ label: 'Equity in / out', value: `AED ${fmt(draftFinancing.equityContributedAed)} / ${fmt(draftFinancing.equityDistributedAed)}` },
				{ label: 'All-in cost / revenue', value: fmt(draftFinancing.allInCostToRevenuePct, 1) + '%' },
			] as item (item.label)}
				<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
					<td colspan="2" class="px-2 py-[3px] text-left text-[10px] text-slate-800">{item.label}</td>
					<td colspan="3" class="px-2 py-[3px] text-right tabular-nums text-slate-900 text-[10px]">{item.value}</td>
				</tr>
			{/each}

			</tbody>
		</table>

		<!-- Section F: Sources & Uses (optional) -->
		{#if sourcesUses}
			<table class="w-full border-collapse" style="border-spacing:0">
				<thead>
				<tr class="bg-[#1F3864]">
					<td colspan="4" class="px-2 py-[4px] text-white font-bold text-[11px] tracking-wide">F.&nbsp;&nbsp;SOURCES &amp; USES</td>
				</tr>
				<tr class="bg-[#D6DCE4] border-b border-[#B8C4CE]">
					<th class="px-2 py-[4px] text-left text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Category</th>
					<th class="px-2 py-[4px] text-left text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Line Item</th>
					<th class="px-2 py-[4px] text-right text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Amount (AED)</th>
					<th class="px-2 py-[4px] text-left text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Basis</th>
				</tr>
				</thead>
				<tbody>
				{#each sourcesUses.sources as item (item.code)}
					<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
						<td class="px-2 py-[3px] text-left text-[10px] font-semibold text-slate-700 uppercase tracking-wider text-[9px]">{item.category}</td>
						<td class="px-2 py-[3px] text-left text-[10px] text-slate-800">{item.label}</td>
						<td class="px-2 py-[3px] text-right tabular-nums text-slate-900 text-[10px]">AED {fmt(item.amountAed)}</td>
						<td class="px-2 py-[3px] text-left text-[9px] text-slate-500">{item.basis}</td>
					</tr>
				{/each}
				{#each sourcesUses.uses as item (item.code)}
					<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
						<td class="px-2 py-[3px] text-left text-[10px] font-semibold text-amber-700 uppercase tracking-wider text-[9px]">{item.category}</td>
						<td class="px-2 py-[3px] text-left text-[10px] text-slate-800">{item.label}</td>
						<td class="px-2 py-[3px] text-right tabular-nums text-slate-900 text-[10px]">AED {fmt(item.amountAed)}</td>
						<td class="px-2 py-[3px] text-left text-[9px] text-slate-500">{item.basis}</td>
					</tr>
				{/each}
				<!-- Grand total row -->
				<tr class="border-t-2 border-[#1F3864] border-b border-[#D9D9D9] font-bold bg-[#EEF2F7]">
					<td class="px-2 py-[3px] text-left text-[10px] text-slate-900 font-bold">Totals</td>
					<td class="px-2 py-[3px] text-left text-[9px] text-slate-500">Sources / Uses</td>
					<td class="px-2 py-[3px] text-right tabular-nums text-slate-900 text-[10px] font-bold">
						AED {fmt(sourcesUses.totalSourcesAed)} / {fmt(sourcesUses.totalUsesAed)}
					</td>
					<td class="px-2 py-[3px] text-left text-[10px] font-bold {Math.abs(sourcesUses.gapAed) > 1_000_000 ? 'text-amber-700' : 'text-slate-600'}">
						Gap AED {fmt(sourcesUses.gapAed)}
					</td>
				</tr>
				</tbody>
			</table>
		{/if}

		<div class="py-3"></div>
	</div>
{/if}
