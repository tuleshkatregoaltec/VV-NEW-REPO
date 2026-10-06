<script lang="ts">
import type { DdaPlotFeature } from '$lib/api/projects'
import {
	createCoordinateProjector,
	normalizeCoordinates,
	pointsToAttribute
} from '$lib/utils/plotGeometry'

const WIDTH = 1000
const HEIGHT = 620
const PAD = 42

let {
	plots = [],
	selectedPlotNumber = null,
	visiblePlotNumbers = new Set<string>(),
	availablePlotNumbers = new Set<string>(),
	loading = false,
	onPlotSelect,
	className = ''
}: {
	plots?: DdaPlotFeature[]
	selectedPlotNumber?: string | null
	visiblePlotNumbers?: Set<string>
	availablePlotNumbers?: Set<string>
	loading?: boolean
	onPlotSelect?: (plot: DdaPlotFeature) => void
	className?: string
} = $props()

const validPlots = $derived(
	plots.filter((plot) => normalizeCoordinates(plot.coordinates).length >= 3)
)
const coordinateSets = $derived(validPlots.map((plot) => normalizeCoordinates(plot.coordinates)))
const projector = $derived(createCoordinateProjector(coordinateSets, WIDTH, HEIGHT, PAD))
const renderedPlots = $derived.by(() => {
	const currentProjector = projector
	if (!currentProjector) return []
	return validPlots
		.map((plot) => {
			const points = normalizeCoordinates(plot.coordinates).map(currentProjector)
			const selected = selectedPlotNumber === plot.plot_number
			const visible = visiblePlotNumbers.has(plot.plot_number)
			const available =
				availablePlotNumbers.size === 0 || availablePlotNumbers.has(plot.plot_number)
			return { plot, points, selected, visible, available }
		})
		.sort((a, b) => Number(a.selected) - Number(b.selected))
})

function plotCategory(plot: DdaPlotFeature) {
	const label = (plot.land_use_summary?.[0] ?? plot.gfa_type ?? '').toLowerCase()
	if (label.includes('residential') || label.includes('villa') || label.includes('apartment')) {
		return 'residential'
	}
	if (label.includes('commercial') || label.includes('retail') || label.includes('office')) {
		return 'commercial'
	}
	if (label.includes('open space') || label.includes('landscape') || label.includes('park')) {
		return 'open'
	}
	return 'planning'
}

function fillColor(plot: DdaPlotFeature) {
	const category = plotCategory(plot)
	if (category === 'residential') return '#0f766e'
	if (category === 'commercial') return '#2563eb'
	if (category === 'open') return '#65a30d'
	return '#f59e0b'
}

function areaLabel(plot: DdaPlotFeature) {
	const sqm = plot.plot_area_sqm
	if (!Number.isFinite(sqm)) return ''
	return sqm >= 1000 ? `${(sqm / 1000).toFixed(1)}k sqm` : `${Math.round(sqm)} sqm`
}

function selectPlot(plot: DdaPlotFeature) {
	onPlotSelect?.(plot)
}
</script>

<div
	class={`relative min-h-[240px] overflow-hidden rounded-lg border border-slate-200 bg-slate-950 ${className}`}
>
	{#if renderedPlots.length > 0}
		<svg
			viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
			class="block h-full min-h-[240px] w-full"
			role="img"
			aria-label="DDA parcel map"
		>
			<defs>
				<pattern id="parcel-map-grid" width="40" height="40" patternUnits="userSpaceOnUse">
					<path d="M 40 0 L 0 0 0 40" fill="none" stroke="rgba(148,163,184,0.12)" stroke-width="1" />
				</pattern>
				<filter id="selected-parcel-shadow" x="-15%" y="-15%" width="130%" height="130%">
					<feDropShadow dx="0" dy="9" stdDeviation="7" flood-color="#020617" flood-opacity="0.32" />
				</filter>
			</defs>
			<rect width={WIDTH} height={HEIGHT} fill="#0f172a" />
			<rect width={WIDTH} height={HEIGHT} fill="url(#parcel-map-grid)" />

			{#each renderedPlots as item (item.plot.plot_number)}
				{#if item.available}
					<a
						href={`#plot-${item.plot.plot_number}`}
						aria-label={`Select plot ${item.plot.plot_number}, ${item.plot.project_name}`}
						class="cursor-pointer outline-none"
						onclick={(event: MouseEvent) => {
							event.preventDefault()
							selectPlot(item.plot)
						}}
					>
						<title>
							Plot {item.plot.plot_number} · {item.plot.project_name} · {areaLabel(item.plot)}
						</title>
						<polygon
							points={pointsToAttribute(item.points)}
							fill={item.selected ? '#14b8a6' : item.visible ? fillColor(item.plot) : '#94a3b8'}
							fill-opacity={item.selected ? '0.78' : item.visible ? '0.36' : '0.12'}
							stroke={item.selected ? '#fef3c7' : item.visible ? 'rgba(255,255,255,0.5)' : 'rgba(226,232,240,0.24)'}
							stroke-width={item.selected ? '4' : '1.4'}
							vector-effect="non-scaling-stroke"
							filter={item.selected ? 'url(#selected-parcel-shadow)' : undefined}
							class="transition-opacity duration-200 hover:opacity-90 focus:opacity-90"
						/>
					</a>
				{:else}
					<g>
						<title>
							Plot {item.plot.plot_number} · {item.plot.project_name} · {areaLabel(item.plot)}
						</title>
						<polygon
							points={pointsToAttribute(item.points)}
							fill={item.selected ? '#14b8a6' : item.visible ? fillColor(item.plot) : '#94a3b8'}
							fill-opacity={item.selected ? '0.78' : item.visible ? '0.36' : '0.12'}
							stroke={item.selected ? '#fef3c7' : item.visible ? 'rgba(255,255,255,0.5)' : 'rgba(226,232,240,0.24)'}
							stroke-width={item.selected ? '4' : '1.4'}
							vector-effect="non-scaling-stroke"
							filter={item.selected ? 'url(#selected-parcel-shadow)' : undefined}
							class="transition-opacity duration-200"
						/>
					</g>
				{/if}
			{/each}
		</svg>
		<div class="absolute left-3 top-3 rounded-md border border-white/10 bg-slate-950/80 px-3 py-2 text-xs text-slate-300 shadow-sm backdrop-blur">
			<span class="font-semibold text-white">{renderedPlots.length.toLocaleString()}</span>
			parcel map
		</div>
	{:else}
		<div class="flex h-full min-h-[240px] items-center justify-center px-6 text-center text-sm text-slate-400">
			{loading ? 'Loading parcel map…' : 'Select a community to load its parcel map.'}
		</div>
	{/if}

	{#if loading && renderedPlots.length > 0}
		<div class="absolute right-3 top-3 rounded-md border border-white/10 bg-slate-950/80 px-3 py-1.5 text-xs font-medium text-slate-300 shadow-sm backdrop-blur">
			Loading…
		</div>
	{/if}
</div>
