<script lang="ts">
import { createQuery } from '@tanstack/svelte-query'
import { untrack } from 'svelte'
import type { DdaPlotFeature } from '$lib/api/projects'
import { workbookStore } from '$lib/feasibility/workbook/store.svelte'
import { projectQueries } from '$lib/queries/projects'
import type { LngLatPoint, SvgPoint } from '$lib/utils/plotGeometry'
import {
	boundsCenterDistance,
	boundsDistance,
	clamp,
	coordinateBounds,
	createCoordinateProjector,
	normalizeCoordinates,
	pointBounds,
	pointsToAttribute,
	polygonArea
} from '$lib/utils/plotGeometry'

type Point = SvgPoint
type Placement = { x: number; y: number; w: number; h: number; rotation: number }
type SurroundingPlot = { plot: DdaPlotFeature; edgeDistance: number; centerDistance: number }

const WIDTH = 1000
const HEIGHT = 680
const PAD = 56

let svgEl = $state<SVGSVGElement | null>(null)
let placements = $state<Record<string, Placement>>({})
let placementSignature = $state('')
let dragging = $state<{ id: string; dx: number; dy: number } | null>(null)

const plotData = $derived(workbookStore.plotData)
const massing = $derived(workbookStore.outputs?.siteMassing)
const buildings = $derived(massing?.buildings ?? [])
const ddaQueryParams = $derived(
	plotData?.community_name ? { area: plotData.community_name, limit: 5000 } : null
)
const ddaPlotsQuery = createQuery(() => projectQueries.ddaPlots(ddaQueryParams))
const ddaPlots = $derived<DdaPlotFeature[]>(ddaQueryParams ? (ddaPlotsQuery.data ?? []) : [])
const selectedDdaPlot = $derived(
	ddaPlots.find((plot) => plot.plot_number === plotData?.plot_number) ?? null
)
const savedPlotCoordinates = $derived(normalizeCoordinates(plotData?.coordinates))
const selectedDdaCoordinates = $derived(normalizeCoordinates(selectedDdaPlot?.coordinates))
const selectedCoordinates = $derived(
	selectedDdaCoordinates.length >= 3 ? selectedDdaCoordinates : savedPlotCoordinates
)
const usingDdaGeometry = $derived(selectedDdaCoordinates.length >= 3)

function fmt(value: number | null | undefined, digits = 0) {
	if (value === null || value === undefined || !Number.isFinite(value)) return '-'
	return value.toLocaleString('en-AE', {
		minimumFractionDigits: digits,
		maximumFractionDigits: digits
	})
}

function nearestSurroundingPlots(
	plots: DdaPlotFeature[],
	selected: LngLatPoint[],
	selectedPlotNumber: string | null | undefined
) {
	const selectedBounds = coordinateBounds(selected)
	if (!selectedBounds) return []
	return plots
		.filter((plot) => plot.plot_number !== selectedPlotNumber)
		.map((plot): SurroundingPlot | null => {
			const bounds = coordinateBounds(normalizeCoordinates(plot.coordinates))
			if (!bounds) return null
			return {
				plot,
				edgeDistance: boundsDistance(selectedBounds, bounds),
				centerDistance: boundsCenterDistance(selectedBounds, bounds)
			}
		})
		.filter((item) => item !== null)
		.sort((a, b) => a.edgeDistance - b.edgeDistance || a.centerDistance - b.centerDistance)
		.slice(0, 18)
		.map((item) => item.plot)
}

const surroundingPlots = $derived(
	nearestSurroundingPlots(
		ddaPlots,
		usingDdaGeometry ? selectedDdaCoordinates : [],
		plotData?.plot_number
	)
)
const coordinateProjector = $derived(
	createCoordinateProjector(
		selectedCoordinates.length >= 3 ? [selectedCoordinates] : [],
		WIDTH,
		HEIGHT,
		PAD
	)
)

