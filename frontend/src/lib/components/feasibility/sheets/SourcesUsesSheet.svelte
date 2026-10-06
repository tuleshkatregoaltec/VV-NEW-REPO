<script lang="ts">
import { workbookStore } from '$lib/feasibility/workbook/store.svelte'

function fmt(value: number | null | undefined, digits = 0) {
	if (value === null || value === undefined || !Number.isFinite(value)) return '—'
	return value.toLocaleString('en-AE', {
		minimumFractionDigits: digits,
		maximumFractionDigits: digits
	})
}

const outputs = $derived(workbookStore.outputs)
const su = $derived(outputs?.sourcesUses)
const isBtr = $derived(workbookStore.assumptions?.developmentModel === 'build_to_rent_residential')
const btr = $derived(outputs?.btr)
const gapAed = $derived(su?.gapAed ?? 0)
const gapOk = $derived(Math.abs(gapAed) < 1000)
const btrSu = $derived(btr?.sourcesUses)
const btrGapAed = $derived(btrSu ? btrSu.totalSourcesAed - btrSu.totalUsesAed : 0)
const btrGapOk = $derived(Math.abs(btrGapAed) < 1000)
</script>

{#if isBtr && btr && btrSu}
<div class="overflow-auto flex-1 bg-white text-[11px] font-[Calibri,'Segoe_UI',Arial,sans-serif] select-none">

	<div class="bg-[#1F3864] border-b-2 border-[#1F3864] text-white px-4 py-2.5 flex items-center justify-between gap-4">
		<div class="text-[13px] font-bold tracking-wide">BTR SOURCES &amp; USES OF FUNDS</div>
		<div class="text-[10px] {btrGapOk ? 'text-blue-200' : 'text-rose-300'} shrink-0">
			Funding gap AED {fmt(btrGapAed)}
		</div>
	</div>

	<table class="w-full border-collapse" style="border-spacing:0">
		<tbody>
		<!-- SOURCES -->
		<tr class="bg-[#1F3864]">
			<td colspan="3" class="px-2 py-[4px] text-white font-bold text-[11px] tracking-wide">A.&nbsp;&nbsp;CAPITAL SOURCES</td>
		</tr>
		<tr class="bg-[#D6DCE4] border-b border-[#B8C4CE]">
			<th class="px-2 py-[4px] text-left text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Source</th>
			<th class="px-2 py-[4px] text-left text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Basis</th>
			<th class="px-2 py-[4px] text-right text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Amount (AED)</th>
		</tr>
		{#each [
			{ label: 'Acquisition debt', basis: 'Peak LTV-based land tranche', amount: btrSu.peakAcqDebtAed },
			{ label: 'Construction debt', basis: 'Peak LTC-based construction tranche', amount: btrSu.peakConDebtAed },
			{ label: 'Sponsor equity', basis: 'Net monthly equity contributions after refund-tail releases', amount: btrSu.actualEquityAed },
			{ label: 'VAT refund / equity release', basis: 'Input VAT recovered during dev tail', amount: btrSu.vatRefundsAed },
		] as row (row.label)}
			{#if row.amount > 0}
			<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
				<td class="px-2 py-[3px] text-left text-[10px] text-slate-800">{row.label}</td>
				<td class="px-2 py-[3px] text-left text-[9px] text-slate-500">{row.basis}</td>
				<td class="px-2 py-[3px] text-right tabular-nums text-[10px] font-medium text-emerald-700">{fmt(row.amount)}</td>
			</tr>
			{/if}
		{/each}
		<tr class="border-t-2 border-[#B8C4CE] bg-[#EEF2F7] font-semibold">
			<td class="px-2 py-[4px] text-left text-[10px] text-slate-900" colspan="2">Total Sources</td>
			<td class="px-2 py-[4px] text-right tabular-nums text-[10px] text-slate-900 font-bold">{fmt(btrSu.totalSourcesAed)}</td>
		</tr>

		<!-- USES -->
		<tr class="bg-[#1F3864]">
			<td colspan="3" class="px-2 py-[4px] text-white font-bold text-[11px] tracking-wide">B.&nbsp;&nbsp;CAPITAL USES</td>
		</tr>
		<tr class="bg-[#D6DCE4] border-b border-[#B8C4CE]">
			<th class="px-2 py-[4px] text-left text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Use</th>
			<th class="px-2 py-[4px] text-left text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Basis</th>
			<th class="px-2 py-[4px] text-right text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Amount (AED)</th>
		</tr>
		{#each [
			{ label: 'Dev cost excl. VAT', basis: 'Land + construction + statutory + lease-up', amount: btrSu.totalDevCostExclVatAed },
			{ label: 'VAT (gross paid)', basis: '5% on applicable cost categories', amount: btrSu.totalVatAed },
			{ label: 'Dev financing costs', basis: 'Construction-period interest carry', amount: btrSu.devFinancingCostsAed },
		] as row (row.label)}
			<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
				<td class="px-2 py-[3px] text-left text-[10px] text-slate-800">{row.label}</td>
				<td class="px-2 py-[3px] text-left text-[9px] text-slate-500">{row.basis}</td>
				<td class="px-2 py-[3px] text-right tabular-nums text-[10px] font-medium text-slate-900">{fmt(row.amount)}</td>
			</tr>
		{/each}
		<tr class="border-t-2 border-[#B8C4CE] bg-[#EEF2F7] font-semibold">
			<td class="px-2 py-[4px] text-left text-[10px] text-slate-900" colspan="2">Total Uses</td>
			<td class="px-2 py-[4px] text-right tabular-nums text-[10px] text-slate-900 font-bold">{fmt(btrSu.totalUsesAed)}</td>
		</tr>

		<!-- Funding gap -->
		<tr class="border-t-2 border-[#1F3864] {btrGapOk ? 'bg-[#EEF2F7]' : 'bg-[#FFF3F3]'}">
			<td class="px-2 py-[4px] text-left text-[10px] font-bold {btrGapOk ? 'text-slate-900' : 'text-rose-800'}">Funding Gap</td>
			<td class="px-2 py-[4px] text-left text-[9px] {btrGapOk ? 'text-slate-500' : 'text-rose-600'}"></td>
			<td class="px-2 py-[4px] text-right tabular-nums text-[10px] font-bold {btrGapOk ? 'text-slate-900' : 'text-rose-700'}">AED {fmt(btrGapAed)}</td>
		</tr>
		</tbody>
	</table>

	<div class="py-3"></div>
