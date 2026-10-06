import { redirect } from '@sveltejs/kit'
import { browser } from '$app/environment'
import { decideAdminAccess } from '$lib/auth/admin-guards'
import { currentUser } from '$lib/stores/user.svelte'
import type { LayoutLoad } from './$types'

export const load: LayoutLoad = async ({ parent }) => {
	if (!browser) return {}

	// Wait for root layout to finish resolveUser() before checking role
	await parent()

	const user = currentUser.data
	const decision = decideAdminAccess(user)
	if (decision.action === 'redirect') {
		throw redirect(302, decision.location)
	}
	return { user }
}
