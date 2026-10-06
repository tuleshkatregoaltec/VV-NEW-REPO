import {
	type CrmDashboardParams,
	type CrmOwnerRegistryParams,
	type CrmOwnerRegistryScope,
	type CrmOwnershipStatus,
	crm
} from '$lib/api/crm'

export const crmKeys = {
	all: ['crm'] as const,
	dashboard: (params: CrmDashboardParams) => [...crmKeys.all, 'dashboard', params] as const,
	lead: (leadId: string) => [...crmKeys.all, 'lead', leadId] as const,
	report: (leadId: string) => [...crmKeys.all, 'report', leadId] as const,
	workspaces: () => [...crmKeys.all, 'workspaces'] as const,
	workspace: (leadId: string) => [...crmKeys.all, 'workspace', leadId] as const,
	saved: () => [...crmKeys.all, 'saved'] as const,
	leadContacts: (leadId: string) => [...crmKeys.all, 'lead-contacts', leadId] as const,
	contactImports: () => [...crmKeys.all, 'contact-imports'] as const,
	contactLists: () => [...crmKeys.all, 'contact-lists'] as const,
	contactList: (listId: number, params: { status?: CrmOwnershipStatus; search?: string }) =>
		[...crmKeys.all, 'contact-list', listId, params] as const,
	ownerRegistry: (scope: CrmOwnerRegistryScope, params: CrmOwnerRegistryParams) =>
		[...crmKeys.all, 'owner-registry', scope, params] as const,
	ownerProfile: (ownerKey: string) => [...crmKeys.all, 'owner-profile', ownerKey] as const,
	ownerWorkspaces: () => [...crmKeys.all, 'owner-workspaces'] as const
}

export const crmQueries = {
	dashboard: (params: CrmDashboardParams) => ({
		queryKey: crmKeys.dashboard(params),
		queryFn: ({ signal }: { signal: AbortSignal }) => crm.dashboard(params, signal),
		placeholderData: (previousData: Awaited<ReturnType<typeof crm.dashboard>> | undefined) =>
			previousData,
		staleTime: 15 * 60 * 1000
	}),
	lead: (leadId: string | null) => ({
		queryKey: crmKeys.lead(leadId ?? ''),
		queryFn: ({ signal }: { signal: AbortSignal }) => crm.lead(leadId ?? '', signal),
		enabled: Boolean(leadId),
		staleTime: 15 * 60 * 1000
	}),
	report: (leadId: string | null) => ({
		queryKey: crmKeys.report(leadId ?? ''),
		queryFn: ({ signal }: { signal: AbortSignal }) => crm.report(leadId ?? '', signal),
		enabled: Boolean(leadId),
		staleTime: 15 * 60 * 1000
	}),
	workspaces: () => ({
		queryKey: crmKeys.workspaces(),
		queryFn: () => crm.workspaces(),
		staleTime: 5 * 60 * 1000
	}),
	workspace: (leadId: string | null) => ({
		queryKey: crmKeys.workspace(leadId ?? ''),
		queryFn: ({ signal }: { signal: AbortSignal }) => crm.workspace(leadId ?? '', signal),
		enabled: Boolean(leadId),
		staleTime: 5 * 60 * 1000
	}),
	saved: () => ({
		queryKey: crmKeys.saved(),
		queryFn: () => crm.savedLeads(),
		staleTime: 5 * 60 * 1000
	}),
	leadContacts: (leadId: string | null) => ({
		queryKey: crmKeys.leadContacts(leadId ?? ''),
		queryFn: ({ signal }: { signal: AbortSignal }) => crm.leadContacts(leadId ?? '', signal),
		enabled: Boolean(leadId),
		staleTime: 5 * 60 * 1000
	}),
	contactImports: (enabled = true) => ({
		queryKey: crmKeys.contactImports(),
		queryFn: ({ signal }: { signal: AbortSignal }) => crm.contactImports(signal),
		enabled,
		staleTime: 2 * 60 * 1000
	}),
	contactLists: () => ({
		queryKey: crmKeys.contactLists(),
		queryFn: () => crm.contactLists(),
		staleTime: 2 * 60 * 1000
	}),
	contactList: (
		listId: number | null,
		params: { status?: CrmOwnershipStatus; search?: string } = {}
	) => ({
		queryKey: crmKeys.contactList(listId ?? 0, params),
		queryFn: () => crm.contactList(listId ?? 0, { ...params, limit: 200 }),
		enabled: Boolean(listId),
		staleTime: 2 * 60 * 1000
	}),
	ownerRegistry: (
		scope: CrmOwnerRegistryScope,
		params: CrmOwnerRegistryParams = {},
		enabled = true
	) => ({
		queryKey: crmKeys.ownerRegistry(scope, params),
		queryFn: ({ signal }: { signal: AbortSignal }) =>
			crm.ownerRegistry(scope, { ...params, limit: 50 }, signal),
		enabled,
		staleTime: 2 * 60 * 1000
	}),
	ownerProfile: (ownerKey: string | null) => ({
		queryKey: crmKeys.ownerProfile(ownerKey ?? ''),
		queryFn: ({ signal }: { signal: AbortSignal }) => crm.ownerProfile(ownerKey ?? '', signal),
		enabled: Boolean(ownerKey),
		staleTime: 2 * 60 * 1000
	}),
	ownerWorkspaces: (enabled = true) => ({
		queryKey: crmKeys.ownerWorkspaces(),
		queryFn: ({ signal }: { signal: AbortSignal }) => crm.ownerWorkspaces(signal),
		enabled,
		staleTime: 2 * 60 * 1000
	})
}