function fallbackPolygon(): Point[] {
	const plotArea = plotData?.plot_area_sqm ?? 0
	const maxGfa = plotData?.max_gfa_sqm ?? 0
	const aspect = clamp(maxGfa > 0 && plotArea > 0 ? Math.sqrt(maxGfa / plotArea) : 1.35, 0.85, 1.85)
	const w = 760
	const h = w / aspect
	const x = (WIDTH - w) / 2
	const y = (HEIGHT - h) / 2
	return [
		{ x, y },
		{ x: x + w, y },
		{ x: x + w, y: y + h },
		{ x, y: y + h }
	]
}

function projectedPolygon(): Point[] {
	if (selectedCoordinates.length < 3 || !coordinateProjector) return fallbackPolygon()
	return selectedCoordinates.map(coordinateProjector)
}

const polygon = $derived(projectedPolygon())
const polygonPoints = $derived(pointsToAttribute(polygon))
const surroundingPolygons = $derived.by(() => {
	if (!coordinateProjector) return []
	return surroundingPlots
		.map((plot) => ({
			plot,
			points: normalizeCoordinates(plot.coordinates).map(coordinateProjector)
		}))
		.filter((item) => {
			if (item.points.length < 3) return false
			const bounds = pointBounds(item.points)
			return (
				bounds.maxX >= -WIDTH * 0.5 &&
				bounds.minX <= WIDTH * 1.5 &&
				bounds.maxY >= -HEIGHT * 0.5 &&
				bounds.minY <= HEIGHT * 1.5
			)
		})
})
const hasCoordinates = $derived(selectedCoordinates.length >= 3)

function defaultPlacement(index: number, total: number, footprintSqm: number): Placement {
	const cols = Math.max(1, Math.ceil(Math.sqrt(total)))
	const rows = Math.max(1, Math.ceil(total / cols))
	const col = index % cols
	const row = Math.floor(index / cols)
	const bounds = pointBounds(polygon)
	const gridPad = Math.min(28, Math.max(10, Math.min(bounds.w, bounds.h) * 0.08))
	const cellW = Math.max((bounds.w - gridPad * 2) / cols, 1)
	const cellH = Math.max((bounds.h - gridPad * 2) / rows, 1)
	const plotArea = Math.max(plotData?.plot_area_sqm ?? massing?.plotAreaSqm ?? footprintSqm, 1)
	const footprintRatio = clamp(footprintSqm / plotArea, 0.005, 0.95)
	const plotAreaPx = Math.max(polygonArea(polygon), bounds.w * bounds.h * 0.45, 1)
	const areaPx = footprintRatio * plotAreaPx
	const side = clamp(Math.sqrt(areaPx), 26, Math.min(cellW, cellH) * 0.82)
	const w = side * 1.15
	const h = side * 0.85
	return {
		x: bounds.minX + gridPad + cellW * col + (cellW - w) / 2,
		y: bounds.minY + gridPad + cellH * row + (cellH - h) / 2,
		w,
		h,
		rotation: total > 1 ? (index % 2 === 0 ? -4 : 4) : 0
	}
}

$effect(() => {
	if (!buildings.length) {
		const current = untrack(() => placements)
		if (Object.keys(current).length > 0) placements = {}
		placementSignature = ''
		return
	}
	const nextSignature = [
		polygonPoints,
		...buildings.map(
			(building) =>
				`${building.id}:${Math.round(building.footprintSqm)}:${building.totalFloors}:${building.totalUnits}`
		)
	].join('|')
	const signatureChanged = untrack(() => placementSignature) !== nextSignature
	const current = untrack(() => placements)
	const next: Record<string, Placement> = {}
	for (const [index, building] of buildings.entries()) {
		next[building.id] =
			signatureChanged || !current[building.id]
				? defaultPlacement(index, buildings.length, building.footprintSqm)
				: current[building.id]
	}
	const currentKeys = Object.keys(current)
	const nextKeys = Object.keys(next)
	const changed =
		signatureChanged ||
		currentKeys.length !== nextKeys.length ||
		nextKeys.some((key) => current[key] === undefined)
	if (changed) {
		placements = next
		placementSignature = nextSignature
	}
})

function pointerToSvg(event: PointerEvent): Point {
	if (!svgEl) return { x: 0, y: 0 }
	const rect = svgEl.getBoundingClientRect()
	return {
		x: ((event.clientX - rect.left) / rect.width) * WIDTH,
		y: ((event.clientY - rect.top) / rect.height) * HEIGHT
	}
}

