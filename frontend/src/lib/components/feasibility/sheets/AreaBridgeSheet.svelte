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
const area = $derived(outputs?.area)
const assumptions = $derived(workbookStore.assumptions)

type BridgeRow = { label: string; sqm: string; note: string; isTotal?: boolean; isSub?: boolean }

const bridgeRows = $derived<BridgeRow[]>(
	area
		? [
				{ label: 'Plot Area', sqm: fmt(area.plotAreaSqm), note: 'From DDA plot data' },
				{ label: 'Max GFA (Regulatory)', sqm: fmt(area.maxGfaSqm), note: 'From site plan' },
				{
					label: 'Above-grade Costable BUA',
					sqm: fmt(area.aboveGradeCostableBua),
					note: `GFA × ${fmt(assumptions?.aboveGradeBuaFactor ?? 1.1, 2)} factor`
				},
				{
					label: 'Basement Parking BUA',
					sqm: fmt(area.basementParkingBua),
					note: `${assumptions?.basementParkingFloors ?? 4} floors × floorplate`,
					isSub: true
				},
				{
					label: 'Podium Parking BUA Add-on',
					sqm: fmt(area.podiumParkingBuaAddon),
					note: `${assumptions?.podiumParkingFloorsOutsideGfa ?? 0} floors outside GFA`,
					isSub: true
				},
				{
					label: 'Service / BOH / Plant Add-on',
					sqm: fmt(area.serviceBohPlantAddon),
					note: `${fmtPct((assumptions?.serviceBohPlantPct ?? 0.03) * 100)} of above-grade BUA`,
					isSub: true
				},
				{
					label: 'Total Costable BUA',
					sqm: fmt(area.totalCostableBua),
					note: 'Sum of all above',
					isTotal: true
				},
				{
					label: 'Sellable Area (NSA)',
					sqm: fmt(area.sellableArea),
					note: `GFA × ${fmtPct(assumptions?.nsaEfficiencyPct ?? 80)} efficiency`
				}
			]
		: []
)

const ratioRows = $derived(
	area
		? [
				{ label: 'NSA / GFA Ratio', value: fmtPct(area.nsaGfaRatio * 100) },
				{ label: 'NSA / Costable BUA', value: fmtPct(area.nsaCostableBuaRatio * 100) },
				{ label: 'Costable BUA / GFA', value: fmtPct(area.costableBuaGfaRatio * 100) }
			]
		: []
)
</script>

{#if !outputs}
<div class="h-full flex items-center justify-center px-6 text-sm text-slate-400">
	Generate an HBU study to view the area bridge.
</div>
{:else}
<div class="h-full overflow-auto">
<div class="px-4 py-4 space-y-5">
	<!-- Area Bridge Table -->
	<div class="rounded-xl border border-slate-200 overflow-hidden">
		<div class="px-4 py-2.5 bg-[#1F3864]">
			<span class="text-xs font-semibold text-white uppercase tracking-[0.12em]">GFA to Costable BUA Reconciliation</span>
		</div>
		<table class="w-full text-sm">
			<thead>
				<tr class="bg-slate-50 text-[11px] uppercase tracking-[0.12em] text-slate-400">
					<th class="text-left px-4 py-2 font-medium">Component</th>
					<th class="text-right px-4 py-2 font-medium">Area (sqm)</th>
					<th class="text-left px-4 py-2 font-medium">Basis</th>
				</tr>
			</thead>
			<tbody>
				{#each bridgeRows as row (row.label)}
					<tr class="border-t border-slate-100 {row.isTotal ? 'bg-[#EEF2F7] font-semibold' : ''} {row.isSub ? 'bg-[#F9F9F9]' : ''}">
						<td class="px-4 py-2 text-slate-800 {row.isSub ? 'pl-8' : ''}">{row.label}</td>
						<td class="px-4 py-2 text-right text-slate-900">{row.sqm}</td>
						<td class="px-4 py-2 text-slate-500 text-xs">{row.note}</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>

	<!-- Ratios -->
	<div class="rounded-xl border border-slate-200 overflow-hidden">
		<div class="px-4 py-2.5 bg-[#1F3864]">
			<span class="text-xs font-semibold text-white uppercase tracking-[0.12em]">Area Ratios</span>
		</div>
		<table class="w-full text-sm">
			<tbody>
				{#each ratioRows as row (row.label)}
					<tr class="border-t border-slate-100">
						<td class="px-4 py-2 text-slate-600">{row.label}</td>
						<td class="px-4 py-2 text-right font-medium text-slate-900">{row.value}</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>

	<!-- Notes -->
	{#if area && area.notes.length > 0}
		<div class="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3">
			<p class="text-[10px] uppercase tracking-[0.12em] text-amber-500 mb-2">Area Notes</p>
			<ul class="list-disc list-inside text-sm text-amber-800 space-y-1">
				{#each area.notes as note}
					<li>{note}</li>
				{/each}
			</ul>
		</div>
	{/if}
</div>
</div>
{/if}
