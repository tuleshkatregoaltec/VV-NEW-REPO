<script lang="ts">
import { workbookStore } from '$lib/feasibility/workbook/store.svelte'

function fmt(value: number, digits = 0): string {
	return value.toLocaleString('en-AE', {
		minimumFractionDigits: digits,
		maximumFractionDigits: digits
	})
}

function fmtPct(value: number | null | undefined): string {
	if (value == null) return '—'
	return `${value.toFixed(1)}%`
}

function fmtMoic(value: number | null | undefined): string {
	if (value == null) return '—'
	return `${value.toFixed(2)}x`
}

const annualCf = $derived(workbookStore.workbook?.annualCashFlow ?? null)
const annualRows = $derived(annualCf?.rows ?? [])
const returns = $derived(workbookStore.workbook?.returns ?? null)

const totals = $derived(
	(() => {
		const rows = annualRows
		return {
			year: 0,
			revenueAed: rows.reduce((s, r) => s + r.revenueAed, 0),
			costsAed: rows.reduce((s, r) => s + r.costsAed, 0),
			unleveredCfAed: rows.reduce((s, r) => s + r.unleveredCfAed, 0),
			debtDrawAed: rows.reduce((s, r) => s + r.debtDrawAed, 0),
			debtRepayAed: rows.reduce((s, r) => s + r.debtRepayAed, 0),
			interestAed: rows.reduce((s, r) => s + r.interestAed, 0),
			equityInAed: rows.reduce((s, r) => s + r.equityInAed, 0),
			equityOutAed: rows.reduce((s, r) => s + r.equityOutAed, 0),
			leveredCfAed: rows.reduce((s, r) => s + r.leveredCfAed, 0),
			closingDebtAed: rows.at(-1)?.closingDebtAed ?? 0
		}
	})()
)

// Style helpers
const TH =
	'px-3 py-[5px] text-right text-[10px] font-semibold text-slate-500 uppercase tracking-wider whitespace-nowrap'
const TH_L =
	'px-3 py-[5px] text-left text-[10px] font-semibold text-slate-500 uppercase tracking-wider'
const TD = 'px-3 py-[4px] text-right text-[11px] tabular-nums text-slate-600 whitespace-nowrap'
const TD_TOT =
	'px-3 py-[4px] text-right text-[11px] tabular-nums font-semibold text-slate-800 whitespace-nowrap'
const TD_NEG = 'px-3 py-[4px] text-right text-[11px] tabular-nums text-slate-900 whitespace-nowrap'
const TD_NEG_TOT =
	'px-3 py-[4px] text-right text-[11px] tabular-nums font-semibold text-slate-900 whitespace-nowrap'
const TD_L = 'px-3 py-[4px] text-left text-[11px] text-slate-700 whitespace-nowrap'
const HDR = 'bg-slate-100 border-t-2 border-slate-300'
const HDR_SUB = 'bg-slate-50 border-t border-slate-200'
const ROW = 'border-t border-slate-100 hover:bg-slate-50/60'
</script>

