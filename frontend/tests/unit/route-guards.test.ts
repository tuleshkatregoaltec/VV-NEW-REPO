import { describe, expect, it } from 'vitest'
import type { AuthenticatedUser } from '$lib/api/auth'
import { decideRouteAccess, getOnboardingRedirect, getRouteCategory } from '$lib/auth/route-guards'

function makeUser(overrides: Partial<AuthenticatedUser> = {}): AuthenticatedUser {
	return {
		id: 'user-1',
		email: 'user@example.com',
		first_name: 'Ada',
		last_name: 'Lovelace',
		organization_id: 'org-1',
		organization_name: 'Acme',
		role: 'owner',
		is_owner: true,
		subscription_status: 'active',
		...overrides
	}
}

describe('getRouteCategory', () => {
	it('classifies public paths', () => {
		expect(getRouteCategory('/')).toBe('public')
		expect(getRouteCategory('/landing-new')).toBe('public')
		expect(getRouteCategory('/invite')).toBe('public')
		expect(getRouteCategory('/reset')).toBe('public')
	})

	it('classifies auth and protected paths', () => {
		expect(getRouteCategory('/auth')).toBe('auth')
		expect(getRouteCategory('/dashboard')).toBe('protected')
	})
})

describe('getOnboardingRedirect', () => {
	it('sends incomplete profiles to setup', () => {
		expect(getOnboardingRedirect(makeUser({ first_name: '' }))).toBe('/setup')
	})

	it('sends users without an org to setup', () => {
		expect(getOnboardingRedirect(makeUser({ organization_id: null }))).toBe('/setup')
	})

	it('sends owners with pending checkout back to setup', () => {
		expect(
			getOnboardingRedirect(makeUser({ subscription_status: 'pending', is_owner: true }))
		).toBe('/setup')
	})

	it('sends non-owners without an active subscription to renew', () => {
		expect(
			getOnboardingRedirect(
				makeUser({
					role: 'member',
					is_owner: false,
					subscription_status: 'past_due'
				})
			)
		).toBe('/renew')
	})
})

describe('decideRouteAccess', () => {
	it('allows public routes for anonymous users', () => {
		expect(decideRouteAccess('/', null)).toEqual({ action: 'allow' })
		expect(decideRouteAccess('/invite', null)).toEqual({ action: 'allow' })
	})

	it('redirects anonymous users from protected routes', () => {
		expect(decideRouteAccess('/dashboard', null)).toEqual({
			action: 'redirect',
			location: '/auth'
		})
	})

	it('redirects authenticated users away from auth to the correct next step', () => {
		expect(decideRouteAccess('/auth', makeUser({ organization_id: null }))).toEqual({
			action: 'redirect',
			location: '/setup'
		})
	})

	it('lets incomplete users reach setup', () => {
		expect(decideRouteAccess('/setup', makeUser({ first_name: '' }))).toEqual({
			action: 'allow'
		})
	})

	it('redirects setup complete without a session id back to dashboard', () => {
		expect(decideRouteAccess('/setup/complete', makeUser())).toEqual({
			action: 'redirect',
			location: '/dashboard'
		})
	})

	it('allows setup complete when a checkout session id is present', () => {
		expect(decideRouteAccess('/setup/complete', makeUser(), { hasPaymentSessionId: true })).toEqual(
			{
				action: 'allow'
			}
		)
	})

	it('redirects active users away from renew', () => {
		expect(decideRouteAccess('/renew', makeUser())).toEqual({
			action: 'redirect',
			location: '/dashboard'
		})
	})

	it('redirects members with an org away from setup', () => {
		expect(
			decideRouteAccess(
				'/setup',
				makeUser({
					role: 'member',
					is_owner: false,
					subscription_status: 'past_due'
				})
			)
		).toEqual({
			action: 'redirect',
			location: '/renew'
		})
	})

	it('allows past-due users onto renew', () => {
		expect(decideRouteAccess('/renew', makeUser({ subscription_status: 'past_due' }))).toEqual({
			action: 'allow'
		})
	})

	it('redirects protected routes based on onboarding state', () => {
		expect(decideRouteAccess('/dashboard', makeUser({ subscription_status: 'past_due' }))).toEqual({
			action: 'redirect',
			location: '/renew'
		})
	})

	it('allows fully active users onto protected routes', () => {
		expect(decideRouteAccess('/dashboard', makeUser())).toEqual({ action: 'allow' })
	})
})
