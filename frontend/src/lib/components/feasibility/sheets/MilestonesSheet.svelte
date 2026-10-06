<script lang="ts">
import { workbookStore } from '$lib/feasibility/workbook/store.svelte'

const outputs = $derived(workbookStore.outputs)
const ms = $derived(outputs?.milestones)

const milestones = $derived(
	ms
		? [
				{ label: 'Land Acquisition', date: ms.landAcquisition },
				{ label: 'Construction Start', date: ms.constructionStart },
				{ label: 'Sales Commencement', date: ms.salesCommencement },
				{ label: 'Pre-Handover Milestone', date: ms.preHandoverMilestone },
				{ label: 'Handover', date: ms.handover }
			]
		: []
)
</script>

{#if !outputs || !ms}
<div class="h-full flex items-center justify-center px-6 text-sm text-slate-400">
	Generate an HBU study to view the project milestones.
</div>
{:else}
<div class="overflow-auto flex-1 bg-white text-[11px] font-[Calibri,'Segoe_UI',Arial,sans-serif] select-none">

	<div class="bg-[#1F3864] border-b-2 border-[#1F3864] text-white px-4 py-2.5">
		<div class="text-[13px] font-bold tracking-wide">PROJECT MILESTONES &amp; SCHEDULE</div>
	</div>

	<table class="w-full border-collapse" style="border-spacing:0">
		<tbody>

		<!-- Timeline -->
		<tr class="bg-[#1F3864]">
			<td colspan="3" class="px-2 py-[4px] text-white font-bold text-[11px] tracking-wide">A.&nbsp;&nbsp;PROJECT TIMELINE</td>
		</tr>
		<tr class="bg-[#D6DCE4] border-b border-[#B8C4CE]">
			<th class="px-2 py-[4px] text-center text-[9px] font-semibold text-slate-600 uppercase tracking-wider w-8">#</th>
			<th class="px-2 py-[4px] text-left text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Milestone</th>
			<th class="px-2 py-[4px] text-right text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Date</th>
		</tr>
		{#each milestones as m, idx (m.label)}
			<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
				<td class="px-2 py-[3px] text-center text-[10px] text-slate-400">{idx + 1}</td>
				<td class="px-2 py-[3px] text-left text-[10px] text-slate-800">{m.label}</td>
				<td class="px-2 py-[3px] text-right tabular-nums text-[10px] text-slate-900">{m.date}</td>
			</tr>
		{/each}

		<!-- Durations -->
		<tr class="bg-[#1F3864]">
			<td colspan="3" class="px-2 py-[4px] text-white font-bold text-[11px] tracking-wide">B.&nbsp;&nbsp;DURATIONS</td>
		</tr>
		{#each [
			{ label: 'Construction Period', value: `${ms.constructionMonths} months` },
			{ label: 'Sales Period', value: `${ms.salesPeriodMonths} months` },
			{ label: 'Total Project Duration', value: `${ms.totalProjectMonths} months` }
		] as d (d.label)}
			<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
				<td class="px-2 py-[3px] text-center text-[10px] text-slate-400">—</td>
				<td class="px-2 py-[3px] text-left text-[10px] text-slate-800">{d.label}</td>
				<td class="px-2 py-[3px] text-right tabular-nums text-[10px] text-slate-900 font-medium">{d.value}</td>
			</tr>
		{/each}

		</tbody>
	</table>

	<div class="py-3"></div>
</div>
{/if}
