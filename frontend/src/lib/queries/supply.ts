import {
	type DeveloperRankingParams,
	type SupplyCatalogueParams,
	type SupplyCatalogueProjectsResponse,
	supply
} from '$lib/api/supply'

type SupplyCatalogueFilters = Omit<SupplyCatalogueParams, 'limit' | 'offset'>

export const supplyKeys = {
	all: ['supply'] as const,
	developerRankings: (params: DeveloperRankingParams) =>
		[...supplyKeys.all, 'developer-rankings', params] as const,
	catalogue: (params: SupplyCatalogueParams) => [...supplyKeys.all, 'catalogue', params] as const,
	catalogueProject: (projectId: number) =>
		[...supplyKeys.all, 'catalogue-project', projectId] as const
}

export const supplyQueries = {
	developerRankings: (params: DeveloperRankingParams) => ({
		queryKey: supplyKeys.developerRankings(params),
		queryFn: () => supply.developerRankings(params),
		staleTime: 30 * 60 * 1000
	}),
	catalogue: (params: SupplyCatalogueParams) => ({
		queryKey: supplyKeys.catalogue(params),
		queryFn: () => supply.catalogue(params),
		placeholderData: (previousData: SupplyCatalogueProjectsResponse | undefined) => previousData,
		staleTime: 30 * 60 * 1000
	}),
	catalogueInfinite: (params: SupplyCatalogueFilters, limit: number) => ({
		queryKey: supplyKeys.catalogue({ ...params, limit }),
		queryFn: ({ pageParam = 0 }: { pageParam: number }) =>
			supply.catalogue({ ...params, limit, offset: pageParam }),
		getNextPageParam: (lastPage: SupplyCatalogueProjectsResponse) => {
			const nextOffset = lastPage.offset + lastPage.projects.length
			return nextOffset < lastPage.total ? nextOffset : undefined
		},
		initialPageParam: 0,
		staleTime: 30 * 60 * 1000
	}),
	catalogueProject: (projectId: number | null) => ({
		queryKey: supplyKeys.catalogueProject(projectId ?? 0),
		queryFn: () => supply.catalogueProject(projectId ?? 0),
		enabled: projectId !== null,
		staleTime: 30 * 60 * 1000
	})
}
