<script lang="ts">
import maplibregl from 'maplibre-gl'
import { onMount } from 'svelte'
import type {
	DdaOutlineFeature,
	DdaPlotFeature,
	GeoPin,
	GeoPolygon,
	ProjectRadarArea,
	ProjectRadarProject,
	RadarBuildingPin
} from '$lib/api/projects'
import { colorTheme } from '$lib/stores/preferences.svelte'
import { SQM_TO_SQFT } from '$lib/utils/units'

const LIGHT_MAP_STYLE = 'https://basemaps.cartocdn.com/gl/voyager-gl-style/style.json'
const DARK_MAP_STYLE = 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json'

interface ProjectPin {
	projectId: number
	projectName: string
	latitude: number
	longitude: number
	marker?: maplibregl.Marker
}

type ProjectMarkerInput = Omit<ProjectPin, 'marker'>
type ZoneHeatmapLayer = 'transaction_activity' | 'avg_price_sqft' | 'rental_yield'
type ProjectPinMode = 'status' | 'risk' | 'developer'
type DdaLayerMode = 'outlines' | 'parcels'
type DdaMapFeature = DdaPlotFeature | DdaOutlineFeature
interface MapViewport {
	west: number
	south: number
	east: number
	north: number
	zoom: number
}
type RadarProjectPin = ProjectRadarProject & {
	coordinate_source?: string | null
	coordinate_method?: string | null
	detail_point_count?: number | null
	building_point_count?: number | null
	land_point_count?: number | null
}
type RadarGeoPin = GeoPin & {
	point_type?: string | null
	point_number?: string | null
	floor_count?: number | null
}

let {
	onProjectSelect,
	onBuildingPinClick,
	onAreaSelect,
	onViewportChange,
	projectPins = [],
	buildingPins = [],
	areaBubbles = [],
	selectedProjectId = null,
	selectedAreaName = null,
	showProjectPins = false,
	showBuildingPins = false,
	showAreaBubbles = false,
	showZoneHeatmap = true,
	activeHeatmapLayer = 'transaction_activity',
	projectPinMode = 'status',
	selectedDeveloperName = null
}: {
	onProjectSelect?: (projectId: number) => void
	onBuildingPinClick?: (pin: GeoPin) => void
	onAreaSelect?: (areaName: string) => void
	onViewportChange?: (viewport: MapViewport) => void
	projectPins?: ProjectRadarProject[]
	buildingPins?: RadarBuildingPin[]
	areaBubbles?: ProjectRadarArea[]
	selectedProjectId?: number | null
	selectedAreaName?: string | null
	showProjectPins?: boolean
	showBuildingPins?: boolean
	showAreaBubbles?: boolean
	showZoneHeatmap?: boolean
	activeHeatmapLayer?: ZoneHeatmapLayer
	projectPinMode?: ProjectPinMode
	selectedDeveloperName?: string | null
} = $props()

let mapContainer = $state<HTMLDivElement>()
let map = $state<maplibregl.Map>()
let projectMarkers = $state<Map<number, ProjectPin>>(new Map())
let currentMarker = $state<maplibregl.Marker | null>(null)
let buildingMarkers = $state<maplibregl.Marker[]>([])
let buildingPopups = $state<maplibregl.Popup[]>([])
let areaPolygonLayer = $state<string | null>(null)
let currentMapStyle = $state<string | null>(null)
let currentProjectMarkerInput = $state<ProjectMarkerInput | null>(null)
let currentAreaPolygon = $state<GeoPolygon | null>(null)
let currentBuildingPins = $state<GeoPin[]>([])
let currentDDAFeatures = $state<DdaMapFeature[]>([])
let currentDDAMode = $state<DdaLayerMode>('outlines')
let currentFitBoundsPins = $state<GeoPin[]>([])
let ddaRenderVersion = 0
const resolvedTheme = $derived(colorTheme.resolved)
const PROJECT_SOURCE_ID = 'radar-projects'
const PROJECT_CLUSTER_LAYER_ID = 'radar-project-clusters'
const PROJECT_CLUSTER_COUNT_LAYER_ID = 'radar-project-cluster-counts'
const PROJECT_HALO_LAYER_ID = 'radar-project-halos'
const PROJECT_LAYER_ID = 'radar-project-pins'
const PROJECT_SELECTED_LAYER_ID = 'radar-project-selected'
const BUILDING_SOURCE_ID = 'radar-pf-towers'
const BUILDING_CLUSTER_LAYER_ID = 'radar-pf-tower-clusters'
const BUILDING_CLUSTER_COUNT_LAYER_ID = 'radar-pf-tower-cluster-counts'
const BUILDING_LAYER_ID = 'radar-pf-tower-pins'
const AREA_SOURCE_ID = 'radar-areas'
const AREA_HEATMAP_LAYER_ID = 'radar-area-heatmap'
const AREA_LAYER_ID = 'radar-area-bubbles'
const AREA_LABEL_LAYER_ID = 'radar-area-labels'
const DDA_SOURCE_ID = 'dda-plots'
const DDA_FILL_LAYER_ID = 'dda-plots-fill'
const DDA_OUTLINE_LAYER_ID = 'dda-plots-outline'
const DDA_OUTLINE_CORE_LAYER_ID = 'dda-plots-outline-core'
let radarHandlersBound = false
let ddaHandlersBound = false
let hoverPopup: maplibregl.Popup | null = null

function getMapStyle(theme: 'light' | 'dark') {
	return theme === 'dark' ? DARK_MAP_STYLE : LIGHT_MAP_STYLE
}

function hasValidLngLat(longitude: number, latitude: number) {
	return (
		Number.isFinite(longitude) &&
		Number.isFinite(latitude) &&
		longitude >= -180 &&
		longitude <= 180 &&
		latitude >= -90 &&
		latitude <= 90
	)
}

