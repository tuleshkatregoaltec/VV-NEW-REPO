<script lang="ts">
import { createQuery } from '@tanstack/svelte-query'
import {
	Activity,
	ArrowLeft,
	Building2,
	Clock3,
	Eye,
	EyeOff,
	Layers3,
	LocateFixed,
	MapPinned,
	PanelLeftClose,
	PanelLeftOpen,
	Search,
	SlidersHorizontal,
	Target,
	TrendingUp,
	X
} from 'lucide-svelte'
import { untrack } from 'svelte'
import type {
	BuildingDetailResponse,
	DdaOutlineFeature,
	DdaPlotFeature,
	GeoPin,
	ProjectDetailResponse,
	ProjectRadarArea,
	ProjectRadarProject
} from '$lib/api/projects'
import AppFrame from '$lib/components/layout/AppFrame.svelte'
import PageContainer from '$lib/components/layout/PageContainer.svelte'
import ProjectMap from '$lib/components/map/ProjectMap.svelte'
import BuildingDetails from '$lib/components/projects/BuildingDetails.svelte'
import { projectQueries } from '$lib/queries/projects'

type PanelView = 'overview' | 'project' | 'area' | 'building'
type RadarOverlayMode = 'pipeline' | 'demand' | 'yield' | 'delivery'
type ProjectStage = 'Next 12m' | 'Future' | 'Unscheduled' | 'Finished'
type DdaLayerMode = 'outlines' | 'parcels'
type DdaMapFeature = DdaOutlineFeature | DdaPlotFeature
interface DdaViewport {
	west: number
	south: number
	east: number
	north: number
	zoom: number
}
interface DdaRequestViewport extends DdaViewport {
	mode: DdaLayerMode
	zoomBucket: number
}

const DDA_PARCEL_MIN_ZOOM = 14
const DDA_OUTLINE_PADDING = 0.45
const DDA_PARCEL_PADDING = 0.45
const DUBAI_CENTER_LNG = 55.2708
const DUBAI_CENTER_LAT = 25.2048
const RADAR_OVERVIEW_ZOOM = 11

let isMinimized = $state(false)
let panelView = $state<PanelView>('overview')
let mapComponent = $state<any>()
let selectedProjectId = $state<number | null>(null)
let selectedAreaName = $state<string | null>(null)
let selectedBuildingId = $state<number | null>(null)
let searchQuery = $state('')
let overlayMode = $state<RadarOverlayMode>('pipeline')
let showProjectPins = $state(true)
let showAreaBubbles = $state(true)
let showDDAPlots = $state(false)
let showBuildingPins = $state(true)
let activeStages = $state<ProjectStage[]>(['Next 12m', 'Future', 'Unscheduled', 'Finished'])
let ddaViewport = $state<DdaViewport | null>(null)
let ddaRequestViewport = $state<DdaRequestViewport | null>(null)
let renderedDDAFeatures = $state<DdaMapFeature[]>([])
let renderedDDAMode = $state<DdaLayerMode>('outlines')

const stageOptions: ProjectStage[] = ['Next 12m', 'Future', 'Unscheduled', 'Finished']
const radarQuery = createQuery(() => projectQueries.radar(1800))
const projectDetailsQuery = createQuery(() =>
	projectQueries.detail(
		panelView === 'project' || panelView === 'building' ? selectedProjectId : null
	)
)
const buildingDetailsQuery = createQuery(() =>
	projectQueries.building(panelView === 'building' ? selectedBuildingId : null)
)

const radar = $derived(radarQuery.data ?? null)
const stats = $derived(radar?.stats ?? null)
const radarProjects = $derived<ProjectRadarProject[]>(radar?.projects ?? [])
const radarAreas = $derived<ProjectRadarArea[]>(dedupeAreas(radar?.areas ?? []))
const projectDetails = $derived<ProjectDetailResponse | null>(projectDetailsQuery.data ?? null)
const buildingDetails = $derived<BuildingDetailResponse | null>(buildingDetailsQuery.data ?? null)
const selectedRadarProject = $derived(
	radarProjects.find((project) => project.project_id === selectedProjectId) ?? null
)
const selectedArea = $derived(
	radarAreas.find(
		(area) => area.area_name === (selectedAreaName ?? selectedRadarProject?.area_name)
	) ?? null
)
const selectedProjectStage = $derived(
	selectedRadarProject ? getProjectStage(selectedRadarProject) : null
)
const selectedProjectIsUpcoming = $derived(
	selectedProjectStage === 'Next 12m' ||
		selectedProjectStage === 'Future' ||
		selectedProjectStage === 'Unscheduled'
)
const mapZoom = $derived(ddaViewport?.zoom ?? 11)
const ddaLayerMode = $derived<DdaLayerMode>(getDdaLayerMode(mapZoom))
const ddaDataMode = $derived<DdaLayerMode>(ddaRequestViewport?.mode ?? ddaLayerMode)
const ddaOutlineParams = $derived.by(() => {
	if (!showDDAPlots || !ddaRequestViewport || ddaRequestViewport.mode !== 'outlines') return null
	return {
		west: roundCoordinate(ddaRequestViewport.west),
		south: roundCoordinate(ddaRequestViewport.south),
		east: roundCoordinate(ddaRequestViewport.east),
		north: roundCoordinate(ddaRequestViewport.north),
		zoom: roundZoom(ddaRequestViewport.zoom),
		limit: ddaRequestViewport.zoom >= 12 ? 120 : 48
	}
})
const ddaPlotParams = $derived.by(() => {
	if (!showDDAPlots || !ddaRequestViewport || ddaRequestViewport.mode !== 'parcels') return null
	const limit = ddaRequestViewport.zoom >= 15 ? 2200 : 900
	return {
		west: roundCoordinate(ddaRequestViewport.west),
		south: roundCoordinate(ddaRequestViewport.south),
		east: roundCoordinate(ddaRequestViewport.east),
		north: roundCoordinate(ddaRequestViewport.north),
		limit,
		include_valuations: true
	}
})
const ddaOutlinesQuery = createQuery(() => projectQueries.ddaOutlines(ddaOutlineParams))
const ddaPlotsQuery = createQuery(() => projectQueries.ddaPlots(ddaPlotParams))
const ddaOutlines = $derived(showDDAPlots ? (ddaOutlinesQuery.data ?? []) : [])
const ddaPlots = $derived(showDDAPlots ? (ddaPlotsQuery.data ?? []) : [])
const visibleDDAFeatures = $derived(ddaDataMode === 'parcels' ? ddaPlots : ddaOutlines)
const visibleDDAQueryLoading = $derived(
	ddaDataMode === 'parcels'
		? ddaPlotsQuery.isPending || ddaPlotsQuery.isFetching
		: ddaOutlinesQuery.isPending || ddaOutlinesQuery.isFetching
)
const visibleDDALabel = $derived(
	renderedDDAMode === 'parcels' ? 'visible parcels' : 'planning outlines'
)
const hasActiveSelection = $derived(
	panelView !== 'overview' ||
		selectedProjectId != null ||
		selectedAreaName != null ||
		selectedBuildingId != null
)
const activeSelectionLabel = $derived.by(() => {
	if (panelView === 'building') {
		if (buildingDetails?.building_number) return `Building ${buildingDetails.building_number}`
		return buildingDetails?.project_name ?? projectDetails?.project_name ?? 'Building details'
	}
	if (panelView === 'project') {
		return selectedRadarProject?.project_name ?? projectDetails?.project_name ?? 'Project details'
	}
	if (panelView === 'area') return selectedArea?.area_name ?? selectedAreaName ?? 'Area lens'
	return 'Radar overview'
})

