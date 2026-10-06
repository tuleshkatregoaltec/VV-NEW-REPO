import { client } from './client'
import type {
	ListingCardResponse as GeneratedListingCardResponse,
	ListingDetailResponse as GeneratedListingDetailResponse,
	ListingFiltersResponse as GeneratedListingFiltersResponse,
	ListingListResponse as GeneratedListingListResponse,
	ListingFloorPlanResponse,
	ListingImageResponse,
	ListingPartyResponse
} from './generated/hey-api/types.gen'

export type ListingMode = 'sale' | 'rent'
export type ListingAssetClass = 'residential' | 'commercial'
export type ListingMarketPosition =
	| 'below_market'
	| 'near_market'
	| 'above_market'
	| 'insufficient_data'
export type ListingBenchmarkLevel = 'building_layout' | 'project_layout' | 'insufficient_data'
export type ListingUrgencySignal = 'explicit_urgency' | 'value_language' | 'none'

export interface ListingIntelligenceFields {
	asset_class: ListingAssetClass
	listing_age_days: number | null
	price_per_sqft_aed: number | null
	market_median_price_per_sqft_aed: number | null
	market_estimate_aed: number | null
	market_delta_pct: number | null
	market_position: ListingMarketPosition
	comparable_count: number
	benchmark_level: ListingBenchmarkLevel
	urgency_signal: ListingUrgencySignal
	urgency_terms: string[]
}

export interface ListingCardResponse
	extends GeneratedListingCardResponse,
		ListingIntelligenceFields {}

export interface ListingDetailResponse
	extends GeneratedListingDetailResponse,
		ListingIntelligenceFields {}

export interface ListingFiltersResponse extends GeneratedListingFiltersResponse {
	asset_classes: ListingAssetClass[]
}

export interface ListingListResponse
	extends Omit<GeneratedListingListResponse, 'listings' | 'filters'> {
	listings: ListingCardResponse[]
	filters: ListingFiltersResponse
}

export interface ListingTrendPoint {
	period: string
	average_asking_price_aed: number | null
	median_asking_price_aed: number | null
	median_price_per_sqft_aed: number | null
	listing_count: number
	median_achieved_price_per_sqft_aed: number | null
	achieved_transaction_count: number
}

export interface ListingAnalyticsResponse {
	total: number
	average_price_aed: number | null
	median_price_aed: number | null
	median_price_per_sqft_aed: number | null
	average_listing_age_days: number | null
	median_listing_age_days: number | null
	newly_listed_30d: number
	below_market_count: number
	near_market_count: number
	above_market_count: number
	benchmarked_count: number
	verified_count: number
	area_count: number
	snapshot_at: string | null
	trend: ListingTrendPoint[]
}

export type { ListingFloorPlanResponse, ListingImageResponse, ListingPartyResponse }

export interface ListingParams {
	mode?: ListingMode
	asset_class?: ListingAssetClass
	limit?: number
	offset?: number
	search?: string
	area?: string
	property_type?: string
	bedrooms?: string
	price_min?: number
	price_max?: number
}

export const listings = {
	list: (params: ListingParams = {}) =>
		client.get<ListingListResponse>(
			client.withQuery('/api/v1/listings', {
				mode: params.mode,
				asset_class: params.asset_class,
				limit: params.limit,
				offset: params.offset,
				search: params.search,
				area: params.area,
				property_type: params.property_type,
				bedrooms: params.bedrooms,
				price_min: params.price_min,
				price_max: params.price_max
			})
		),

	filters: (params: Pick<ListingParams, 'mode' | 'asset_class'> = {}) =>
		client.get<ListingFiltersResponse>(
			client.withQuery('/api/v1/listings/filters', {
				mode: params.mode,
				asset_class: params.asset_class
			})
		),

	analytics: (params: ListingParams = {}) =>
		client.get<ListingAnalyticsResponse>(
			client.withQuery('/api/v1/listings/analytics', {
				mode: params.mode,
				asset_class: params.asset_class,
				search: params.search,
				area: params.area,
				property_type: params.property_type,
				bedrooms: params.bedrooms,
				price_min: params.price_min,
				price_max: params.price_max
			})
		),

	get: (listingId: string) =>
		client.get<ListingDetailResponse>(`/api/v1/listings/${encodeURIComponent(listingId)}`)
}
