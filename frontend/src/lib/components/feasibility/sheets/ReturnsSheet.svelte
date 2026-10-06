<script lang="ts">
import { workbookStore } from '$lib/feasibility/workbook/store.svelte'

function fmt(value: number, digits = 0) {
	return value.toLocaleString('en-AE', {
		minimumFractionDigits: digits,
		maximumFractionDigits: digits
	})
}

const outputs = $derived(workbookStore.outputs)
const draftSensitivities = $derived(
	[] as Array<{
		code: string
		label: string
		changeNote: string
		projectIrrPct: number | null
		equityIrrPct: number | null
		allInMarginPct: number | null
		peakDebtAed: number | null
		totalFinanceCostsAed: number | null
	}>
)

const grossRevenueAed = $derived(outputs?.program.grossRevenueAed ?? 0)
const totalCostsInclVatAed = $derived(outputs?.costs.totalCostsInclVatAed ?? 0)
const offPlanProceedsAed = $derived(outputs?.funding.offPlanProceedsAed ?? 0)
const debtFundingAed = $derived(outputs?.funding.debtFundingAed ?? 0)
const equityFundingAed = $derived(outputs?.funding.equityFundingAed ?? 0)
const totalSourcesAed = $derived(outputs?.funding.cashReconSourcesAed ?? 0)
const totalUsesAed = $derived(outputs?.funding.cashReconUsesAed ?? 0)
const peakNetSponsorCapitalAed = $derived(outputs?.returns.peakEquityAed ?? 0)
const returnOnCostPct = $derived(
	totalCostsInclVatAed > 0
		? ((grossRevenueAed - totalCostsInclVatAed) / totalCostsInclVatAed) * 100
		: 0
)
const revenueMultiple = $derived(
	totalCostsInclVatAed > 0 ? grossRevenueAed / totalCostsInclVatAed : 0
)

const fundingGap = $derived(outputs?.funding.cashReconGapAed ?? totalSourcesAed - totalUsesAed)
const localProfit = $derived(grossRevenueAed - totalCostsInclVatAed)
</script>

