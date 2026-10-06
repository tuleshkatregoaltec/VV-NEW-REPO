import { news } from '$lib/api/news'

export const newsKeys = {
	all: ['news'] as const,
	list: (scope: string, limit: number) => [...newsKeys.all, scope, { limit }] as const,
	summary: () => [...newsKeys.all, 'summary'] as const
}

export const newsQueries = {
	summary: () => ({
		queryKey: newsKeys.summary(),
		queryFn: () => news.summary(),
		staleTime: 15 * 60 * 1000
	}),
	listInfinite: (scope: string, limit: number) => ({
		queryKey: newsKeys.list(scope, limit),
		queryFn: ({ pageParam = 0 }: { pageParam: number }) => news.list({ limit, offset: pageParam }),
		getNextPageParam: (lastPage: { offset: number; articles: Array<unknown>; total: number }) => {
			const nextOffset = lastPage.offset + lastPage.articles.length
			return nextOffset < lastPage.total ? nextOffset : undefined
		},
		initialPageParam: 0
	})
}
