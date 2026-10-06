import { QueryClient } from '@tanstack/svelte-query'
import { browser } from '$app/environment'

let queryClient: QueryClient | undefined

export function getQueryClient(): QueryClient {
	if (!queryClient) {
		queryClient = new QueryClient({
			defaultOptions: {
				queries: {
					enabled: browser,
					staleTime: 5 * 60 * 1000,
					refetchOnWindowFocus: false
				}
			}
		})
	}

	return queryClient
}
