import { feasibility } from '$lib/api/feasibility'
import type { Plot } from '$lib/api/generated/hey-api/types.gen'

export interface PlotSearchParams {
	q?: string
	community?: string
	minPlotAreaSqm?: number
	maxPlotAreaSqm?: number
	offset?: number
	limit?: number
}

async function fetchAllCommunityPlots(community: string, limit: number): Promise<Plot[]> {
	const allPlots: Plot[] = []
	let offset = 0

	while (community) {
		const page = await feasibility.searchPlots({ community, offset, limit })
		allPlots.push(...page)
		if (page.length < limit) break
		offset += page.length
	}

	return allPlots
}

export const feasibilityKeys = {
	all: ['feasibility'] as const,
	areas: () => [...feasibilityKeys.all, 'areas'] as const,
	studies: () => [...feasibilityKeys.all, 'studies'] as const,
	study: (studyId: number | string) => [...feasibilityKeys.all, 'study', studyId] as const,
	communities: () => [...feasibilityKeys.all, 'communities'] as const,
	searchPlots: (params: PlotSearchParams) =>
		[...feasibilityKeys.all, 'searchPlots', params] as const,
	communityPlots: (community: string, limit: number) =>
		[...feasibilityKeys.all, 'communityPlots', { community, limit }] as const,
	plotData: (plotNumber: string) => [...feasibilityKeys.all, 'plotData', plotNumber] as const,
	generateStudy: (plotNumber: string, usageOverride?: string) =>
		[...feasibilityKeys.all, 'generateStudy', plotNumber, usageOverride] as const
}

export const feasibilityQueries = {
	areas: () => ({
		queryKey: feasibilityKeys.areas(),
		queryFn: () => feasibility.getAreas(),
		staleTime: Infinity
	}),
	studies: () => ({
		queryKey: feasibilityKeys.studies(),
		queryFn: () => feasibility.listStudies(),
		staleTime: 30 * 1000
	}),
	study: (studyId: number | null) => ({
		queryKey: feasibilityKeys.study(studyId ?? ''),
		queryFn: () => {
			if (!studyId) throw new Error('Study ID is required.')
			return feasibility.getStudy(studyId)
		},
		enabled: Boolean(studyId),
		staleTime: 30 * 1000
	}),
	communities: () => ({
		queryKey: feasibilityKeys.communities(),
		queryFn: () => feasibility.getCommunities(),
		staleTime: Infinity
	}),
	searchPlots: (params: PlotSearchParams) => ({
		queryKey: feasibilityKeys.searchPlots(params),
		queryFn: () => feasibility.searchPlots(params),
		staleTime: 5 * 60 * 1000
	}),
	communityPlots: (community: string | null, limit = 100) => ({
		queryKey: feasibilityKeys.communityPlots(community ?? '', limit),
		queryFn: () => fetchAllCommunityPlots(community ?? '', limit),
		enabled: Boolean(community),
		staleTime: 5 * 60 * 1000
	}),
	plotData: (plotNumber: string | null) => ({
		queryKey: feasibilityKeys.plotData(plotNumber ?? ''),
		queryFn: () => {
			if (!plotNumber) throw new Error('Plot number is required.')
			return feasibility.getPlotData(plotNumber)
		},
		enabled: Boolean(plotNumber),
		staleTime: Infinity
	}),
	generateStudy: (
		plotNumber: string | null,
		usageOverride?: 'residential' | 'commercial' | 'mixed_use' | 'unknown'
	) => ({
		queryKey: feasibilityKeys.generateStudy(plotNumber ?? '', usageOverride),
		queryFn: () => {
			if (!plotNumber) throw new Error('Plot number is required.')
			return feasibility.generateStudy({ plot_number: plotNumber, usage_override: usageOverride })
		},
		enabled: Boolean(plotNumber),
		staleTime: Infinity
	})
}
