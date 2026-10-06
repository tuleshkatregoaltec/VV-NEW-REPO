import { type InboundListParams, inbound } from '$lib/api/inbound'

export const inboundKeys = {
	all: ['crm', 'inbound'] as const,
	list: (params: InboundListParams) =>
		[
			...inboundKeys.all,
			'list',
			params.workspace ?? '',
			params.status ?? '',
			params.search ?? ''
		] as const,
	imports: () => [...inboundKeys.all, 'imports'] as const,
	detail: (id: number) => [...inboundKeys.all, 'detail', id] as const,
	matches: (id: number) => [...inboundKeys.all, 'matches', id] as const
}

export const inboundQueries = {
	list: (params: InboundListParams, enabled = true) => ({
		queryKey: inboundKeys.list(params),
		queryFn: ({ signal }: { signal: AbortSignal }) => inbound.list(params, signal),
		enabled,
		staleTime: 0,
		refetchOnMount: 'always' as const
	}),
	imports: (enabled = true) => ({
		queryKey: inboundKeys.imports(),
		queryFn: ({ signal }: { signal: AbortSignal }) => inbound.imports(signal),
		enabled,
		staleTime: 30_000
	}),
	detail: (id: number | null) => ({
		queryKey: inboundKeys.detail(id ?? 0),
		queryFn: ({ signal }: { signal: AbortSignal }) => inbound.get(id ?? 0, signal),
		enabled: id !== null,
		staleTime: 0,
		refetchOnMount: 'always' as const
	}),
	matches: (id: number | null) => ({
		queryKey: inboundKeys.matches(id ?? 0),
		queryFn: ({ signal }: { signal: AbortSignal }) => inbound.matches(id ?? 0, signal),
		enabled: id !== null,
		staleTime: 0,
		refetchOnMount: 'always' as const
	})
}
