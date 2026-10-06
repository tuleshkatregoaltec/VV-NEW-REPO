import { client } from './client'
import type {
	NewsArticleResponse,
	NewsListResponse,
	NewsSummaryResponse,
	NewsSummarySection
} from './generated/hey-api/types.gen'

export type { NewsArticleResponse, NewsListResponse, NewsSummaryResponse, NewsSummarySection }

export const news = {
	list: (params: { limit?: number; offset?: number }) =>
		client.get<NewsListResponse>(client.withQuery('/api/v1/news/articles', params)),
	summary: () => client.get<NewsSummaryResponse>('/api/v1/news/summary')
}
