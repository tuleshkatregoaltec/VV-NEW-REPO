<script lang="ts">
import { admin, type CreateUserRequest, type OrganizationListResponse } from '$lib/api/admin'
import { ApiError } from '$lib/api/client'
import Modal from '$lib/components/ui/Modal.svelte'

let {
	open = false,
	orgs = [],
	onClose,
	onCreated
}: {
	open: boolean
	orgs: OrganizationListResponse[]
	onClose: () => void
	onCreated: () => void | Promise<void>
} = $props()

let email = $state('')
let password = $state('')
let firstName = $state('')
let lastName = $state('')
let orgMode = $state<'new' | 'existing'>('new')
let newOrgName = $state('')
let existingOrgId = $state('')
let tokenLimit = $state(100000)
let submitting = $state(false)
let error = $state('')
let success = $state('')

function reset() {
	email = ''
	password = ''
	firstName = ''
	lastName = ''
	orgMode = 'new'
	newOrgName = ''
	existingOrgId = orgs[0]?.id ?? ''
	tokenLimit = 100000
	error = ''
	success = ''
}

$effect(() => {
	if (open) {
		reset()
		existingOrgId = orgs[0]?.id ?? ''
	}
})

async function submit() {
	error = ''
	success = ''

	if (!email || !password || !firstName || !lastName) {
		error = 'All fields are required.'
		return
	}
	if (orgMode === 'new' && !newOrgName.trim()) {
		error = 'Organization name is required.'
		return
	}
	if (orgMode === 'existing' && !existingOrgId) {
		error = 'Please select an organization.'
		return
	}

	submitting = true
	try {
		const payload: CreateUserRequest = {
			email,
			password,
			first_name: firstName,
			last_name: lastName,
			org_mode: orgMode,
			org_name: orgMode === 'new' ? newOrgName.trim() : undefined,
			org_id: orgMode === 'existing' ? existingOrgId : undefined,
			daily_token_limit: tokenLimit
		}
		const result = await admin.users.create(payload)
		success = `Created ${result.email} in "${result.organization_name}"`
		await onCreated()
		setTimeout(() => {
			onClose()
		}, 1500)
	} catch (e) {
		error = e instanceof ApiError ? e.message : 'Failed to create user'
	} finally {
		submitting = false
	}
}
</script>

<Modal {open} {onClose} title="Create user" size="md">
	<div class="space-y-4">
		<!-- Name row -->
		<div class="grid grid-cols-2 gap-3">
			<div>
				<label for="create-user-first-name" class="mb-1 block text-xs font-medium text-fg-4">First name</label>
				<input
					id="create-user-first-name"
					type="text"
					bind:value={firstName}
					placeholder="Jane"
					class="w-full rounded-md border border-border px-3 py-2 text-sm text-fg-1 focus:outline-none focus:ring-2 focus:ring-focus"
				/>
			</div>
			<div>
				<label for="create-user-last-name" class="mb-1 block text-xs font-medium text-fg-4">Last name</label>
				<input
					id="create-user-last-name"
					type="text"
					bind:value={lastName}
					placeholder="Smith"
					class="w-full rounded-md border border-border px-3 py-2 text-sm text-fg-1 focus:outline-none focus:ring-2 focus:ring-focus"
				/>
			</div>
		</div>

		<!-- Email -->
		<div>
			<label for="create-user-email" class="mb-1 block text-xs font-medium text-fg-4">Email</label>
			<input
				id="create-user-email"
				type="email"
				bind:value={email}
				placeholder="jane@example.com"
				class="w-full rounded-md border border-border px-3 py-2 text-sm text-fg-1 focus:outline-none focus:ring-2 focus:ring-focus"
			/>
		</div>

		<!-- Password -->
		<div>
			<label for="create-user-password" class="mb-1 block text-xs font-medium text-fg-4">Password</label>
			<input
				id="create-user-password"
				type="password"
				bind:value={password}
				placeholder="Temporary password"
				class="w-full rounded-md border border-border px-3 py-2 text-sm text-fg-1 focus:outline-none focus:ring-2 focus:ring-focus"
			/>
		</div>

		<!-- Org mode toggle -->
		<div>
			<label for={orgMode === 'new' ? 'create-user-new-org' : 'create-user-existing-org'} class="mb-2 block text-xs font-medium text-fg-4">Organization</label>
			<div class="flex gap-2 mb-3">
				<button
					type="button"
					onclick={() => (orgMode = 'new')}
					class="flex-1 rounded-md border py-1.5 text-sm transition-colors
                        {orgMode === 'new'
						? 'border-navy bg-navy text-on-navy'
						: 'border-border bg-white text-fg-3 hover:bg-slate-50'}"
				>
					New org
				</button>
				<button
					type="button"
					onclick={() => (orgMode = 'existing')}
					class="flex-1 rounded-md border py-1.5 text-sm transition-colors
                        {orgMode === 'existing'
						? 'border-navy bg-navy text-on-navy'
						: 'border-border bg-white text-fg-3 hover:bg-slate-50'}"
				>
					Existing org
				</button>
			</div>

			{#if orgMode === 'new'}
				<input
					id="create-user-new-org"
					type="text"
					bind:value={newOrgName}
					placeholder="Organization name"
					class="w-full rounded-md border border-border px-3 py-2 text-sm text-fg-1 focus:outline-none focus:ring-2 focus:ring-focus"
				/>
				<p class="mt-1 text-xs text-fg-4">Subscription will be set to active automatically.</p>
			{:else}
				<select
					id="create-user-existing-org"
					bind:value={existingOrgId}
					class="w-full rounded-md border border-border px-3 py-2 text-sm text-fg-1 focus:outline-none focus:ring-2 focus:ring-focus"
				>
					{#each orgs as org (org.id)}
						<option value={org.id}>{org.name} ({org.subscription_status})</option>
					{/each}
				</select>
				<p class="mt-1 text-xs text-fg-4">User will be added as a member.</p>
			{/if}
		</div>

		<!-- Token limit -->
		<div>
			<label for="create-user-token-limit" class="mb-1 block text-xs font-medium text-fg-4">Daily token limit</label>
			<input
				id="create-user-token-limit"
				type="number"
				bind:value={tokenLimit}
				min="0"
				step="10000"
				class="w-full rounded-md border border-border px-3 py-2 text-sm text-fg-1 focus:outline-none focus:ring-2 focus:ring-focus"
			/>
		</div>

		{#if error}
			<p class="rounded-lg border border-[rgba(163,36,36,0.2)] bg-error-bg px-3 py-2 text-sm text-error">
				{error}
			</p>
		{/if}
		{#if success}
			<p class="rounded-lg border border-[rgba(17,122,72,0.2)] bg-success-bg px-3 py-2 text-sm text-success">
				{success}
			</p>
		{/if}

		<div class="flex justify-end gap-3 pt-2">
			<button
				type="button"
				onclick={onClose}
				disabled={submitting}
				class="rounded-md border border-border px-4 py-2 text-sm text-fg-2 transition-colors hover:bg-slate-50 disabled:opacity-50"
			>
				Cancel
			</button>
			<button
				type="button"
				onclick={submit}
				disabled={submitting}
				class="rounded-md bg-navy px-4 py-2 text-sm font-medium text-on-navy transition-colors hover:bg-primary-hover disabled:opacity-50"
			>
				{submitting ? 'Creating...' : 'Create user'}
			</button>
		</div>
	</div>
</Modal>
