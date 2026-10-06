import { redirect } from '@sveltejs/kit'
import posthog from 'posthog-js'
import { browser } from '$app/environment'
import { env } from '$env/dynamic/public'
import { decideRouteAccess, getRouteCategory } from '$lib/auth/route-guards'
import { getQueryClient } from '$lib/queries/client'
import { getCurrentUser } from '$lib/stores/user.svelte'
import type { LayoutLoad } from './$types'

export const prerender = false
export const ssr = false

export const load: LayoutLoad = async ({ url }) => {
	const queryClient = getQueryClient()

	if (!browser) return { queryClient }

	// Initialize PostHog
	if (env.PUBLIC_POSTHOG_KEY && env.PUBLIC_POSTHOG_HOST && !posthog.__loaded) {
		try {
			posthog.init(env.PUBLIC_POSTHOG_KEY, {
				api_host: env.PUBLIC_POSTHOG_HOST,
				ui_host: 'https://eu.posthog.com',
				defaults: '2025-11-30'
			})
		} catch (error) {
			console.warn('Failed to initialize PostHog:', error)
		}
	}

	const pathname = url.pathname
	if (getRouteCategory(pathname) === 'public') {
		return { queryClient }
	}

	let user = null
	try {
		user = await getCurrentUser()
	} catch {
		user = null
	}

	const decision = decideRouteAccess(pathname, user, {
		hasPaymentSessionId: Boolean(url.searchParams.get('session_id'))
	})

	if (decision.action === 'redirect') {
		if (decision.location === '/auth') {
			const next = `${url.pathname}${url.search}`
			throw redirect(302, `/auth?next=${encodeURIComponent(next)}`)
		}
		throw redirect(302, decision.location)
	}

	return { queryClient }
}
