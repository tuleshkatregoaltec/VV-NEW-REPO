import type { ListingListResponse, MarketTrendResponse } from '$lib/api/generated/hey-api/types.gen'

export type ChatArtifactStatus = 'loading' | 'ready' | 'error' | 'stale'

export interface ChatArtifactBase {
	id: string
	type: 'listing_results' | 'market_trend' | 'custom_chart'
	status: ChatArtifactStatus
	title: string
	subtitle?: string | null
	created_at: string
	query?: Record<string, unknown> | null
	error?: string | null
}

export interface ListingResultsArtifact extends ChatArtifactBase {
	type: 'listing_results'
	data?: ListingListResponse | null
}

export interface MarketTrendArtifact extends ChatArtifactBase {
	type: 'market_trend'
	data?: MarketTrendResponse | null
}

export interface CustomChartPoint {
	label: string
	value: number
	record_count?: number | null
	date?: string | null
}

export interface CustomChartSeries {
	label: string
	points: CustomChartPoint[]
}

export interface CustomChartData {
	chart_type: 'line' | 'bar' | 'horizontal_bar' | 'doughnut'
	metric: string
	metric_label: string
	dimension: string
	dimension_label: string
	data_source?: string | null
	sort_direction?: 'asc' | 'desc' | null
	points: CustomChartPoint[]
	series?: CustomChartSeries[] | null
	summary?: {
		point_count?: number | null
		total_records?: number | null
		period_start?: string | null
		period_end?: string | null
	} | null
}

export interface CustomChartArtifact extends ChatArtifactBase {
	type: 'custom_chart'
	data?: CustomChartData | null
}

export type ChatArtifact = ListingResultsArtifact | MarketTrendArtifact | CustomChartArtifact

export interface ChatArtifactStreamEvent {
	type: 'artifact_opened' | 'artifact_updated'
	artifact: ChatArtifact
}

export function isChatArtifact(value: unknown): value is ChatArtifact {
	if (!value || typeof value !== 'object') return false
	const candidate = value as Partial<ChatArtifact>
	return (
		typeof candidate.id === 'string' &&
		(candidate.type === 'listing_results' ||
			candidate.type === 'market_trend' ||
			candidate.type === 'custom_chart') &&
		(candidate.status === 'loading' ||
			candidate.status === 'ready' ||
			candidate.status === 'error' ||
			candidate.status === 'stale') &&
		typeof candidate.title === 'string'
	)
}

export function artifactSortValue(artifact: ChatArtifact): number {
	const time = new Date(artifact.created_at).getTime()
	return Number.isFinite(time) ? time : 0
}