const filteredMapProjects = $derived.by(() =>
	radarProjects.filter((project) => activeStages.includes(getProjectStage(project)))
)
const visibleMapProjects = $derived.by(() => {
	const limit = mapProjectRenderLimit(mapZoom)
	if (filteredMapProjects.length <= limit) return filteredMapProjects
	const selected = selectedProjectId
		? filteredMapProjects.find((project) => project.project_id === selectedProjectId)
		: null
	const ranked = [...filteredMapProjects]
		.sort((a, b) => mapPinScore(b) - mapPinScore(a))
		.slice(0, limit)
	if (selected && !ranked.some((project) => project.project_id === selected.project_id)) {
		ranked.push(selected)
	}
	return ranked
})

const searchResults = $derived.by(() => {
	const query = searchQuery.trim().toLowerCase()
	if (query.length < 2) return { projects: [], areas: [] }
	return {
		projects: radarProjects
			.filter((project) =>
				[
					project.project_name,
					project.area_name,
					project.developer_name ?? '',
					project.master_project_en ?? ''
				]
					.join(' ')
					.toLowerCase()
					.includes(query)
			)
			.slice(0, 7),
		areas: radarAreas.filter((area) => area.area_name.toLowerCase().includes(query)).slice(0, 5)
	}
})

const topAreas = $derived(
	[...radarAreas].sort((a, b) => b.pipeline_units - a.pipeline_units).slice(0, 5)
)

const rankedProjects = $derived.by(() => {
	const projects = [...filteredMapProjects]
	if (overlayMode === 'demand') {
		return projects
			.sort(
				(a, b) =>
					b.sales_transaction_count_12m +
					b.rental_contract_count_12m -
					(a.sales_transaction_count_12m + a.rental_contract_count_12m)
			)
			.slice(0, 6)
	}
	if (overlayMode === 'yield') {
		return projects.sort((a, b) => (b.gross_yield_pct ?? 0) - (a.gross_yield_pct ?? 0)).slice(0, 6)
	}
	if (overlayMode === 'delivery') {
		return projects.sort((a, b) => b.delivery_confidence - a.delivery_confidence).slice(0, 6)
	}
	return projects.sort((a, b) => b.no_of_units - a.no_of_units).slice(0, 6)
})

const isLoading = $derived(
	radarQuery.isPending ||
		(panelView === 'project' &&
			(projectDetailsQuery.isPending || projectDetailsQuery.isFetching)) ||
		(panelView === 'building' &&
			(buildingDetailsQuery.isPending || buildingDetailsQuery.isFetching))
)

function dedupeAreas(areas: ProjectRadarArea[]): ProjectRadarArea[] {
	const seen = new Set<string>()
	return areas.filter((area) => {
		const key = area.area_name.trim().toLowerCase()
		if (seen.has(key)) return false
		seen.add(key)
		return true
	})
}

function roundCoordinate(value: number): number {
	return Math.round(value * 1000) / 1000
}

function roundZoom(value: number): number {
	return Math.round(value * 4) / 4
}

function getDdaLayerMode(zoom: number): DdaLayerMode {
	return zoom >= DDA_PARCEL_MIN_ZOOM ? 'parcels' : 'outlines'
}

function getDdaZoomBucket(zoom: number, mode: DdaLayerMode): number {
	if (mode === 'outlines') return 0
	return zoom >= 15 ? 15 : 14
}

function paddedViewport(viewport: DdaViewport, mode: DdaLayerMode): DdaRequestViewport {
	const padding = mode === 'parcels' ? DDA_PARCEL_PADDING : DDA_OUTLINE_PADDING
	const lngPad = (viewport.east - viewport.west) * padding
	const latPad = (viewport.north - viewport.south) * padding
	return {
		west: Math.max(54, viewport.west - lngPad),
		south: Math.max(24, viewport.south - latPad),
		east: Math.min(57, viewport.east + lngPad),
		north: Math.min(26, viewport.north + latPad),
		zoom: viewport.zoom,
		mode,
		zoomBucket: getDdaZoomBucket(viewport.zoom, mode)
	}
}

function viewportContains(outer: DdaRequestViewport, inner: DdaViewport): boolean {
	return (
		outer.west <= inner.west &&
		outer.south <= inner.south &&
		outer.east >= inner.east &&
		outer.north >= inner.north
	)
}

function ensureDdaRequestViewport(viewport: DdaViewport) {
	const mode = getDdaLayerMode(viewport.zoom)
	const zoomBucket = getDdaZoomBucket(viewport.zoom, mode)
	if (
		!ddaRequestViewport ||
		ddaRequestViewport.mode !== mode ||
		ddaRequestViewport.zoomBucket !== zoomBucket ||
		!viewportContains(ddaRequestViewport, viewport)
	) {
		ddaRequestViewport = paddedViewport(viewport, mode)
	}
}

