import { admin } from '$lib/api/admin'

export const adminKeys = {
	all: ['admin'] as const,
	organizations: () => [...adminKeys.all, 'organizations'] as const,
	organization: (id: string) => [...adminKeys.organizations(), id] as const
}

export const adminQueries = {
	organizations: {
		list: () => ({
			queryKey: adminKeys.organizations(),
			queryFn: () => admin.organizations.list()
		}),
		detail: (id: string) => ({
			queryKey: adminKeys.organization(id),
			queryFn: () => admin.organizations.get(id),
			enabled: Boolean(id)
		})
	}
}
