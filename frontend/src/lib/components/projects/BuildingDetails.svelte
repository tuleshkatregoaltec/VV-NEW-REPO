<script lang="ts">
import type { BuildingDetailResponse } from '$lib/api/projects'

let {
	building,
	onBack
}: {
	building: BuildingDetailResponse
	onBack: () => void
} = $props()
</script>

<div class="p-5 space-y-5">
	<!-- Back button + header -->
	<div class="border-b border-slate-200 pb-4">
		<button
			onclick={onBack}
			class="flex items-center gap-1.5 text-xs text-slate-500 hover:text-fg-1 transition-colors mb-3"
		>
			<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7"
				></path>
			</svg>
			Back to {building.project_name}
		</button>

		<div class="flex items-start gap-2">
			<div
				class="w-8 h-8 bg-primary-light rounded-md flex items-center justify-center flex-shrink-0 mt-0.5"
			>
				<svg class="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
					<path
						stroke-linecap="round"
						stroke-linejoin="round"
						stroke-width="2"
						d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16"
					></path>
				</svg>
			</div>
			<div>
				<h2 class="text-xl font-semibold text-fg-1 leading-tight">
					{building.building_number ? `Building ${building.building_number}` : 'Building'}
				</h2>
				<p class="text-sm text-slate-500 mt-0.5">{building.project_name}</p>
			</div>
		</div>
	</div>

	<!-- Stats -->
	<div class="grid grid-cols-2 gap-3">
		{#if building.floors}
			<div class="bg-slate-50 rounded-xl p-3 border border-slate-100">
				<div class="text-xs text-slate-500 mb-1">Floors</div>
				<div class="font-display text-2xl font-normal tracking-normal text-fg-1">{building.floors}</div>
			</div>
		{/if}
		{#if building.total_units > 0}
			<div class="bg-slate-50 rounded-xl p-3 border border-slate-100">
				<div class="text-xs text-slate-500 mb-1">Registered Units</div>
				<div class="font-display text-2xl font-normal tracking-normal text-fg-1">{building.total_units.toLocaleString()}</div>
			</div>
		{/if}
	</div>

	<!-- Unit composition by bedroom -->
	{#if building.unit_composition.length > 0}
		<div class="space-y-2.5">
			<h3 class="text-sm font-semibold text-slate-700 uppercase tracking-wide">Unit Mix</h3>
			<div class="space-y-2">
				{#each building.unit_composition as unit (unit.rooms_en)}
					<div>
						<div class="flex items-center justify-between mb-1">
							<span class="text-sm font-medium text-slate-700">{unit.rooms_en}</span>
							<div class="flex items-center gap-2">
								{#if unit.avg_area_sqm}
									<span class="text-xs text-slate-400">{unit.avg_area_sqm} m²</span>
								{/if}
								<span class="text-xs text-slate-500">{unit.count} · {unit.percentage}%</span>
							</div>
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
	{:else}
		<p class="text-sm text-slate-400 text-center py-4">No unit data available for this building.</p>
	{/if}

	<!-- Note about project-level analytics -->
	<div class="bg-slate-50 rounded-xl p-3 border border-slate-100 text-xs text-slate-500">
		Sale price and rental analytics are shown at the project level. Select the project to view full
		analytics.
	</div>
</div>