function clamp(value: number, min: number, max: number) {
	return Math.min(max, Math.max(min, value))
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

function projectStatusColor(status: string) {
	if (status === 'Completed') return '#15803d'
	if (status === 'Under Construction') return '#b45309'
	if (status === 'Future/Announced') return '#2563eb'
	if (status === 'Stalled') return '#b91c1c'
	return '#64748b'
}

function projectRiskColor(risk: string) {
	if (risk === 'High Risk') return '#b91c1c'
	if (risk === 'Warning') return '#d97706'
	if (risk === 'Medium') return '#2563eb'
	return '#15803d'
}

function developerMatches(project: ProjectRadarProject) {
	if (!selectedDeveloperName) return true
	return project.developer_name?.toLowerCase() === selectedDeveloperName.toLowerCase()
}

function projectColor(project: ProjectRadarProject) {
	if (projectPinMode === 'risk') return projectRiskColor(projectRisk(project))
	if (projectPinMode === 'developer') return developerMatches(project) ? '#2a5a78' : '#94a3b8'
	return projectStatusColor(projectOfficialStatus(project))
}

function projectOpacity(project: ProjectRadarProject) {
	if (projectPinMode !== 'developer' || !selectedDeveloperName) return 0.82
	return developerMatches(project) ? 0.9 : 0.22
}

function projectRadius(project: ProjectRadarProject) {
	return clamp(5.5 + Math.sqrt(project.no_of_units || 0) / 7, 5.5, 17)
}

function areaRadius(area: ProjectRadarArea) {
	return clamp(6 + Math.sqrt(area.pipeline_units || area.mapped_projects || 0) / 35, 7, 20)
}

function areaMetricValue(area: ProjectRadarArea, layer: ZoneHeatmapLayer) {
	if (layer === 'avg_price_sqft') return (area.avg_sale_price_sqm ?? 0) / SQM_TO_SQFT
	if (layer === 'rental_yield') return area.gross_yield_pct ?? 0
	return (area.sales_transaction_count ?? 0) + (area.rental_contract_count ?? 0)
}

function areaMetricLabel(area: ProjectRadarArea, layer: ZoneHeatmapLayer) {
	const value = areaMetricValue(area, layer)
	if (layer === 'avg_price_sqft')
		return value > 0 ? `AED ${Math.round(value).toLocaleString()} / sqft` : '~'
	if (layer === 'rental_yield') return value > 0 ? `${value.toFixed(1)}% gross yield` : '~'
	return `${(area.sales_transaction_count ?? 0).toLocaleString()} sales · ${(area.rental_contract_count ?? 0).toLocaleString()} leases`
}

function areaHeatmapMax(layer: ZoneHeatmapLayer) {
	const values = areaBubbles
		.map((area) => areaMetricValue(area, layer))
		.filter((value) => value > 0)
	return values.length > 0 ? Math.max(...values) : 1
}

function plotCategory(feature: DdaMapFeature) {
	const label = (
		feature.land_use_summary?.[0] ??
		('gfa_type' in feature ? feature.gfa_type : '') ??
		''
	).toLowerCase()
	if (label.includes('residential') || label.includes('villa') || label.includes('apartment')) {
		return 'Residential'
	}
	if (label.includes('commercial') || label.includes('retail') || label.includes('office')) {
		return 'Commercial'
	}
	if (label.includes('open space') || label.includes('landscape') || label.includes('park')) {
		return 'Open Space'
	}
	if (label.includes('utilit')) return 'Utilities'
	return 'Planning'
}

function plotColor(category: string) {
	if (category === 'Residential') return '#2a5a78'
	if (category === 'Commercial') return '#3a8fad'
	if (category === 'Open Space') return '#7a8f50'
	if (category === 'Utilities') return '#64748b'
	return '#a55a13'
}

function developmentColor(status: string, fallbackCategory: string) {
	if (status === 'developed_confirmed') return '#147d64'
	if (status === 'developed_probable') return '#5b8c6f'
	if (status === 'planned_unbuilt_candidate') return '#d99a2b'
	if (status === 'no_observed_asset') return '#64748b'
	if (status === 'non_developable') return '#7a8f50'
	return plotColor(fallbackCategory)
}

function outlineDevelopmentColor(developedShare: number) {
	if (developedShare >= 75) return '#147d64'
	if (developedShare >= 40) return '#5b8c6f'
	if (developedShare > 0) return '#d99a2b'
	return '#64748b'
}

function isDDAOutlineFeature(feature: DdaMapFeature): feature is DdaOutlineFeature {
	return 'kind' in feature && 'plot_count' in feature && !('plot_number' in feature)
}

function projectFeature(project: ProjectRadarProject): GeoJSON.Feature {
	const radarProject = project as RadarProjectPin
	const officialStatus = projectOfficialStatus(project)
	const risk = projectRisk(project)
	return {
		type: 'Feature',
		geometry: { type: 'Point', coordinates: [project.longitude, project.latitude] },
		properties: {
			project_id: project.project_id,
			project_name: project.project_name,
			area_name: project.area_name,
			developer_name: project.developer_name ?? '',
			official_status: officialStatus,
			risk,
			no_of_units: project.no_of_units,
			sales_transaction_count: project.sales_transaction_count,
			rental_contract_count: project.rental_contract_count,
			gross_yield_pct: project.gross_yield_pct ?? 0,
			coordinate_source: coordinateSourceLabel(radarProject),
			detail_point_count: radarProject.detail_point_count ?? 0,
			building_point_count: radarProject.building_point_count ?? 0,
			land_point_count: radarProject.land_point_count ?? 0,
			radius: projectRadius(project),
			color: projectColor(project),
			opacity: projectOpacity(project)
		}
	}
}

function buildingFeature(building: RadarBuildingPin): GeoJSON.Feature {
	const activity = building.sales_transaction_count + building.rental_contract_count
	return {
		type: 'Feature',
		geometry: { type: 'Point', coordinates: [building.longitude, building.latitude] },
		properties: {
			location_id: building.location_id,
			building_name: building.building_name,
			project_name: building.project_name ?? '',
			area_name: building.area_name,
			sales_transaction_count: building.sales_transaction_count,
			rental_contract_count: building.rental_contract_count,
			total_sales_volume: building.total_sales_volume,
			median_sale_price: building.median_sale_price ?? 0,
			median_annual_rent: building.median_annual_rent ?? 0,
			listing_inventory_count: building.listing_inventory_count,
			matched_source_signatures: building.matched_source_signatures,
			last_activity_date: building.last_activity_date ?? '',
			activity,
			color:
				activity > 0 ? '#0f766e' : building.listing_inventory_count > 0 ? '#2563eb' : '#64748b',
			radius: clamp(
				4.5 + Math.log10(Math.max(1, activity + building.listing_inventory_count)),
				5,
				9
			)
		}
	}
}

function areaFeature(
	area: ProjectRadarArea,
	index: number,
	layer: ZoneHeatmapLayer,
	maxValue: number
): GeoJSON.Feature | null {
	if (area.latitude == null || area.longitude == null) return null
	if (!hasValidLngLat(area.longitude, area.latitude)) return null
	const metricValue = areaMetricValue(area, layer)
	const heatWeight = metricValue > 0 ? clamp(Math.sqrt(metricValue / maxValue), 0.24, 1) : 0
	return {
		type: 'Feature',
		geometry: { type: 'Point', coordinates: [area.longitude, area.latitude] },
		properties: {
			area_name: area.area_name,
			active_projects: area.active_projects,
			pipeline_units: area.pipeline_units,
			sales_transaction_count: area.sales_transaction_count,
			rental_contract_count: area.rental_contract_count,
			avg_sale_price_sqft: (area.avg_sale_price_sqm ?? 0) / SQM_TO_SQFT,
			gross_yield_pct: area.gross_yield_pct ?? 0,
			heat_metric_value: metricValue,
			heat_metric_label: areaMetricLabel(area, layer),
			heat_weight: heatWeight,
			dda_plot_count: area.dda_plot_count,
			radius: areaRadius(area),
			show_label: index < 12
		}
	}
}

function featureCollection(features: GeoJSON.Feature[]): GeoJSON.FeatureCollection {
	return { type: 'FeatureCollection', features }
}

function formatAedCompact(value: number) {
	if (!Number.isFinite(value) || value <= 0) return '~'
	if (value >= 1_000_000_000) return `AED ${(value / 1_000_000_000).toFixed(1)}B`
	if (value >= 1_000_000) return `AED ${(value / 1_000_000).toFixed(1)}M`
	return `AED ${(value / 1_000).toFixed(0)}K`
}

function towerPopupHtml(props: Record<string, unknown>) {
	const project = String(props.project_name || '')
	const area = String(props.area_name || 'Unknown')
	const context = project ? `${project} · ${area}` : area
	return (
		`<div style="min-width:205px;font-size:12px;line-height:1.5;">` +
		`<div style="font-weight:700;color:var(--color-map-popup-fg);">${escapeHtml(props.building_name)}</div>` +
		`<div style="color:var(--color-map-popup-muted);margin-top:2px;">${escapeHtml(context)}</div>` +
		`<div style="margin-top:7px;color:var(--color-map-popup-fg);">${Number(
			props.sales_transaction_count || 0
		).toLocaleString()} sales · ${Number(props.rental_contract_count || 0).toLocaleString()} leases</div>` +
		`<div style="color:var(--color-map-popup-muted);margin-top:2px;">Median sale ${formatAedCompact(
			Number(props.median_sale_price || 0)
		)} · median rent ${formatAedCompact(Number(props.median_annual_rent || 0))}</div>` +
		`<div style="color:var(--color-map-popup-muted);margin-top:2px;">${Number(
			props.listing_inventory_count || 0
		).toLocaleString()} PF listings · ${Number(
			props.matched_source_signatures || 0
		).toLocaleString()} matched address signatures</div>` +
		`</div>`
	)
}

function formatSqmCompact(value: number) {
	if (!Number.isFinite(value) || value <= 0) return '~'
	return value >= 1000 ? `${(value / 1000).toFixed(1)}k sqm` : `${Math.round(value)} sqm`
}

function escapeHtml(value: unknown) {
	return String(value ?? '')
		.replaceAll('&', '&amp;')
		.replaceAll('<', '&lt;')
		.replaceAll('>', '&gt;')
		.replaceAll('"', '&quot;')
		.replaceAll("'", '&#39;')
}

function coordinateSourceLabel(project: RadarProjectPin) {
	if (project.coordinate_source === 'dld_mashrooi') return 'DLD Mashrooi'
	if (project.coordinate_source === 'pf_reelly_consensus') return 'PF + Reelly coordinate consensus'
	if (project.coordinate_source === 'pf_location_hierarchy') return 'PF location hierarchy'
	if (project.coordinate_source === 'reelly_catalogue') return 'Reelly project catalogue'
	return 'DLD building centroid'
}

function detailPointLabel(pin: RadarGeoPin) {
	const pointType = (pin.point_type ?? 'building').toLowerCase()
	return pointType === 'land' ? 'Land' : 'Building'
}

function ddaParcelPopupHtml(props: Record<string, unknown>) {
	const areaSqm = Number(props.plot_area_sqm)
	const maxGfaSqm = Number(props.max_gfa_sqm)
	const valuationMin = Number(props.valuation_min_aed)
	const valuationMax = Number(props.valuation_max_aed)
	const rateMin = Number(props.valuation_rate_min_aed_sqft)
	const rateMax = Number(props.valuation_rate_max_aed_sqft)
	const plotNumber = escapeHtml(props.plot_number)
	const communityName = escapeHtml(props.community_name)
	const developmentStatus = String(props.development_status || 'no_observed_asset')
	const developmentLabel = developmentStatus
		.split('_')
		.map((word) => word.charAt(0).toUpperCase() + word.slice(1))
		.join(' ')
	const developmentNote = escapeHtml(props.development_note || '')
	const linkedAssets = Number(props.linked_physical_asset_count || 0)
	const subdivisionConfirmed = Number(props.subdivision_confirmed_count || 0)
	const subdivisionPlots = Number(props.subdivision_plot_count || 0)
	const valuationLabel =
		valuationMin > 0 && valuationMax > 0
			? `${formatAedCompact(valuationMin)} - ${formatAedCompact(valuationMax)}`
			: '~'
	const rateLabel = rateMin > 0 && rateMax > 0 ? `AED ${rateMin}-${rateMax} / sqft` : '~'
	return (
		`<div style="min-width:210px;font-size:12px;line-height:1.55;">` +
		`<div style="font-weight:700;color:var(--color-map-popup-fg);">Plot ${plotNumber}</div>` +
		`<div style="color:var(--color-map-popup-muted);margin-top:2px;">${formatSqmCompact(areaSqm)} · ${communityName}</div>` +
		`<div style="margin-top:7px;font-weight:700;color:var(--color-map-popup-fg);">${escapeHtml(developmentLabel)}</div>` +
		(developmentNote
			? `<div style="color:var(--color-map-popup-muted);margin-top:2px;">${developmentNote}</div>`
			: '') +
		(linkedAssets > 0
			? `<div style="color:var(--color-map-popup-muted);margin-top:2px;">${linkedAssets.toLocaleString()} linked physical asset record(s)</div>`
			: '') +
		(subdivisionPlots > 0
			? `<div style="color:var(--color-map-popup-muted);margin-top:2px;">Subdivision evidence ${subdivisionConfirmed.toLocaleString()} / ${subdivisionPlots.toLocaleString()} plots</div>`
			: '') +
		`<div style="margin-top:8px;border-top:1px solid color-mix(in srgb,var(--color-map-popup-muted) 20%,transparent);padding-top:7px;">` +
		`<div style="color:var(--color-map-popup-muted);">Indicative valuation</div>` +
		`<div style="font-weight:700;color:var(--color-map-popup-fg);font-size:13px;">${valuationLabel}</div>` +
		`<div style="color:var(--color-map-popup-muted);margin-top:2px;">${formatSqmCompact(maxGfaSqm)} max GFA · ${rateLabel}</div>` +
		`</div>` +
		`</div>`
	)
}

function ddaOutlinePopupHtml(props: Record<string, unknown>) {
	const developedShare = Number(props.developed_share || 0)
	return (
		`<div style="font-size:12px;line-height:1.6;">` +
		`<div style="font-weight:700;color:var(--color-map-popup-fg);">${escapeHtml(props.name)}</div>` +
		`<div style="color:var(--color-map-popup-muted);margin-top:2px;">${Number(
			props.plot_count || 0
		).toLocaleString()} plots · ${escapeHtml(props.kind)}</div>` +
		`<div style="font-weight:700;color:var(--color-map-popup-fg);margin-top:5px;">${developedShare.toFixed(1)}% developed evidence</div>` +
		`<div style="color:var(--color-map-popup-muted);margin-top:2px;">${Number(
			props.developed_confirmed_count || 0
		).toLocaleString()} confirmed · ${Number(
			props.developed_probable_count || 0
		).toLocaleString()} probable</div>` +
		`</div>`
	)
}

function ddaFeatureCollection(features: DdaMapFeature[]): GeoJSON.FeatureCollection {
	return featureCollection(
		features.map((feature) => {
			const isOutline = isDDAOutlineFeature(feature)
			const category = plotCategory(feature)
			const developmentStatus = isOutline ? '' : (feature.development_status ?? 'no_observed_asset')
			return {
				type: 'Feature',
				geometry: { type: 'Polygon', coordinates: [feature.coordinates] },
				properties: isOutline
					? {
							feature_type: 'outline',
							name: feature.name,
							kind: feature.kind,
							plot_count: feature.plot_count,
							total_plot_area_sqm: feature.total_plot_area_sqm,
							total_gfa_sqm: feature.total_gfa_sqm,
							developed_confirmed_count: feature.developed_confirmed_count,
							developed_probable_count: feature.developed_probable_count,
							developed_share: feature.developed_share,
							category,
							color: outlineDevelopmentColor(feature.developed_share ?? 0)
						}
					: {
							feature_type: 'parcel',
							plot_number: feature.plot_number,
							plot_area_sqm: feature.plot_area_sqm,
							max_gfa_sqm: feature.max_gfa_sqm ?? 0,
							valuation_rate_min_aed_sqft: feature.valuation_rate_min_aed_sqft ?? 0,
							valuation_rate_max_aed_sqft: feature.valuation_rate_max_aed_sqft ?? 0,
							valuation_min_aed: feature.valuation_min_aed ?? 0,
							valuation_max_aed: feature.valuation_max_aed ?? 0,
							valuation_confidence: feature.valuation_confidence ?? '',
							valuation_note: feature.valuation_note ?? '',
							community_name: feature.community_name,
							development_status: feature.development_status,
							development_confidence: feature.development_confidence,
							development_method: feature.development_method,
							development_note: feature.development_note ?? '',
							linked_physical_asset_count: feature.linked_physical_asset_count,
							subdivision_plot_count: feature.subdivision_plot_count,
							subdivision_confirmed_count: feature.subdivision_confirmed_count,
							category,
							color: developmentColor(developmentStatus, category)
						}
			}
		})
	)
}

function notifyViewportChange() {
	if (!map || !onViewportChange) return
	const bounds = map.getBounds()
	onViewportChange({
		west: bounds.getWest(),
		south: bounds.getSouth(),
		east: bounds.getEast(),
		north: bounds.getNorth(),
		zoom: map.getZoom()
	})
}

onMount(() => {
	if (!mapContainer) {
		console.error('Map container not found')
		return
	}

	// Initialize MapLibre
	currentMapStyle = getMapStyle(resolvedTheme)
	map = new maplibregl.Map({
		container: mapContainer,
		style: currentMapStyle, // Carto basemaps accept font CORS warnings.
		center: [55.2708, 25.2048], // Dubai [lng, lat]
		zoom: 11
	})

	// Add navigation controls
	map.addControl(new maplibregl.NavigationControl(), 'top-right')

	map.on('load', () => {
		syncRadarLayers()
		notifyViewportChange()
	})
	map.on('moveend', notifyViewportChange)

	map.on('error', (e) => {
		console.error('Map error:', e)
	})

	return () => {
		map?.remove()
	}
})

$effect(() => {
	const currentMap = map
	const nextStyle = getMapStyle(resolvedTheme)
	if (!currentMap || currentMapStyle === nextStyle) return

	currentMapStyle = nextStyle
	_unbindDDAHandlers()
	areaPolygonLayer = null
	currentMap.setStyle(nextStyle)
	currentMap.once('style.load', () => {
		if (currentMapStyle !== nextStyle) return
		syncRadarLayers()
		replayCurrentOverlays()
	})
})

$effect(() => {
	projectPins
	buildingPins
	areaBubbles
	selectedProjectId
	selectedAreaName
	showProjectPins
	showBuildingPins
	showAreaBubbles
	showZoneHeatmap
	activeHeatmapLayer
	projectPinMode
	selectedDeveloperName
	resolvedTheme
	map
	syncRadarLayers()
})

function _removeAreaPolygon() {
	if (!map) return
	try {
		if (areaPolygonLayer && map.getLayer(areaPolygonLayer)) map.removeLayer(areaPolygonLayer)
		if (areaPolygonLayer && map.getLayer(`${areaPolygonLayer}-outline`)) {
			map.removeLayer(`${areaPolygonLayer}-outline`)
		}
		if (map.getSource('area-polygon')) map.removeSource('area-polygon')
	} catch (_e) {
		// Layer or source might not exist during a style reload.
	}
	areaPolygonLayer = null
}

function _clearProjectMarkers() {
	if (currentMarker) {
		currentMarker.remove()
		currentMarker = null
	}
	projectMarkers.forEach((pin) => {
		pin.marker?.remove()
	})
	projectMarkers.clear()
}

function _clearBuildingMarkers() {
	buildingPopups.forEach((p) => {
		p.remove()
	})
	buildingPopups = []
	buildingMarkers.forEach((marker) => {
		marker.remove()
	})
	buildingMarkers = []
}

function _clearRenderedOverlays() {
	_clearProjectMarkers()
	_clearBuildingMarkers()
	_removeAreaPolygon()
	_removeDDALayers()
}

function fitMapToPins(pins: GeoPin[], duration?: number) {
	if (!map || pins.length === 0) return
	const validPins = pins.filter((pin) => hasValidLngLat(pin.longitude, pin.latitude))
	if (validPins.length === 0) return
	const lats = validPins.map((p) => p.latitude)
	const lngs = validPins.map((p) => p.longitude)
	const options = duration === undefined ? { padding: 60 } : { padding: 60, duration }
	map.fitBounds(
		[
			[Math.min(...lngs), Math.min(...lats)],
			[Math.max(...lngs), Math.max(...lats)]
		],
		options
	)
}

function replayCurrentOverlays() {
	if (!map) return
	if (!map.isStyleLoaded()) {
		map.once('style.load', replayCurrentOverlays)
		return
	}

	const projectMarker = currentProjectMarkerInput
	const areaPolygon = currentAreaPolygon
	const buildingPins = [...currentBuildingPins]
	const ddaFeatures = [...currentDDAFeatures]
	const ddaMode = currentDDAMode
	const fitBoundsPins = [...currentFitBoundsPins]

	_clearRenderedOverlays()

	if (projectMarker) {
		addProjectMarker(
			projectMarker.projectId,
			projectMarker.projectName,
			projectMarker.latitude,
			projectMarker.longitude
		)
	}
	if ((areaPolygon?.coordinates?.length ?? 0) > 0 && areaPolygon) {
		drawAreaPolygon(areaPolygon)
	}
	if (buildingPins.length > 0) {
		addBuildingMarkers(buildingPins)
	}
	if (ddaFeatures.length > 0) {
		showDDAFeatures(ddaFeatures, ddaMode)
	}
	if (fitBoundsPins.length > 0) {
		fitMapToPins(fitBoundsPins, 0)
	}
}

function setSourceData(
	sourceId: string,
	data: GeoJSON.FeatureCollection,
	options: Omit<maplibregl.GeoJSONSourceSpecification, 'type' | 'data'> = {}
) {
	if (!map) return
	const source = map.getSource(sourceId) as maplibregl.GeoJSONSource | undefined
	if (source) {
		source.setData(data)
	} else {
		map.addSource(sourceId, { type: 'geojson', data, ...options })
	}
}

function setLayerVisibility(layerId: string, visible: boolean) {
	if (!map?.getLayer(layerId)) return
	map.setLayoutProperty(layerId, 'visibility', visible ? 'visible' : 'none')
}

function raiseProjectLayers() {
	if (!map) return
	for (const layerId of [
		PROJECT_CLUSTER_LAYER_ID,
		PROJECT_CLUSTER_COUNT_LAYER_ID,
		PROJECT_HALO_LAYER_ID,
		PROJECT_LAYER_ID,
		PROJECT_SELECTED_LAYER_ID
	]) {
		if (map.getLayer(layerId)) map.moveLayer(layerId)
	}
}

function bindRadarHandlers() {
	if (!map || radarHandlersBound) return
	radarHandlersBound = true

	map.on('click', PROJECT_LAYER_ID, (event) => {
		const id = Number(event.features?.[0]?.properties?.project_id)
		if (Number.isFinite(id)) onProjectSelect?.(id)
	})

	map.on('click', PROJECT_CLUSTER_LAYER_ID, (event) => {
		const feature = event.features?.[0]
		const clusterId = feature?.properties?.cluster_id
		const source = map?.getSource(PROJECT_SOURCE_ID) as maplibregl.GeoJSONSource | undefined
		if (!map || clusterId == null || !source || feature?.geometry?.type !== 'Point') return
		const center = (feature.geometry as GeoJSON.Point).coordinates as [number, number]
		void source.getClusterExpansionZoom(Number(clusterId)).then((zoom) => {
			if (!map || zoom == null) return
			map.easeTo({
				center,
				zoom,
				duration: 650
			})
		})
	})

	map.on('click', BUILDING_CLUSTER_LAYER_ID, (event) => {
		const feature = event.features?.[0]
		const clusterId = feature?.properties?.cluster_id
		const source = map?.getSource(BUILDING_SOURCE_ID) as maplibregl.GeoJSONSource | undefined
		if (!map || clusterId == null || !source || feature?.geometry?.type !== 'Point') return
		const center = (feature.geometry as GeoJSON.Point).coordinates as [number, number]
		void source.getClusterExpansionZoom(Number(clusterId)).then((zoom) => {
			if (!map || zoom == null) return
			map.easeTo({ center, zoom, duration: 550 })
		})
	})

	map.on('click', BUILDING_LAYER_ID, (event) => {
		const props = event.features?.[0]?.properties
		if (!map || !props) return
		new maplibregl.Popup({ className: 'building-popup', offset: 12 })
			.setLngLat(event.lngLat)
			.setHTML(towerPopupHtml(props))
			.addTo(map)
	})

	map.on('click', AREA_LAYER_ID, (event) => {
		const areaName = event.features?.[0]?.properties?.area_name
		if (typeof areaName === 'string' && areaName) onAreaSelect?.(areaName)
	})

	map.on('mouseenter', PROJECT_LAYER_ID, (event) => {
		if (!map) return
		map.getCanvas().style.cursor = 'pointer'
		const props = event.features?.[0]?.properties
		if (!props) return
		hoverPopup?.remove()
		hoverPopup = new maplibregl.Popup({
			closeButton: false,
			closeOnClick: false,
			className: 'building-popup',
			offset: 14
		})
			.setLngLat(event.lngLat)
			.setHTML(
				`<div style="min-width:180px;font-size:12px;line-height:1.45;">` +
					`<div style="font-weight:700;color:var(--color-map-popup-fg);">${escapeHtml(props.project_name)}</div>` +
					`<div style="color:var(--color-map-popup-muted);margin-top:2px;">${escapeHtml(props.area_name)} · ${escapeHtml(props.official_status)}</div>` +
					`<div style="color:var(--color-map-popup-muted);margin-top:2px;">Risk ${escapeHtml(props.risk)}</div>` +
					`<div style="color:var(--color-map-popup-muted);margin-top:2px;">${escapeHtml(props.coordinate_source)} · ${Number(
						props.building_point_count || 0
					).toLocaleString()} buildings · ${Number(
						props.land_point_count || 0
					).toLocaleString()} lands</div>` +
					`<div style="color:var(--color-map-popup-muted);margin-top:6px;">${Number(
						props.no_of_units || 0
					).toLocaleString()} units · ${Number(
						props.sales_transaction_count || 0
					).toLocaleString()} sales txns</div>` +
					`</div>`
			)
			.addTo(map)
	})

	map.on('mouseleave', PROJECT_LAYER_ID, () => {
		if (!map) return
		map.getCanvas().style.cursor = ''
		hoverPopup?.remove()
		hoverPopup = null
	})

	map.on('mouseenter', PROJECT_CLUSTER_LAYER_ID, () => {
		if (map) map.getCanvas().style.cursor = 'pointer'
	})
	map.on('mouseleave', PROJECT_CLUSTER_LAYER_ID, () => {
		if (map) map.getCanvas().style.cursor = ''
	})

	for (const layerId of [BUILDING_CLUSTER_LAYER_ID, BUILDING_LAYER_ID]) {
		map.on('mouseenter', layerId, () => {
			if (map) map.getCanvas().style.cursor = 'pointer'
		})
		map.on('mouseleave', layerId, () => {
			if (map) map.getCanvas().style.cursor = ''
		})
	}

	map.on('mouseenter', AREA_LAYER_ID, () => {
		if (map) map.getCanvas().style.cursor = 'pointer'
	})
	map.on('mouseleave', AREA_LAYER_ID, () => {
		if (map) map.getCanvas().style.cursor = ''
	})
}

function syncRadarLayers() {
	if (!map || !map.isStyleLoaded()) return

	const heatmapMax = areaHeatmapMax(activeHeatmapLayer)
	const projectFeatures = showProjectPins
		? projectPins
				.filter((project) => hasValidLngLat(project.longitude, project.latitude))
				.map((project) => projectFeature(project))
		: []
	const buildingFeatures = showBuildingPins
		? buildingPins
				.filter((building) => hasValidLngLat(building.longitude, building.latitude))
				.map((building) => buildingFeature(building))
		: []
	const areaFeatures = areaBubbles
		.map((area, index) => areaFeature(area, index, activeHeatmapLayer, heatmapMax))
		.filter((feature): feature is GeoJSON.Feature => feature !== null)

	setSourceData(AREA_SOURCE_ID, featureCollection(areaFeatures))
	setSourceData(PROJECT_SOURCE_ID, featureCollection(projectFeatures), {
		cluster: true,
		clusterMaxZoom: 13,
		clusterRadius: 48
	})
	setSourceData(BUILDING_SOURCE_ID, featureCollection(buildingFeatures), {
		cluster: true,
		clusterMaxZoom: 15,
		clusterRadius: 38
	})

	if (!map.getLayer(AREA_HEATMAP_LAYER_ID)) {
		map.addLayer({
			id: AREA_HEATMAP_LAYER_ID,
			type: 'heatmap',
			source: AREA_SOURCE_ID,
			maxzoom: 15,
			paint: {
				'heatmap-weight': ['interpolate', ['linear'], ['get', 'heat_weight'], 0, 0, 1, 1],
				'heatmap-intensity': ['interpolate', ['linear'], ['zoom'], 9, 1.55, 14, 3.2],
				'heatmap-radius': ['interpolate', ['linear'], ['zoom'], 9, 34, 14, 92],
				'heatmap-opacity': ['interpolate', ['linear'], ['zoom'], 9, 0.86, 15, 0.58],
				'heatmap-color': [
					'interpolate',
					['linear'],
					['heatmap-density'],
					0,
					'rgba(42, 90, 120, 0)',
					0.16,
					'rgba(42, 90, 120, 0.42)',
					0.38,
					'rgba(58, 143, 173, 0.68)',
					0.62,
					'rgba(211, 161, 95, 0.84)',
					0.82,
					'rgba(180, 83, 9, 0.92)',
					1,
					'rgba(163, 36, 36, 0.96)'
				]
			},
			layout: {
				visibility: showZoneHeatmap ? 'visible' : 'none'
			}
		})
	}
	if (!map.getLayer(AREA_LAYER_ID)) {
		map.addLayer({
			id: AREA_LAYER_ID,
			type: 'circle',
			source: AREA_SOURCE_ID,
			paint: {
				'circle-radius': ['get', 'radius'],
				'circle-color': '#2a5a78',
				'circle-opacity': 0.02,
				'circle-stroke-color': '#2a5a78',
				'circle-stroke-width': 1.5,
				'circle-stroke-opacity': 0
			}
		})
	}
	if (!map.getLayer(AREA_LABEL_LAYER_ID)) {
		map.addLayer({
			id: AREA_LABEL_LAYER_ID,
			type: 'symbol',
			source: AREA_SOURCE_ID,
			filter: ['==', ['get', 'show_label'], true],
			layout: {
				'text-field': ['get', 'area_name'],
				'text-size': 11,
				'text-offset': [0, 1.8],
				'text-anchor': 'top'
			},
			paint: {
				'text-color': resolvedTheme === 'dark' ? '#e2e8f0' : '#0f172a',
				'text-halo-color': resolvedTheme === 'dark' ? '#020617' : '#ffffff',
				'text-halo-width': 1.2
			}
		})
	}
	if (!map.getLayer(BUILDING_CLUSTER_LAYER_ID)) {
		map.addLayer({
			id: BUILDING_CLUSTER_LAYER_ID,
			type: 'circle',
			source: BUILDING_SOURCE_ID,
			filter: ['has', 'point_count'],
			paint: {
				'circle-color': '#0f3d4a',
				'circle-radius': ['step', ['get', 'point_count'], 15, 30, 20, 100, 25],
				'circle-opacity': 0.88,
				'circle-stroke-color': '#ffffff',
				'circle-stroke-width': 1.5,
				'circle-stroke-opacity': 0.9
			}
		})
	}
	if (!map.getLayer(BUILDING_CLUSTER_COUNT_LAYER_ID)) {
		map.addLayer({
			id: BUILDING_CLUSTER_COUNT_LAYER_ID,
			type: 'symbol',
			source: BUILDING_SOURCE_ID,
			filter: ['has', 'point_count'],
			layout: {
				'text-field': ['get', 'point_count_abbreviated'],
				'text-font': ['Open Sans Semibold', 'Arial Unicode MS Bold'],
				'text-size': 10
			},
			paint: { 'text-color': '#ffffff' }
		})
	}
	if (!map.getLayer(BUILDING_LAYER_ID)) {
		map.addLayer({
			id: BUILDING_LAYER_ID,
			type: 'circle',
			source: BUILDING_SOURCE_ID,
			filter: ['!', ['has', 'point_count']],
			paint: {
				'circle-radius': ['get', 'radius'],
				'circle-color': ['get', 'color'],
				'circle-opacity': 0.78,
				'circle-stroke-color': '#ffffff',
				'circle-stroke-width': 1.5,
				'circle-stroke-opacity': 0.95
			}
		})
	}
	if (!map.getLayer(PROJECT_CLUSTER_LAYER_ID)) {
		map.addLayer({
			id: PROJECT_CLUSTER_LAYER_ID,
			type: 'circle',
			source: PROJECT_SOURCE_ID,
			filter: ['has', 'point_count'],
			paint: {
				'circle-color': [
					'step',
					['get', 'point_count'],
					'#111827',
					40,
					'#1f3a5f',
					120,
					'#334155',
					260,
					'#0f172a'
				],
				'circle-radius': ['step', ['get', 'point_count'], 17, 40, 23, 120, 29, 260, 36],
				'circle-opacity': 0.92,
				'circle-stroke-color': '#ffffff',
				'circle-stroke-width': 2.2,
				'circle-stroke-opacity': 0.96
			}
		})
	}
	if (!map.getLayer(PROJECT_CLUSTER_COUNT_LAYER_ID)) {
		map.addLayer({
			id: PROJECT_CLUSTER_COUNT_LAYER_ID,
			type: 'symbol',
			source: PROJECT_SOURCE_ID,
			filter: ['has', 'point_count'],
			layout: {
				'text-field': ['get', 'point_count_abbreviated'],
				'text-font': ['Open Sans Semibold', 'Arial Unicode MS Bold'],
				'text-size': 11
			},
			paint: {
				'text-color': '#ffffff'
			}
		})
	}
	if (!map.getLayer(PROJECT_HALO_LAYER_ID)) {
		map.addLayer({
			id: PROJECT_HALO_LAYER_ID,
			type: 'circle',
			source: PROJECT_SOURCE_ID,
			filter: ['!', ['has', 'point_count']],
			paint: {
				'circle-radius': ['+', ['get', 'radius'], 3],
				'circle-color': ['get', 'color'],
				'circle-opacity': 0.2
			}
		})
	}
	if (!map.getLayer(PROJECT_LAYER_ID)) {
		map.addLayer({
			id: PROJECT_LAYER_ID,
			type: 'circle',
			source: PROJECT_SOURCE_ID,
			filter: ['!', ['has', 'point_count']],
			paint: {
				'circle-radius': ['get', 'radius'],
				'circle-color': ['get', 'color'],
				'circle-opacity': ['get', 'opacity'],
				'circle-stroke-color': '#ffffff',
				'circle-stroke-width': 2,
				'circle-stroke-opacity': 0.96
			}
		})
	}
	if (!map.getLayer(PROJECT_SELECTED_LAYER_ID)) {
		map.addLayer({
			id: PROJECT_SELECTED_LAYER_ID,
			type: 'circle',
			source: PROJECT_SOURCE_ID,
			filter: [
				'all',
				['!', ['has', 'point_count']],
				['==', ['get', 'project_id'], selectedProjectId ?? -1]
			],
			paint: {
				'circle-radius': ['+', ['get', 'radius'], 7],
				'circle-color': 'rgba(255,255,255,0)',
				'circle-stroke-color': '#f59e0b',
				'circle-stroke-width': 3,
				'circle-stroke-opacity': 0.95
			}
		})
	}

	map.setLayoutProperty(AREA_HEATMAP_LAYER_ID, 'visibility', showZoneHeatmap ? 'visible' : 'none')
	map.setLayoutProperty(AREA_LAYER_ID, 'visibility', 'visible')
	map.setPaintProperty(AREA_LAYER_ID, 'circle-opacity', showAreaBubbles ? 0.34 : 0.02)
	map.setPaintProperty(AREA_LAYER_ID, 'circle-stroke-opacity', showAreaBubbles ? 0.62 : 0)
	map.setLayoutProperty(
		AREA_LABEL_LAYER_ID,
		'visibility',
		showAreaBubbles || selectedAreaName ? 'visible' : 'none'
	)
	map.setPaintProperty(
		AREA_LABEL_LAYER_ID,
		'text-color',
		resolvedTheme === 'dark' ? '#e2e8f0' : '#0f172a'
	)
	map.setPaintProperty(
		AREA_LABEL_LAYER_ID,
		'text-halo-color',
		resolvedTheme === 'dark' ? '#020617' : '#ffffff'
	)
	map.setFilter(PROJECT_SELECTED_LAYER_ID, [
		'all',
		['!', ['has', 'point_count']],
		['==', ['get', 'project_id'], selectedProjectId ?? -1]
	])
	map.setFilter(AREA_LABEL_LAYER_ID, [
		'any',
		['==', ['get', 'show_label'], true],
		['==', ['get', 'area_name'], selectedAreaName ?? '']
	])
	setLayerVisibility(PROJECT_CLUSTER_LAYER_ID, showProjectPins)
	setLayerVisibility(PROJECT_CLUSTER_COUNT_LAYER_ID, showProjectPins)
	setLayerVisibility(PROJECT_HALO_LAYER_ID, showProjectPins)
	setLayerVisibility(PROJECT_LAYER_ID, showProjectPins)
	setLayerVisibility(PROJECT_SELECTED_LAYER_ID, showProjectPins)
	setLayerVisibility(BUILDING_CLUSTER_LAYER_ID, showBuildingPins)
	setLayerVisibility(BUILDING_CLUSTER_COUNT_LAYER_ID, showBuildingPins)
	setLayerVisibility(BUILDING_LAYER_ID, showBuildingPins)
	raiseProjectLayers()
	bindRadarHandlers()
}

// Draw area polygon on map
function drawAreaPolygon(polygon: GeoPolygon) {
	if (!map) {
		console.error('Map not initialized')
		return
	}
	currentAreaPolygon = polygon

	const drawPolygon = () => {
		if (!map) return
		if (currentAreaPolygon !== polygon) return
		try {
			_removeAreaPolygon()

			const sourceId = 'area-polygon'
			const layerId = 'area-polygon-layer'

			// Add source with polygon data
			map.addSource(sourceId, {
				type: 'geojson',
				data: {
					type: 'Feature',
					geometry: {
						type: 'Polygon',
						coordinates: [polygon.coordinates]
					},
					properties: {}
				}
			})

			// Add fill layer
			map.addLayer({
				id: layerId,
				type: 'fill',
				source: sourceId,
				paint: {
					'fill-color': '#2a5a78',
					'fill-opacity': 0.2
				}
			})

			// Add outline layer
			map.addLayer({
				id: `${layerId}-outline`,
				type: 'line',
				source: sourceId,
				paint: {
					'line-color': '#2a5a78',
					'line-width': 3,
					'line-opacity': 1
				}
			})

			areaPolygonLayer = layerId
		} catch (error) {
			console.error('Error drawing polygon:', error)
		}
	}

	if (map.isStyleLoaded()) {
		drawPolygon()
	} else {
		map.once('styledata', drawPolygon)
	}
}

// Add building pin markers to map
function addBuildingMarkers(pins: GeoPin[]) {
	if (!map) return

	currentBuildingPins = [...pins]
	_clearBuildingMarkers()

	pins.forEach((pin) => {
		if (!hasValidLngLat(pin.longitude, pin.latitude)) return
		const currentMap = map
		if (!currentMap) return
		const radarPin = pin as RadarGeoPin
		const isLand = (radarPin.point_type ?? '').toLowerCase() === 'land'
		const markerColor = isLand ? '#a55a13' : '#2a5a78'
		const markerEl = document.createElement('div')
		markerEl.style.cssText =
			'cursor: pointer; display: flex; flex-direction: column; align-items: center;'
		markerEl.innerHTML = `
				<svg width="28" height="36" viewBox="0 0 28 36" fill="none" xmlns="http://www.w3.org/2000/svg">
					<path d="M14 0C6.268 0 0 6.268 0 14C0 24.5 14 36 14 36C14 36 28 24.5 28 14C28 6.268 21.732 0 14 0Z" fill="${markerColor}"/>
					<circle cx="14" cy="14" r="6" fill="white"/>
				</svg>
			`

		const label = pin.building_name || pin.project_name
		const meta = `${detailPointLabel(radarPin)}${radarPin.floor_count ? ` · ${radarPin.floor_count} floors` : ''}`
		const popup = new maplibregl.Popup({
			offset: [0, -38],
			closeButton: false,
			closeOnClick: false,
			className: 'building-popup'
		}).setHTML(
			`<div style="font-size:13px;color:var(--color-map-popup-fg);white-space:nowrap;padding:2px 0;">` +
				`<div style="font-weight:700;">${escapeHtml(label)}</div>` +
				`<div style="font-size:11px;color:var(--color-map-popup-muted);margin-top:2px;">${escapeHtml(meta)}</div>` +
				`</div>`
		)

		const marker = new maplibregl.Marker({ element: markerEl })
			.setLngLat([pin.longitude, pin.latitude])
			.addTo(currentMap)

		markerEl.addEventListener('mouseenter', () =>
			popup.addTo(currentMap).setLngLat([pin.longitude, pin.latitude])
		)
		markerEl.addEventListener('mouseleave', () => popup.remove())
		markerEl.addEventListener('click', () => onBuildingPinClick?.(pin))

		buildingMarkers.push(marker)
		buildingPopups.push(popup)
	})
}

// Add or update a marker on the map
export function addProjectMarker(
	projectId: number,
	projectName: string,
	latitude: number,
	longitude: number
) {
	if (!map) return
	if (!hasValidLngLat(longitude, latitude)) return
	currentProjectMarkerInput = { projectId, projectName, latitude, longitude }

	// Remove previous marker if exists
	if (currentMarker) {
		currentMarker.remove()
	}

	// Create marker element
	const markerEl = document.createElement('div')
	markerEl.className =
		'w-10 h-10 bg-[#1c344a] rounded-full flex items-center justify-center shadow-lg border-2 border-white cursor-pointer hover:bg-[#0b1b2b] transition-colors'
	markerEl.innerHTML = `
			<svg class="w-5 h-5 text-white" fill="currentColor" viewBox="0 0 20 20">
				<path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16z" clip-rule="evenodd" />
			</svg>
		`

	// Create and add marker to map
	const marker = new maplibregl.Marker({ element: markerEl })
		.setLngLat([longitude, latitude])
		.addTo(map)

	// Create popup
	const popup = new maplibregl.Popup({ offset: 25, className: 'building-popup' }).setHTML(
		`<div style="font-size:13px;font-weight:600;color:var(--color-map-popup-fg);">${escapeHtml(projectName)}</div>`
	)

	marker.setPopup(popup)

	// Store current marker
	currentMarker = marker

	// Store in project markers map
	projectMarkers.set(projectId, {
		projectId,
		projectName,
		latitude,
		longitude,
		marker
	})
}

// Clear all markers and polygon
export function clearMarkers() {
	currentProjectMarkerInput = null
	currentAreaPolygon = null
	currentBuildingPins = []
	currentFitBoundsPins = []
	_clearProjectMarkers()
	_clearBuildingMarkers()
	_removeAreaPolygon()
}

// Fly to project and display area + buildings
export function flyToProject(
	projectId: number,
	projectName: string,
	latitude: number,
	longitude: number,
	areaPolygon: GeoPolygon | null = null,
	geoPins: GeoPin[] = [],
	zoom: number = 14
) {
	if (!map) {
		console.error('Map not initialized')
		return
	}

	// Clear previous markers
	clearMarkers()

	const hasProjectCoordinates = hasValidLngLat(longitude, latitude)

	if (hasProjectCoordinates) {
		// Fly to location
		map.flyTo({ center: [longitude, latitude], zoom, duration: 2000 })

		// Add main project marker
		addProjectMarker(projectId, projectName, latitude, longitude)
	}

	if ((areaPolygon?.coordinates?.length ?? 0) > 0 && areaPolygon) {
		drawAreaPolygon(areaPolygon)
	}

	// Add building pin markers if available
	if (geoPins && geoPins.length > 0) {
		addBuildingMarkers(geoPins)
		if (!hasProjectCoordinates) fitMapToPins(geoPins)
	}
}

export function flyToLocation(lng: number, lat: number, zoom: number = 14) {
	if (!hasValidLngLat(lng, lat)) return
	map?.flyTo({ center: [lng, lat], zoom })
}

function handleDDAPlotClick(e: maplibregl.MapLayerMouseEvent) {
	const props = e.features?.[0]?.properties
	if (!props || !map) return
	if (props.feature_type === 'outline') {
		new maplibregl.Popup({ className: 'building-popup' })
			.setLngLat(e.lngLat)
			.setHTML(ddaOutlinePopupHtml(props))
			.addTo(map)
		return
	}
	new maplibregl.Popup({ className: 'building-popup' })
		.setLngLat(e.lngLat)
		.setHTML(ddaParcelPopupHtml(props))
		.addTo(map)
}

function handleDDAPlotMouseEnter() {
	if (map) map.getCanvas().style.cursor = 'pointer'
}

function handleDDAPlotMouseMove(e: maplibregl.MapLayerMouseEvent) {
	if (!map) return
	const props = e.features?.[0]?.properties
	if (!props) return
	if (!hoverPopup) {
		hoverPopup = new maplibregl.Popup({
			closeButton: false,
			closeOnClick: false,
			className: 'building-popup',
			offset: 14
		}).addTo(map)
	}
	hoverPopup
		.setLngLat(e.lngLat)
		.setHTML(
			props.feature_type === 'outline' ? ddaOutlinePopupHtml(props) : ddaParcelPopupHtml(props)
		)
}

function handleDDAPlotMouseLeave() {
	if (map) map.getCanvas().style.cursor = ''
	hoverPopup?.remove()
	hoverPopup = null
}

function _unbindDDAHandlers() {
	if (!map) return
	try {
		map.off('click', DDA_FILL_LAYER_ID, handleDDAPlotClick)
		map.off('mouseenter', DDA_FILL_LAYER_ID, handleDDAPlotMouseEnter)
		map.off('mousemove', DDA_FILL_LAYER_ID, handleDDAPlotMouseMove)
		map.off('mouseleave', DDA_FILL_LAYER_ID, handleDDAPlotMouseLeave)
	} catch (_e) {
		// Handlers may not be bound yet.
	}
	ddaHandlersBound = false
}

function _bindDDAHandlers() {
	if (!map || ddaHandlersBound || !map.getLayer(DDA_FILL_LAYER_ID)) return
	ddaHandlersBound = true
	map.on('click', DDA_FILL_LAYER_ID, handleDDAPlotClick)
	map.on('mouseenter', DDA_FILL_LAYER_ID, handleDDAPlotMouseEnter)
	map.on('mousemove', DDA_FILL_LAYER_ID, handleDDAPlotMouseMove)
	map.on('mouseleave', DDA_FILL_LAYER_ID, handleDDAPlotMouseLeave)
}

function _removeDDALayers() {
	if (!map) return
	try {
		_unbindDDAHandlers()
		if (map.getLayer(DDA_OUTLINE_CORE_LAYER_ID)) map.removeLayer(DDA_OUTLINE_CORE_LAYER_ID)
		if (map.getLayer(DDA_FILL_LAYER_ID)) map.removeLayer(DDA_FILL_LAYER_ID)
		if (map.getLayer(DDA_OUTLINE_LAYER_ID)) map.removeLayer(DDA_OUTLINE_LAYER_ID)
		if (map.getSource(DDA_SOURCE_ID)) map.removeSource(DDA_SOURCE_ID)
	} catch (_e) {}
}

function ddaBeforeLayerId() {
	if (!map) return undefined
	if (map.getLayer(PROJECT_HALO_LAYER_ID)) return PROJECT_HALO_LAYER_ID
	if (map.getLayer('area-polygon-layer')) return 'area-polygon-layer'
	return undefined
}

function applyDDAPaint(mode: DdaLayerMode) {
	if (!map) return
	if (map.getLayer(DDA_FILL_LAYER_ID)) {
		map.setPaintProperty(DDA_FILL_LAYER_ID, 'fill-opacity', mode === 'parcels' ? 0.3 : 0.045)
	}
	if (map.getLayer(DDA_OUTLINE_LAYER_ID)) {
		map.setPaintProperty(DDA_OUTLINE_LAYER_ID, 'line-color', '#fff7ed')
		map.setPaintProperty(DDA_OUTLINE_LAYER_ID, 'line-width', [
			'interpolate',
			['linear'],
			['zoom'],
			10,
			mode === 'parcels' ? 1.4 : 1.7,
			16,
			mode === 'parcels' ? 4.4 : 2.8
		])
		map.setPaintProperty(DDA_OUTLINE_LAYER_ID, 'line-opacity', mode === 'parcels' ? 0.86 : 0.46)
	}
	if (map.getLayer(DDA_OUTLINE_CORE_LAYER_ID)) {
		map.setPaintProperty(
			DDA_OUTLINE_CORE_LAYER_ID,
			'line-color',
			mode === 'parcels' ? '#92400e' : '#d97706'
		)
		map.setPaintProperty(DDA_OUTLINE_CORE_LAYER_ID, 'line-width', [
			'interpolate',
			['linear'],
			['zoom'],
			10,
			mode === 'parcels' ? 0.75 : 0.7,
			16,
			mode === 'parcels' ? 2.3 : 1.4
		])
		map.setPaintProperty(
			DDA_OUTLINE_CORE_LAYER_ID,
			'line-opacity',
			mode === 'parcels' ? 0.94 : 0.58
		)
	}
}

function ensureDDALayers(mode: DdaLayerMode) {
	if (!map) return
	if (!map.getSource(DDA_SOURCE_ID)) {
		map.addSource(DDA_SOURCE_ID, { type: 'geojson', data: featureCollection([]) })
	}

	const beforeId = ddaBeforeLayerId()
	if (!map.getLayer(DDA_FILL_LAYER_ID)) {
		map.addLayer(
			{
				id: DDA_FILL_LAYER_ID,
				type: 'fill',
				source: DDA_SOURCE_ID,
				paint: { 'fill-color': ['get', 'color'], 'fill-opacity': 0 }
			},
			beforeId
		)
	}
	if (!map.getLayer(DDA_OUTLINE_LAYER_ID)) {
		map.addLayer(
			{
				id: DDA_OUTLINE_LAYER_ID,
				type: 'line',
				source: DDA_SOURCE_ID,
				paint: { 'line-color': '#fff7ed', 'line-width': 1, 'line-opacity': 0 }
			},
			beforeId
		)
	}
	if (!map.getLayer(DDA_OUTLINE_CORE_LAYER_ID)) {
		map.addLayer(
			{
				id: DDA_OUTLINE_CORE_LAYER_ID,
				type: 'line',
				source: DDA_SOURCE_ID,
				paint: { 'line-color': '#d97706', 'line-width': 1, 'line-opacity': 0 }
			},
			beforeId
		)
	}

	applyDDAPaint(mode)
	_bindDDAHandlers()
}

export function showDDAFeatures(features: DdaMapFeature[], mode: DdaLayerMode) {
	if (!map) return
	const requestedFeatures = [...features]
	const renderVersion = ++ddaRenderVersion
	currentDDAFeatures = requestedFeatures
	currentDDAMode = mode

	const render = () => {
		if (!map) return
		if (renderVersion !== ddaRenderVersion) return
		ensureDDALayers(mode)
		const source = map.getSource(DDA_SOURCE_ID) as maplibregl.GeoJSONSource | undefined
		source?.setData(ddaFeatureCollection(requestedFeatures))
	}

	if (map.isStyleLoaded()) {
		render()
	} else {
		map.once('styledata', render)
	}
}

export function showDDAPlots(plots: DdaPlotFeature[]) {
	showDDAFeatures(plots, 'parcels')
}

export function hideDDAPlots() {
	ddaRenderVersion += 1
	currentDDAFeatures = []
	_removeDDALayers()
}

// Show all building pins for a master project and fit map to their bounds
export function fitBounds(pins: GeoPin[]) {
	if (!map || pins.length === 0) return
	clearMarkers()
	currentFitBoundsPins = [...pins]
	addBuildingMarkers(pins)
	fitMapToPins(pins)
}
</script>

<div class="w-full h-full relative" style="min-height: 400px;">
	<div bind:this={mapContainer} class="absolute inset-0" style="width: 100%; height: 100%;"></div>
</div>