function handleViewportChange(viewport: DdaViewport) {
	ddaViewport = viewport
	if (showDDAPlots) ensureDdaRequestViewport(viewport)
}

function mapProjectRenderLimit(zoom: number): number {
	if (zoom < 11.75) return 520
	if (zoom < 12.75) return 1000
	return 2400
}

function stageScore(project: ProjectRadarProject): number {
	const stage = getProjectStage(project)
	if (stage === 'Next 12m') return 3000
	if (stage === 'Future') return 2200
	if (stage === 'Unscheduled') return 1400
	return 700
}

function mapPinScore(project: ProjectRadarProject): number {
	return (
		stageScore(project) +
		(project.no_of_units ?? 0) +
		(project.sales_transaction_count_12m + project.rental_contract_count_12m) * 0.35 +
		(project.delivery_confidence ?? 0) * 500
	)
}

function getProjectStage(project: ProjectRadarProject): ProjectStage {
	if (project.completion_status === 'FINISHED') return 'Finished'
	if (project.pipeline_status === 'delivering_next_12_months') return 'Next 12m'
	if (project.pipeline_status === 'future') return 'Future'
	return 'Unscheduled'
}

function formatCompact(value: number | null | undefined): string {
	const resolved = Number(value ?? 0)
	if (resolved >= 1_000_000_000) return `${(resolved / 1_000_000_000).toFixed(1)}B`
	if (resolved >= 1_000_000) return `${(resolved / 1_000_000).toFixed(1)}M`
	if (resolved >= 1_000) return `${Math.round(resolved / 1_000)}K`
	return Math.round(resolved).toLocaleString()
}

function formatCurrency(value: number | null | undefined): string {
	if (!value) return '-'
	return `AED ${formatCompact(value)}`
}

function formatPct(value: number | null | undefined): string {
	if (value == null || !Number.isFinite(value)) return '-'
	return `${value.toFixed(1)}%`
}

function modeLabel(mode: RadarOverlayMode) {
	if (mode === 'demand') return 'Demand'
	if (mode === 'yield') return 'Yield'
	if (mode === 'delivery') return 'Delivery'
	return 'Pipeline'
}

function projectMetric(project: ProjectRadarProject) {
	if (overlayMode === 'demand') {
		return `${formatCompact(project.sales_transaction_count_12m + project.rental_contract_count_12m)} txns`
	}
	if (overlayMode === 'yield') return formatPct(project.gross_yield_pct)
	if (overlayMode === 'delivery') return formatPct(project.delivery_confidence * 100)
	return `${formatCompact(project.no_of_units)} units`
}

function toggleStage(stage: ProjectStage) {
	activeStages = activeStages.includes(stage)
		? activeStages.filter((item) => item !== stage)
		: [...activeStages, stage]
}

function handleProjectSelect(projectId: number) {
	const radarProject = radarProjects.find((project) => project.project_id === projectId)
	selectedProjectId = projectId
	selectedAreaName = radarProject?.area_name ?? selectedAreaName
	selectedBuildingId = null
	panelView = 'project'
	searchQuery = ''
}

function handleAreaSelect(areaName: string) {
	const area = radarAreas.find((item) => item.area_name === areaName)
	selectedAreaName = areaName
	selectedProjectId = null
	selectedBuildingId = null
	panelView = 'area'
	showDDAPlots = true
	if (area?.latitude != null && area.longitude != null && mapComponent) {
		mapComponent.flyToLocation(area.longitude, area.latitude, 14.5)
	}
	searchQuery = ''
}

function handleBuildingSelect(propertyId: number, lng?: number, lat?: number) {
	selectedBuildingId = propertyId
	panelView = 'building'
	if (lng && lat && mapComponent) mapComponent.flyToLocation(lng, lat, 17)
}

function handleBuildingPinClick(pin: GeoPin) {
	if (pin.property_id) {
		handleBuildingSelect(pin.property_id, pin.longitude, pin.latitude)
	} else {
		mapComponent?.flyToLocation(pin.longitude, pin.latitude, 17)
	}
}

function handleBackToProject() {
	selectedBuildingId = null
	panelView = selectedProjectId ? 'project' : 'overview'
}

function resetRadarView() {
	selectedProjectId = null
	selectedAreaName = null
	selectedBuildingId = null
	panelView = 'overview'
	searchQuery = ''
	mapComponent?.clearMarkers?.()
	mapComponent?.flyToLocation?.(DUBAI_CENTER_LNG, DUBAI_CENTER_LAT, RADAR_OVERVIEW_ZOOM)
}

$effect(() => {
	if (showDDAPlots && ddaViewport) {
		ensureDdaRequestViewport(ddaViewport)
	}
	if (!showDDAPlots) {
		ddaRequestViewport = null
		renderedDDAFeatures = []
	}
})

$effect(() => {
	if (!projectDetails || !mapComponent || (panelView !== 'project' && panelView !== 'building'))
		return
	const project = projectDetails
	const map = mapComponent
	const pins = showBuildingPins ? (project.geo_pins ?? []) : []
	untrack(() =>
		map.flyToProject(
			project.project_id,
			project.project_name,
			project.latitude,
			project.longitude,
			project.area_polygon,
			pins,
			13
		)
	)
})

$effect(() => {
	if (!mapComponent) return
	const map = mapComponent
	const features = visibleDDAFeatures
	const enabled = showDDAPlots
	const mode = ddaDataMode
	untrack(() => {
		if (enabled && features.length > 0) {
			renderedDDAFeatures = features
			renderedDDAMode = mode
			map.showDDAFeatures(features, mode)
		} else if (enabled && visibleDDAQueryLoading && renderedDDAFeatures.length > 0) {
			map.showDDAFeatures(renderedDDAFeatures, renderedDDAMode)
		} else {
			renderedDDAFeatures = []
			map.hideDDAPlots()
		}
	})
})
</script>