function startDrag(event: PointerEvent, id: string) {
	const placement = placements[id]
	if (!placement) return
	const point = pointerToSvg(event)
	dragging = { id, dx: point.x - placement.x, dy: point.y - placement.y }
	event.currentTarget instanceof Element && event.currentTarget.setPointerCapture?.(event.pointerId)
}

function drag(event: PointerEvent) {
	if (!dragging) return
	const placement = placements[dragging.id]
	if (!placement) return
	const point = pointerToSvg(event)
	placements = {
		...placements,
		[dragging.id]: {
			...placement,
			x: clamp(point.x - dragging.dx, PAD / 2, WIDTH - placement.w - PAD / 2),
			y: clamp(point.y - dragging.dy, PAD / 2, HEIGHT - placement.h - PAD / 2)
		}
	}
}

function endDrag() {
	dragging = null
}

function rotatePlacement(id: string, delta: number) {
	const placement = placements[id]
	if (!placement) return
	placements = {
		...placements,
		[id]: {
			...placement,
			rotation: placement.rotation + delta
		}
	}
}

function resetPlacements() {
	const next: Record<string, Placement> = {}
	for (const [index, building] of buildings.entries()) {
		next[building.id] = defaultPlacement(index, buildings.length, building.footprintSqm)
	}
	placements = next
}
</script>

<svelte:window onpointermove={drag} onpointerup={endDrag} />

