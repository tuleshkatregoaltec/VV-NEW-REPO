import {
	getOrganizationInvitations,
	getOrganizationMembers,
	getOrganizationSubscription
} from '$lib/api/organization'

export const organizationKeys = {
	all: ['organization'] as const,
	members: () => [...organizationKeys.all, 'members'] as const,
	subscription: () => [...organizationKeys.all, 'subscription'] as const,
	invitations: () => [...organizationKeys.all, 'invitations'] as const
}

export const organizationQueries = {
	members: (enabled: boolean) => ({
		queryKey: organizationKeys.members(),
		queryFn: () => getOrganizationMembers(),
		enabled
	}),
	subscription: (enabled: boolean) => ({
		queryKey: organizationKeys.subscription(),
		queryFn: () => getOrganizationSubscription(),
		enabled
	}),
	invitations: (enabled: boolean) => ({
		queryKey: organizationKeys.invitations(),
		queryFn: () => getOrganizationInvitations(),
		enabled
	})
}
