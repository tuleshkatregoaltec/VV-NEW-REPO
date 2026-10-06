<script lang="ts">
import { createQuery } from '@tanstack/svelte-query'
import { goto } from '$app/navigation'
import { page } from '$app/state'
import { admin, type OrgUserResponse } from '$lib/api/admin'
import { ApiError } from '$lib/api/client'
import ConfirmModal from '$lib/components/ui/ConfirmModal.svelte'
import Modal from '$lib/components/ui/Modal.svelte'
import { adminKeys, adminQueries } from '$lib/queries/admin'
import { getQueryClient } from '$lib/queries/client'

let error = $state('')
const queryClient = getQueryClient()
let lastSyncedOrg = $state('')

// Settings edit state
let editMaxUsers = $state(0)
let editSubscription = $state('')
let saving = $state(false)
let savingSubscription = $state(false)

// Delete org
let confirmDeleteOrg = $state(false)
let deletingOrg = $state(false)

// Token limit modal
let selectedUser = $state<OrgUserResponse | null>(null)
let showTokenModal = $state(false)
let editedLimit = $state(0)
let savingLimit = $state(false)
let limitError = $state('')

// Delete user
let confirmDeleteUser = $state<OrgUserResponse | null>(null)
let deletingUser = $state(false)

const organizationId = $derived(page.params.id ?? '')

const orgQuery = createQuery(() => adminQueries.organizations.detail(organizationId))

const org = $derived(orgQuery.data ?? null)
const loadError = $derived.by(() => {
	if (!organizationId) return 'Organization ID is missing'
	if (!orgQuery.isError) return ''
	return orgQuery.error instanceof ApiError ? orgQuery.error.message : 'Failed to load organization'
})

$effect(() => {
	if (!org) return

	const syncKey = `${org.id}:${org.max_users}:${org.subscription_status}`
	if (syncKey !== lastSyncedOrg) {
		editMaxUsers = org.max_users
		editSubscription = org.subscription_status
		lastSyncedOrg = syncKey
	}
})

async function refreshOrganization() {
	if (!organizationId) return

	await Promise.all([
		queryClient.invalidateQueries({ queryKey: adminKeys.organization(organizationId) }),
		queryClient.invalidateQueries({ queryKey: adminKeys.organizations() })
	])
}

async function saveSettings() {
	if (!org) return
	error = ''
	saving = true
	try {
		await admin.organizations.update(org.id, {
			max_users: editMaxUsers
		})
		await refreshOrganization()
	} catch (e) {
		error = e instanceof ApiError ? e.message : 'Failed to save'
	} finally {
		saving = false
	}
}

async function saveSubscription() {
	if (!org) return
	error = ''
	savingSubscription = true
	try {
		await admin.organizations.setSubscription(org.id, editSubscription)
		await refreshOrganization()
	} catch (e) {
		error = e instanceof ApiError ? e.message : 'Failed to update subscription'
	} finally {
		savingSubscription = false
	}
}

async function deleteOrg() {
	if (!org) return
	error = ''
	deletingOrg = true
	try {
		await admin.organizations.delete(org.id)
		await queryClient.invalidateQueries({ queryKey: adminKeys.organizations() })
		goto('/admin/organizations')
	} catch (e) {
		error = e instanceof ApiError ? e.message : 'Failed to delete'
		deletingOrg = false
		confirmDeleteOrg = false
	}
}

function openTokenModal(user: OrgUserResponse) {
	selectedUser = user
	editedLimit = user.daily_token_limit
	limitError = ''
	showTokenModal = true
}

async function saveTokenLimit() {
	if (!selectedUser) return
	savingLimit = true
	limitError = ''
	try {
		await admin.users.updateTokenLimit(selectedUser.id, editedLimit)
		showTokenModal = false
		await refreshOrganization()
	} catch (e) {
		limitError = e instanceof ApiError ? e.message : 'Failed to update limit'
	} finally {
		savingLimit = false
	}
}

async function deleteUser() {
	if (!confirmDeleteUser) return
	error = ''
	deletingUser = true
	try {
		await admin.users.delete(confirmDeleteUser.id)
		confirmDeleteUser = null
		await refreshOrganization()
	} catch (e) {
		alert(e instanceof ApiError ? e.message : 'Failed to delete user')
	} finally {
		deletingUser = false
	}
}

function fullName(u: OrgUserResponse) {
	const name = `${u.first_name || ''} ${u.last_name || ''}`.trim()
	return name || u.email
}

function formatDate(d: string | null) {
	if (!d) return '—'
	return new Date(d).toLocaleDateString(undefined, {
		month: 'short',
		day: 'numeric',
		year: 'numeric'
	})
}