</div>
{:else if !outputs || !su}
<div class="h-full flex items-center justify-center px-6 text-sm text-slate-400">
	Generate an HBU study to view sources & uses.
</div>
{:else}
<div class="overflow-auto flex-1 bg-white text-[11px] font-[Calibri,'Segoe_UI',Arial,sans-serif] select-none">

	<div class="bg-[#1F3864] border-b-2 border-[#1F3864] text-white px-4 py-2.5 flex items-center justify-between gap-4">
		<div class="text-[13px] font-bold tracking-wide">SOURCES &amp; USES OF FUNDS</div>
		<div class="text-[10px] {gapOk ? 'text-blue-200' : 'text-rose-300'} shrink-0">
			Funding gap AED {fmt(gapAed)}
		</div>
	</div>

	<table class="w-full border-collapse" style="border-spacing:0">
		<tbody>

		<!-- Sources -->
		<tr class="bg-[#1F3864]">
			<td colspan="3" class="px-2 py-[4px] text-white font-bold text-[11px] tracking-wide">A.&nbsp;&nbsp;CAPITAL SOURCES</td>
		</tr>
		<tr class="bg-[#D6DCE4] border-b border-[#B8C4CE]">
			<th class="px-2 py-[4px] text-left text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Source</th>
			<th class="px-2 py-[4px] text-left text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Basis</th>
			<th class="px-2 py-[4px] text-right text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Amount (AED)</th>
		</tr>
		{#each su.sources as row (row.code)}
			<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
				<td class="px-2 py-[3px] text-left text-[10px] text-slate-800">{row.label}</td>
				<td class="px-2 py-[3px] text-left text-[9px] text-slate-500">{row.basis}</td>
				<td class="px-2 py-[3px] text-right tabular-nums text-[10px] font-medium text-emerald-700">{fmt(row.amountAed)}</td>
			</tr>
		{/each}
		<tr class="border-t-2 border-[#B8C4CE] bg-[#EEF2F7] font-semibold">
			<td class="px-2 py-[4px] text-left text-[10px] text-slate-900" colspan="2">Total Sources</td>
			<td class="px-2 py-[4px] text-right tabular-nums text-[10px] text-slate-900 font-bold">{fmt(su.totalSourcesAed)}</td>
		</tr>

		<!-- Uses -->
		<tr class="bg-[#1F3864]">
			<td colspan="3" class="px-2 py-[4px] text-white font-bold text-[11px] tracking-wide">B.&nbsp;&nbsp;CAPITAL USES</td>
		</tr>
		<tr class="bg-[#D6DCE4] border-b border-[#B8C4CE]">
			<th class="px-2 py-[4px] text-left text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Use</th>
			<th class="px-2 py-[4px] text-left text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Basis</th>
			<th class="px-2 py-[4px] text-right text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Amount (AED)</th>
		</tr>
		{#each su.uses as row (row.code)}
			<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
				<td class="px-2 py-[3px] text-left text-[10px] text-slate-800">{row.label}</td>
				<td class="px-2 py-[3px] text-left text-[9px] text-slate-500">{row.basis}</td>
				<td class="px-2 py-[3px] text-right tabular-nums text-[10px] font-medium text-emerald-700">{fmt(row.amountAed)}</td>
			</tr>
		{/each}
		<tr class="border-t-2 border-[#B8C4CE] bg-[#EEF2F7] font-semibold">
			<td class="px-2 py-[4px] text-left text-[10px] text-slate-900" colspan="2">Total Uses</td>
			<td class="px-2 py-[4px] text-right tabular-nums text-[10px] text-slate-900 font-bold">{fmt(su.totalUsesAed)}</td>
		</tr>

		<!-- Funding gap row -->
		<tr class="border-t-2 border-[#1F3864] {gapOk ? 'bg-[#EEF2F7]' : 'bg-[#FFF3F3]'}">
			<td class="px-2 py-[4px] text-left text-[10px] font-bold {gapOk ? 'text-slate-900' : 'text-rose-800'}">Funding Gap</td>
			<td class="px-2 py-[4px] text-left text-[9px] {gapOk ? 'text-slate-500' : 'text-rose-600'}"></td>
			<td class="px-2 py-[4px] text-right tabular-nums text-[10px] font-bold {gapOk ? 'text-slate-900' : 'text-rose-700'}">AED {fmt(gapAed)}</td>
		</tr>

		</tbody>
	</table>

	<div class="py-3"></div>
</div>
{/if}
