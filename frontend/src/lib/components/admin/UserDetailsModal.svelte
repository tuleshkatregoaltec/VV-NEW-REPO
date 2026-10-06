<script lang="ts">
import { admin, type OrgUserResponse } from '$lib/api/admin'
import { ApiError } from '$lib/api/client'
import Modal from '$lib/components/ui/Modal.svelte'

let {
	open = false,
	user,
	onClose,
	onUpdated
}: {
	open: boolean
	user: OrgUserResponse | null
	onClose: () => void
	onUpdated: () => void
} = $props()

let editedLimit = $state(0)
let saving = $state(false)
let error = $state('')

// Sync edited limit when user changes
$effect(() => {
	if (user) {
		editedLimit = user.daily_token_limit
	}
})

function formatNumber(num: number): string {
	return num.toLocaleString()
}

function getUsageColor(percentage: number): string {
	if (percentage >= 90) return 'bg-error'
	if (percentage >= 70) return 'bg-warning'
	return 'bg-success'
}

function getUsageTextColor(percentage: number): string {
	if (percentage >= 90) return 'text-error'
	if (percentage >= 70) return 'text-warning'
	return 'text-success'
}

async function saveLimit() {
	if (!user) return

	saving = true
	error = ''

	try {
		await admin.users.updateTokenLimit(user.id, editedLimit)

		// Update local user object
		user.daily_token_limit = editedLimit

		onUpdated()
		onClose()
	} catch (e) {
		error = e instanceof ApiError ? e.message : 'Failed to update token limit'
	} finally {
		saving = false
	}
}

function fullName(u: OrgUserResponse): string {
	const name = `${u.first_name || ''} ${u.last_name || ''}`.trim()
	return name || u.email
}
</script>

<Modal {open} {onClose} title="User token usage" size="lg">
	{#if user}
		<!-- User Info -->
		<div class="mb-6">
			<h3 class="mb-2 text-lg font-semibold text-fg-1">{fullName(user)}</h3>
			<p class="text-sm text-fg-3">{user.email}</p>
		</div>

		<!-- Token Usage Stats -->
		<div class="mb-6 rounded-lg border border-border bg-slate-50 p-4">
			<h4 class="mb-3 text-sm font-medium text-fg-2">Today's usage</h4>

			<!-- Progress Bar -->
			<div class="mb-4">
				<div class="flex justify-between text-sm mb-1">
					<span class="font-medium {getUsageTextColor(user.usage_percentage)}">
						{formatNumber(user.tokens_used_today)} / {formatNumber(user.daily_token_limit)} tokens
					</span>
					<span class="font-medium {getUsageTextColor(user.usage_percentage)}">
						{user.usage_percentage.toFixed(1)}%
					</span>
				</div>
				<div class="h-3 w-full overflow-hidden rounded-full bg-slate-200">
					<div
						class="h-full transition-all duration-300 {getUsageColor(user.usage_percentage)}"
						style="width: {Math.min(user.usage_percentage, 100)}%"
					></div>
				</div>
			</div>

			<!-- Stats Grid -->
			<div class="grid grid-cols-2 gap-4">
				<div>
					<p class="text-xs text-fg-4">Remaining today</p>
					<p class="text-lg font-semibold text-fg-1">
						{formatNumber(Math.max(0, user.daily_token_limit - user.tokens_used_today))}
					</p>
				</div>
				<div>
					<p class="text-xs text-fg-4">Daily limit</p>
					<p class="text-lg font-semibold text-fg-1">
						{formatNumber(user.daily_token_limit)}
					</p>
				</div>
			</div>
		</div>

		<!-- Edit Token Limit -->
		<div class="border-t pt-4">
			<h4 class="mb-3 text-sm font-medium text-fg-2">Configure daily limit</h4>

			<div class="mb-4">
				<label for="token-limit-input" class="mb-2 block text-sm font-medium text-fg-2">
					Daily token limit
				</label>
				<input
					id="token-limit-input"
					type="number"
					bind:value={editedLimit}
					min="0"
					step="1000"
					class="w-full rounded-md border border-border px-3 py-2 text-fg-1 shadow-sm focus:outline-none focus:ring-2 focus:ring-focus"
				/>
				<p class="mt-1 text-xs text-fg-4">Set to 0 for unlimited usage (not recommended)</p>
			</div>

			{#if error}
				<div class="mb-4 rounded border border-[rgba(163,36,36,0.2)] bg-error-bg p-3">
					<p class="text-sm text-error">{error}</p>
				</div>
			{/if}

			<div class="flex justify-end gap-3">
				<button
					onclick={onClose}
					disabled={saving}
					class="rounded-md border border-border bg-white px-4 py-2 text-fg-2 transition-colors hover:bg-slate-50 disabled:opacity-50"
				>
					Cancel
				</button>
				<button
					onclick={saveLimit}
					disabled={saving || editedLimit === user.daily_token_limit}
					class="rounded-md bg-navy px-4 py-2 text-on-navy transition-colors hover:bg-primary-hover disabled:opacity-50"
				>
					{saving ? 'Saving...' : 'Save changes'}
				</button>
			</div>
		</div>
	{/if}
</Modal>
