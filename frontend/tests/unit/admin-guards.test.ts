import { describe, expect, it } from 'vitest'

import { decideAdminAccess } from '$lib/auth/admin-guards'

describe('decideAdminAccess', () => {
	it('redirects anonymous users away from admin', () => {
		expect(decideAdminAccess(null)).toEqual({
			action: 'redirect',
			location: '/dashboard'
		})
	})

	it('redirects non-admin users away from admin', () => {
		expect(decideAdminAccess({ role: 'owner' })).toEqual({
			action: 'redirect',
			location: '/dashboard'
		})
	})

	it('allows admin users into admin routes', () => {
		expect(decideAdminAccess({ role: 'admin' })).toEqual({ action: 'allow' })
	})
})
