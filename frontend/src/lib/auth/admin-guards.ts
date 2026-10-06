import type { AuthenticatedUser } from '$lib/api/auth'

export type AdminGuardDecision = { action: 'allow' } | { action: 'redirect'; location: string }

export function decideAdminAccess(
	user: Pick<AuthenticatedUser, 'role'> | null
): AdminGuardDecision {
	if (!user || user.role !== 'admin') {
		return { action: 'redirect', location: '/dashboard' }
	}

	return { action: 'allow' }
}
