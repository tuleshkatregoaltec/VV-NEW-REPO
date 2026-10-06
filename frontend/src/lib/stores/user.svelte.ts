import posthog from 'posthog-js'
import { browser } from '$app/environment'
import { type AuthMeResponse, get_session, me } from '$lib/api/auth'

const REFRESH_INTERVAL = 5 * 60 * 1000 // 5 minutes

const userState = $state<{ data: AuthMeResponse | null }>({ data: null })

let refreshInterval: number | null = null
let lastRefresh = 0
let autoRefreshStarted = false
let identifiedUserId: string | null = null

function handleVisibilityChange() {
	if (!document.hidden && Date.now() - lastRefresh > 60 * 1000) {
		refreshUser()
	}
}

function identifyUser(user: AuthMeResponse) {
	if (browser && posthog.__loaded && identifiedUserId !== user.id) {
		posthog.identify(user.id, {
			email: user.email,
			first_name: user.first_name,
			last_name: user.last_name,
			organization_id: user.organization_id,
			organization_name: user.organization_name
		})
		identifiedUserId = user.id
	}
}

function setUser(user: AuthMeResponse | null) {
	userState.data = user
	if (browser && user) {
		identifyUser(user)
		startAutoRefresh()
	}
}

function clearUser() {
	userState.data = null
	autoRefreshStarted = false
	identifiedUserId = null
	if (refreshInterval) {
		clearInterval(refreshInterval)
		refreshInterval = null
	}
	if (browser) {
		if (posthog.__loaded) {
			posthog.reset()
		}
		document.removeEventListener('visibilitychange', handleVisibilityChange)
	}
}

async function getCurrentUser(): Promise<AuthMeResponse | null> {
	if (!browser) return null

	const session = await get_session()
	if (!session) {
		clearUser()
		return null
	}

	if (userState.data && userState.data.id === session.user.id) {
		return userState.data
	}

	return refreshUser()
}

/** Refresh user data from backend. Use after payment, invite acceptance, etc. */
async function refreshUser(): Promise<AuthMeResponse | null> {
	if (!browser) return null

	try {
		const session = await get_session()
		if (!session) {
			clearUser()
			return null
		}

		const user = await me()
		setUser(user)
		lastRefresh = Date.now()
		return user
	} catch (error) {
		console.error('Failed to refresh user:', error)
		return userState.data
	}
}

function startAutoRefresh() {
	if (!browser || autoRefreshStarted) return
	autoRefreshStarted = true

	if (refreshInterval) clearInterval(refreshInterval)
	refreshInterval = window.setInterval(() => refreshUser(), REFRESH_INTERVAL)
	document.removeEventListener('visibilitychange', handleVisibilityChange)
	document.addEventListener('visibilitychange', handleVisibilityChange)
}

export const currentUser = userState
export { clearUser, getCurrentUser, refreshUser }
