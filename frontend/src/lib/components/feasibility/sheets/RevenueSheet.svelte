<script lang="ts">
import { workbookStore } from '$lib/feasibility/workbook/store.svelte'

function fmt(value: number, digits = 0) {
	return value.toLocaleString('en-AE', {
		minimumFractionDigits: digits,
		maximumFractionDigits: digits
	})
}

function fmtMoney(value: number | null | undefined) {
	return value == null || !Number.isFinite(value) ? '—' : `AED ${fmt(value)}`
}

function fmtPct(value: number | null | undefined, digits = 1) {
	return value == null || !Number.isFinite(value) ? '—' : `${fmt(value, digits)}%`
}

const assumptions = $derived(workbookStore.assumptions)
const outputs = $derived(workbookStore.outputs)
const research = $derived(workbookStore.research)

const offPlanPricing = $derived(research?.off_plan_market_pricing ?? [])
const offPlanBenchmarks = $derived(research?.off_plan_unit_benchmarks ?? [])

const depositPct = $derived(outputs?.funding.depositPct ?? 0)
const preHandoverPct = $derived(outputs?.funding.preHandoverPct ?? 0)
const handoverPct = $derived(outputs?.funding.handoverPct ?? 0)

// Simple schedule dates from assumptions
const salesCommencementDate = $derived(assumptions?.salesCommencementDate ?? '—')
const constructionDate = $derived(assumptions?.constructionDate ?? '—')
const handoverDate = $derived(assumptions?.handoverDate ?? '—')
const salesPeriodMonths = $derived(assumptions?.salesPeriodMonths ?? 0)
</script>

{#if !outputs || !assumptions}
<div class="h-full flex items-center justify-center text-sm text-slate-400">
No sales and collections data available.
</div>
{:else}
<div class="overflow-auto flex-1 bg-white text-[11px] font-[Calibri,'Segoe_UI',Arial,sans-serif] select-none">

<!-- Title bar -->
<div class="bg-[#1F3864] border-b-2 border-[#1F3864] text-white px-4 py-2.5 flex items-center justify-between gap-4">
<div class="text-[13px] font-bold tracking-wide">SALES &amp; COLLECTIONS</div>
<div class="text-[10px] text-blue-200 shrink-0">
{salesCommencementDate} → {handoverDate}
</div>
</div>

<!-- Summary bar -->
<div class="flex border-b border-[#B8C4CE] bg-[#EEF2F7] divide-x divide-[#D9D9D9]">
<div class="px-2 py-1.5 flex-1">
<div class="text-[9px] uppercase tracking-wider text-slate-500 font-semibold">Gross Revenue</div>
<div class="text-[11px] font-bold text-slate-900 tabular-nums">AED {fmt(outputs.program.grossRevenueAed)}</div>
</div>
<div class="px-2 py-1.5 flex-1">
<div class="text-[9px] uppercase tracking-wider text-slate-500 font-semibold">Off-plan Proceeds</div>
<div class="text-[11px] font-bold text-slate-900 tabular-nums">AED {fmt(outputs.funding.offPlanProceedsAed)}</div>
</div>
<div class="px-2 py-1.5 flex-1">
<div class="text-[9px] uppercase tracking-wider text-slate-500 font-semibold">Total Units</div>
<div class="text-[11px] font-bold text-slate-900 tabular-nums">{fmt(outputs.program.totalUnits)}</div>
</div>
<div class="px-2 py-1.5 flex-1">
<div class="text-[9px] uppercase tracking-wider text-slate-500 font-semibold">Avg Rate</div>
<div class="text-[11px] font-bold text-slate-900 tabular-nums">AED {fmt(outputs.program.weightedAvgSalesRatePsqm)} /sqm</div>
</div>
</div>

<table class="w-full border-collapse" style="border-spacing:0">
<tbody>

<!-- Section A: Payment Plan Tranches -->
<tr class="bg-[#1F3864]">
<td colspan="5" class="px-2 py-[4px] text-white font-bold text-[11px] tracking-wide">A.&nbsp;&nbsp;PAYMENT PLAN TRANCHES</td>
</tr>
<tr class="bg-[#D6DCE4] border-b border-[#B8C4CE]">
<th class="px-2 py-[4px] text-left text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Tranche</th>
<th class="px-2 py-[4px] text-right text-[9px] font-semibold text-slate-600 uppercase tracking-wider">%</th>
<th colspan="3" class="px-2 py-[4px] text-right text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Amount AED</th>
</tr>
{#each [
{ label: 'Deposit', pct: depositPct, amountAed: outputs.program.grossRevenueAed * depositPct / 100 },
{ label: 'Pre-handover', pct: preHandoverPct, amountAed: outputs.program.grossRevenueAed * preHandoverPct / 100 },
{ label: 'Handover', pct: handoverPct, amountAed: outputs.program.grossRevenueAed * handoverPct / 100 },
] as tranche (tranche.label)}
<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
<td class="px-2 py-[3px] text-left text-[10px] text-slate-800">{tranche.label}</td>
<td class="px-2 py-[3px] text-right tabular-nums text-slate-900 text-[10px]">{fmtPct(tranche.pct)}</td>
<td colspan="3" class="px-2 py-[3px] text-right tabular-nums text-slate-900 text-[10px]">{fmtMoney(tranche.amountAed)}</td>
</tr>
{/each}
<tr class="border-t-2 border-[#1F3864] border-b border-[#D9D9D9] font-bold bg-[#EEF2F7]">
<td class="px-2 py-[3px] text-left text-[10px] text-slate-900 font-bold">Total</td>
<td class="px-2 py-[3px] text-right tabular-nums text-slate-900 text-[10px] font-bold">{fmtPct(depositPct + preHandoverPct + handoverPct)}</td>
<td colspan="3" class="px-2 py-[3px] text-right tabular-nums text-slate-900 text-[10px] font-bold">{fmtMoney(outputs.program.grossRevenueAed)}</td>
</tr>

