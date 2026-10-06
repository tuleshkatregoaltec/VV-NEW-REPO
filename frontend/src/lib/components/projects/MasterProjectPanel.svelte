<script lang="ts">
import type { MasterProjectResponse } from '$lib/api/projects'

let {
	master,
	onProjectSelect
}: {
	master: MasterProjectResponse
	onProjectSelect: (projectId: number) => void
} = $props()

function statusLabel(status: string | null): string {
	if (status === 'C') return 'Completed'
	if (status === 'U') return 'Under Construction'
	if (status === 'P') return 'Planned'
	return status || ''
}

function statusColor(status: string | null): string {
	if (status === 'C') return 'bg-emerald-100 text-emerald-700'
	if (status === 'U') return 'bg-amber-100 text-amber-700'
	if (status === 'P') return 'bg-blue-100 text-blue-700'
	return 'bg-slate-100 text-slate-600'
}

function getProjectKey(project: MasterProjectResponse['projects'][number], index: number): string {
	return [
		project.project_id,
		project.project_name,
		project.project_status,
		project.percent_completed,
		index
	]
		.filter((value) => value != null && value !== '')
		.join(':')
}
</script>

<div class="p-5 space-y-5">
	<!-- Header -->
	<div class="border-b border-slate-200 pb-4">
		<div class="flex items-center gap-2 mb-1">
			<span
				class="text-[10px] font-semibold uppercase tracking-wider text-fg-4 bg-slate-100 px-2 py-0.5 rounded-sm"
				>Master Project</span
			>
		</div>
		<h2 class="text-xl font-semibold text-fg-1 leading-tight">{master.master_name}</h2>
		<div class="flex flex-wrap items-center gap-x-2 gap-y-1 mt-2 text-sm text-slate-500">
			<span class="flex items-center gap-1">
				<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
					<path
						stroke-linecap="round"
						stroke-linejoin="round"
						stroke-width="2"
						d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z"
					></path>
					<path
						stroke-linecap="round"
						stroke-linejoin="round"
						stroke-width="2"
						d="M15 11a3 3 0 11-6 0 3 3 0 016 0z"
					></path>
				</svg>
				{master.area_name}
			</span>
			{#if master.developer_name}
				<span class="text-slate-300">•</span>
				<span>{master.developer_name}</span>
			{/if}
		</div>
	</div>

	<!-- Stats grid -->
	<div class="grid grid-cols-3 gap-3">
		<div class="bg-slate-50 rounded-xl p-3 border border-slate-100 text-center">
			<div class="text-xs text-slate-500 mb-1">Projects</div>
			<div class="font-display text-2xl font-normal tracking-normal text-fg-1">{master.total_projects}</div>
		</div>
		<div class="bg-slate-50 rounded-xl p-3 border border-slate-100 text-center">
			<div class="text-xs text-slate-500 mb-1">Buildings</div>
			<div class="font-display text-2xl font-normal tracking-normal text-fg-1">{master.total_buildings.toLocaleString()}</div>
		</div>
		<div class="bg-slate-50 rounded-xl p-3 border border-slate-100 text-center">
			<div class="text-xs text-slate-500 mb-1">Units</div>
			<div class="font-display text-2xl font-normal tracking-normal text-fg-1">{master.total_units.toLocaleString()}</div>
		</div>
	</div>

	<!-- Unit mix -->
	{#if master.unit_composition.length > 0}
		<div class="space-y-2.5">
			<h3 class="text-sm font-semibold text-slate-700 uppercase tracking-wide">Unit Mix</h3>
			<div class="space-y-2">
				{#each master.unit_composition as unit (unit.property_sub_type)}
					<div>
						<div class="flex items-center justify-between mb-1">
							<span class="text-sm font-medium text-slate-700">{unit.property_sub_type}</span>
							<span class="text-xs text-slate-500"
								>{unit.count.toLocaleString()} · {unit.percentage}%</span
							>
						</div>
						<div class="w-full bg-slate-200 rounded-full h-1.5">
							<div
								class="bg-primary-light h-1.5 rounded-full"
								style="width: {unit.percentage}%"
							></div>
						</div>
					</div>
				{/each}
			</div>
		</div>
	{/if}

	<!-- Sub-projects list -->
	<div class="space-y-2">
		<h3 class="text-sm font-semibold text-slate-700 uppercase tracking-wide">
			Sub-Projects ({master.total_projects})
		</h3>
		<div class="space-y-1.5 max-h-72 overflow-y-auto">
			{#each master.projects as project, index (getProjectKey(project, index))}
				<button
					onclick={() => onProjectSelect(project.project_id)}
					class="w-full text-left bg-slate-50 rounded-lg px-3 py-2.5 border border-border hover:bg-slate-100 hover:border-slate-300 transition-colors"
				>
					<div class="flex items-start justify-between gap-2">
						<div class="min-w-0 flex-1">
							<div class="text-sm font-medium text-slate-900 truncate">{project.project_name}</div>
							<div class="flex items-center gap-2 mt-1 text-xs text-slate-500">
								{#if project.no_of_buildings}
									<span>{project.no_of_buildings} bldgs</span>
								{/if}
								{#if project.no_of_units}
									<span>· {project.no_of_units.toLocaleString()} units</span>
								{/if}
								{#if project.percent_completed != null && project.project_status !== 'C'}
									<span>· {project.percent_completed}%</span>
								{/if}
							</div>
						</div>
						<div class="flex items-center gap-1.5 flex-shrink-0">
							{#if project.project_status}
								<span
									class="text-[10px] font-medium px-1.5 py-0.5 rounded-full {statusColor(
										project.project_status
									)}"
								>
									{statusLabel(project.project_status)}
								</span>
							{/if}
							<svg
								class="w-3.5 h-3.5 text-slate-400"
								fill="none"
								stroke="currentColor"
								viewBox="0 0 24 24"
							>
								<path
									stroke-linecap="round"
									stroke-linejoin="round"
									stroke-width="2"
									d="M9 5l7 7-7 7"
								></path>
							</svg>
						</div>
					</div>
				</button>
			{/each}
		</div>
	</div>
</div>
