<script lang="ts">
import { createQuery } from '@tanstack/svelte-query'
import {
	Activity,
	ArrowLeft,
	BadgeCheck,
	BarChart3,
	Layers3,
	LocateFixed,
	MapPinned,
	PanelLeftClose,
	PanelLeftOpen,
	Search,
	TrendingUp,
	UsersRound,
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
	ProjectRadarProject,
	ProjectSearchResult,
	RadarBuildingPin,
	RadarPeriodDays
} from '$lib/api/projects'
import AppFrame from '$lib/components/layout/AppFrame.svelte'
import PageContainer from '$lib/components/layout/PageContainer.svelte'
import ProjectMap from '$lib/components/map/RadarLabMap.svelte'
import BuildingDetails from '$lib/components/projects/BuildingDetails.svelte'
import { projectQueries } from '$lib/queries/projects'
import { SQM_TO_SQFT } from '$lib/utils/units'

type PanelView = 'overview' | 'project' | 'area' | 'building'
type ZoneHeatmapLayer = 'transaction_activity' | 'avg_price_sqft' | 'rental_yield'
type ProjectPinMode = 'status' | 'risk' | 'developer'
type DdaLayerMode = 'outlines' | 'parcels'
type DdaMapFeature = DdaOutlineFeature | DdaPlotFeature
type SearchProjectResult = Pick<
	ProjectSearchResult,
	'project_id' | 'project_name' | 'area_name' | 'developer_name' | 'master_project_en'
> & {
	status_label?: string
}
type SearchProject = SearchProjectResult | ProjectRadarProject
type RadarGeoPin = GeoPin & {
	point_type?: string | null
	point_number?: string | null
	floor_count?: number | null
}
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

const DDA_OUTLINE_MIN_ZOOM = 10
const DDA_PARCEL_MIN_ZOOM = 15.25
const DDA_OUTLINE_PADDING = 0.22
const DDA_PARCEL_PADDING = 0.12
const DUBAI_CENTER_LNG = 55.2708
const DUBAI_CENTER_LAT = 25.2048
const RADAR_OVERVIEW_ZOOM = 11
const RADAR_BUILDING_MIN_ZOOM = 12

let isMinimized = $state(false)
let panelView = $state<PanelView>('overview')
let mapComponent = $state<any>()
let selectedProjectId = $state<number | null>(null)
let selectedAreaName = $state<string | null>(null)
let selectedBuildingId = $state<number | null>(null)
let searchQuery = $state('')
let activityPeriodDays = $state<RadarPeriodDays>(365)
let activeHeatmapLayer = $state<ZoneHeatmapLayer>('transaction_activity')
let showZoneHeatmap = $state(true)
let projectPinMode = $state<ProjectPinMode>('status')
let selectedDeveloperName = $state<string | null>(null)
let showProjectPins = $state(true)
let showAreaBubbles = $state(false)
let showDDAPlots = $state(false)
let showBuildingPins = $state(true)
let ddaViewport = $state<DdaViewport | null>(null)
let ddaRequestViewport = $state<DdaRequestViewport | null>(null)
let renderedDDAFeatures = $state<DdaMapFeature[]>([])
let renderedDDAMode = $state<DdaLayerMode>('outlines')

const heatmapLayerOptions: Array<{ value: ZoneHeatmapLayer; label: string; caption: string }> = [
	{ value: 'transaction_activity', label: 'Activity', caption: 'DLD sales and Ejari leases' },
	{ value: 'avg_price_sqft', label: 'Price / sqft', caption: 'Sales rate' },
	{ value: 'rental_yield', label: 'Yield', caption: 'Gross rent yield' }
]
const activityPeriodOptions: Array<{ value: RadarPeriodDays; label: string }> = [
	{ value: 365, label: 'TTM' },
	{ value: 180, label: '180d' },
	{ value: 90, label: '90d' },
	{ value: 30, label: '30d' }
]
const projectPinModeOptions: Array<{ value: ProjectPinMode; label: string; caption: string }> = [
	{ value: 'status', label: 'Status', caption: 'Official DLD status colours' },
	{ value: 'risk', label: 'Risk', caption: 'Internal risk overlay' },
	{ value: 'developer', label: 'Developer', caption: 'Portfolio geography' }
]
const radarOverviewQuery = createQuery(() => projectQueries.radarOverview(activityPeriodDays))
const projectListQuery = createQuery(() => ({
	...projectQueries.list(),
	enabled: searchQuery.trim().length >= 2
}))
const projectDetailsQuery = createQuery(() =>
	projectQueries.detail(
		panelView === 'project' || panelView === 'building' ? selectedProjectId : null
	)
)
const buildingDetailsQuery = createQuery(() =>
	projectQueries.building(panelView === 'building' ? selectedBuildingId : null)
)

