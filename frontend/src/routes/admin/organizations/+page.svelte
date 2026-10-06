<script lang="ts">
import { createQuery } from '@tanstack/svelte-query'
import { goto } from '$app/navigation'
import { admin, type OrganizationListResponse } from '$lib/api/admin'
import { ApiError } from '$lib/api/client'
import CreateUserModal from '$lib/components/admin/CreateUserModal.svelte'
import ConfirmModal from '$lib/components/ui/ConfirmModal.svelte'
import { adminKeys, adminQueries } from '$lib/queries/admin'
import { getQueryClient } from '$lib/queries/client'

let showCreateUser = $state(false)
let activatingOrgId = $state<string | null>(null)
let deletingOrgId = $state<string | null>(null)
let confirmDeleteOrg = $state<OrganizationListResponse | null>(null)
const queryClient = getQueryClient()

const organizationsQuery = createQuery(() => adminQueries.organizations.list())

const orgs = $derived(organizationsQuery.data ?? [])
const error = $derived(
	organizationsQuery.isError
		? organizationsQuery.error instanceof ApiError
			? organizationsQuery.error.message
			: 'Failed to load organizations'
		: ''
)

async function refreshOrganizations() {
	await queryClient.invalidateQueries({ queryKey: adminKeys.organizations() })
}

async function activateOrg(org: OrganizationListResponse) {
	activatingOrgId = org.id
	try {
		const updated = await admin.organizations.setSubscription(org.id, 'active')
		queryClient.setQueryData<OrganizationListResponse[]>(
			adminKeys.organizations(),
			(current = []) => current.map((item) => (item.id === org.id ? updated : item))
		)
	} catch (e) {
		alert(e instanceof ApiError ? e.message : 'Failed to activate')
	} finally {
		activatingOrgId = null
	}
}

async function deleteOrg() {
	if (!confirmDeleteOrg) return
	const orgToDelete = confirmDeleteOrg
	deletingOrgId = orgToDelete.id
	try {
		await admin.organizations.delete(orgToDelete.id)
		queryClient.setQueryData<OrganizationListResponse[]>(
			adminKeys.organizations(),
			(current = []) => current.filter((item) => item.id !== orgToDelete.id)
		)
		confirmDeleteOrg = null
	} catch (e) {
		alert(e instanceof ApiError ? e.message : 'Failed to delete')
	} finally {
		deletingOrgId = null
	}
}

function statusBadge(status: string) {
	switch (status) {
		case 'active':
			return 'bg-success-bg text-success'
		case 'trialing':
			return 'bg-navy-pale text-navy'
		case 'past_due':
			return 'bg-warning-bg text-warning'
		case 'canceled':
			return 'bg-error-bg text-error'
		default:
			return 'bg-bone-muted text-fg-3'
	}
}

function formatDate(d: string) {
	return new Date(d).toLocaleDateString(undefined, {
		year: 'numeric',
		month: 'short',
		day: 'numeric'
	})
}
</script>

<div class="flex flex-col gap-5">
	<section class="mb-5 overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
		<div class="flex flex-col gap-4 bg-navy px-5 py-5 text-bone sm:flex-row sm:items-end sm:justify-between">
			<div>
				<p class="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Admin</p>
				<h1 class="mt-2 font-display text-3xl leading-tight tracking-[var(--tracking-display)] text-bone">
					Organizations
				</h1>
				<p class="mt-2 max-w-2xl text-sm leading-6 text-slate-300">
					Review workspace owners, subscription state, member capacity, and admin actions.
				</p>
			</div>
			<button
				onclick={() => (showCreateUser = true)}
				class="inline-flex h-10 items-center justify-center rounded-md bg-bone px-4 text-sm font-semibold text-navy transition-colors hover:bg-white"
			>
				Create user
			</button>
		</div>
	</section>

	{#if organizationsQuery.isPending}
		<div class="py-16 text-center text-fg-4">Loading...</div>
	{:else if error}
		<div class="rounded-lg border border-[rgba(163,36,36,0.2)] bg-error-bg p-4 text-sm text-error">{error}</div>
	{:else if orgs.length === 0}
		<div class="py-16 text-center text-fg-4">No organizations yet.</div>
	{:else}
		<div class="overflow-hidden rounded-lg border border-border bg-white shadow-sm">
			<table class="min-w-full divide-y divide-border">
				<thead>
					<tr class="bg-slate-50">
						<th
							class="px-5 py-3 text-left text-xs font-semibold uppercase tracking-wider text-fg-4"
							>Organization</th
						>
						<th
							class="px-5 py-3 text-left text-xs font-semibold uppercase tracking-wider text-fg-4"
							>Owner</th
						>
						<th
							class="px-5 py-3 text-center text-xs font-semibold uppercase tracking-wider text-fg-4"
							>Members</th
						>
						<th
							class="px-5 py-3 text-center text-xs font-semibold uppercase tracking-wider text-fg-4"
							>Subscription</th
						>
						<th
							class="px-5 py-3 text-left text-xs font-semibold uppercase tracking-wider text-fg-4"
							>Created</th
						>
						<th class="px-5 py-3"></th>
					</tr>
				</thead>
				<tbody class="divide-y divide-border">
					{#each orgs as org (org.id)}
						<tr class="transition-colors hover:bg-slate-50">
							<td class="px-5 py-4">
								<span class="text-sm font-medium text-fg-1">{org.name}</span>
							</td>
							<td class="px-5 py-4 text-sm text-fg-3">{org.owner_email}</td>
							<td class="px-5 py-4 text-center text-sm text-fg-3">
								{org.user_count} / {org.max_users}
							</td>
							<td class="px-5 py-4 text-center">
								<span
									class="inline-flex items-center rounded-sm px-2.5 py-0.5 text-xs font-semibold {statusBadge(
										org.subscription_status
									)}"
								>
									{org.subscription_status}
								</span>
							</td>
							<td class="px-5 py-4 text-sm text-fg-4">{formatDate(org.created_at)}</td>
							<td class="px-5 py-4">
								<div class="flex items-center justify-end gap-2">
									{#if org.subscription_status !== 'active'}
										<button
											onclick={() => activateOrg(org)}
											disabled={activatingOrgId === org.id}
											class="rounded-md border border-[rgba(17,122,72,0.2)] bg-success-bg px-2.5 py-1 text-xs font-medium text-success transition-colors hover:opacity-90 disabled:opacity-50"
										>
											{activatingOrgId === org.id ? '...' : 'Activate'}
										</button>
									{/if}
									<button
										onclick={() => goto(`/admin/organizations/${org.id}`)}
										class="rounded-md px-2.5 py-1 text-xs font-medium text-primary-light transition-colors hover:bg-navy-pale hover:text-navy"
									>
										View →
									</button>
									<button
										onclick={() => (confirmDeleteOrg = org)}
										class="rounded-md px-2.5 py-1 text-xs font-medium text-error transition-colors hover:bg-error-bg hover:opacity-90"
									>
										Delete
									</button>
								</div>
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{/if}
</div>

<CreateUserModal
	open={showCreateUser}
	{orgs}
	onClose={() => (showCreateUser = false)}
	onCreated={refreshOrganizations}
/>

<ConfirmModal
	open={confirmDeleteOrg !== null}
	title="Delete organization"
	message={`Delete '${confirmDeleteOrg?.name}'? This removes the org and all its data. Users will lose access.`}
	confirmText={deletingOrgId ? 'Deleting...' : 'Delete'}
	confirmVariant="danger"
	onConfirm={deleteOrg}
	onCancel={() => (confirmDeleteOrg = null)}
/>
