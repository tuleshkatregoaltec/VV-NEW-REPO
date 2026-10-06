import { type ListingListResponse, type ListingParams, listings } from '$lib/api/listings'

type ListingFilters = Omit<ListingParams, 'limit' | 'offset'>

export const listingKeys = {
	all: ['listings'] as const,
	list: (params: ListingParams) => [...listingKeys.all, 'list', params] as const,
	filters: (params: Pick<ListingParams, 'mode' | 'asset_class'>) =>
		[...listingKeys.all, 'filters', params] as const,
	analytics: (params: ListingParams) => [...listingKeys.all, 'analytics', params] as const,
	detail: (listingId: string) => [...listingKeys.all, 'detail', listingId] as const
}

export const listingQueries = {
	list: (params: ListingParams) => ({
		queryKey: listingKeys.list(params),
		queryFn: () => listings.list(params),
		staleTime: 30 * 60 * 1000
	}),
	listInfinite: (params: ListingFilters, limit: number) => ({
		queryKey: listingKeys.list({ ...params, limit }),
		queryFn: ({ pageParam = 0 }: { pageParam: number }) =>
			listings.list({ ...params, limit, offset: pageParam }),
		getNextPageParam: (lastPage: ListingListResponse) => {
			const nextOffset = lastPage.offset + lastPage.listings.length
			return nextOffset < lastPage.total ? nextOffset : undefined
		},
		initialPageParam: 0,
		staleTime: 30 * 60 * 1000
	}),
	filters: (params: Pick<ListingParams, 'mode' | 'asset_class'>) => ({
		queryKey: listingKeys.filters(params),
		queryFn: () => listings.filters(params),
		staleTime: 30 * 60 * 1000
	}),
	analytics: (params: ListingFilters) => ({
		queryKey: listingKeys.analytics(params),
		queryFn: () => listings.analytics(params),
		staleTime: 30 * 60 * 1000
	}),
	detail: (listingId: string | null) => ({
		queryKey: listingKeys.detail(listingId ?? ''),
		queryFn: () => listings.get(listingId ?? ''),
		enabled: Boolean(listingId),
		staleTime: 30 * 60 * 1000
	})
}