{#if annualRows.length === 0}
	<div class="h-full flex items-center justify-center px-6 text-sm text-slate-400">
		Generate an HBU study to build the cash-flow view.
	</div>
{:else}
	<div class="h-full overflow-auto">
		<table class="w-full border-collapse text-xs min-w-[700px]">
			<!-- Header -->
			<thead class="sticky top-0 z-10 bg-white shadow-sm">
				<tr class="border-b-2 border-slate-300">
					<th class="{TH_L} w-44">Line item</th>
					{#each annualRows as row}
						<th class={TH}>{row.year}</th>
					{/each}
					<th class="{TH} bg-slate-50">Total</th>
				</tr>
			</thead>

			<tbody>
				<!-- ── REVENUE ── -->
				<tr class={HDR}>
					<td class="px-3 py-[5px] text-[10px] font-semibold text-slate-700 uppercase tracking-wider" colspan={annualRows.length + 2}>
						Revenue inflows
					</td>
				</tr>
				<tr class={ROW}>
					<td class={TD_L}>Revenue inflows</td>
					{#each annualRows as row}
						<td class={TD}>{fmt(row.revenueAed)}</td>
					{/each}
					<td class="{TD_TOT} bg-slate-50">{fmt(totals.revenueAed)}</td>
				</tr>

				<!-- ── COSTS ── -->
				<tr class={HDR}>
					<td class="px-3 py-[5px] text-[10px] font-semibold text-slate-700 uppercase tracking-wider" colspan={annualRows.length + 2}>
						Project costs
					</td>
				</tr>
				<tr class={ROW}>
					<td class={TD_L}>Project costs</td>
					{#each annualRows as row}
						<td class={TD_NEG}>({fmt(Math.abs(row.costsAed))})</td>
					{/each}
					<td class="{TD_NEG_TOT} bg-slate-50">({fmt(Math.abs(totals.costsAed))})</td>
				</tr>

				<!-- ── UNLEVERED CF ── -->
				<tr class={HDR}>
					<td class="px-3 py-[5px] text-[10px] font-semibold text-slate-700 uppercase tracking-wider" colspan={annualRows.length + 2}>
						Unlevered cash flow
					</td>
				</tr>
				<tr class={ROW}>
					<td class="{TD_L} font-semibold text-slate-800">Unlevered net CF</td>
					{#each annualRows as row}
						<td class={row.unleveredCfAed < 0 ? TD_NEG : TD}>
							{row.unleveredCfAed < 0 ? '(' : ''}{fmt(Math.abs(row.unleveredCfAed))}{row.unleveredCfAed < 0 ? ')' : ''}
						</td>
					{/each}
					<td class="{totals.unleveredCfAed < 0 ? TD_NEG_TOT : TD_TOT} bg-slate-50">
						{totals.unleveredCfAed < 0 ? '(' : ''}{fmt(Math.abs(totals.unleveredCfAed))}{totals.unleveredCfAed < 0 ? ')' : ''}
					</td>
				</tr>

				<!-- ── DEBT ── -->
				<tr class={HDR}>
					<td class="px-3 py-[5px] text-[10px] font-semibold text-slate-700 uppercase tracking-wider" colspan={annualRows.length + 2}>
						Debt
					</td>
				</tr>
				<tr class={ROW}>
					<td class={TD_L}>Debt draws</td>
					{#each annualRows as row}
						<td class={TD}>{fmt(row.debtDrawAed)}</td>
					{/each}
					<td class="{TD_TOT} bg-slate-50">{fmt(totals.debtDrawAed)}</td>
				</tr>
				<tr class={ROW}>
					<td class={TD_L}>Debt repayment</td>
					{#each annualRows as row}
						<td class={TD_NEG}>({fmt(Math.abs(row.debtRepayAed))})</td>
					{/each}
					<td class="{TD_NEG_TOT} bg-slate-50">({fmt(Math.abs(totals.debtRepayAed))})</td>
				</tr>
				<tr class={ROW}>
					<td class={TD_L}>Interest paid</td>
					{#each annualRows as row}
						<td class={TD_NEG}>({fmt(Math.abs(row.interestAed))})</td>
					{/each}
					<td class="{TD_NEG_TOT} bg-slate-50">({fmt(Math.abs(totals.interestAed))})</td>
				</tr>

				<!-- ── DEBT BALANCE ── -->
				<tr class={HDR_SUB}>
					<td class="px-3 py-[5px] text-[10px] font-semibold text-slate-600 uppercase tracking-wider" colspan={annualRows.length + 2}>
						Closing debt balance
					</td>
				</tr>
				<tr class={ROW}>
					<td class={TD_L}>Closing debt balance</td>
					{#each annualRows as row}
						<td class={TD}>{fmt(row.closingDebtAed)}</td>
					{/each}
					<td class="{TD_TOT} bg-slate-50">{fmt(totals.closingDebtAed)}</td>
				</tr>

				<!-- ── EQUITY ── -->
				<tr class={HDR}>
					<td class="px-3 py-[5px] text-[10px] font-semibold text-slate-700 uppercase tracking-wider" colspan={annualRows.length + 2}>
						Equity
					</td>
				</tr>
				<tr class={ROW}>
					<td class={TD_L}>Equity in</td>
					{#each annualRows as row}
						<td class={TD_NEG}>({fmt(Math.abs(row.equityInAed))})</td>
					{/each}
					<td class="{TD_NEG_TOT} bg-slate-50">({fmt(Math.abs(totals.equityInAed))})</td>
				</tr>
				<tr class={ROW}>
					<td class={TD_L}>Equity out</td>
					{#each annualRows as row}
						<td class={TD}>{fmt(row.equityOutAed)}</td>
					{/each}
					<td class="{TD_TOT} bg-slate-50">{fmt(totals.equityOutAed)}</td>
				</tr>

				<!-- ── LEVERED CF ── -->
				<tr class={HDR}>
					<td class="px-3 py-[5px] text-[10px] font-semibold text-slate-700 uppercase tracking-wider" colspan={annualRows.length + 2}>
						Levered (equity) cash flow
					</td>
				</tr>
				<tr class={ROW}>
					<td class="{TD_L} font-semibold text-slate-800">Levered net CF</td>
					{#each annualRows as row}
						<td class={row.leveredCfAed < 0 ? TD_NEG : TD}>
							{row.leveredCfAed < 0 ? '(' : ''}{fmt(Math.abs(row.leveredCfAed))}{row.leveredCfAed < 0 ? ')' : ''}
						</td>
					{/each}
					<td class="{totals.leveredCfAed < 0 ? TD_NEG_TOT : TD_TOT} bg-slate-50">
						{totals.leveredCfAed < 0 ? '(' : ''}{fmt(Math.abs(totals.leveredCfAed))}{totals.leveredCfAed < 0 ? ')' : ''}
					</td>
				</tr>

				<!-- ── RETURNS ── -->
				<tr class="border-t-2 border-slate-300 bg-slate-100">
					<td class="px-3 py-[5px] text-[10px] font-semibold text-slate-700 uppercase tracking-wider" colspan={annualRows.length + 2}>
						Returns summary
					</td>
				</tr>
				<tr class={ROW}>
					<td class={TD_L}>Project IRR</td>
					<td class="px-3 py-[4px] text-[11px] text-emerald-700" colspan={annualRows.length}>
						{fmtPct(returns?.projectIrrPct)}
					</td>
					<td class="px-3 py-[4px] text-right text-[11px] tabular-nums font-semibold text-emerald-700 whitespace-nowrap bg-slate-50">{fmtPct(returns?.projectIrrPct)}</td>
				</tr>
				<tr class={ROW}>
					<td class={TD_L}>Project MoIC</td>
					<td class="px-3 py-[4px] text-[11px] text-emerald-700" colspan={annualRows.length}>
						{fmtMoic(returns?.projectMoic)}
					</td>
					<td class="px-3 py-[4px] text-right text-[11px] tabular-nums font-semibold text-emerald-700 whitespace-nowrap bg-slate-50">{fmtMoic(returns?.projectMoic)}</td>
				</tr>
				<tr class={ROW}>
					<td class={TD_L}>Equity IRR</td>
					<td class="px-3 py-[4px] text-[11px] text-emerald-700" colspan={annualRows.length}>
						{fmtPct(returns?.equityIrrPct)}
					</td>
					<td class="px-3 py-[4px] text-right text-[11px] tabular-nums font-semibold text-emerald-700 whitespace-nowrap bg-slate-50">{fmtPct(returns?.equityIrrPct)}</td>
				</tr>
				<tr class={ROW}>
					<td class={TD_L}>Equity MoIC</td>
					<td class="px-3 py-[4px] text-[11px] text-emerald-700" colspan={annualRows.length}>
						{fmtMoic(returns?.equityMoic)}
					</td>
					<td class="px-3 py-[4px] text-right text-[11px] tabular-nums font-semibold text-emerald-700 whitespace-nowrap bg-slate-50">{fmtMoic(returns?.equityMoic)}</td>
				</tr>
				<tr class={ROW}>
					<td class={TD_L}>Gross margin</td>
					<td class="px-3 py-[4px] text-[11px] text-emerald-700" colspan={annualRows.length}>
						{fmtPct(returns?.grossMarginPct)}
					</td>
					<td class="px-3 py-[4px] text-right text-[11px] tabular-nums font-semibold text-emerald-700 whitespace-nowrap bg-slate-50">{fmtPct(returns?.grossMarginPct)}</td>
				</tr>
			</tbody>
		</table>
	</div>
{/if}
