import type { AuthenticatedUser } from '$lib/api/auth'

export type RouteCategory = 'public' | 'auth' | 'onboarding' | 'recovery' | 'protected'

export type GuardDecision = { action: 'allow' } | { action: 'redirect'; location: string }

const PUBLIC_PATHS = [
	'/',
	'/landing-new',
	'/landing-v2',
	'/landing2',
	'/invite',
	'/terms',
	'/privacy',
	'/reset',
	'/auth/reset-password'
]
const AUTH_PATHS = ['/auth']
const ONBOARDING_PATHS = [
	'/setup',
	'/setup/complete',
	'/payment-cancel',
	'/profile-setup',
	'/organization-setup',
	'/payment-success'
]
const RECOVERY_PATHS = ['/renew']

function hasActiveSubscription(status: AuthenticatedUser['subscription_status']): boolean {
	return status === 'active' || status === 'trialing'
}

export function matchesCategory(pathname: string, paths: string[]): boolean {
	return paths.some((path) => pathname === path || pathname.startsWith(`${path}/`))
}

export function getRouteCategory(pathname: string): RouteCategory {
	if (matchesCategory(pathname, PUBLIC_PATHS)) return 'public'
	if (matchesCategory(pathname, AUTH_PATHS)) return 'auth'
	if (matchesCategory(pathname, ONBOARDING_PATHS)) return 'onboarding'
	if (matchesCategory(pathname, RECOVERY_PATHS)) return 'recovery'
	return 'protected'
}

export function getOnboardingRedirect(
	user: Pick<
		AuthenticatedUser,
		'first_name' | 'last_name' | 'organization_id' | 'is_owner' | 'subscription_status'
	>
): string {
	if (!user.first_name || !user.last_name) return '/setup'
	if (!user.organization_id) return '/setup'

	if (!hasActiveSubscription(user.subscription_status)) {
		if (
			user.is_owner &&
			(!user.subscription_status ||
				user.subscription_status === 'failed' ||
				user.subscription_status === 'pending')
		) {
			return '/setup'
		}

		return '/renew'
	}

	return '/dashboard'
}

export function decideRouteAccess(
	pathname: string,
	user: Pick<
		AuthenticatedUser,
		'first_name' | 'last_name' | 'organization_id' | 'is_owner' | 'subscription_status'
	> | null,
	options: { hasPaymentSessionId?: boolean } = {}
): GuardDecision {
	const category = getRouteCategory(pathname)

	if (category === 'public') {
		return { action: 'allow' }
	}

	if (category === 'auth') {
		if (!user) return { action: 'allow' }
		return { action: 'redirect', location: getOnboardingRedirect(user) }
	}

	if (!user) {
		return { action: 'redirect', location: '/auth' }
	}

	if (category === 'onboarding') {
		if (pathname.startsWith('/setup/complete')) {
			if (!user.first_name || !user.last_name) {
				return { action: 'redirect', location: '/setup' }
			}

			if (!user.organization_id || !user.is_owner) {
				return { action: 'redirect', location: getOnboardingRedirect(user) }
			}

			if (!options.hasPaymentSessionId) {
				return { action: 'redirect', location: '/dashboard' }
			}

			return { action: 'allow' }
		}

		if (pathname.startsWith('/setup')) {
			if (!user.first_name || !user.last_name) {
				return { action: 'allow' }
			}

			if (user.organization_id && !user.is_owner) {
				return { action: 'redirect', location: '/renew' }
			}

			if (user.organization_id && hasActiveSubscription(user.subscription_status)) {
				return { action: 'redirect', location: '/dashboard' }
			}

			return { action: 'allow' }
		}

		return { action: 'allow' }
	}

	if (category === 'recovery') {
		if (!user.first_name || !user.last_name) {
			return { action: 'redirect', location: '/setup' }
		}

		if (!user.organization_id) {
			return { action: 'redirect', location: '/setup' }
		}

		if (hasActiveSubscription(user.subscription_status)) {
			return { action: 'redirect', location: '/dashboard' }
		}

		return { action: 'allow' }
	}

	const target = getOnboardingRedirect(user)
	if (target !== '/dashboard') {
		return { action: 'redirect', location: target }
	}

	return { action: 'allow' }
}
