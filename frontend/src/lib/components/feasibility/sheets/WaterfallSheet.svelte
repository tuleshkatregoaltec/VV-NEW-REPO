<script lang="ts">
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

const outputs = $derived(workbookStore.outputs)
const wf = $derived(outputs?.waterfall)
const assumptions = $derived(workbookStore.assumptions)

type WaterfallStep = {
	step: number
	label: string
	amount: string
	note: string
	isTotal?: boolean
}

const steps = $derived<WaterfallStep[]>(
	wf
		? [
				{
					step: 0,
					label: 'Total Equity Contributions',
					amount: `AED ${fmt(wf.totalEquityContributions)}`,
					note: 'Sum of equity draws across project life'
				},
				{
					step: 0,
					label: 'Total Equity Distributions',
					amount: `AED ${fmt(wf.totalEquityDistributions)}`,
					note: 'Sum of equity returns across project life'
				},
				{
					step: 1,
					label: 'Return of Capital',
					amount: `AED ${fmt(wf.returnOfCapital)}`,
					note: 'Equity investors receive contributed capital back first'
				},
				{
					step: 0,
					label: 'Cash Remaining After RoC',
					amount: `AED ${fmt(wf.cashRemainingAfterRoc)}`,
					note: 'Distributions minus return of capital',
					isTotal: true
				},
				{
					step: 2,
					label: 'Preferred Return',
					amount: `AED ${fmt(wf.preferredReturnPaid)}`,
					note: `Hurdle: AED ${fmt(wf.preferredReturnHurdle)} (${fmtPct((assumptions?.preferredReturnPa ?? 0.08) * 100)} p.a. for ${assumptions?.projectYears ?? 5} yrs)`
				},
				{
					step: 0,
					label: 'Cash Remaining After Pref',
					amount: `AED ${fmt(wf.cashRemainingAfterPref)}`,
					note: 'Remaining after preferred return',
					isTotal: true
				},
				{
					step: 3,
					label: 'Residual to Equity',
					amount: `AED ${fmt(wf.residualToEquity)}`,
					note: `${fmtPct((1 - (assumptions?.sponsorPromotePct ?? 0.2)) * 100)} of residual`
				},
				{
					step: 4,
					label: 'Sponsor Promote',
					amount: `AED ${fmt(wf.sponsorPromote)}`,
					note: `${fmtPct((assumptions?.sponsorPromotePct ?? 0.2) * 100)} of residual`
				}
			]
		: []
)
</script>

{#if !outputs || !wf}
<div class="h-full flex items-center justify-center px-6 text-sm text-slate-400">
	Generate an HBU study to view the equity waterfall.
</div>
{:else}
<div class="h-full overflow-auto">
<div class="px-4 py-4 space-y-5">
	<!-- Waterfall steps table -->
	<div class="rounded-xl border border-slate-200 overflow-hidden">
		<div class="px-4 py-2.5 bg-[#1F3864]">
			<span class="text-xs font-semibold text-white uppercase tracking-[0.12em]">Equity Waterfall</span>
		</div>
		<table class="w-full text-sm">
			<thead>
				<tr class="bg-slate-50 text-[11px] uppercase tracking-[0.12em] text-slate-400">
					<th class="text-center px-4 py-2 font-medium w-16">Step</th>
					<th class="text-left px-4 py-2 font-medium">Distribution</th>
					<th class="text-right px-4 py-2 font-medium">Amount</th>
					<th class="text-left px-4 py-2 font-medium">Basis</th>
				</tr>
			</thead>
			<tbody>
				{#each steps as row, i (i)}
					<tr class="border-t border-slate-100 {row.isTotal ? 'bg-[#EEF2F7] font-semibold' : ''}">
						<td class="px-4 py-2 text-center text-slate-400">{row.step > 0 ? row.step : ''}</td>
						<td class="px-4 py-2 text-slate-800">{row.label}</td>
						<td class="px-4 py-2 text-right font-medium text-slate-900">{row.amount}</td>
						<td class="px-4 py-2 text-slate-500 text-xs">{row.note}</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>

	<!-- Return metrics -->
	<div class="grid gap-3 sm:grid-cols-3">
		<div class="rounded-xl border border-slate-200 px-4 py-3">
			<p class="text-[10px] uppercase tracking-[0.12em] text-slate-400">Equity MOIC</p>
			<p class="text-base font-semibold text-slate-900 mt-1">{fmt(outputs.returns.equityMoic, 2)}x</p>
		</div>
		<div class="rounded-xl border border-slate-200 px-4 py-3">
			<p class="text-[10px] uppercase tracking-[0.12em] text-slate-400">Equity IRR</p>
			<p class="text-base font-semibold text-slate-900 mt-1">{outputs.returns.equityIrrPct != null ? fmtPct(outputs.returns.equityIrrPct) : 'N/A'}</p>
		</div>
		<div class="rounded-xl border border-slate-200 px-4 py-3">
			<p class="text-[10px] uppercase tracking-[0.12em] text-slate-400">Levered Margin on Equity</p>
			<p class="text-base font-semibold text-slate-900 mt-1">{fmtPct(outputs.returns.leveredMarginOnEquityPct)}</p>
		</div>
	</div>
</div>
</div>
{/if}
