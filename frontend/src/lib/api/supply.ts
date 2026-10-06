import { client } from './client'
import type {
	DeveloperRankingCriterionResponse,
	DeveloperRankingResponse,
	DeveloperRankingSummaryResponse,
	DeveloperRankingsResponse,
	SupplyCatalogueFinancialMetricResponse,
	SupplyCatalogueProjectCardResponse,
	SupplyCatalogueProjectDetailResponse,
	SupplyCatalogueProjectsResponse,
	SupplyCatalogueRiskIndicatorResponse,
	UpcomingProjectResponse,
	UpcomingProjectsResponse
} from './generated/hey-api/types.gen'

export type DeveloperRankingMetric =
	| 'proprietary_score'
	| 'units_sold'
	| 'sales_volume'
	| 'avg_price_sqft'
	| 'pipeline_units'
	| 'active_projects'
	| 'completed_projects'
	| 'avg_completion_pct'

export type DeveloperRankingPeriod = 'ytd' | '1y' | '3y' | '5y'
export type SupplyCatalogueSort =
	| 'recommended'
	| 'newest'
	| 'price_low'
	| 'price_high'
	| 'delivery_soon'
	| 'delivery_latest'

export type {
	DeveloperRankingCriterionResponse,
	DeveloperRankingResponse,
	DeveloperRankingSummaryResponse,
	DeveloperRankingsResponse,
	SupplyCatalogueFinancialMetricResponse,
	SupplyCatalogueProjectCardResponse,
	SupplyCatalogueProjectDetailResponse,
	SupplyCatalogueProjectsResponse,
	SupplyCatalogueRiskIndicatorResponse,
	UpcomingProjectResponse,
	UpcomingProjectsResponse
}

export interface SupplyCatalogueParams {
	limit?: number
	offset?: number
	search?: string
	area?: string
	status?: string
	developer?: string
	sort?: SupplyCatalogueSort
	include_past?: boolean
}

export interface DeveloperRankingParams {
	period?: DeveloperRankingPeriod
	metric?: DeveloperRankingMetric
	limit?: number
}

export const supply = {
	getUpcomingProjects: () =>
		client.get<UpcomingProjectsResponse>('/api/v1/supply/upcoming-projects'),

	catalogue: (params: SupplyCatalogueParams = {}) =>
		client.get<SupplyCatalogueProjectsResponse>(
			client.withQuery('/api/v1/supply/catalogue/projects', {
				limit: params.limit,
				offset: params.offset,
				search: params.search,
				area: params.area,
				status: params.status,
				developer: params.developer,
				sort: params.sort,
				include_past: params.include_past
			})
		),

	catalogueProject: (projectId: number) =>
		client.get<SupplyCatalogueProjectDetailResponse>(
			`/api/v1/supply/catalogue/projects/${projectId}`
		),

	developerRankings: (params: DeveloperRankingParams = {}) =>
		client.get<DeveloperRankingsResponse>(
			client.withQuery('/api/v1/supply/developer-rankings', {
				period: params.period,
				metric: params.metric,
				limit: params.limit
			})
		)
}