const radar = $derived(radarOverviewQuery.data ?? null)
const stats = $derived(radar?.stats ?? null)
const radarAreas = $derived<ProjectRadarArea[]>(dedupeAreas(radar?.areas ?? []))
const projectDetails = $derived<ProjectDetailResponse | null>(projectDetailsQuery.data ?? null)
const buildingDetails = $derived<BuildingDetailResponse | null>(buildingDetailsQuery.data ?? null)
const mapZoom = $derived(ddaViewport?.zoom ?? 11)
const radarPinParams = $derived.by(() => {
	if (!showProjectPins || !ddaViewport) return null
	const params = {
		west: roundCoordinate(ddaViewport.west),
		south: roundCoordinate(ddaViewport.south),
		east: roundCoordinate(ddaViewport.east),
		north: roundCoordinate(ddaViewport.north),
		limit: mapProjectRenderLimit(mapZoom),
		period_days: activityPeriodDays
	}
	if (projectPinMode === 'developer' && selectedDeveloperName) {
		return { ...params, developer: selectedDeveloperName }
	}
	return params
})
const areaProjectParams = $derived.by(() => {
	if (panelView !== 'area' || !selectedAreaName) return null
	return { area: selectedAreaName, limit: 25, period_days: activityPeriodDays }
})
const radarPinsQuery = createQuery(() => projectQueries.radarPins(radarPinParams))
const radarBuildingPinParams = $derived.by(() => {
	if (!showBuildingPins || !ddaViewport || mapZoom < RADAR_BUILDING_MIN_ZOOM) return null
	return {
		west: roundCoordinate(ddaViewport.west),
		south: roundCoordinate(ddaViewport.south),
		east: roundCoordinate(ddaViewport.east),
		north: roundCoordinate(ddaViewport.north),
		limit: 5000,
		period_days: activityPeriodDays
	}
})
const radarBuildingPinsQuery = createQuery(() =>
	projectQueries.radarBuildingPins(radarBuildingPinParams)
)
const areaProjectsQuery = createQuery(() => projectQueries.radarPins(areaProjectParams))
const radarPinProjects = $derived<ProjectRadarProject[]>(radarPinsQuery.data ?? [])
const radarBuildingPins = $derived<RadarBuildingPin[]>(radarBuildingPinsQuery.data ?? [])
const areaProjects = $derived<ProjectRadarProject[]>(areaProjectsQuery.data ?? [])
const radarProjects = $derived<ProjectRadarProject[]>(
	mergeRadarProjects(radarPinProjects, areaProjects)
)
const searchProjectCatalog = $derived<SearchProject[]>(projectListQuery.data ?? radarProjects)
const radarProjectsById = $derived(
	new Map(radarProjects.map((project) => [project.project_id, project]))
)
const selectedRadarProject = $derived(
	radarProjects.find((project) => project.project_id === selectedProjectId) ?? null
)
const selectedArea = $derived(
	radarAreas.find(
		(area) => area.area_name === (selectedAreaName ?? selectedRadarProject?.area_name)
	) ?? null
)
const developerOptions = $derived.by(() => {
	const counts = new Map<string, number>()
	for (const project of radarPinProjects) {
		const developer = project.developer_name?.trim()
		if (!developer) continue
		counts.set(developer, (counts.get(developer) ?? 0) + 1)
	}
	return [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 30)
})
const ddaLayerMode = $derived<DdaLayerMode>(getDdaLayerMode(mapZoom))
const ddaDataMode = $derived<DdaLayerMode>(ddaRequestViewport?.mode ?? ddaLayerMode)
const ddaOutlineParams = $derived.by(() => {
	if (!showDDAPlots || !ddaRequestViewport || ddaRequestViewport.mode !== 'outlines') return null
	if (ddaRequestViewport.zoom < DDA_OUTLINE_MIN_ZOOM) return null
	return {
		west: roundCoordinate(ddaRequestViewport.west),
		south: roundCoordinate(ddaRequestViewport.south),
		east: roundCoordinate(ddaRequestViewport.east),
		north: roundCoordinate(ddaRequestViewport.north),
		zoom: roundZoom(ddaRequestViewport.zoom),
		limit: ddaRequestViewport.zoom >= 13 ? 80 : 40
	}
})
const ddaPlotParams = $derived.by(() => {
	if (!showDDAPlots || !ddaRequestViewport || ddaRequestViewport.mode !== 'parcels') return null
	const limit = ddaRequestViewport.zoom >= 16 ? 900 : 450
	return {
		west: roundCoordinate(ddaRequestViewport.west),
		south: roundCoordinate(ddaRequestViewport.south),
		east: roundCoordinate(ddaRequestViewport.east),
		north: roundCoordinate(ddaRequestViewport.north),
		limit,
		include_valuations: false
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
const planningLayerHint = $derived.by(() => {
	if (!showDDAPlots) return 'Planning layer off'
	if (mapZoom < DDA_OUTLINE_MIN_ZOOM) return 'Zoom in for planning context'
	if (visibleDDAQueryLoading && renderedDDAFeatures.length === 0) return 'Loading planning context'
	if (renderedDDAFeatures.length > 0) {
		return `${renderedDDAFeatures.length.toLocaleString()} ${visibleDDALabel}`
	}
	return 'No planning features in this viewport'
})
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

const visibleMapProjects = $derived.by(() => {
	const limit = mapProjectRenderLimit(mapZoom)
	if (radarPinProjects.length <= limit) return radarPinProjects
	const selected = selectedProjectId
		? radarPinProjects.find((project) => project.project_id === selectedProjectId)
		: null
	const ranked = [...radarPinProjects]
		.sort((a, b) => mapPinScore(b) - mapPinScore(a))
		.slice(0, limit)
	if (selected && !ranked.some((project) => project.project_id === selected.project_id)) {
		ranked.push(selected)
	}
	return ranked
})
const projectPinHint = $derived.by(() => {
	if (!showProjectPins) return 'Project pins off'
	if (radarPinsQuery.isFetching && radarPinProjects.length === 0) return 'Loading project pins'
	if (visibleMapProjects.length > 0) {
		return `${visibleMapProjects.length.toLocaleString()} visible project pins`
	}
	return 'No project pins in this viewport'
})
const buildingPinHint = $derived.by(() => {
	if (!showBuildingPins) return 'Tower pins off'
	if (mapZoom < RADAR_BUILDING_MIN_ZOOM) return 'Zoom in for PF towers'
	if (radarBuildingPinsQuery.isFetching && radarBuildingPins.length === 0) {
		return 'Loading tower pins'
	}
	if (radarBuildingPins.length > 0) {
		return `${radarBuildingPins.length.toLocaleString()} visible PF towers`
	}
	return 'No PF towers in this viewport'
})

const searchResults = $derived.by(() => {
	const query = searchQuery.trim().toLowerCase()
	if (query.length < 2) return { projects: [], areas: [] }
	return {
		projects: searchProjectCatalog
			.filter((project) => projectMatchesSearch(project, query))
			.slice(0, 7),
		areas: radarAreas.filter((area) => area.area_name.toLowerCase().includes(query)).slice(0, 5)
	}
})

const topHeatmapAreas = $derived.by(() =>
	[...radarAreas]
		.sort((a, b) => areaMetricValue(b, activeHeatmapLayer) - areaMetricValue(a, activeHeatmapLayer))
		.slice(0, 5)
)

const selectedProjectRisk = $derived(
	selectedRadarProject ? projectRisk(selectedRadarProject) : null
)
const selectedProjectOfficialStatus = $derived(
	selectedRadarProject ? projectOfficialStatus(selectedRadarProject) : null
)
const activeHeatmapOption = $derived(
	heatmapLayerOptions.find((option) => option.value === activeHeatmapLayer) ??
		heatmapLayerOptions[0]
)

const isLoading = $derived(
	radarOverviewQuery.isPending ||
		(panelView === 'project' &&
			(projectDetailsQuery.isPending || projectDetailsQuery.isFetching)) ||
		(panelView === 'building' &&
			(buildingDetailsQuery.isPending || buildingDetailsQuery.isFetching))
)
const radarQueryError = $derived.by(() => {
	if (radarOverviewQuery.isError) return 'Market overview failed to load'
	if (radarPinsQuery.isError) return 'Project pins failed to load'
	if (radarBuildingPinsQuery.isError) return 'Tower pins failed to load'
	if (areaProjectsQuery.isError) return 'Zone projects failed to load'
	if (projectDetailsQuery.isError) return 'Project details failed to load'
	if (buildingDetailsQuery.isError) return 'Building details failed to load'
	if (showDDAPlots && (ddaOutlinesQuery.isError || ddaPlotsQuery.isError)) {
		return 'Planning context failed to load'
	}
	return null
})

function dedupeAreas(areas: ProjectRadarArea[]): ProjectRadarArea[] {
	const seen = new Set<string>()
	return areas.filter((area) => {
		const key = area.area_name.trim().toLowerCase()
		if (seen.has(key)) return false
		seen.add(key)
		return true
	})
}

function mergeRadarProjects(...lists: ProjectRadarProject[][]): ProjectRadarProject[] {
	const merged = new Map<number, ProjectRadarProject>()
	for (const projects of lists) {
		for (const project of projects) {
			merged.set(project.project_id, project)
		}
	}
	return [...merged.values()]
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
	if (viewport.zoom < DDA_OUTLINE_MIN_ZOOM) {
		ddaRequestViewport = null
		return
	}
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

function mapProjectRenderLimit(_zoom: number): number {
	// Project points are clustered in MapLibre, so the Dubai-wide view can keep
	// the complete 2.1k catalogue without dropping lower-ranked projects.
	return 2500
}

function statusScore(project: ProjectRadarProject): number {
	const status = projectOfficialStatus(project)
	if (status === 'Under Construction') return 2600
	if (status === 'Completed') return 2200
	if (status === 'Future/Announced') return 1500
	if (status === 'Stalled') return 400
	return 1000
}

function mapPinScore(project: ProjectRadarProject): number {
	return (
		statusScore(project) +
		(project.no_of_units ?? 0) +
		((project.sales_transaction_count ?? 0) + (project.rental_contract_count ?? 0)) * 0.35 +
		(project.delivery_confidence ?? 0) * 500
	)
}

function projectMatchesSearch(project: SearchProject, query: string): boolean {
	return [
		project.project_name,
		project.area_name,
		project.developer_name ?? '',
		project.master_project_en ?? ''
	]
		.join(' ')
		.toLowerCase()
		.includes(query)
}

function searchProjectStatus(project: SearchProject): string {
	const radarProject = radarProjectsById.get(project.project_id)
	if (radarProject) return projectOfficialStatus(radarProject)
	if ('completion_status' in project) return projectOfficialStatus(project)
	return 'Project'
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

function formatPriceSqft(value: number | null | undefined): string {
	if (value == null || !Number.isFinite(value) || value <= 0) return '~'
	return `AED ${Math.round(value).toLocaleString()}`
}

function formatPct(value: number | null | undefined): string {
	if (value == null || !Number.isFinite(value)) return '-'
	return `${value.toFixed(1)}%`
}

function geoPinType(pin: GeoPin): string {
	return ((pin as RadarGeoPin).point_type ?? 'building').toLowerCase()
}

function geoPinBadgeClass(pin: GeoPin): string {
	return geoPinType(pin) === 'land' ? 'bg-amber-700' : 'bg-info'
}

function geoPinBadgeLabel(pin: GeoPin): string {
	return geoPinType(pin) === 'land' ? 'L' : 'B'
}

function heatmapLayerLabel(layer: ZoneHeatmapLayer) {
	return heatmapLayerOptions.find((option) => option.value === layer)?.label ?? 'Heatmap'
}

function areaMetricValue(area: ProjectRadarArea, layer: ZoneHeatmapLayer): number {
	if (layer === 'avg_price_sqft') return (area.avg_sale_price_sqm ?? 0) / SQM_TO_SQFT
	if (layer === 'rental_yield') return area.gross_yield_pct ?? 0
	return (area.sales_transaction_count ?? 0) + (area.rental_contract_count ?? 0)
}

function areaMetricLabel(area: ProjectRadarArea, layer: ZoneHeatmapLayer): string {
	const value = areaMetricValue(area, layer)
	if (layer === 'avg_price_sqft') return formatPriceSqft(value)
	if (layer === 'rental_yield') return value > 0 ? formatPct(value) : '~'
	return `${formatCompact(area.sales_transaction_count)} sales · ${formatCompact(area.rental_contract_count)} leases`
}

function projectOfficialStatus(project: ProjectRadarProject) {
	const status = `${project.project_status ?? ''} ${project.completion_status ?? ''}`.toLowerCase()
	if (status.includes('stall') || status.includes('suspend') || status.includes('hold'))
		return 'Stalled'
	if (status.includes('complete') || status.includes('finish')) return 'Completed'
	if (status.includes('planned') || project.pipeline_status === 'future') return 'Future/Announced'
	return 'Under Construction'
}

function projectRisk(project: ProjectRadarProject) {
	const status = `${project.project_status ?? ''} ${project.completion_status ?? ''}`.toLowerCase()
	const confidence = project.delivery_confidence ?? 0
	const completion = project.percent_completed ?? 0
	if (status.includes('stall') || status.includes('suspend') || status.includes('hold'))
		return 'High Risk'
	if (status.includes('complete') || status.includes('finish')) return 'OK'
	if (confidence < 0.35 && completion < 80) return 'High Risk'
	if (confidence < 0.55 || completion < 25) return 'Warning'
	if (confidence < 0.72) return 'Medium'
	return 'OK'
}

function riskPillClass(risk: string | null) {
	if (risk === 'High Risk') return 'border-red-200 bg-red-50 text-red-700'
	if (risk === 'Warning') return 'border-amber-200 bg-amber-50 text-amber-800'
	if (risk === 'Medium') return 'border-sky-200 bg-sky-50 text-sky-800'
	return 'border-emerald-200 bg-emerald-50 text-emerald-700'
}

function statusPillClass(status: string | null) {
	if (status === 'Completed') return 'border-emerald-200 bg-emerald-50 text-emerald-700'
	if (status === 'Under Construction') return 'border-amber-200 bg-amber-50 text-amber-800'
	if (status === 'Future/Announced') return 'border-blue-200 bg-blue-50 text-blue-700'
	if (status === 'Stalled') return 'border-red-200 bg-red-50 text-red-700'
	return 'border-slate-200 bg-slate-50 text-slate-600'
}

function projectMetric(project: ProjectRadarProject) {
	return `${formatCompact(project.no_of_units)} units`
}

function handleProjectSelect(projectId: number, areaName?: string | null) {
	const radarProject = radarProjects.find((project) => project.project_id === projectId)
	selectedProjectId = projectId
	selectedAreaName = radarProject?.area_name ?? areaName ?? selectedAreaName
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
	if (area?.latitude != null && area.longitude != null && mapComponent) {
		mapComponent.flyToLocation(area.longitude, area.latitude, 13.2)
	}
	searchQuery = ''
}

function togglePlanningLayer() {
	showDDAPlots = !showDDAPlots
	if (!showDDAPlots) return
	if (ddaViewport) ensureDdaRequestViewport(ddaViewport)
}

function handleDeveloperFocus(developerName: string | null | undefined) {
	if (!developerName) return
	selectedDeveloperName = developerName
	projectPinMode = 'developer'
	showProjectPins = true
	const firstProject = radarPinProjects.find((project) => project.developer_name === developerName)
	if (firstProject && mapComponent) {
		mapComponent.flyToLocation(firstProject.longitude, firstProject.latitude, 12.5)
	}
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
	selectedDeveloperName = null
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

<svelte:head>
	<title>Radar - Vitevue</title>
</svelte:head>

<AppFrame>
	<PageContainer variant="fullBleed" class="h-full overflow-hidden">
		<div class="relative h-full overflow-hidden bg-slate-950">
			<div class="absolute inset-0">
					<ProjectMap
						bind:this={mapComponent}
						projectPins={showProjectPins ? visibleMapProjects : []}
						buildingPins={showBuildingPins ? radarBuildingPins : []}
						areaBubbles={radarAreas}
					{selectedProjectId}
					selectedAreaName={selectedArea?.area_name ?? selectedAreaName}
					{showProjectPins}
					showBuildingPins={showBuildingPins && mapZoom >= RADAR_BUILDING_MIN_ZOOM}
					{showAreaBubbles}
					{showZoneHeatmap}
					{activeHeatmapLayer}
					{projectPinMode}
					{selectedDeveloperName}
					onProjectSelect={handleProjectSelect}
					onAreaSelect={handleAreaSelect}
					onBuildingPinClick={handleBuildingPinClick}
					onViewportChange={handleViewportChange}
				/>
			</div>

				<div class="pointer-events-none absolute inset-x-3 top-3 z-30 md:inset-x-4 md:top-4">
					<div class="pointer-events-none mx-auto flex max-w-[1480px] flex-col gap-2">
						<div class="grid gap-2 xl:grid-cols-[minmax(230px,0.6fr)_minmax(680px,1.55fr)_minmax(300px,0.85fr)]">
							<div class="radar-glass pointer-events-auto flex min-h-14 items-center justify-between gap-3 rounded-lg px-3 py-2">
								<div class="min-w-0">
								<div class="flex items-center gap-2 font-mono text-[10px] font-semibold uppercase tracking-[0.08em] text-fg-4">
									<Activity size={13} />
									Radar
								</div>
								<h1 class="truncate text-sm font-semibold text-slate-950">
									DLD & Ejari market map
								</h1>
								{#if stats}
									<p class="truncate text-[10px] text-slate-500">
										{stats.activity_period_start ?? '~'} to {stats.activity_period_end ?? '~'} · {(stats.activity_coverage_pct ?? 0).toFixed(1)}% mapped
									</p>
								{/if}
							</div>
						</div>

							<div class="radar-glass pointer-events-auto flex flex-col gap-2 rounded-lg px-2 py-2 md:flex-row md:flex-wrap md:items-center">
							<div class="flex min-w-0 flex-1 flex-nowrap items-center gap-1.5 overflow-x-auto md:flex-wrap md:overflow-visible">
								<div class="flex shrink-0 items-center gap-1 rounded-md bg-[var(--color-navy-900)] p-1 text-white">
									{#each heatmapLayerOptions as option (option.value)}
										<button
											type="button"
											class="whitespace-nowrap rounded px-2.5 py-1.5 text-xs font-semibold transition-colors {activeHeatmapLayer === option.value ? 'bg-white text-navy shadow-sm' : 'text-white/68 hover:bg-white/10 hover:text-white'}"
											onclick={() => {
												activeHeatmapLayer = option.value
												showZoneHeatmap = true
											}}
										>
											{option.label}
										</button>
									{/each}
								</div>

								<div class="flex shrink-0 items-center gap-1 rounded-md bg-panel p-1" aria-label="Activity period">
									{#each activityPeriodOptions as option (option.value)}
										<button
											type="button"
											class="whitespace-nowrap rounded px-2 py-1.5 text-xs font-semibold transition-colors {activityPeriodDays === option.value ? 'bg-card text-fg-1 shadow-sm' : 'text-fg-4 hover:bg-card/70 hover:text-fg-1'}"
											title={`Trailing ${option.value} days`}
											onclick={() => (activityPeriodDays = option.value)}
										>
											{option.label}
										</button>
									{/each}
								</div>

								<div class="hidden h-6 w-px bg-border sm:block"></div>

									<button
										type="button"
										class="radar-layer-button {showProjectPins ? 'is-active' : ''}"
										aria-pressed={showProjectPins}
										aria-label="Projects"
										title="Projects"
										onclick={() => (showProjectPins = !showProjectPins)}
									>
									<MapPinned size={16} />
									<span>Projects</span>
								</button>

								{#if showProjectPins}
									<div class="flex shrink-0 items-center gap-1 rounded-md bg-panel p-1">
										{#each projectPinModeOptions as option (option.value)}
											<button
												type="button"
												class="whitespace-nowrap rounded px-2 py-1.5 text-xs font-semibold transition-colors {projectPinMode === option.value ? 'bg-card text-fg-1 shadow-sm' : 'text-fg-4 hover:bg-card/70 hover:text-fg-1'}"
												title={option.caption}
												onclick={() => {
													projectPinMode = option.value
													showProjectPins = true
												}}
											>
												{option.label}
											</button>
										{/each}
									</div>
								{/if}

								<button
									type="button"
									class="radar-layer-button {showBuildingPins ? 'is-active' : ''}"
									aria-pressed={showBuildingPins}
									aria-label="PF towers"
									title="Property Finder tower coordinates"
									onclick={() => (showBuildingPins = !showBuildingPins)}
								>
									<MapPinned size={16} />
									<span>Towers</span>
								</button>

									<button
										type="button"
										class="radar-layer-button {showDDAPlots ? 'is-planning' : ''}"
										aria-pressed={showDDAPlots}
										aria-label="Planning"
										title="DDA planning"
										onclick={togglePlanningLayer}
									>
									<Layers3 size={16} />
									<span>Planning</span>
								</button>
							</div>
						</div>

							<div class="pointer-events-auto relative">
							<div class="radar-glass flex h-full min-h-14 items-center gap-2 rounded-lg px-3 py-2">
								<Search class="text-slate-400" size={16} />
								<input
									bind:value={searchQuery}
									type="search"
									placeholder="Search project, zone, developer"
									class="h-9 min-w-0 flex-1 bg-transparent text-sm text-slate-900 outline-none placeholder:text-slate-400"
								/>
								{#if searchQuery}
									<button
										type="button"
										class="flex h-7 w-7 items-center justify-center rounded-md text-slate-400 hover:bg-slate-100 hover:text-slate-700"
										aria-label="Clear search"
										onclick={() => (searchQuery = '')}
									>
										<X size={14} />
									</button>
								{/if}
							</div>

							{#if searchQuery.trim().length >= 2}
								<div class="radar-search-results absolute left-0 right-0 top-[calc(100%+0.5rem)] max-h-80 overflow-y-auto rounded-lg border border-slate-200 bg-white/98 p-1 shadow-2xl backdrop-blur">
									{#each searchResults.projects as project (project.project_id)}
										<button
											type="button"
											class="flex w-full items-center justify-between gap-3 rounded-md px-3 py-2 text-left hover:bg-slate-50"
											onclick={() => handleProjectSelect(project.project_id, project.area_name)}
										>
											<span class="min-w-0">
												<span class="block truncate text-sm font-semibold text-slate-950">
													{project.project_name}
												</span>
												<span class="block truncate text-xs text-slate-500">
													{project.area_name} · {project.developer_name || 'Developer n/a'}
												</span>
													</span>
													<span class="rounded-sm bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold text-slate-600">
														{searchProjectStatus(project)}
													</span>
											</button>
										{/each}
									{#each searchResults.areas as area, index (`${area.area_id}-${area.area_name}-${index}`)}
											<button
												type="button"
												class="flex w-full items-center justify-between gap-3 rounded-md px-3 py-2 text-left hover:bg-panel"
												onclick={() => handleAreaSelect(area.area_name)}
											>
											<span class="min-w-0">
												<span class="block truncate text-sm font-semibold text-slate-950">
													{area.area_name}
												</span>
												<span class="block truncate text-xs text-slate-500">
													{areaMetricLabel(area, activeHeatmapLayer)} · {area.active_projects.toLocaleString()} active projects
												</span>
											</span>
												<span class="rounded-sm bg-info-bg px-1.5 py-0.5 text-[10px] font-semibold text-info">
													Zone
												</span>
										</button>
									{/each}
									{#if searchResults.projects.length === 0 && searchResults.areas.length === 0}
										<p class="px-3 py-5 text-center text-sm text-slate-500">No radar matches.</p>
									{/if}
								</div>
							{/if}
						</div>
					</div>

						{#if radarQueryError}
							<div
								class="pointer-events-auto rounded-lg border border-red-200 bg-red-50/95 px-3 py-2 text-xs font-semibold text-red-800 shadow-sm backdrop-blur"
								role="alert"
							>
								{radarQueryError}. Refresh the view to retry.
							</div>
						{/if}

						{#if projectPinMode === 'developer' && showProjectPins}
							<div class="flex flex-wrap items-center gap-2">
								<label class="radar-glass pointer-events-auto flex min-w-[260px] items-center gap-2 rounded-lg px-3 py-2">
								<span class="whitespace-nowrap text-xs font-semibold text-slate-500">Developer</span>
								<select
									bind:value={selectedDeveloperName}
									class="h-8 min-w-0 flex-1 rounded-md border border-border bg-card px-2 text-xs font-medium text-fg-1 outline-none focus:border-border-focus"
								>
									<option value={null}>All developers</option>
									{#each developerOptions as [developer, count] (developer)}
										<option value={developer}>{developer} ({count})</option>
									{/each}
								</select>
							</label>
						</div>
					{/if}
				</div>
			</div>

			<div class="radar-legend pointer-events-none absolute bottom-4 left-4 z-20 hidden w-[min(380px,calc(100vw-2rem))] rounded-lg border border-white/70 bg-white/92 px-3 py-2 shadow-xl backdrop-blur md:block">
				<div class="flex items-center justify-between gap-3">
					<div class="min-w-0">
						<p class="text-xs font-semibold text-slate-950">{activeHeatmapOption.label} heatmap</p>
						<p class="truncate text-[11px] text-slate-500">
							{radarAreas.length} zones · {stats?.mapped_projects?.toLocaleString() ?? '0'} mapped projects
							· {projectPinHint}
							· {buildingPinHint}
							{#if showDDAPlots}
								· {planningLayerHint}
							{/if}
						</p>
					</div>
					<div class="h-2 w-32 rounded-full bg-[linear-gradient(90deg,rgba(42,90,120,0.12),rgba(58,143,173,0.58),rgba(211,161,95,0.78),rgba(163,36,36,0.84))]"></div>
				</div>
				{#if showDDAPlots}
					<div class="mt-2 flex flex-wrap gap-x-3 gap-y-1 border-t border-slate-200 pt-2 text-[10px] font-medium text-slate-600">
						<span class="flex items-center gap-1"><span class="h-2 w-2 rounded-full bg-[#147d64]"></span>Confirmed</span>
						<span class="flex items-center gap-1"><span class="h-2 w-2 rounded-full bg-[#5b8c6f]"></span>Probable / villa subdivision</span>
						<span class="flex items-center gap-1"><span class="h-2 w-2 rounded-full bg-[#d99a2b]"></span>Planned</span>
						<span class="flex items-center gap-1"><span class="h-2 w-2 rounded-full bg-slate-500"></span>No observed asset</span>
					</div>
				{/if}
			</div>

			{#if isMinimized}
				<button
					type="button"
					class="radar-theme-surface absolute bottom-4 right-4 z-30 flex h-11 items-center gap-2 rounded-lg border border-slate-200 bg-white/95 px-3 text-sm font-semibold text-slate-900 shadow-xl backdrop-blur"
					aria-label="Open information panel"
					onclick={() => (isMinimized = false)}
				>
					<PanelLeftOpen size={17} />
					Info
				</button>
			{:else}
				<aside class="radar-info-panel radar-theme-surface absolute inset-x-3 bottom-3 z-20 flex max-h-[52dvh] flex-col overflow-hidden rounded-lg border border-slate-200 bg-white/95 shadow-2xl backdrop-blur md:inset-x-auto md:bottom-4 md:right-4 md:top-[116px] md:max-h-none md:w-[min(390px,calc(100vw-2rem))]">
					<header class="border-b border-slate-200 px-4 py-3">
						<div class="flex items-start justify-between gap-3">
							<div class="min-w-0">
								<p class="font-mono text-[10px] font-semibold uppercase tracking-[0.08em] text-fg-4">
									{hasActiveSelection ? 'Selection' : activeHeatmapOption.label}
								</p>
								<h2 class="mt-1 truncate text-lg font-semibold text-slate-950">
									{hasActiveSelection ? activeSelectionLabel : 'Market readout'}
								</h2>
							</div>
							<div class="flex items-center gap-1">
								{#if hasActiveSelection}
									<button
										type="button"
										class="flex h-8 w-8 items-center justify-center rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-900"
										aria-label="Back to overview"
										onclick={resetRadarView}
									>
										<ArrowLeft size={16} />
									</button>
								{/if}
								<button
									type="button"
									class="flex h-8 w-8 items-center justify-center rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-900"
									aria-label="Hide information panel"
									onclick={() => (isMinimized = true)}
								>
									<PanelLeftClose size={16} />
								</button>
							</div>
						</div>
					</header>

					<div class="flex-1 overflow-y-auto">
						{#if isLoading}
							<div class="space-y-3 p-4">
								<div class="h-5 w-2/3 rounded bg-slate-100"></div>
								<div class="h-20 rounded bg-slate-100"></div>
								<div class="h-32 rounded bg-slate-100"></div>
							</div>
						{:else if panelView === 'building' && buildingDetails}
							<BuildingDetails building={buildingDetails} onBack={handleBackToProject} />
						{:else if panelView === 'project' && (selectedRadarProject || projectDetails)}
							<section class="space-y-4 p-4">
								<div>
											<div class="flex items-start justify-between gap-3">
												<div class="min-w-0">
													<p class="font-mono text-[10px] font-semibold uppercase tracking-[0.08em] text-fg-4">
													{selectedProjectOfficialStatus ?? 'Project'}
												</p>
											<h3 class="mt-1 text-lg font-semibold text-slate-950">
												{selectedRadarProject?.project_name ?? projectDetails?.project_name}
											</h3>
											<p class="mt-1 text-sm text-slate-500">
												{selectedRadarProject?.area_name ?? projectDetails?.area_name}
											</p>
											<div class="mt-3 flex flex-wrap gap-1.5">
												<span class="rounded-full border px-2 py-1 text-[11px] font-semibold {statusPillClass(selectedProjectOfficialStatus)}">
													{selectedProjectOfficialStatus ?? 'Status pending'}
												</span>
													<span class="rounded-full border px-2 py-1 text-[11px] font-semibold {riskPillClass(selectedProjectRisk)}">
														Risk {selectedProjectRisk ?? 'pending'}
													</span>
											</div>
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
										<div class="mt-4 grid grid-cols-2 gap-2 text-xs">
											<div class="min-w-0 border-t border-slate-200 pt-2">
												<p class="text-slate-500">Developer</p>
												<p class="mt-0.5 truncate font-semibold text-slate-950">
													{selectedRadarProject?.developer_name ?? 'n/a'}
												</p>
											</div>
											<div class="min-w-0 border-t border-slate-200 pt-2">
												<div class="flex items-center justify-between gap-2">
													<div class="min-w-0">
														<p class="text-slate-500">Master project</p>
														<p class="mt-0.5 truncate font-semibold text-slate-950">
															{selectedRadarProject?.master_project_en ?? 'n/a'}
														</p>
													</div>
													{#if selectedRadarProject?.developer_name}
														<button
															type="button"
																class="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-md bg-panel text-fg-4 hover:text-info"
															aria-label="Map developer portfolio"
															title="Map developer portfolio"
															onclick={() => handleDeveloperFocus(selectedRadarProject?.developer_name)}
														>
															<UsersRound size={14} />
														</button>
													{/if}
						</div>

					</div>
				</div>
									{/if}

										<div class="mt-4 grid grid-cols-2 gap-x-4 gap-y-3 border-t border-slate-200 pt-3">
											<div>
												<p class="text-[11px] text-slate-500">Units</p>
												<p class="text-sm font-semibold text-slate-950">
													{formatCompact(selectedRadarProject?.no_of_units ?? projectDetails?.no_of_units)}
												</p>
											</div>
											<div>
												<p class="text-[11px] text-slate-500">Progress</p>
												<p class="text-sm font-semibold text-slate-950">
													{formatPct(selectedRadarProject?.percent_completed)}
												</p>
											</div>
											<div>
												<p class="text-[11px] text-slate-500">Sales volume 12m</p>
												<p class="text-sm font-semibold text-slate-950">
											{formatCurrency(selectedRadarProject?.total_sales_volume)}
												</p>
											</div>
											<div>
												<p class="text-[11px] text-slate-500">Gross yield</p>
												<p class="text-sm font-semibold text-slate-950">
													{formatPct(selectedRadarProject?.gross_yield_pct)}
												</p>
											</div>
										</div>
								</div>

								<div class="border-t border-slate-200 pt-3">
									<div class="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
										<BadgeCheck size={14} />
										DLD project record
									</div>
									<div class="grid grid-cols-3 gap-2 text-xs">
										<div>
											<p class="text-slate-500">Licence no.</p>
											<p class="mt-0.5 font-semibold text-slate-950">~</p>
										</div>
										<div>
											<p class="text-slate-500">Sold / available</p>
											<p class="mt-0.5 font-semibold text-slate-950">~</p>
										</div>
										<div>
											<p class="text-slate-500">Delivery date</p>
											<p class="mt-0.5 font-semibold text-slate-950">
												{projectDetails?.completion_date ?? projectDetails?.project_end_date ?? '~'}
											</p>
										</div>
									</div>
									{#if selectedRadarProject?.percent_completed != null}
										<div class="mt-3">
											<div class="mb-1 flex items-center justify-between text-[11px] text-slate-500">
												<span>Construction progress</span>
												<span>{formatPct(selectedRadarProject.percent_completed)}</span>
											</div>
											<div class="h-1.5 overflow-hidden rounded-full bg-slate-200">
													<div
														class="h-full rounded-full bg-info"
													style={`width: ${Math.min(100, Math.max(0, selectedRadarProject.percent_completed))}%`}
												></div>
											</div>
										</div>
									{/if}
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
													<p class="text-slate-500">Active projects</p>
													<p class="font-semibold text-slate-950">
														{selectedArea.active_projects.toLocaleString()}
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
											Building & land pins ({projectDetails.geo_pins.length})
										</div>
										<div class="max-h-52 overflow-y-auto p-2">
											{#each projectDetails.geo_pins as pin, index (`${pin.property_id ?? 'pin'}-${pin.building_name}-${pin.latitude}-${pin.longitude}-${index}`)}
												<button
													type="button"
													class="flex w-full items-center gap-2 rounded-md px-2 py-2 text-left hover:bg-slate-50"
													onclick={() => handleBuildingPinClick(pin)}
												>
													<span class="flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-bold text-white {geoPinBadgeClass(pin)}">
														{geoPinBadgeLabel(pin)}
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
							<section class="space-y-5 p-5">
								<div class="flex items-start justify-between gap-3 border-b border-border pb-4">
									<div class="min-w-0">
										<p class="font-mono text-[10px] uppercase tracking-[0.08em] text-fg-4">Zone profile</p>
										<h3 class="mt-1 truncate text-lg font-semibold text-fg-1">{selectedArea.area_name}</h3>
									</div>
									<span class="rounded-md border border-border bg-panel px-2 py-1 text-[11px] font-semibold text-fg-3">
										{heatmapLayerLabel(activeHeatmapLayer)}
									</span>
								</div>

								<div class="grid grid-cols-2 gap-x-4 gap-y-4">
									<div>
										<p class="font-mono text-[10px] uppercase tracking-[0.08em] text-fg-4">Sales</p>
										<p class="mt-1 text-base font-semibold tabular-nums text-fg-1">
											{(selectedArea.sales_transaction_count ?? 0).toLocaleString()}
										</p>
									</div>
									<div>
										<p class="font-mono text-[10px] uppercase tracking-[0.08em] text-fg-4">Ejari leases</p>
										<p class="mt-1 text-base font-semibold tabular-nums text-fg-1">
											{(selectedArea.rental_contract_count ?? 0).toLocaleString()}
										</p>
									</div>
									<div>
										<p class="font-mono text-[10px] uppercase tracking-[0.08em] text-fg-4">Price / sqft</p>
										<p class="mt-1 text-base font-semibold tabular-nums text-fg-1">
											{formatPriceSqft((selectedArea.avg_sale_price_sqm ?? 0) / SQM_TO_SQFT)}
										</p>
									</div>
									<div>
										<p class="font-mono text-[10px] uppercase tracking-[0.08em] text-fg-4">Annual rent</p>
										<p class="mt-1 text-base font-semibold tabular-nums text-fg-1">
											{formatCurrency(selectedArea.median_annual_rent)}
										</p>
									</div>
									<div>
										<p class="font-mono text-[10px] uppercase tracking-[0.08em] text-fg-4">Gross yield</p>
										<p class="mt-1 text-base font-semibold tabular-nums text-fg-1">
											{selectedArea.gross_yield_pct ? formatPct(selectedArea.gross_yield_pct) : '~'}
										</p>
									</div>
									<div>
										<p class="font-mono text-[10px] uppercase tracking-[0.08em] text-fg-4">Active projects</p>
										<p class="mt-1 text-base font-semibold tabular-nums text-fg-1">
											{selectedArea.active_projects.toLocaleString()}
										</p>
									</div>
									<div>
										<p class="font-mono text-[10px] uppercase tracking-[0.08em] text-fg-4">Completed</p>
										<p class="mt-1 text-base font-semibold tabular-nums text-fg-1">
											{selectedArea.completed_projects.toLocaleString()}
										</p>
									</div>
								</div>

								<div class="border-t border-border pt-4">
									<div class="flex items-center gap-2 text-sm font-semibold text-fg-1">
										<BarChart3 size={15} />
										Rent by unit type
									</div>
									<p class="mt-2 text-sm font-semibold text-fg-1">Studio ~ · 1BR ~ · 2BR ~ · 3BR ~</p>
								</div>

								{#if selectedArea.top_developers.length > 0}
									<div class="border-t border-border pt-4">
										<p class="mb-2 font-mono text-[10px] uppercase tracking-[0.08em] text-fg-4">
											Top active developers
										</p>
										<div class="flex flex-wrap gap-1.5">
											{#each selectedArea.top_developers.slice(0, 3) as developer (developer)}
												<button
													type="button"
													class="rounded-md border border-border bg-panel px-2 py-1 text-[11px] font-semibold text-fg-2 hover:bg-card"
													onclick={() => handleDeveloperFocus(developer)}
												>
													{developer}
												</button>
											{/each}
										</div>
									</div>
								{/if}

									<div class="border-t border-border pt-4">
									<p class="mb-2 text-sm font-semibold text-fg-1">Projects in zone</p>
									<div class="divide-y divide-border">
										{#if areaProjectsQuery.isFetching && areaProjects.length === 0}
											<p class="py-3 text-sm text-fg-4">Loading zone projects...</p>
										{/if}
										{#each areaProjects.slice(0, 5) as project (project.project_id)}
											<button
												type="button"
												class="grid w-full grid-cols-[1fr_auto] items-center gap-3 py-2 text-left hover:bg-panel/70"
												onclick={() => handleProjectSelect(project.project_id)}
											>
												<span class="min-w-0">
													<span class="block truncate text-sm font-semibold text-fg-1">
														{project.project_name}
													</span>
														<span class="text-xs text-fg-4">
															{formatCompact(project.no_of_units)} units · {projectOfficialStatus(project)}
														</span>
												</span>
												<span class="font-mono text-xs font-semibold text-fg-4">{projectMetric(project)}</span>
											</button>
										{/each}
										{#if !areaProjectsQuery.isFetching && areaProjects.length === 0}
											<p class="py-3 text-sm text-fg-4">No mapped projects returned for this zone.</p>
										{/if}
									</div>
								</div>
							</section>
						{:else}
							<section class="space-y-5 p-5">
								<div class="grid grid-cols-3 gap-4 border-b border-border pb-4">
									<div>
										<p class="font-mono text-[10px] uppercase tracking-[0.08em] text-fg-4">Zones</p>
										<p class="mt-1 text-lg font-semibold tabular-nums text-fg-1">{radarAreas.length}</p>
									</div>
									<div>
										<p class="font-mono text-[10px] uppercase tracking-[0.08em] text-fg-4">Projects</p>
										<p class="mt-1 text-lg font-semibold tabular-nums text-fg-1">
											{formatCompact(stats?.mapped_projects)}
										</p>
									</div>
									<div>
										<p class="font-mono text-[10px] uppercase tracking-[0.08em] text-fg-4">Layer</p>
										<p class="mt-1 truncate text-sm font-semibold text-fg-1">{activeHeatmapOption.label}</p>
									</div>
								</div>

								<div>
									<div class="mb-2 flex items-center gap-2 text-sm font-semibold text-fg-1">
										<TrendingUp size={16} />
										Leading zones
									</div>
									<div class="divide-y divide-border">
										{#each topHeatmapAreas.slice(0, 4) as area, index (`${area.area_id}-${area.area_name}-${index}`)}
											<button
												type="button"
												class="grid w-full grid-cols-[1fr_auto] items-center gap-3 py-3 text-left transition-colors hover:bg-panel/70"
												onclick={() => handleAreaSelect(area.area_name)}
											>
												<span class="min-w-0">
													<span class="block truncate text-sm font-semibold text-fg-1">
														{area.area_name}
													</span>
														<span class="text-xs text-fg-4">
															{area.active_projects.toLocaleString()} active · {area.completed_projects.toLocaleString()} completed
														</span>
												</span>
												<span class="font-mono text-xs font-semibold text-info">
													{areaMetricLabel(area, activeHeatmapLayer)}
												</span>
											</button>
										{/each}
									</div>
								</div>

								<div class="border-t border-border pt-4">
									<div class="flex items-center justify-between gap-3">
										<div>
											<p class="text-sm font-semibold text-fg-1">Planning context</p>
											<p class="mt-1 text-xs text-fg-4">{planningLayerHint}</p>
										</div>
										<button
											type="button"
											class="rounded-md border border-border bg-panel px-2.5 py-1.5 text-xs font-semibold text-fg-2 hover:bg-card"
											onclick={togglePlanningLayer}
										>
											{showDDAPlots ? 'Hide' : 'Show'}
										</button>
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
	.radar-glass {
		border: 1px solid rgba(226, 232, 240, 0.86);
		background: rgba(255, 255, 255, 0.9);
		box-shadow: 0 16px 44px -34px rgba(15, 23, 42, 0.48);
		backdrop-filter: blur(18px) saturate(1.12);
	}

	.radar-layer-button {
		display: inline-flex;
		height: 2rem;
		align-items: center;
		justify-content: center;
		gap: 0.4rem;
		border-radius: 0.5rem;
		border: 1px solid var(--color-border);
		background: var(--color-bg-card);
		padding: 0 0.65rem;
		font-size: 0.75rem;
		font-weight: 650;
		color: var(--color-fg-3);
		transition:
			background-color 140ms ease,
			color 140ms ease,
			border-color 140ms ease,
			box-shadow 140ms ease;
	}

	.radar-layer-button:hover {
		border-color: var(--color-border-strong);
		background: var(--color-bg-panel);
		color: var(--color-fg-1);
	}

	.radar-layer-button.is-active {
		border-color: rgba(11, 27, 43, 0.72);
		background: var(--color-navy-900);
		color: white;
		box-shadow: 0 10px 24px -18px rgba(15, 23, 42, 0.8);
	}

		.radar-layer-button.is-planning {
			border-color: rgba(165, 90, 19, 0.3);
			background: var(--color-warning);
			color: white;
		}

		@media (max-width: 639px) {
			.radar-layer-button {
				width: 2rem;
				padding: 0;
			}

			.radar-layer-button span {
				display: none;
			}
		}

		.radar-search-results {
		z-index: 70;
	}

	.radar-info-panel {
		box-shadow: 0 24px 70px -36px rgba(15, 23, 42, 0.46);
	}

	.radar-legend {
		box-shadow: 0 18px 50px -34px rgba(15, 23, 42, 0.46);
	}

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
	:global(:root[data-theme="dark"] .radar-theme-surface [class~="hover:bg-slate-100"]:hover) {
		background-color: rgba(51, 65, 85, 0.58);
	}

	:global(:root[data-theme="dark"] .radar-theme-surface [class~="hover:text-slate-900"]:hover),
	:global(:root[data-theme="dark"] .radar-theme-surface [class~="hover:text-slate-700"]:hover) {
		color: var(--color-fg-1);
	}

	:global(:root[data-theme="dark"] .radar-glass),
	:global(:root[data-theme="dark"] .radar-search-results),
	:global(:root[data-theme="dark"] .radar-legend) {
		border-color: rgba(148, 163, 184, 0.26);
		background: rgba(15, 23, 42, 0.9);
		box-shadow: 0 18px 46px -30px rgba(0, 0, 0, 0.82);
	}

	:global(:root[data-theme="dark"] .radar-glass [class~="text-slate-950"]),
	:global(:root[data-theme="dark"] .radar-glass [class~="text-slate-900"]),
	:global(:root[data-theme="dark"] .radar-search-results [class~="text-slate-950"]),
	:global(:root[data-theme="dark"] .radar-legend [class~="text-slate-950"]) {
		color: var(--color-fg-1);
	}

	:global(:root[data-theme="dark"] .radar-glass [class~="text-slate-500"]),
	:global(:root[data-theme="dark"] .radar-glass [class~="text-slate-400"]),
	:global(:root[data-theme="dark"] .radar-search-results [class~="text-slate-500"]),
	:global(:root[data-theme="dark"] .radar-legend [class~="text-slate-500"]) {
		color: var(--color-fg-4);
	}

	:global(:root[data-theme="dark"] .radar-glass input),
	:global(:root[data-theme="dark"] .radar-glass select) {
		border-color: var(--color-border);
		background-color: rgba(15, 23, 42, 0.72);
		color: var(--color-fg-1);
	}

	:global(:root[data-theme="dark"] .radar-layer-button) {
		border-color: var(--color-border);
		background: rgba(21, 30, 43, 0.94);
		color: var(--color-fg-4);
	}

	:global(:root[data-theme="dark"] .radar-layer-button:hover) {
		background: rgba(51, 65, 85, 0.72);
		color: var(--color-fg-1);
	}
</style>