<!-- Section B: Schedule -->
<tr class="bg-[#1F3864]">
<td colspan="5" class="px-2 py-[4px] text-white font-bold text-[11px] tracking-wide">B.&nbsp;&nbsp;SCHEDULE</td>
</tr>
<tr class="bg-[#D6DCE4] border-b border-[#B8C4CE]">
<th colspan="2" class="px-2 py-[4px] text-left text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Item</th>
<th colspan="3" class="px-2 py-[4px] text-right text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Value</th>
</tr>
{#each [
{ label: 'Sales commencement', value: salesCommencementDate },
{ label: 'Construction start', value: constructionDate },
{ label: 'Handover', value: handoverDate },
{ label: 'Sales period', value: `${salesPeriodMonths} months` },
] as item (item.label)}
<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
<td colspan="2" class="px-2 py-[3px] text-left text-[10px] text-slate-800">{item.label}</td>
<td colspan="3" class="px-2 py-[3px] text-right tabular-nums text-slate-900 text-[10px]">{item.value}</td>
</tr>
{/each}

<!-- Section C: Revenue by Unit Type -->
<tr class="bg-[#1F3864]">
<td colspan="5" class="px-2 py-[4px] text-white font-bold text-[11px] tracking-wide">C.&nbsp;&nbsp;REVENUE BY UNIT TYPE</td>
</tr>
<tr class="bg-[#D6DCE4] border-b border-[#B8C4CE]">
<th class="px-1 py-[4px] text-center text-[9px] font-semibold text-slate-500 uppercase tracking-wider">#</th>
<th class="px-2 py-[4px] text-left text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Unit Type</th>
<th class="px-2 py-[4px] text-right text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Units</th>
<th class="px-2 py-[4px] text-right text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Rate (AED/sqm)</th>
<th class="px-2 py-[4px] text-right text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Revenue (AED)</th>
</tr>
{#each outputs.program.rows as row, idx (row.id)}
<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
<td class="px-1 py-[3px] text-center text-[9px] text-slate-400">{idx + 1}</td>
<td class="px-2 py-[3px] text-left text-[10px] text-slate-800">{row.label}</td>
<td class="px-2 py-[3px] text-right tabular-nums text-slate-900 text-[10px]">{fmt(row.units)}</td>
<td class="px-2 py-[3px] text-right tabular-nums text-slate-900 text-[10px]">{fmt(row.sellingRatePsqm)}</td>
<td class="px-2 py-[3px] text-right tabular-nums text-slate-900 text-[10px]">{fmtMoney(row.revenueAed)}</td>
</tr>
{/each}
<tr class="border-t-2 border-[#1F3864] border-b border-[#D9D9D9] font-bold bg-[#EEF2F7]">
<td colspan="2" class="px-2 py-[3px] text-left text-[10px] text-slate-900 font-bold">Total</td>
<td class="px-2 py-[3px] text-right tabular-nums text-slate-900 text-[10px] font-bold">{fmt(outputs.program.totalUnits)}</td>
<td class="px-2 py-[3px] text-right tabular-nums text-slate-900 text-[10px] font-bold">{fmt(outputs.program.weightedAvgSalesRatePsqm)}</td>
<td class="px-2 py-[3px] text-right tabular-nums text-slate-900 text-[10px] font-bold">{fmtMoney(outputs.program.grossRevenueAed)}</td>
</tr>

</tbody>
</table>

<!-- Section D: Off-Plan Pricing Basis (from research) -->
{#if offPlanPricing.length}
<table class="w-full border-collapse" style="border-spacing:0">
<tbody>
<tr class="bg-[#1F3864]">
<td colspan="5" class="px-2 py-[4px] text-white font-bold text-[11px] tracking-wide">D.&nbsp;&nbsp;OFF-PLAN PRICING BASIS</td>
</tr>
<tr class="bg-[#D6DCE4] border-b border-[#B8C4CE]">
<th class="px-2 py-[4px] text-left text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Unit Type</th>
<th class="px-2 py-[4px] text-right text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Horizon</th>
<th class="px-2 py-[4px] text-right text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Avg Months</th>
<th class="px-2 py-[4px] text-right text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Rate (AED/sqm)</th>
<th class="px-2 py-[4px] text-right text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Transactions</th>
</tr>
{#each offPlanPricing as row (`${row.unit_type}-${row.horizon_bucket}`)}
<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
<td class="px-2 py-[3px] text-left text-[10px] text-slate-800">{row.unit_type}</td>
<td class="px-2 py-[3px] text-right tabular-nums text-slate-500 text-[10px]">{row.horizon_bucket}</td>
<td class="px-2 py-[3px] text-right tabular-nums text-slate-900 text-[10px]">{fmt(row.avg_months_to_completion, 1)}</td>
<td class="px-2 py-[3px] text-right tabular-nums text-slate-900 text-[10px]">{fmt(row.median_price_sqm)}</td>
<td class="px-2 py-[3px] text-right tabular-nums text-slate-500 text-[10px]">{fmt(row.transaction_count)}</td>
</tr>
{/each}
</tbody>
</table>
{/if}

<!-- Section E: Unit Benchmarks (from research) -->
{#if offPlanBenchmarks.length}
<table class="w-full border-collapse" style="border-spacing:0">
<tbody>
<tr class="bg-[#1F3864]">
<td colspan="3" class="px-2 py-[4px] text-white font-bold text-[11px] tracking-wide">E.&nbsp;&nbsp;UNIT BENCHMARKS</td>
</tr>
<tr class="bg-[#D6DCE4] border-b border-[#B8C4CE]">
<th class="px-2 py-[4px] text-left text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Unit Type</th>
<th class="px-2 py-[4px] text-right text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Selected Rate</th>
<th class="px-2 py-[4px] text-right text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Sample</th>
</tr>
{#each offPlanBenchmarks as row (`${row.unit_type}-${row.selected_horizon_bucket}`)}
<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
<td class="px-2 py-[3px] text-left text-[10px] text-slate-800">{row.unit_type}</td>
<td class="px-2 py-[3px] text-right tabular-nums text-slate-900 text-[10px]">AED {fmt(row.selected_price_sqm)}/sqm</td>
<td class="px-2 py-[3px] text-right tabular-nums text-slate-500 text-[10px]">{fmt(row.transaction_count)}</td>
</tr>
{/each}

</tbody>
</table>
{/if}

<div class="py-3"></div>
</div>
{/if}
