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
const vat = $derived(outputs?.vatBridge)
const netOk = $derived(Math.abs(vat?.netVatPosition ?? 0) < 1000)
</script>

{#if !outputs || !vat}
<div class="h-full flex items-center justify-center px-6 text-sm text-slate-400">
	Generate an HBU study to view the VAT bridge.
</div>
{:else}
<div class="overflow-auto flex-1 bg-white text-[11px] font-[Calibri,'Segoe_UI',Arial,sans-serif] select-none">

	<div class="bg-[#1F3864] border-b-2 border-[#1F3864] text-white px-4 py-2.5 flex items-center justify-between gap-4">
		<div class="text-[13px] font-bold tracking-wide">VAT BRIDGE</div>
		<div class="text-[10px] {netOk ? 'text-blue-200' : 'text-rose-300'} shrink-0">
			Net VAT position AED {fmt(vat.netVatPosition)}
		</div>
	</div>

	<table class="w-full border-collapse" style="border-spacing:0">
		<tbody>

		<!-- Per-category VAT -->
		<tr class="bg-[#1F3864]">
			<td colspan="4" class="px-2 py-[4px] text-white font-bold text-[11px] tracking-wide">A.&nbsp;&nbsp;VAT BY COST CATEGORY</td>
		</tr>
		<tr class="bg-[#D6DCE4] border-b border-[#B8C4CE]">
			<th class="px-2 py-[4px] text-left text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Category</th>
			<th class="px-2 py-[4px] text-right text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Cost (AED)</th>
			<th class="px-2 py-[4px] text-center text-[9px] font-semibold text-slate-600 uppercase tracking-wider">VAT?</th>
			<th class="px-2 py-[4px] text-right text-[9px] font-semibold text-slate-600 uppercase tracking-wider">VAT (AED)</th>
		</tr>
		{#each vat.categories as cat (cat.label)}
			<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
				<td class="px-2 py-[3px] text-left text-[10px] text-slate-800">{cat.label}</td>
				<td class="px-2 py-[3px] text-right tabular-nums text-[10px] text-slate-900">{fmt(cat.costAed)}</td>
				<td class="px-2 py-[3px] text-center text-[9px] {cat.vatApplicable ? 'text-emerald-700' : 'text-slate-400'}">{cat.vatApplicable ? 'Yes' : 'No'}</td>
				<td class="px-2 py-[3px] text-right tabular-nums text-[10px] font-medium text-slate-900">{fmt(cat.vatAed)}</td>
			</tr>
		{/each}
		<tr class="border-t-2 border-[#B8C4CE] bg-[#EEF2F7] font-semibold">
			<td class="px-2 py-[4px] text-left text-[10px] text-slate-900">Total</td>
			<td class="px-2 py-[4px] text-right tabular-nums text-[10px] text-slate-900 font-bold">{fmt(vat.totalCostAed)}</td>
			<td class="px-2 py-[4px]"></td>
			<td class="px-2 py-[4px] text-right tabular-nums text-[10px] text-slate-900 font-bold">{fmt(vat.totalVatAed)}</td>
		</tr>

		<!-- Cash Flow Reconciliation -->
		<tr class="bg-[#1F3864]">
			<td colspan="4" class="px-2 py-[4px] text-white font-bold text-[11px] tracking-wide">B.&nbsp;&nbsp;VAT CASH FLOW RECONCILIATION</td>
		</tr>
		{#each [
			{ label: 'Budget VAT', value: fmt(vat.totalVatAed), ok: true },
			{ label: 'Monthly VAT Paid', value: fmt(vat.totalVatPaidMonthly), ok: true },
			{ label: 'VAT Refunded', value: fmt(vat.totalVatRefunded), ok: true },
			{ label: 'Net VAT Position', value: fmt(vat.netVatPosition), ok: netOk }
		] as row (row.label)}
			<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60 {row.label === 'Net VAT Position' ? (row.ok ? 'bg-[#E8F5E9]' : 'bg-[#FFF3F3]') : ''}">
				<td class="px-2 py-[3px] text-left text-[10px] text-slate-800 {row.label === 'Net VAT Position' ? 'font-semibold' : ''}" colspan="3">{row.label}</td>
				<td class="px-2 py-[3px] text-right tabular-nums text-[10px] font-medium {row.label === 'Net VAT Position' ? (row.ok ? 'text-slate-900' : 'text-rose-700') : 'text-slate-900'}">AED {row.value}</td>
			</tr>
		{/each}

		</tbody>
	</table>

	<div class="py-3"></div>
</div>
{/if}
