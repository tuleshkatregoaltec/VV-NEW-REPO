<script lang="ts">
import maplibregl from 'maplibre-gl'
import { onMount } from 'svelte'
import type {
	DdaOutlineFeature,
	DdaPlotFeature,
	GeoPin,
	GeoPolygon,
	ProjectRadarArea,
	ProjectRadarProject
} from '$lib/api/projects'
import { colorTheme } from '$lib/stores/preferences.svelte'

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
type RadarOverlayMode = 'pipeline' | 'demand' | 'yield' | 'delivery'
type DdaLayerMode = 'outlines' | 'parcels'
type DdaMapFeature = DdaPlotFeature | DdaOutlineFeature
interface MapViewport {
	west: number
	south: number
	east: number
	north: number
	zoom: number
}

let {
	onProjectSelect,
	onBuildingPinClick,
	onAreaSelect,
	onViewportChange,
	projectPins = [],
	areaBubbles = [],
	selectedProjectId = null,
	selectedAreaName = null,
	showProjectPins = true,
	showAreaBubbles = true,
	overlayMode = 'pipeline'
}: {
	onProjectSelect?: (projectId: number) => void
	onBuildingPinClick?: (pin: GeoPin) => void
	onAreaSelect?: (areaName: string) => void
	onViewportChange?: (viewport: MapViewport) => void
	projectPins?: ProjectRadarProject[]
	areaBubbles?: ProjectRadarArea[]
	selectedProjectId?: number | null
	selectedAreaName?: string | null
	showProjectPins?: boolean
	showAreaBubbles?: boolean
	overlayMode?: RadarOverlayMode
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
const PROJECT_HALO_LAYER_ID = 'radar-project-halos'
const PROJECT_LAYER_ID = 'radar-project-pins'
const PROJECT_SELECTED_LAYER_ID = 'radar-project-selected'
const AREA_SOURCE_ID = 'radar-areas'
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

function projectStage(project: ProjectRadarProject) {
	if (project.completion_status === 'FINISHED') return 'Finished'
	if (project.pipeline_status === 'delivering_next_12_months') return 'Next 12m'
	if (project.pipeline_status === 'future') return 'Future'
	return 'Unscheduled'
}

function projectColor(project: ProjectRadarProject, mode: RadarOverlayMode) {
	if (mode === 'demand') return '#2563eb'
	if (mode === 'yield') {
		const value = project.gross_yield_pct ?? 0
		if (value >= 9) return '#059669'
		if (value >= 6.5) return '#0d9488'
		if (value > 0) return '#f59e0b'
		return '#94a3b8'
	}
	if (mode === 'delivery') {
		if (project.delivery_confidence >= 0.75) return '#059669'
		if (project.delivery_confidence >= 0.5) return '#f59e0b'
		return '#dc2626'
	}
	if (project.completion_status === 'FINISHED') return '#64748b'
	if (project.pipeline_status === 'delivering_next_12_months') return '#0f766e'
	if (project.pipeline_status === 'future') return '#0369a1'
	return '#7c3aed'
}

function projectRadius(project: ProjectRadarProject, mode: RadarOverlayMode) {
	if (mode === 'demand') {
		return clamp(
			5 + Math.sqrt(project.sales_transaction_count_12m + project.rental_contract_count_12m) / 5,
			5,
			24
		)
	}
	if (mode === 'yield') {
		return clamp(5 + (project.gross_yield_pct ?? 0) * 1.2, 5, 23)
	}
	if (mode === 'delivery') {
		return clamp(5 + project.delivery_confidence * 15, 5, 22)
	}
	return clamp(5 + Math.sqrt(project.no_of_units || 0) / 4, 5, 24)
}

function areaRadius(area: ProjectRadarArea) {
	return clamp(9 + Math.sqrt(area.pipeline_units || area.mapped_projects || 0) / 18, 10, 42)
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
	if (category === 'Residential') return '#0f766e'
	if (category === 'Commercial') return '#2563eb'
	if (category === 'Open Space') return '#65a30d'
	if (category === 'Utilities') return '#64748b'
	return '#f59e0b'
}

function isDDAOutlineFeature(feature: DdaMapFeature): feature is DdaOutlineFeature {
	return 'kind' in feature && 'plot_count' in feature && !('plot_number' in feature)
}

function projectFeature(project: ProjectRadarProject): GeoJSON.Feature {
	return {
		type: 'Feature',
		geometry: { type: 'Point', coordinates: [project.longitude, project.latitude] },
		properties: {
			project_id: project.project_id,
			project_name: project.project_name,
			area_name: project.area_name,
			developer_name: project.developer_name ?? '',
			stage: projectStage(project),
			no_of_units: project.no_of_units,
			sales_transaction_count_12m: project.sales_transaction_count_12m,
			rental_contract_count_12m: project.rental_contract_count_12m,
			gross_yield_pct: project.gross_yield_pct ?? 0,
			radius: projectRadius(project, overlayMode),
			color: projectColor(project, overlayMode)
		}
	}
}

function areaFeature(area: ProjectRadarArea, index: number): GeoJSON.Feature | null {
	if (area.latitude == null || area.longitude == null) return null
	if (!hasValidLngLat(area.longitude, area.latitude)) return null
	return {
		type: 'Feature',
		geometry: { type: 'Point', coordinates: [area.longitude, area.latitude] },
		properties: {
			area_name: area.area_name,
			active_projects: area.active_projects,
			pipeline_units: area.pipeline_units,
			sales_transaction_count_12m: area.sales_transaction_count_12m,
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

function ddaParcelPopupHtml(props: Record<string, unknown>) {
	const areaSqm = Number(props.plot_area_sqm)
	const maxGfaSqm = Number(props.max_gfa_sqm)
	const valuationMin = Number(props.valuation_min_aed)
	const valuationMax = Number(props.valuation_max_aed)
	const rateMin = Number(props.valuation_rate_min_aed_sqft)
	const rateMax = Number(props.valuation_rate_max_aed_sqft)
	const plotNumber = escapeHtml(props.plot_number)
	const communityName = escapeHtml(props.community_name)
	const valuationLabel =
		valuationMin > 0 && valuationMax > 0
			? `${formatAedCompact(valuationMin)} - ${formatAedCompact(valuationMax)}`
			: '~'
	const rateLabel = rateMin > 0 && rateMax > 0 ? `AED ${rateMin}-${rateMax} / sqft` : '~'
	return (
		`<div style="min-width:210px;font-size:12px;line-height:1.55;">` +
		`<div style="font-weight:700;color:var(--color-map-popup-fg);">Plot ${plotNumber}</div>` +
		`<div style="color:var(--color-map-popup-muted);margin-top:2px;">${formatSqmCompact(areaSqm)} · ${communityName}</div>` +
		`<div style="margin-top:8px;border-top:1px solid color-mix(in srgb,var(--color-map-popup-muted) 20%,transparent);padding-top:7px;">` +
		`<div style="color:var(--color-map-popup-muted);">Indicative valuation</div>` +
		`<div style="font-weight:700;color:var(--color-map-popup-fg);font-size:13px;">${valuationLabel}</div>` +
		`<div style="color:var(--color-map-popup-muted);margin-top:2px;">${formatSqmCompact(maxGfaSqm)} max GFA · ${rateLabel}</div>` +
		`</div>` +
		`</div>`
	)
}

function ddaOutlinePopupHtml(props: Record<string, unknown>) {
	return (
		`<div style="font-size:12px;line-height:1.6;">` +
		`<div style="font-weight:700;color:var(--color-map-popup-fg);">${escapeHtml(props.name)}</div>` +
		`<div style="color:var(--color-map-popup-muted);margin-top:2px;">${Number(
			props.plot_count || 0
		).toLocaleString()} plots · ${escapeHtml(props.kind)}</div>` +
		`</div>`
	)
}

function ddaFeatureCollection(features: DdaMapFeature[]): GeoJSON.FeatureCollection {
	return featureCollection(
		features.map((feature) => {
			const isOutline = isDDAOutlineFeature(feature)
			const category = plotCategory(feature)
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
							category,
							color: '#f59e0b'
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
							category,
							color: plotColor(category)
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
	areaBubbles
	selectedProjectId
	selectedAreaName
	showProjectPins
	showAreaBubbles
	overlayMode
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

function setSourceData(sourceId: string, data: GeoJSON.FeatureCollection) {
	if (!map) return
	const source = map.getSource(sourceId) as maplibregl.GeoJSONSource | undefined
	if (source) {
		source.setData(data)
	} else {
		map.addSource(sourceId, { type: 'geojson', data })
	}
}

function bindRadarHandlers() {
	if (!map || radarHandlersBound) return
	radarHandlersBound = true

	map.on('click', PROJECT_LAYER_ID, (event) => {
		const id = Number(event.features?.[0]?.properties?.project_id)
		if (Number.isFinite(id)) onProjectSelect?.(id)
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
					`<div style="color:var(--color-map-popup-muted);margin-top:2px;">${escapeHtml(props.area_name)} · ${escapeHtml(props.stage)}</div>` +
					`<div style="color:var(--color-map-popup-muted);margin-top:6px;">${Number(
						props.no_of_units || 0
					).toLocaleString()} units · ${Number(
						props.sales_transaction_count_12m || 0
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

	map.on('mouseenter', AREA_LAYER_ID, () => {
		if (map) map.getCanvas().style.cursor = 'pointer'
	})
	map.on('mouseleave', AREA_LAYER_ID, () => {
		if (map) map.getCanvas().style.cursor = ''
	})
}

function syncRadarLayers() {
	if (!map || !map.isStyleLoaded()) return

	const projectFeatures = showProjectPins
		? projectPins
				.filter((project) => hasValidLngLat(project.longitude, project.latitude))
				.map((project) => projectFeature(project))
		: []
	const areaFeatures = showAreaBubbles
		? areaBubbles
				.map((area, index) => areaFeature(area, index))
				.filter((feature): feature is GeoJSON.Feature => feature !== null)
		: []

	setSourceData(AREA_SOURCE_ID, featureCollection(areaFeatures))
	setSourceData(PROJECT_SOURCE_ID, featureCollection(projectFeatures))

	if (!map.getLayer(AREA_LAYER_ID)) {
		map.addLayer({
			id: AREA_LAYER_ID,
			type: 'circle',
			source: AREA_SOURCE_ID,
			paint: {
				'circle-radius': ['get', 'radius'],
				'circle-color': '#0f766e',
				'circle-opacity': 0.14,
				'circle-stroke-color': '#0f766e',
				'circle-stroke-width': 1.5,
				'circle-stroke-opacity': 0.36
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
	if (!map.getLayer(PROJECT_HALO_LAYER_ID)) {
		map.addLayer({
			id: PROJECT_HALO_LAYER_ID,
			type: 'circle',
			source: PROJECT_SOURCE_ID,
			paint: {
				'circle-radius': ['+', ['get', 'radius'], 3],
				'circle-color': ['get', 'color'],
				'circle-opacity': 0.12
			}
		})
	}
	if (!map.getLayer(PROJECT_LAYER_ID)) {
		map.addLayer({
			id: PROJECT_LAYER_ID,
			type: 'circle',
			source: PROJECT_SOURCE_ID,
			paint: {
				'circle-radius': ['get', 'radius'],
				'circle-color': ['get', 'color'],
				'circle-opacity': 0.78,
				'circle-stroke-color': resolvedTheme === 'dark' ? '#020617' : '#ffffff',
				'circle-stroke-width': 1.6,
				'circle-stroke-opacity': 0.92
			}
		})
	}
	if (!map.getLayer(PROJECT_SELECTED_LAYER_ID)) {
		map.addLayer({
			id: PROJECT_SELECTED_LAYER_ID,
			type: 'circle',
			source: PROJECT_SOURCE_ID,
			filter: ['==', ['get', 'project_id'], selectedProjectId ?? -1],
			paint: {
				'circle-radius': ['+', ['get', 'radius'], 7],
				'circle-color': 'rgba(255,255,255,0)',
				'circle-stroke-color': '#f59e0b',
				'circle-stroke-width': 3,
				'circle-stroke-opacity': 0.95
			}
		})
	}

	map.setFilter(PROJECT_SELECTED_LAYER_ID, ['==', ['get', 'project_id'], selectedProjectId ?? -1])
	map.setFilter(AREA_LABEL_LAYER_ID, [
		'any',
		['==', ['get', 'show_label'], true],
		['==', ['get', 'area_name'], selectedAreaName ?? '']
	])
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
					'fill-color': '#0d9488',
					'fill-opacity': 0.2
				}
			})

			// Add outline layer
			map.addLayer({
				id: `${layerId}-outline`,
				type: 'line',
				source: sourceId,
				paint: {
					'line-color': '#0d9488',
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
		const markerEl = document.createElement('div')
		markerEl.style.cssText =
			'cursor: pointer; display: flex; flex-direction: column; align-items: center;'
		markerEl.innerHTML = `
				<svg width="28" height="36" viewBox="0 0 28 36" fill="none" xmlns="http://www.w3.org/2000/svg">
					<path d="M14 0C6.268 0 0 6.268 0 14C0 24.5 14 36 14 36C14 36 28 24.5 28 14C28 6.268 21.732 0 14 0Z" fill="#0d9488"/>
					<circle cx="14" cy="14" r="6" fill="white"/>
				</svg>
			`

		const label = pin.building_name || pin.project_name
		const popup = new maplibregl.Popup({
			offset: [0, -38],
			closeButton: false,
			closeOnClick: false,
			className: 'building-popup'
		}).setHTML(
			`<div style="font-size:13px;font-weight:600;color:var(--color-map-popup-fg);white-space:nowrap;padding:2px 0;">${escapeHtml(label)}</div>`
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
