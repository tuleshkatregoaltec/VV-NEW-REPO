import { client } from './client'
import type {
	BuildingDetailResponse,
	BuildingInfo,
	BuildingUnitType,
	DdaOutlineFeature,
	DdaPlotFeature,
	GeoPin,
	GeoPolygon,
	MasterProjectResponse,
	MasterProjectSummary,
	ProjectDetailResponse,
	ProjectRadarArea,
	ProjectRadarOverviewResponse,
	ProjectRadarProject,
	ProjectRadarResponse,
	ProjectRadarStats,
	ProjectSearchResult,
	ProjectUnitComposition
} from './generated/hey-api/types.gen'

export type {
	BuildingDetailResponse,
	BuildingInfo,
	BuildingUnitType,
	DdaOutlineFeature,
	DdaPlotFeature,
	GeoPin,
	GeoPolygon,
	MasterProjectResponse,
	MasterProjectSummary,
	ProjectDetailResponse,
	ProjectRadarArea,
	ProjectRadarOverviewResponse,
	ProjectRadarProject,
	ProjectRadarResponse,
	ProjectRadarStats,
	ProjectSearchResult,
	ProjectUnitComposition
}

export type SearchSelection =
	| { type: 'master'; masterName: string }
	| { type: 'project'; projectId: number }

export interface DdaPlotParams {
	area?: string | null
	west?: number | null
	south?: number | null
	east?: number | null
	north?: number | null
	limit?: number
	include_valuations?: boolean
}

export interface DdaOutlineParams {
	west: number
	south: number
	east: number
	north: number
	zoom: number
	limit?: number
}

export interface RadarPinParams {
	west?: number | null
	south?: number | null
	east?: number | null
	north?: number | null
	area?: string | null
	developer?: string | null
	limit?: number
	period_days?: RadarPeriodDays
}

export interface RadarBuildingPin {
	location_id: string
	source_location_id: string
	building_name: string
	project_name?: string | null
	area_name: string
	latitude: number
	longitude: number
	coordinate_source: string
	coordinate_precision: string
	matched_source_signatures: number
	sales_transaction_count: number
	rental_contract_count: number
	total_sales_volume: number
	median_sale_price?: number | null
	median_annual_rent?: number | null
	listing_inventory_count: number
	last_activity_date?: string | null
}

export interface RadarBuildingPinParams {
	west: number
	south: number
	east: number
	north: number
	limit?: number
	period_days?: RadarPeriodDays
}

export type RadarPeriodDays = 30 | 90 | 180 | 365

export const projects = {
	list: (): Promise<ProjectSearchResult[]> => client.get(`/api/v1/projects/list`),
	radar: (limit = 1400, periodDays: RadarPeriodDays = 365): Promise<ProjectRadarResponse> =>
		client.get(client.withQuery('/api/v1/projects/radar', { limit, period_days: periodDays })),
	radarOverview: (periodDays: RadarPeriodDays = 365): Promise<ProjectRadarOverviewResponse> =>
		client.get(client.withQuery('/api/v1/projects/radar/overview', { period_days: periodDays })),
	radarPins: (params: RadarPinParams): Promise<ProjectRadarProject[]> =>
		client.get(client.withQuery('/api/v1/projects/radar/pins', { ...params })),
	radarBuildingPins: (params: RadarBuildingPinParams): Promise<RadarBuildingPin[]> =>
		client.get(client.withQuery('/api/v1/projects/radar/building-pins', { ...params })),
	getDetails: (id: number): Promise<ProjectDetailResponse> => client.get(`/api/v1/projects/${id}`),
	getMaster: (name: string): Promise<MasterProjectResponse> =>
		client.get(client.withQuery('/api/v1/projects/master', { name })),
	getBuilding: (propertyId: number): Promise<BuildingDetailResponse> =>
		client.get(`/api/v1/projects/building/${propertyId}`),
	ddaPlots: (params: DdaPlotParams): Promise<DdaPlotFeature[]> =>
		client.get(client.withQuery('/api/v1/projects/dda-plots', { ...params })),
	ddaOutlines: (params: DdaOutlineParams): Promise<DdaOutlineFeature[]> =>
		client.get(client.withQuery('/api/v1/projects/dda-outlines', { ...params }))
}