<AppFrame>
	<PageContainer variant="fullBleed" class="h-full overflow-hidden">
		<div class="relative h-full overflow-hidden bg-slate-950">
			<div class="absolute inset-0">
				<ProjectMap
					bind:this={mapComponent}
					projectPins={visibleMapProjects}
					areaBubbles={radarAreas}
					{selectedProjectId}
					selectedAreaName={selectedArea?.area_name ?? selectedAreaName}
					{showProjectPins}
					{showAreaBubbles}
					{overlayMode}
					onProjectSelect={handleProjectSelect}
					onAreaSelect={handleAreaSelect}
					onBuildingPinClick={handleBuildingPinClick}
					onViewportChange={handleViewportChange}
				/>
			</div>

			<div class="radar-theme-surface absolute bottom-4 right-4 z-10 hidden max-w-sm rounded-md border border-white/60 bg-white/95 px-3 py-2 text-xs text-slate-600 shadow-lg backdrop-blur md:block">
				<div class="flex items-center gap-2 font-medium text-slate-900">
					<span class="h-2.5 w-2.5 rounded-full bg-teal-600"></span>
					{modeLabel(overlayMode)} overlay
				</div>
					<p class="mt-1">
						{visibleMapProjects.length.toLocaleString()} visible projects · {radarAreas.length} area bubbles
						{#if showDDAPlots}
							· {renderedDDAFeatures.length.toLocaleString()} DDA {visibleDDALabel}
						{/if}
					</p>
			</div>

			{#if isMinimized}
				<aside class="radar-theme-surface absolute left-4 top-4 z-20 w-[72px] overflow-hidden rounded-lg border border-slate-200 bg-white/95 shadow-xl backdrop-blur">
					<div class="flex flex-col items-center gap-2 p-3">
						<button
							type="button"
							class="flex h-10 w-10 items-center justify-center rounded-md bg-slate-900 text-white transition-colors hover:bg-slate-700"
							aria-label="Expand radar panel"
							onclick={() => (isMinimized = false)}
						>
							<PanelLeftOpen size={18} />
						</button>
						<div class="h-px w-full bg-slate-200"></div>
						{#if hasActiveSelection}
							<button
								type="button"
								class="flex h-10 w-10 items-center justify-center rounded-md bg-teal-50 text-teal-700 transition-colors hover:bg-teal-100 hover:text-teal-900"
								aria-label="Back to radar overview"
								title="Back to radar overview"
								onclick={resetRadarView}
							>
								<ArrowLeft size={18} />
							</button>
						{/if}
						<button
							type="button"
							class="flex h-10 w-10 items-center justify-center rounded-md {showProjectPins ? 'bg-teal-50 text-teal-700' : 'text-slate-400 hover:bg-slate-100'}"
							aria-label="Toggle project pins"
							onclick={() => (showProjectPins = !showProjectPins)}
						>
							<MapPinned size={18} />
						</button>
						<button
							type="button"
							class="flex h-10 w-10 items-center justify-center rounded-md {showAreaBubbles ? 'bg-sky-50 text-sky-700' : 'text-slate-400 hover:bg-slate-100'}"
							aria-label="Toggle area bubbles"
							onclick={() => (showAreaBubbles = !showAreaBubbles)}
						>
							<Target size={18} />
						</button>
							<button
								type="button"
								class="flex h-10 w-10 items-center justify-center rounded-md {showDDAPlots ? 'bg-amber-50 text-amber-700' : 'text-slate-400 hover:bg-slate-100'}"
								aria-label="Toggle DDA planning layer"
								onclick={() => (showDDAPlots = !showDDAPlots)}
							>
							<Layers3 size={18} />
						</button>
					</div>
				</aside>
			{:else}
				<aside class="radar-theme-surface absolute bottom-4 left-4 top-4 z-20 flex w-[min(440px,calc(100vw-2rem))] flex-col overflow-hidden rounded-lg border border-slate-200 bg-white/95 shadow-2xl backdrop-blur">
					<header class="border-b border-slate-200 px-4 py-3">
						<div class="flex items-start justify-between gap-3">
							<div>
								<div class="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-teal-700">
									<Activity size={14} />
									Projects Radar
								</div>
								<h1 class="mt-1 text-xl font-semibold tracking-normal text-slate-950">
									Supply, demand, and planning signals
								</h1>
							</div>
							<button
								type="button"
								class="flex h-9 w-9 items-center justify-center rounded-md text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-900"
								aria-label="Collapse radar panel"
								onclick={() => (isMinimized = true)}
							>
								<PanelLeftClose size={18} />
							</button>
						</div>

						<div class="mt-3 grid grid-cols-3 gap-2">
							<div class="rounded-md bg-slate-50 px-3 py-2">
								<p class="text-[11px] text-slate-500">Mapped</p>
								<p class="text-sm font-semibold text-slate-950">
									{formatCompact(stats?.mapped_projects)}
								</p>
							</div>
							<div class="rounded-md bg-slate-50 px-3 py-2">
								<p class="text-[11px] text-slate-500">Pipeline units</p>
								<p class="text-sm font-semibold text-slate-950">
									{formatCompact(stats?.pipeline_units)}
								</p>
							</div>
							<div class="rounded-md bg-slate-50 px-3 py-2">
								<p class="text-[11px] text-slate-500">DDA plots</p>
								<p class="text-sm font-semibold text-slate-950">
									{formatCompact(stats?.dda_plot_count)}
								</p>
							</div>
						</div>
					</header>

					<div class="border-b border-slate-200 p-4">
						<div class="relative">
							<Search class="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={16} />
							<input
								bind:value={searchQuery}
								type="search"
								placeholder="Search project, area, developer..."
								class="h-10 w-full rounded-md border border-slate-200 bg-white pl-9 pr-9 text-sm text-slate-900 outline-none transition-colors placeholder:text-slate-400 focus:border-teal-500 focus:ring-2 focus:ring-teal-100"
							/>
							{#if searchQuery}
								<button
									type="button"
									class="absolute right-2 top-1/2 flex h-7 w-7 -translate-y-1/2 items-center justify-center rounded-md text-slate-400 hover:bg-slate-100 hover:text-slate-700"
									aria-label="Clear search"
									onclick={() => (searchQuery = '')}
								>
									<X size={14} />
								</button>
							{/if}
						</div>

						{#if searchQuery.trim().length >= 2}
							<div class="mt-2 max-h-64 overflow-y-auto rounded-md border border-slate-200 bg-white">
								{#each searchResults.projects as project (project.project_id)}
									<button
										type="button"
										class="w-full border-b border-slate-100 px-3 py-2 text-left transition-colors last:border-b-0 hover:bg-slate-50"
										onclick={() => handleProjectSelect(project.project_id)}
									>
										<div class="flex items-center justify-between gap-3">
											<div class="min-w-0">
												<p class="truncate text-sm font-semibold text-slate-950">
													{project.project_name}
												</p>
												<p class="truncate text-xs text-slate-500">
													{project.area_name} · {project.developer_name || 'Developer n/a'}
												</p>
											</div>
											<span class="rounded-sm bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold text-slate-600">
												{getProjectStage(project)}
											</span>
										</div>
									</button>
								{/each}
								{#each searchResults.areas as area, index (`${area.area_id}-${area.area_name}-${index}`)}
									<button
										type="button"
										class="w-full px-3 py-2 text-left transition-colors hover:bg-teal-50"
										onclick={() => handleAreaSelect(area.area_name)}
									>
										<div class="flex items-center justify-between gap-3">
											<div class="min-w-0">
												<p class="truncate text-sm font-semibold text-slate-950">
													{area.area_name}
												</p>
												<p class="truncate text-xs text-slate-500">
													{formatCompact(area.pipeline_units)} pipeline units · {area.dda_plot_count.toLocaleString()} DDA plots
												</p>
											</div>
											<span class="rounded-sm bg-teal-100 px-1.5 py-0.5 text-[10px] font-semibold text-teal-700">
												Area
											</span>
										</div>
									</button>
								{/each}
								{#if searchResults.projects.length === 0 && searchResults.areas.length === 0}
									<p class="px-3 py-5 text-center text-sm text-slate-500">No radar matches.</p>
								{/if}
							</div>
						{/if}
					</div>

					{#if hasActiveSelection}
						<div class="border-b border-slate-200 bg-slate-50/80 px-4 py-3">
							<button
								type="button"
								class="flex w-full items-center gap-3 rounded-md border border-slate-200 bg-white px-3 py-2 text-left transition-colors hover:border-teal-200 hover:bg-teal-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500"
								aria-label="Back to radar overview"
								onclick={resetRadarView}
							>
								<span class="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-md bg-slate-900 text-white">
									<ArrowLeft size={16} />
								</span>
								<span class="min-w-0 flex-1">
									<span class="block text-xs font-semibold uppercase tracking-wide text-slate-500">
										Back to radar overview
									</span>
									<span class="block truncate text-sm font-semibold text-slate-950">
										{activeSelectionLabel}
									</span>
								</span>
							</button>
						</div>
					{/if}

					<div class="flex-1 overflow-y-auto">
							<section class="border-b border-slate-200 p-4">
								<div class="mb-3 flex items-center justify-between">
									<div class="flex items-center gap-2 text-sm font-semibold text-slate-950">
										<SlidersHorizontal size={16} />
										Signal
									</div>
									{#if selectedProjectId || selectedAreaName}
										<button
										type="button"
										class="text-xs font-medium text-slate-500 hover:text-slate-900"
										onclick={resetRadarView}
									>
										Clear
									</button>
								{/if}
							</div>
							<div class="grid grid-cols-4 gap-1 rounded-md bg-slate-100 p-1">
								{#each ['pipeline', 'demand', 'yield', 'delivery'] as mode (mode)}
									<button
										type="button"
										class="rounded px-2 py-1.5 text-xs font-semibold transition-colors {overlayMode === mode ? 'bg-white text-slate-950 shadow-sm' : 'text-slate-500 hover:text-slate-900'}"
										onclick={() => (overlayMode = mode as RadarOverlayMode)}
									>
										{modeLabel(mode as RadarOverlayMode)}
									</button>
								{/each}
							</div>

							<div class="mt-4 flex items-center justify-between">
								<div class="text-sm font-semibold text-slate-950">Layers</div>
								{#if showDDAPlots}
									<div class="text-xs font-medium text-amber-700">
										{renderedDDAFeatures.length.toLocaleString()} {visibleDDALabel}
									</div>
								{/if}
							</div>
							<div class="mt-3 grid grid-cols-2 gap-2">
								<button
									type="button"
									class="flex items-center justify-between rounded-md border px-3 py-2 text-sm transition-colors {showProjectPins ? 'border-teal-200 bg-teal-50 text-teal-800' : 'border-slate-200 text-slate-500 hover:bg-slate-50'}"
									onclick={() => (showProjectPins = !showProjectPins)}
								>
									<span class="flex items-center gap-2"><MapPinned size={15} /> Projects</span>
									{#if showProjectPins}<Eye size={14} />{:else}<EyeOff size={14} />{/if}
								</button>
								<button
									type="button"
									class="flex items-center justify-between rounded-md border px-3 py-2 text-sm transition-colors {showAreaBubbles ? 'border-sky-200 bg-sky-50 text-sky-800' : 'border-slate-200 text-slate-500 hover:bg-slate-50'}"
									onclick={() => (showAreaBubbles = !showAreaBubbles)}
								>
									<span class="flex items-center gap-2"><Target size={15} /> Areas</span>
									{#if showAreaBubbles}<Eye size={14} />{:else}<EyeOff size={14} />{/if}
								</button>
								<button
									type="button"
									class="flex items-center justify-between rounded-md border px-3 py-2 text-sm transition-colors {showDDAPlots ? 'border-amber-200 bg-amber-50 text-amber-800' : 'border-slate-200 text-slate-500 hover:bg-slate-50'}"
									onclick={() => (showDDAPlots = !showDDAPlots)}
								>
									<span class="flex items-center gap-2"><Layers3 size={15} /> DDA planning</span>
									{#if showDDAPlots}<Eye size={14} />{:else}<EyeOff size={14} />{/if}
								</button>
								<button
									type="button"
									class="flex items-center justify-between rounded-md border px-3 py-2 text-sm transition-colors {showBuildingPins ? 'border-slate-300 bg-white text-slate-800' : 'border-slate-200 text-slate-500 hover:bg-slate-50'}"
									onclick={() => (showBuildingPins = !showBuildingPins)}
								>
									<span class="flex items-center gap-2"><Building2 size={15} /> Buildings</span>
									{#if showBuildingPins}<Eye size={14} />{:else}<EyeOff size={14} />{/if}
								</button>
							</div>

							<div class="mt-4 text-sm font-semibold text-slate-950">Project stage</div>
							<div class="mt-2 flex flex-wrap gap-1.5">
								{#each stageOptions as stage (stage)}
									<button
										type="button"
										class="rounded-full border px-2.5 py-1 text-xs font-medium transition-colors {activeStages.includes(stage) ? 'border-slate-900 bg-slate-900 text-white' : 'border-slate-200 text-slate-500 hover:bg-slate-50'}"
										onclick={() => toggleStage(stage)}
									>
										{stage}
									</button>
								{/each}
							</div>
						</section>

						{#if isLoading}
							<div class="flex h-32 items-center justify-center text-sm text-slate-500">
								Loading radar signals...
							</div>
						{:else if panelView === 'building' && buildingDetails}
							<BuildingDetails building={buildingDetails} onBack={handleBackToProject} />
						{:else if panelView === 'project' && (selectedRadarProject || projectDetails)}
							<section class="space-y-4 p-4">
								<div class="rounded-md border border-slate-200 bg-white p-4">
									<div class="flex items-start justify-between gap-3">
										<div class="min-w-0">
											<p class="text-xs font-semibold uppercase tracking-wide text-teal-700">
												{selectedRadarProject ? getProjectStage(selectedRadarProject) : 'Project'}
											</p>
											<h2 class="mt-1 text-lg font-semibold text-slate-950">
												{selectedRadarProject?.project_name ?? projectDetails?.project_name}
											</h2>
											<p class="mt-1 text-sm text-slate-500">
												{selectedRadarProject?.area_name ?? projectDetails?.area_name}
											</p>
										</div>
										<button
											type="button"
											class="flex h-8 w-8 items-center justify-center rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-900"
											aria-label="Center selected project"
											onclick={() => {
												if (projectDetails && mapComponent) {
													mapComponent.flyToLocation(projectDetails.longitude, projectDetails.latitude, 14)
												}
											}}
										>
											<LocateFixed size={16} />
										</button>
									</div>
									{#if selectedRadarProject?.developer_name || selectedRadarProject?.master_project_en}
										<div class="mt-3 grid grid-cols-2 gap-2 text-xs">
											<div class="min-w-0 rounded-md bg-slate-50 px-3 py-2">
												<p class="text-slate-500">Developer</p>
												<p class="mt-0.5 truncate font-semibold text-slate-950">
													{selectedRadarProject?.developer_name ?? 'n/a'}
												</p>
											</div>
											<div class="min-w-0 rounded-md bg-slate-50 px-3 py-2">
												<p class="text-slate-500">Master project</p>
												<p class="mt-0.5 truncate font-semibold text-slate-950">
													{selectedRadarProject?.master_project_en ?? 'n/a'}
												</p>
											</div>
										</div>
									{/if}

									<div class="mt-4 grid grid-cols-2 gap-2">
										{#if selectedProjectIsUpcoming}
											<div class="rounded-md bg-teal-50 px-3 py-2">
												<p class="text-[11px] text-teal-700">Delivery confidence</p>
												<p class="text-sm font-semibold text-slate-950">
													{formatPct((selectedRadarProject?.delivery_confidence ?? 0) * 100)}
												</p>
											</div>
											<div class="rounded-md bg-slate-50 px-3 py-2">
												<p class="text-[11px] text-slate-500">Completion</p>
												<p class="text-sm font-semibold text-slate-950">
													{formatPct(selectedRadarProject?.percent_completed)}
												</p>
											</div>
											<div class="rounded-md bg-slate-50 px-3 py-2">
												<p class="text-[11px] text-slate-500">Pipeline units</p>
												<p class="text-sm font-semibold text-slate-950">
													{formatCompact(selectedRadarProject?.no_of_units ?? projectDetails?.no_of_units)}
												</p>
											</div>
											<div class="rounded-md bg-slate-50 px-3 py-2">
												<p class="text-[11px] text-slate-500">Market activity</p>
												<p class="text-sm font-semibold text-slate-950">
													{formatCompact(
														(selectedRadarProject?.sales_transaction_count_12m ?? 0) +
															(selectedRadarProject?.rental_contract_count_12m ?? 0)
													)}
												</p>
											</div>
										{:else}
											<div class="rounded-md bg-teal-50 px-3 py-2">
												<p class="text-[11px] text-teal-700">Gross yield</p>
												<p class="text-sm font-semibold text-slate-950">
													{formatPct(selectedRadarProject?.gross_yield_pct)}
												</p>
											</div>
											<div class="rounded-md bg-slate-50 px-3 py-2">
												<p class="text-[11px] text-slate-500">Sales volume 12m</p>
												<p class="text-sm font-semibold text-slate-950">
													{formatCurrency(selectedRadarProject?.total_sales_volume_12m)}
												</p>
											</div>
											<div class="rounded-md bg-slate-50 px-3 py-2">
												<p class="text-[11px] text-slate-500">Median sale</p>
												<p class="text-sm font-semibold text-slate-950">
													{formatCurrency(selectedRadarProject?.median_sale_price)}
												</p>
											</div>
											<div class="rounded-md bg-slate-50 px-3 py-2">
												<p class="text-[11px] text-slate-500">Rental contracts</p>
												<p class="text-sm font-semibold text-slate-950">
													{formatCompact(selectedRadarProject?.rental_contract_count_12m)}
												</p>
											</div>
										{/if}
									</div>
								</div>

								{#if selectedArea}
									<div class="rounded-md border border-slate-200 bg-slate-50 p-3">
										<div class="flex items-center justify-between gap-3">
											<div>
												<p class="text-xs font-semibold uppercase tracking-wide text-slate-500">
													Area context
												</p>
												<p class="mt-1 text-sm font-semibold text-slate-950">
													{selectedArea.area_name}
												</p>
											</div>
											<button
												type="button"
												class="rounded-md bg-white px-2.5 py-1.5 text-xs font-semibold text-slate-700 shadow-sm hover:bg-slate-100"
												onclick={() => handleAreaSelect(selectedArea.area_name)}
											>
												Open area
											</button>
										</div>
										<div class="mt-3 grid grid-cols-3 gap-2 text-xs">
											<div>
												<p class="text-slate-500">Pipeline</p>
												<p class="font-semibold text-slate-950">
													{formatCompact(selectedArea.pipeline_units)}
												</p>
											</div>
											<div>
												<p class="text-slate-500">DDA plots</p>
												<p class="font-semibold text-slate-950">
													{formatCompact(selectedArea.dda_plot_count)}
												</p>
											</div>
											<div>
												<p class="text-slate-500">GFA</p>
												<p class="font-semibold text-slate-950">
													{formatCompact(selectedArea.dda_total_gfa_sqm)} sqm
												</p>
											</div>
										</div>
									</div>
								{/if}

								{#if projectDetails?.geo_pins?.length}
									<div class="rounded-md border border-slate-200 bg-white">
										<div class="border-b border-slate-100 px-3 py-2 text-sm font-semibold text-slate-950">
											Building pins ({projectDetails.geo_pins.length})
										</div>
										<div class="max-h-52 overflow-y-auto p-2">
											{#each projectDetails.geo_pins as pin, index (`${pin.property_id ?? 'pin'}-${pin.building_name}-${pin.latitude}-${pin.longitude}-${index}`)}
												<button
													type="button"
													class="flex w-full items-center gap-2 rounded-md px-2 py-2 text-left hover:bg-slate-50"
													onclick={() => handleBuildingPinClick(pin)}
												>
													<span class="flex h-5 w-5 items-center justify-center rounded-full bg-teal-600 text-[10px] font-bold text-white">
														{index + 1}
													</span>
													<span class="min-w-0 flex-1 truncate text-sm text-slate-700">
														{pin.building_name || pin.project_name}
													</span>
												</button>
											{/each}
										</div>
									</div>
								{/if}
							</section>
						{:else if panelView === 'area' && selectedArea}
							<section class="space-y-4 p-4">
								<div class="rounded-md border border-slate-200 bg-white p-4">
									<p class="text-xs font-semibold uppercase tracking-wide text-teal-700">Area lens</p>
									<h2 class="mt-1 text-lg font-semibold text-slate-950">{selectedArea.area_name}</h2>
									<div class="mt-4 grid grid-cols-2 gap-2">
										<div class="rounded-md bg-slate-50 px-3 py-2">
											<p class="text-[11px] text-slate-500">Active projects</p>
											<p class="text-sm font-semibold text-slate-950">
												{selectedArea.active_projects.toLocaleString()}
											</p>
										</div>
										<div class="rounded-md bg-slate-50 px-3 py-2">
											<p class="text-[11px] text-slate-500">Pipeline units</p>
											<p class="text-sm font-semibold text-slate-950">
												{formatCompact(selectedArea.pipeline_units)}
											</p>
										</div>
										<div class="rounded-md bg-slate-50 px-3 py-2">
											<p class="text-[11px] text-slate-500">Sales volume 12m</p>
											<p class="text-sm font-semibold text-slate-950">
												{formatCurrency(selectedArea.total_sales_volume_12m)}
											</p>
										</div>
										<div class="rounded-md bg-slate-50 px-3 py-2">
											<p class="text-[11px] text-slate-500">DDA GFA</p>
											<p class="text-sm font-semibold text-slate-950">
												{formatCompact(selectedArea.dda_total_gfa_sqm)} sqm
											</p>
										</div>
									</div>
									{#if selectedArea.dda_dominant_land_uses.length > 0}
										<div class="mt-3 flex flex-wrap gap-1.5">
													{#each selectedArea.dda_dominant_land_uses as use, index (`${use}-${index}`)}
												<span class="rounded-full bg-amber-50 px-2 py-1 text-[11px] font-medium text-amber-800">
													{use}
												</span>
											{/each}
										</div>
									{/if}
								</div>

								<div class="rounded-md border border-slate-200 bg-white">
									<div class="border-b border-slate-100 px-3 py-2 text-sm font-semibold text-slate-950">
										Top projects in view mode
									</div>
									<div class="divide-y divide-slate-100">
										{#each radarProjects.filter((project) => project.area_name === selectedArea.area_name).slice(0, 8) as project (project.project_id)}
											<button
												type="button"
												class="flex w-full items-center justify-between gap-3 px-3 py-2 text-left hover:bg-slate-50"
												onclick={() => handleProjectSelect(project.project_id)}
											>
												<span class="min-w-0">
													<span class="block truncate text-sm font-medium text-slate-950">
														{project.project_name}
													</span>
													<span class="text-xs text-slate-500">
														{formatCompact(project.no_of_units)} units · {getProjectStage(project)}
													</span>
												</span>
												<span class="text-xs font-semibold text-slate-500">{projectMetric(project)}</span>
											</button>
										{/each}
									</div>
								</div>
							</section>
						{:else}
							<section class="space-y-4 p-4">
								<div>
									<div class="mb-2 flex items-center gap-2 text-sm font-semibold text-slate-950">
										<Clock3 size={16} />
										Highest pipeline areas
									</div>
									<div class="space-y-2">
										{#each topAreas as area, index (`${area.area_id}-${area.area_name}-${index}`)}
											<button
												type="button"
												class="w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-left transition-colors hover:border-teal-200 hover:bg-teal-50"
												onclick={() => handleAreaSelect(area.area_name)}
											>
												<div class="flex items-center justify-between gap-3">
													<div class="min-w-0">
														<p class="truncate text-sm font-semibold text-slate-950">
															{area.area_name}
														</p>
														<p class="text-xs text-slate-500">
															{formatCompact(area.pipeline_units)} units · {area.active_projects.toLocaleString()} active projects
														</p>
													</div>
													<span class="text-xs font-semibold text-teal-700">
														{formatCompact(area.sales_transaction_count_12m)} sales
													</span>
												</div>
											</button>
										{/each}
									</div>
								</div>

								<div>
									<div class="mb-2 flex items-center gap-2 text-sm font-semibold text-slate-950">
										{#if overlayMode === 'demand'}
											<TrendingUp size={16} />
										{:else}
											<MapPinned size={16} />
										{/if}
										Project ranking
									</div>
									<div class="space-y-2">
										{#each rankedProjects as project (project.project_id)}
											<button
												type="button"
												class="w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-left transition-colors hover:border-slate-300 hover:bg-slate-50"
												onclick={() => handleProjectSelect(project.project_id)}
											>
												<div class="flex items-center justify-between gap-3">
													<div class="min-w-0">
														<p class="truncate text-sm font-semibold text-slate-950">
															{project.project_name}
														</p>
														<p class="truncate text-xs text-slate-500">
															{project.area_name} · {getProjectStage(project)}
														</p>
													</div>
													<span class="text-xs font-semibold text-slate-700">
														{projectMetric(project)}
													</span>
												</div>
											</button>
										{/each}
									</div>
								</div>
							</section>
						{/if}
					</div>
				</aside>
			{/if}
		</div>
	</PageContainer>
</AppFrame>

<style>
	:global(:root[data-theme="dark"] .radar-theme-surface) {
		border-color: var(--color-border);
		background: rgba(15, 23, 34, 0.94);
		color: var(--color-fg-3);
		box-shadow: var(--shadow-xl);
	}

	:global(:root[data-theme="dark"] .radar-theme-surface[class~="bg-white/95"]),
	:global(:root[data-theme="dark"] .radar-theme-surface [class~="bg-white"]) {
		background-color: rgba(21, 30, 43, 0.94);
	}

	:global(:root[data-theme="dark"] .radar-theme-surface [class~="bg-slate-50"]),
	:global(:root[data-theme="dark"] .radar-theme-surface [class~="bg-slate-50/80"]),
	:global(:root[data-theme="dark"] .radar-theme-surface [class~="bg-slate-100"]) {
		background-color: rgba(30, 41, 59, 0.54);
	}

	:global(:root[data-theme="dark"] .radar-theme-surface[class~="border-white/60"]),
	:global(:root[data-theme="dark"] .radar-theme-surface [class~="border-slate-100"]),
	:global(:root[data-theme="dark"] .radar-theme-surface [class~="border-slate-200"]),
	:global(:root[data-theme="dark"] .radar-theme-surface [class~="border-slate-300"]) {
		border-color: var(--color-border);
	}

	:global(:root[data-theme="dark"] .radar-theme-surface [class~="divide-slate-100"] > :not([hidden]) ~ :not([hidden])) {
		border-color: var(--color-border);
	}

	:global(:root[data-theme="dark"] .radar-theme-surface [class~="text-slate-950"]),
	:global(:root[data-theme="dark"] .radar-theme-surface [class~="text-slate-900"]),
	:global(:root[data-theme="dark"] .radar-theme-surface [class~="text-slate-800"]) {
		color: var(--color-fg-1);
	}

	:global(:root[data-theme="dark"] .radar-theme-surface [class~="text-slate-700"]),
	:global(:root[data-theme="dark"] .radar-theme-surface [class~="text-slate-600"]) {
		color: var(--color-fg-2);
	}

	:global(:root[data-theme="dark"] .radar-theme-surface [class~="text-slate-500"]),
	:global(:root[data-theme="dark"] .radar-theme-surface [class~="text-slate-400"]) {
		color: var(--color-fg-4);
	}

	:global(:root[data-theme="dark"] .radar-theme-surface [class~="bg-teal-50"]),
	:global(:root[data-theme="dark"] .radar-theme-surface [class~="bg-teal-100"]) {
		background-color: rgba(20, 184, 166, 0.15);
	}

	:global(:root[data-theme="dark"] .radar-theme-surface [class~="text-teal-700"]),
	:global(:root[data-theme="dark"] .radar-theme-surface [class~="text-teal-800"]) {
		color: #5eead4;
	}

	:global(:root[data-theme="dark"] .radar-theme-surface [class~="border-teal-200"]) {
		border-color: rgba(94, 234, 212, 0.26);
	}

	:global(:root[data-theme="dark"] .radar-theme-surface [class~="bg-sky-50"]) {
		background-color: rgba(56, 189, 248, 0.14);
	}

	:global(:root[data-theme="dark"] .radar-theme-surface [class~="text-sky-700"]),
	:global(:root[data-theme="dark"] .radar-theme-surface [class~="text-sky-800"]) {
		color: #7dd3fc;
	}

	:global(:root[data-theme="dark"] .radar-theme-surface [class~="border-sky-200"]) {
		border-color: rgba(125, 211, 252, 0.25);
	}

	:global(:root[data-theme="dark"] .radar-theme-surface [class~="bg-amber-50"]) {
		background-color: rgba(245, 158, 11, 0.14);
	}

	:global(:root[data-theme="dark"] .radar-theme-surface [class~="text-amber-700"]),
	:global(:root[data-theme="dark"] .radar-theme-surface [class~="text-amber-800"]) {
		color: #fbbf24;
	}

	:global(:root[data-theme="dark"] .radar-theme-surface [class~="border-amber-200"]) {
		border-color: rgba(251, 191, 36, 0.25);
	}

	:global(:root[data-theme="dark"] .radar-theme-surface input) {
		border-color: var(--color-border);
		background: rgba(10, 15, 24, 0.72);
		color: var(--color-fg-1);
	}

	:global(:root[data-theme="dark"] .radar-theme-surface input::placeholder) {
		color: var(--color-fg-5);
	}

	:global(:root[data-theme="dark"] .radar-theme-surface [class~="hover:bg-slate-50"]:hover),
	:global(:root[data-theme="dark"] .radar-theme-surface [class~="hover:bg-slate-100"]:hover),
	:global(:root[data-theme="dark"] .radar-theme-surface [class~="hover:bg-teal-50"]:hover),
	:global(:root[data-theme="dark"] .radar-theme-surface [class~="hover:bg-teal-100"]:hover) {
		background-color: rgba(51, 65, 85, 0.58);
	}

	:global(:root[data-theme="dark"] .radar-theme-surface [class~="hover:text-slate-900"]:hover),
	:global(:root[data-theme="dark"] .radar-theme-surface [class~="hover:text-slate-700"]:hover),
	:global(:root[data-theme="dark"] .radar-theme-surface [class~="hover:text-teal-900"]:hover) {
		color: var(--color-fg-1);
	}
</style>