<div class="space-y-4">
	<div class="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm">
		<div class="flex items-start justify-between gap-3">
			<div>
				<p class="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Plot Sandbox</p>
				<h3 class="mt-1 text-base font-semibold text-slate-900">GIS outline and massing annotation</h3>
				<p class="mt-1 text-xs leading-5 text-slate-500">
					Drag the building blocks to sketch a site-test-fit. This is an annotation layer only; it does not change model returns yet.
				</p>
			</div>
			<button
				type="button"
				class="rounded-full border border-slate-300 px-3 py-1 text-[11px] font-semibold text-slate-600 transition hover:border-teal-400 hover:text-teal-700"
				onclick={resetPlacements}
			>
				Reset
			</button>
		</div>

		<div class="mt-4 overflow-hidden rounded-2xl border border-slate-200 bg-slate-950">
			<svg
				bind:this={svgEl}
				viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
				class="block aspect-[1.47/1] w-full touch-none"
				role="img"
				aria-label="Plot annotation sandbox"
			>
				<defs>
					<pattern id="sandbox-grid" width="40" height="40" patternUnits="userSpaceOnUse">
						<path d="M 40 0 L 0 0 0 40" fill="none" stroke="rgba(148,163,184,0.16)" stroke-width="1" />
					</pattern>
					<filter id="building-shadow" x="-20%" y="-20%" width="140%" height="140%">
						<feDropShadow dx="0" dy="8" stdDeviation="8" flood-color="#020617" flood-opacity="0.28" />
					</filter>
					<filter id="selected-plot-glow" x="-10%" y="-10%" width="120%" height="120%">
						<feDropShadow dx="0" dy="0" stdDeviation="5" flood-color="#5eead4" flood-opacity="0.32" />
					</filter>
				</defs>
				<rect width={WIDTH} height={HEIGHT} fill="#0f172a" />
				<rect width={WIDTH} height={HEIGHT} fill="url(#sandbox-grid)" />
				{#each surroundingPolygons as surrounding (surrounding.plot.plot_number)}
					<polygon
						points={pointsToAttribute(surrounding.points)}
						fill="rgba(148,163,184,0.16)"
						stroke="rgba(226,232,240,0.32)"
						stroke-width="1.5"
						vector-effect="non-scaling-stroke"
					/>
				{/each}
				<polygon
					points={polygonPoints}
					fill="rgba(20,184,166,0.22)"
					stroke="#5eead4"
					stroke-width="4"
					vector-effect="non-scaling-stroke"
					filter="url(#selected-plot-glow)"
				/>
				<polygon
					points={polygonPoints}
					fill="none"
					stroke="rgba(255,255,255,0.52)"
					stroke-width="1"
					stroke-dasharray="8 10"
					vector-effect="non-scaling-stroke"
				/>

				{#each buildings as building, index (building.id)}
					{@const placement = placements[building.id]}
					{#if placement}
						<g
							transform={`translate(${placement.x + placement.w / 2} ${placement.y + placement.h / 2}) rotate(${placement.rotation}) translate(${-placement.w / 2} ${-placement.h / 2})`}
							class="cursor-grab active:cursor-grabbing"
							onpointerdown={(event) => startDrag(event, building.id)}
						>
							<rect
								width={placement.w}
								height={placement.h}
								rx="14"
								fill={index % 2 === 0 ? '#38bdf8' : '#34d399'}
								fill-opacity="0.9"
								stroke="white"
								stroke-opacity="0.75"
								stroke-width="2"
								filter="url(#building-shadow)"
							/>
							<line x1="14" y1="18" x2={placement.w - 14} y2="18" stroke="rgba(255,255,255,0.55)" stroke-width="2" />
							<line x1="14" y1={placement.h - 18} x2={placement.w - 14} y2={placement.h - 18} stroke="rgba(255,255,255,0.35)" stroke-width="2" />
							<text x="16" y={placement.h / 2 - 4} fill="#082f49" font-size="24" font-weight="700">
								{index + 1}
							</text>
							<text x="16" y={placement.h / 2 + 20} fill="#0f172a" font-size="15" font-weight="600">
								{fmt(building.totalFloors)} fl
							</text>
						</g>
					{/if}
				{/each}
			</svg>
		</div>

		<div class="mt-3 rounded-2xl border border-slate-200 bg-slate-50 p-3 text-xs text-slate-600">
			{#if hasCoordinates}
				Using {selectedCoordinates.length} GIS coordinate points from the plot file
				{#if surroundingPolygons.length > 0}
					with {surroundingPolygons.length} surrounding parcels for context.
				{:else if ddaPlotsQuery.isFetching}
					while surrounding parcels load.
				{:else}
					without nearby parcel context.
				{/if}
			{:else}
				No plot polygon coordinates were available, so the canvas is using a scaled placeholder outline.
			{/if}
		</div>
	</div>

	<div class="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm">
		<p class="text-sm font-semibold text-slate-900">Massing Schedule</p>
		<div class="mt-3 space-y-2">
			{#if buildings.length === 0}
				<p class="text-sm text-slate-500">Generate or open a workbook to produce massing outputs.</p>
			{:else}
				{#each buildings as building (building.id)}
					<div class="rounded-2xl border border-slate-200 bg-white p-3">
						<div class="flex items-center justify-between gap-3">
							<p class="text-sm font-semibold text-slate-900">{building.label}</p>
							<p class="text-xs font-medium text-teal-700">{fmt(building.footprintSqm)} sqm footprint</p>
						</div>
						<div class="mt-2 grid grid-cols-3 gap-2 text-xs text-slate-600">
							<div><span class="text-slate-400">Floors</span><br />{fmt(building.totalFloors)}</div>
							<div><span class="text-slate-400">Height</span><br />{fmt(building.estimatedHeightM, 1)} m</div>
							<div><span class="text-slate-400">Units</span><br />{fmt(building.totalUnits)}</div>
						</div>
						<div class="mt-3 flex items-center gap-2">
							<button
								type="button"
								class="rounded-full border border-slate-200 px-3 py-1 text-[11px] font-semibold text-slate-600 transition hover:border-sky-300 hover:text-sky-700"
								onclick={() => rotatePlacement(building.id, -15)}
							>
								Rotate -15 deg
							</button>
							<button
								type="button"
								class="rounded-full border border-slate-200 px-3 py-1 text-[11px] font-semibold text-slate-600 transition hover:border-sky-300 hover:text-sky-700"
								onclick={() => rotatePlacement(building.id, 15)}
							>
								Rotate +15 deg
							</button>
						</div>
					</div>
				{/each}
			{/if}
		</div>
	</div>
</div>