{#if !outputs}
	<div class="h-full flex items-center justify-center text-sm text-slate-400">
		No returns data available.
	</div>
{:else}
	<div class="overflow-auto flex-1 bg-white text-[11px] font-[Calibri,'Segoe_UI',Arial,sans-serif] select-none">

		<!-- Title bar -->
		<div class="bg-[#1F3864] border-b-2 border-[#1F3864] text-white px-4 py-2.5 flex items-center justify-between gap-4">
			<div class="text-[13px] font-bold tracking-wide">RETURNS &amp; BENCHMARKS</div>
			<div class="text-[10px] text-blue-200 shrink-0">AED unless stated</div>
		</div>

		<!-- Summary bar -->
		<div class="flex border-b border-[#B8C4CE] bg-[#EEF2F7] divide-x divide-[#D9D9D9]">
			<div class="px-2 py-1.5 flex-1">
				<div class="text-[9px] uppercase tracking-wider text-slate-500 font-semibold">Gross Profit</div>
				<div class="text-[11px] font-bold text-slate-900 tabular-nums">AED {fmt(localProfit)}</div>
			</div>
			<div class="px-2 py-1.5 flex-1">
				<div class="text-[9px] uppercase tracking-wider text-slate-500 font-semibold">Equity IRR</div>
				<div class="text-[11px] font-bold text-slate-900 tabular-nums">{outputs?.returns.equityIrrPct != null ? fmt(outputs.returns.equityIrrPct, 1) + '%' : '—'}</div>
			</div>
			<div class="px-2 py-1.5 flex-1">
				<div class="text-[9px] uppercase tracking-wider text-slate-500 font-semibold">Equity MOIC</div>
				<div class="text-[11px] font-bold text-slate-900 tabular-nums">{outputs?.returns.equityMoic != null ? fmt(outputs.returns.equityMoic, 2) + 'x' : '—'}</div>
			</div>
			<div class="px-2 py-1.5 flex-1">
				<div class="text-[9px] uppercase tracking-wider text-slate-500 font-semibold">Funding Gap</div>
				<div class="text-[11px] font-bold {Math.abs(fundingGap) > 1_000_000 ? 'text-amber-700' : 'text-slate-900'} tabular-nums">AED {fmt(fundingGap)}</div>
			</div>
		</div>

		<!-- Section A: Returns Summary -->
		<table class="w-full border-collapse" style="border-spacing:0">
			<tbody>
			<tr class="bg-[#1F3864]">
				<td colspan="4" class="px-2 py-[4px] text-white font-bold text-[11px] tracking-wide">A.&nbsp;&nbsp;RETURNS SUMMARY</td>
			</tr>
			<tr class="bg-[#D6DCE4] border-b border-[#B8C4CE]">
				<th class="px-1 py-[4px] text-center text-[9px] font-semibold text-slate-500 uppercase tracking-wider">#</th>
				<th class="px-2 py-[4px] text-left text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Metric</th>
				<th class="px-2 py-[4px] text-right text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Value</th>
				<th class="px-2 py-[4px] text-left text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Note</th>
			</tr>
			<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
				<td class="px-1 py-[3px] text-center text-[9px] text-slate-400">a</td>
				<td class="px-2 py-[3px] text-left text-[10px] text-slate-900 font-semibold">Project IRR</td>
				<td class="px-2 py-[3px] text-right tabular-nums text-[10px] font-bold text-emerald-700">
					{outputs?.returns.projectIrrPct != null ? fmt(outputs.returns.projectIrrPct, 1) + '%' : '—'}
				</td>
				<td class="px-2 py-[3px] text-left text-[9px] text-slate-500">Timed cash-flow IRR</td>
			</tr>
			<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
				<td class="px-1 py-[3px] text-center text-[9px] text-slate-400">b</td>
				<td class="px-2 py-[3px] text-left text-[10px] text-slate-900 font-semibold">Equity IRR</td>
				<td class="px-2 py-[3px] text-right tabular-nums text-[10px] font-bold text-emerald-700">
					{outputs?.returns.equityIrrPct != null ? fmt(outputs.returns.equityIrrPct, 1) + '%' : '—'}
				</td>
				<td class="px-2 py-[3px] text-left text-[9px] text-slate-500">Sponsor cash flows</td>
			</tr>
			<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
				<td class="px-1 py-[3px] text-center text-[9px] text-slate-400">c</td>
				<td class="px-2 py-[3px] text-left text-[10px] text-slate-800">Return on cost</td>
				<td class="px-2 py-[3px] text-right tabular-nums text-slate-900 text-[10px]">{fmt(returnOnCostPct, 1)}%</td>
				<td class="px-2 py-[3px]"></td>
			</tr>
			<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
				<td class="px-1 py-[3px] text-center text-[9px] text-slate-400">d</td>
				<td class="px-2 py-[3px] text-left text-[10px] text-slate-800">Revenue multiple</td>
				<td class="px-2 py-[3px] text-right tabular-nums text-slate-900 text-[10px]">{fmt(revenueMultiple, 2)}x</td>
				<td class="px-2 py-[3px]"></td>
			</tr>
			<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
				<td class="px-1 py-[3px] text-center text-[9px] text-slate-400">e</td>
				<td class="px-2 py-[3px] text-left text-[10px] text-slate-800">Project MOIC</td>
				<td class="px-2 py-[3px] text-right tabular-nums text-slate-900 text-[10px]">{outputs?.returns.projectMoic != null ? fmt(outputs.returns.projectMoic, 2) + 'x' : '—'}</td>
				<td class="px-2 py-[3px] text-left text-[9px] text-slate-500">Timed cash-flow multiple</td>
			</tr>
			<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
				<td class="px-1 py-[3px] text-center text-[9px] text-slate-400">f</td>
				<td class="px-2 py-[3px] text-left text-[10px] text-slate-800">Equity MOIC</td>
				<td class="px-2 py-[3px] text-right tabular-nums text-slate-900 text-[10px]">{outputs?.returns.equityMoic != null ? fmt(outputs.returns.equityMoic, 2) + 'x' : '—'}</td>
				<td class="px-2 py-[3px] text-left text-[9px] text-slate-500">Sponsor distributions vs equity contributions</td>
			</tr>
			<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
				<td class="px-1 py-[3px] text-center text-[9px] text-slate-400">g</td>
				<td class="px-2 py-[3px] text-left text-[10px] text-slate-800">All-in profit</td>
				<td class="px-2 py-[3px] text-right tabular-nums text-slate-900 text-[10px]">{outputs?.returns.allInProjectProfitAed != null ? 'AED ' + fmt(outputs.returns.allInProjectProfitAed) : '—'}</td>
				<td class="px-2 py-[3px] text-left text-[9px] text-slate-500">Revenue less total project cost including finance carry</td>
			</tr>
			<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
				<td class="px-1 py-[3px] text-center text-[9px] text-slate-400">h</td>
				<td class="px-2 py-[3px] text-left text-[10px] text-slate-800">All-in margin</td>
				<td class="px-2 py-[3px] text-right tabular-nums text-slate-900 text-[10px]">{outputs?.returns.allInMarginPct != null ? fmt(outputs.returns.allInMarginPct, 1) + '%' : '—'}</td>
				<td class="px-2 py-[3px] text-left text-[9px] text-slate-500">All-in profit as share of gross revenue</td>
			</tr>
			<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
				<td class="px-1 py-[3px] text-center text-[9px] text-slate-400">i</td>
				<td class="px-2 py-[3px] text-left text-[10px] text-slate-800">Peak debt</td>
				<td class="px-2 py-[3px] text-right tabular-nums text-slate-900 text-[10px]">{outputs?.cashFlow.peakFundingAed != null ? 'AED ' + fmt(outputs.cashFlow.peakFundingAed) : '—'}</td>
				<td class="px-2 py-[3px] text-left text-[9px] text-slate-500">Monthly financing path</td>
			</tr>
			<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
				<td class="px-1 py-[3px] text-center text-[9px] text-slate-400">j</td>
				<td class="px-2 py-[3px] text-left text-[10px] text-slate-800">Peak net sponsor capital</td>
				<td class="px-2 py-[3px] text-right tabular-nums text-slate-900 text-[10px]">AED {fmt(peakNetSponsorCapitalAed)}</td>
				<td class="px-2 py-[3px] text-left text-[9px] text-slate-500">Maximum cumulative equity in less distributions out</td>
			</tr>
			<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
				<td class="px-1 py-[3px] text-center text-[9px] text-slate-400">k</td>
				<td class="px-2 py-[3px] text-left text-[10px] text-slate-800">Interest carry</td>
				<td class="px-2 py-[3px] text-right tabular-nums text-slate-900 text-[10px]">{outputs?.returns.totalInterestPaidAed != null ? 'AED ' + fmt(outputs.returns.totalInterestPaidAed) : '—'}</td>
				<td class="px-2 py-[3px] text-left text-[9px] text-slate-500">Capitalized monthly interest</td>
			</tr>
			<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
				<td class="px-1 py-[3px] text-center text-[9px] text-slate-400">l</td>
				<td class="px-2 py-[3px] text-left text-[10px] text-slate-800">Financing / exit fees</td>
				<td class="px-2 py-[3px] text-right tabular-nums text-slate-900 text-[10px]">
					{outputs?.returns != null ? 'AED ' + fmt((outputs.returns.financingFeeAed ?? 0) + (outputs.returns.exitFeeAed ?? 0)) : '—'}
				</td>
				<td class="px-2 py-[3px] text-left text-[9px] text-slate-500">Upfront financing fee plus handover exit fee</td>
			</tr>
			<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
				<td class="px-1 py-[3px] text-center text-[9px] text-slate-400">m</td>
				<td class="px-2 py-[3px] text-left text-[10px] text-slate-800">Off-plan proceeds</td>
				<td class="px-2 py-[3px] text-right tabular-nums text-slate-900 text-[10px]">AED {fmt(offPlanProceedsAed)}</td>
				<td class="px-2 py-[3px] text-left text-[9px] text-slate-500">Deposit + pre-handover collections</td>
			</tr>
			<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
				<td class="px-1 py-[3px] text-center text-[9px] text-slate-400">n</td>
				<td class="px-2 py-[3px] text-left text-[10px] text-slate-800">Debt / equity funding</td>
				<td class="px-2 py-[3px] text-right tabular-nums text-slate-900 text-[10px]">AED {fmt(debtFundingAed)} / {fmt(equityFundingAed)}</td>
				<td class="px-2 py-[3px]"></td>
			</tr>
			<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
				<td class="px-1 py-[3px] text-center text-[9px] text-slate-400">o</td>
				<td class="px-2 py-[3px] text-left text-[10px] text-slate-800">Break-even Sale Rate</td>
				<td class="px-2 py-[3px] text-right tabular-nums text-slate-900 text-[10px]">{outputs?.returns.breakEvenSaleRateAedSqft != null ? fmt(outputs.returns.breakEvenSaleRateAedSqft) + ' AED/sqft' : '—'}</td>
				<td class="px-2 py-[3px] text-left text-[9px] text-slate-500">Total cost / sellable area</td>
			</tr>
			<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
				<td class="px-1 py-[3px] text-center text-[9px] text-slate-400">p</td>
				<td class="px-2 py-[3px] text-left text-[10px] text-slate-800">Levered Margin on Equity</td>
				<td class="px-2 py-[3px] text-right tabular-nums text-slate-900 text-[10px]">{outputs?.returns.leveredMarginOnEquityPct != null ? fmt(outputs.returns.leveredMarginOnEquityPct, 1) + '%' : '—'}</td>
				<td class="px-2 py-[3px] text-left text-[9px] text-slate-500">Levered profit / total equity</td>
			</tr>
			<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
				<td class="px-1 py-[3px] text-center text-[9px] text-slate-400">q</td>
				<td class="px-2 py-[3px] text-left text-[10px] text-slate-800">Debt as % of Cost</td>
				<td class="px-2 py-[3px] text-right tabular-nums text-emerald-700 text-[10px]">{outputs?.returns.debtAsPctOfCost != null ? fmt(outputs.returns.debtAsPctOfCost, 1) + '%' : '—'}</td>
				<td class="px-2 py-[3px] text-left text-[9px] text-slate-500">Peak debt / total cost</td>
			</tr>
			<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
				<td class="px-1 py-[3px] text-center text-[9px] text-slate-400">r</td>
				<td class="px-2 py-[3px] text-left text-[10px] text-slate-800">Average Debt Outstanding</td>
				<td class="px-2 py-[3px] text-right tabular-nums text-emerald-700 text-[10px]">{outputs?.returns.averageDebtOutstandingAed != null ? 'AED ' + fmt(outputs.returns.averageDebtOutstandingAed) : '—'}</td>
				<td class="px-2 py-[3px] text-left text-[9px] text-slate-500">Time-weighted average</td>
			</tr>
			<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
				<td class="px-1 py-[3px] text-center text-[9px] text-slate-400">s</td>
				<td class="px-2 py-[3px] text-left text-[10px] text-slate-800">Financing Fee</td>
				<td class="px-2 py-[3px] text-right tabular-nums text-emerald-700 text-[10px]">{outputs?.returns.financingFeeAed != null ? 'AED ' + fmt(outputs.returns.financingFeeAed) : '—'}</td>
				<td class="px-2 py-[3px] text-left text-[9px] text-slate-500">1% of total debt commitment</td>
			</tr>
			<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
				<td class="px-1 py-[3px] text-center text-[9px] text-slate-400">t</td>
				<td class="px-2 py-[3px] text-left text-[10px] text-slate-800">Exit Fee</td>
				<td class="px-2 py-[3px] text-right tabular-nums text-emerald-700 text-[10px]">{outputs?.returns.exitFeeAed != null ? 'AED ' + fmt(outputs.returns.exitFeeAed) : '—'}</td>
				<td class="px-2 py-[3px] text-left text-[9px] text-slate-500">1% of opening debt at handover</td>
			</tr>
			<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
				<td class="px-1 py-[3px] text-center text-[9px] text-slate-400">u</td>
				<td class="px-2 py-[3px] text-left text-[10px] text-slate-800 font-semibold">Total Financing Costs</td>
				<td class="px-2 py-[3px] text-right tabular-nums text-emerald-700 text-[10px] font-bold">{outputs?.returns.totalFinancingCostsAed != null ? 'AED ' + fmt(outputs.returns.totalFinancingCostsAed) : '—'}</td>
				<td class="px-2 py-[3px] text-left text-[9px] text-slate-500">Interest + fees</td>
			</tr>
			</tbody>
		</table>

		<!-- Section B: Sensitivity Scenarios (optional) -->
		{#if draftSensitivities.length}
			<table class="w-full border-collapse" style="border-spacing:0">
				<thead>
				<tr class="bg-[#1F3864]">
					<td colspan="7" class="px-2 py-[4px] text-white font-bold text-[11px] tracking-wide">B.&nbsp;&nbsp;SENSITIVITY SCENARIOS</td>
				</tr>
				<tr class="bg-[#D6DCE4] border-b border-[#B8C4CE]">
					<th class="px-2 py-[4px] text-left text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Scenario</th>
					<th class="px-2 py-[4px] text-left text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Change</th>
					<th class="px-2 py-[4px] text-right text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Project IRR</th>
					<th class="px-2 py-[4px] text-right text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Equity IRR</th>
					<th class="px-2 py-[4px] text-right text-[9px] font-semibold text-slate-600 uppercase tracking-wider">All-in Margin</th>
					<th class="px-2 py-[4px] text-right text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Peak Debt</th>
					<th class="px-2 py-[4px] text-right text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Finance Carry</th>
				</tr>
				</thead>
				<tbody>
				{#each draftSensitivities as scenario (scenario.code)}
					<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
						<td class="px-2 py-[3px] text-left text-[10px] text-slate-800 font-semibold">{scenario.label}</td>
						<td class="pl-6 pr-2 py-[3px] text-left text-[9px] text-slate-500 italic">{scenario.changeNote}</td>
						<td class="px-2 py-[3px] text-right tabular-nums text-slate-900 text-[10px]">{scenario.projectIrrPct != null ? fmt(scenario.projectIrrPct, 1) + '%' : '—'}</td>
						<td class="px-2 py-[3px] text-right tabular-nums text-slate-900 text-[10px]">{scenario.equityIrrPct != null ? fmt(scenario.equityIrrPct, 1) + '%' : '—'}</td>
						<td class="px-2 py-[3px] text-right tabular-nums text-slate-900 text-[10px]">{scenario.allInMarginPct != null ? fmt(scenario.allInMarginPct, 1) + '%' : '—'}</td>
						<td class="px-2 py-[3px] text-right tabular-nums text-slate-900 text-[10px]">{scenario.peakDebtAed != null ? 'AED ' + fmt(scenario.peakDebtAed) : '—'}</td>
						<td class="px-2 py-[3px] text-right tabular-nums text-slate-900 text-[10px]">{scenario.totalFinanceCostsAed != null ? 'AED ' + fmt(scenario.totalFinanceCostsAed) : '—'}</td>
					</tr>
				{/each}
				</tbody>
			</table>
		{/if}

		<div class="py-3"></div>
	</div>
{/if}