function usageColor(pct: number) {
	if (pct >= 90) return 'bg-error'
	if (pct >= 70) return 'bg-warning'
	return 'bg-success'
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
</script>

<div class="flex flex-col">
	{#if orgQuery.isPending}
		<div class="py-16 text-center text-fg-4">Loading...</div>
	{:else if loadError && !org}
		<div class="mb-4 rounded-lg border border-[rgba(163,36,36,0.2)] bg-error-bg p-4 text-sm text-error">
			{loadError}
		</div>
		<button
			onclick={() => goto('/admin/organizations')}
			class="text-sm text-primary-light hover:underline"
		>
			← Back to Organizations
		</button>
	{:else if org}
		<!-- Header -->
		<section class="mb-5 overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
			<div class="flex flex-col gap-4 bg-navy px-5 py-5 text-bone sm:flex-row sm:items-end sm:justify-between">
				<div>
					<button
						onclick={() => goto('/admin/organizations')}
						class="mb-2 flex items-center gap-1 text-sm text-slate-300 transition hover:text-bone"
					>
						← Organizations
					</button>
					<p class="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Admin organization</p>
					<h1 class="mt-2 font-display text-3xl leading-tight tracking-[var(--tracking-display)] text-bone">
						{org.name}
					</h1>
					<p class="mt-2 text-sm text-slate-300">Owner: {org.owner_email}</p>
				</div>
				<button
					onclick={() => (confirmDeleteOrg = true)}
					class="rounded-md border border-[rgba(246,241,231,0.22)] px-3 py-2 text-sm font-medium text-bone transition-colors hover:bg-white/10"
				>
					Delete org
				</button>
			</div>
		</section>

		{#if error}
			<div class="mb-4 rounded-lg border border-[rgba(163,36,36,0.2)] bg-error-bg p-3 text-sm text-error">
				{error}
			</div>
		{/if}

		<!-- Settings row -->
		<div class="mb-5 grid grid-cols-1 gap-4 md:grid-cols-2">
			<!-- Org settings -->
			<div class="rounded-lg border border-border bg-white p-5 shadow-sm">
				<h2 class="mb-4 text-sm font-semibold uppercase tracking-wider text-fg-3">Settings</h2>
				<div class="space-y-4">
					<div>
						<label for="org-max-users" class="mb-1 block text-xs font-medium text-fg-4">
							Max users
						</label>
						<input
							id="org-max-users"
							type="number"
							bind:value={editMaxUsers}
							min="1"
							class="w-full rounded-md border border-border px-3 py-2 text-sm text-fg-1 focus:border-navy focus:outline-none focus:ring-2 focus:ring-navy/10"
						/>
					</div>
					<button
						onclick={saveSettings}
						disabled={saving}
						class="w-full rounded-md bg-navy py-2 text-sm font-medium text-on-navy transition-colors hover:bg-primary-hover disabled:opacity-50"
					>
						{saving ? 'Saving...' : 'Save settings'}
					</button>
				</div>
			</div>

			<!-- Subscription -->
			<div class="rounded-lg border border-border bg-white p-5 shadow-sm">
				<h2 class="mb-4 text-sm font-semibold uppercase tracking-wider text-fg-3">
					Subscription
				</h2>
				<div class="space-y-4">
					<div class="flex items-center gap-2">
						<span class="text-xs text-fg-4">Current:</span>
						<span
							class="inline-flex rounded-sm px-2.5 py-0.5 text-xs font-semibold {statusBadge(
								org.subscription_status
							)}"
						>
							{org.subscription_status}
						</span>
					</div>
					<div>
						<label for="org-subscription-status" class="mb-1 block text-xs font-medium text-fg-4">
							Set status
						</label>
						<select
							id="org-subscription-status"
							bind:value={editSubscription}
							class="w-full rounded-md border border-border px-3 py-2 text-sm text-fg-1 focus:border-navy focus:outline-none focus:ring-2 focus:ring-navy/10"
						>
							<option value="active">active</option>
							<option value="trialing">trialing</option>
							<option value="pending">pending</option>
							<option value="past_due">past_due</option>
							<option value="canceled">canceled</option>
							<option value="none">none</option>
						</select>
					</div>
					<button
						onclick={saveSubscription}
						disabled={savingSubscription || editSubscription === org.subscription_status}
						class="w-full rounded-md bg-navy py-2 text-sm font-medium text-on-navy transition-colors hover:bg-primary-hover disabled:opacity-50"
					>
						{savingSubscription ? 'Updating...' : 'Update subscription'}
					</button>
				</div>
			</div>
		</div>

		<!-- Users table -->
		<div class="overflow-hidden rounded-lg border border-border bg-white shadow-sm">
			<div class="flex items-center justify-between border-b border-border px-5 py-4">
				<h2 class="text-sm font-semibold uppercase tracking-wider text-fg-3">
					Members ({org.users.length} / {org.max_users})
				</h2>
			</div>

			{#if org.users.length === 0}
				<div class="px-5 py-12 text-center text-sm text-fg-4">No members yet.</div>
			{:else}
				<table class="min-w-full divide-y divide-border">
					<thead>
						<tr class="bg-slate-50">
							<th
								class="px-5 py-3 text-left text-xs font-semibold uppercase tracking-wider text-fg-4"
								>User</th
							>
							<th
								class="px-5 py-3 text-center text-xs font-semibold uppercase tracking-wider text-fg-4"
								>Role</th
							>
							<th
								class="px-5 py-3 text-center text-xs font-semibold uppercase tracking-wider text-fg-4"
								>Token usage</th
							>
							<th
								class="px-5 py-3 text-left text-xs font-semibold uppercase tracking-wider text-fg-4"
								>Last login</th
							>
							<th class="px-5 py-3"></th>
						</tr>
					</thead>
					<tbody class="divide-y divide-border">
						{#each org.users as user (user.id)}
							<tr class="transition-colors hover:bg-slate-50">
								<td class="px-5 py-4">
									<div class="text-sm font-medium text-fg-1">{fullName(user)}</div>
									<div class="text-xs text-fg-4">{user.email}</div>
								</td>
								<td class="px-5 py-4 text-center">
									<span
										class="rounded-sm px-2 py-0.5 text-xs font-medium {user.role === 'owner'
											? 'bg-navy-pale text-navy'
											: 'bg-bone-muted text-fg-3'}"
									>
										{user.role}
									</span>
								</td>
								<td class="px-5 py-4">
									<div class="flex flex-col items-center gap-1">
										<span class="text-xs text-fg-4">
											{user.tokens_used_today.toLocaleString()} / {user.daily_token_limit.toLocaleString()}
										</span>
										<div class="h-1.5 w-24 overflow-hidden rounded-full bg-slate-200">
											<div
												class="h-full {usageColor(user.usage_percentage)}"
												style="width: {Math.min(user.usage_percentage, 100)}%"
											></div>
										</div>
									</div>
								</td>
								<td class="px-5 py-4 text-sm text-fg-4">{formatDate(user.last_login)}</td>
								<td class="px-5 py-4">
									<div class="flex items-center justify-end gap-2">
										<button
											onclick={() => openTokenModal(user)}
											class="rounded-md px-2.5 py-1 text-xs font-medium text-primary-light transition-colors hover:bg-navy-pale hover:text-navy"
										>
											Edit limit
										</button>
										<button
											onclick={() => (confirmDeleteUser = user)}
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
			{/if}
		</div>
	{/if}
</div>

<!-- Token limit modal -->
<Modal
	open={showTokenModal}
	onClose={() => (showTokenModal = false)}
	title="Edit token limit"
	size="md"
>
	{#if selectedUser}
		<div class="space-y-4">
			<div>
				<p class="text-sm font-medium text-fg-1">{fullName(selectedUser)}</p>
				<p class="text-xs text-fg-4">{selectedUser.email}</p>
			</div>
			<div>
				<label for="daily-token-limit" class="mb-1 block text-xs font-medium text-fg-4">
					Daily token limit
				</label>
				<input
					id="daily-token-limit"
					type="number"
					bind:value={editedLimit}
					min="0"
					step="10000"
					class="w-full rounded-md border border-border px-3 py-2 text-sm text-fg-1 focus:outline-none focus:ring-2 focus:ring-focus"
				/>
				<p class="mt-1 text-xs text-fg-4">
					Current usage today: {selectedUser.tokens_used_today.toLocaleString()} tokens
				</p>
			</div>
			{#if limitError}
				<p class="text-sm text-error">{limitError}</p>
			{/if}
			<div class="flex justify-end gap-3 pt-2">
				<button
					onclick={() => (showTokenModal = false)}
					class="rounded-md border border-border px-4 py-2 text-sm text-fg-2 transition-colors hover:bg-slate-50"
				>
					Cancel
				</button>
				<button
					onclick={saveTokenLimit}
					disabled={savingLimit || editedLimit === selectedUser.daily_token_limit}
					class="rounded-md bg-navy px-4 py-2 text-sm font-medium text-on-navy transition-colors hover:bg-primary-hover disabled:opacity-50"
				>
					{savingLimit ? 'Saving...' : 'Save'}
				</button>
			</div>
		</div>
	{/if}
</Modal>

<ConfirmModal
	open={confirmDeleteUser !== null}
	title="Delete user"
	message={`Delete ${confirmDeleteUser?.email}? This removes them from Supabase and this organization.`}
	confirmText={deletingUser ? 'Deleting...' : 'Delete user'}
	confirmVariant="danger"
	onConfirm={deleteUser}
	onCancel={() => (confirmDeleteUser = null)}
/>

<ConfirmModal
	open={confirmDeleteOrg}
	title="Delete organization"
	message={`Delete '${org?.name}'? This removes the organization. Users will lose access immediately.`}
	confirmText={deletingOrg ? 'Deleting...' : 'Delete organization'}
	confirmVariant="danger"
	onConfirm={deleteOrg}
	onCancel={() => (confirmDeleteOrg = false)}
/>
