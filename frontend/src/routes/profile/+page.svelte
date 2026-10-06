<script lang="ts">
import { logout, update_user_profile } from '$lib/api/auth'
import ThemePreferenceControl from '$lib/components/preferences/ThemePreferenceControl.svelte'
import { areaUnit } from '$lib/stores/preferences.svelte'
import { currentUser, refreshUser } from '$lib/stores/user.svelte'

let editingName = $state(false)
let firstName = $state('')
let lastName = $state('')
let editError = $state('')
let editSuccess = $state('')
let failedAvatarUrl = $state<string | null>(null)
let displayName = $derived(
	currentUser.data
		? `${currentUser.data.first_name ?? ''} ${currentUser.data.last_name ?? ''}`.trim() ||
				currentUser.data.email
		: ''
)
let initials = $derived(
	currentUser.data
		? `${currentUser.data.first_name?.[0] ?? ''}${currentUser.data.last_name?.[0] ?? ''}`.toUpperCase()
		: ''
)
let avatarUrl = $derived(
	currentUser.data?.avatar_url && currentUser.data.avatar_url !== failedAvatarUrl
		? currentUser.data.avatar_url
		: ''
)

$effect(() => {
	if (currentUser.data && !editingName) {
		firstName = currentUser.data.first_name || ''
		lastName = currentUser.data.last_name || ''
	}
})

function handleNameEdit() {
	editError = ''
	editSuccess = ''

	if (!firstName.trim() || !lastName.trim()) {
		editError = 'Both first and last names are required'
		return
	}

	const trimmedFirstName = firstName.trim()
	const trimmedLastName = lastName.trim()

	update_user_profile(trimmedFirstName, trimmedLastName)
		.then(async () => {
			await refreshUser()
			editSuccess = 'Profile updated successfully'
			editingName = false

			setTimeout(() => {
				editSuccess = ''
			}, 3000)
		})
		.catch(() => {
			editError = 'Failed to sync profile changes'
		})
}

function handleCancel() {
	editingName = false
	editError = ''
	if (currentUser.data) {
		firstName = currentUser.data.first_name || ''
		lastName = currentUser.data.last_name || ''
	}
}

function handleAvatarError() {
	failedAvatarUrl = currentUser.data?.avatar_url ?? null
}
</script>

		<section class="ui-surface mb-5 overflow-hidden">
			<div class="bg-navy px-5 py-5 text-bone">
				<p class="text-xs font-semibold uppercase tracking-[0.18em] text-on-navy-muted">Account</p>
				<h1 class="mt-2 font-display text-3xl leading-tight tracking-[var(--tracking-display)] text-bone">
					Profile
				</h1>
				<p class="mt-2 max-w-2xl text-sm leading-6 text-on-navy-muted">
					Manage your personal details, display preferences, and account access.
				</p>
			</div>
		</section>

		<div class="space-y-6">
			<!-- Account Details Section -->
			<div class="ui-surface p-6">
				<div class="flex items-center justify-between mb-4">
					<h2 class="text-lg font-semibold text-fg-1">Account details</h2>
					{#if !editingName}
						<button
							type="button"
							onclick={() => (editingName = true)}
							class="text-sm text-info hover:text-fg-1 font-medium transition-colors"
						>
							Edit name
						</button>
					{/if}
				</div>

				{#if editingName}
					<div class="space-y-4">
						<div>
							<label for="profile-first-name" class="block text-sm font-medium text-fg-2 mb-1">First name</label>
							<input
								id="profile-first-name"
								type="text"
								bind:value={firstName}
								class="ui-field w-full px-3 py-2"
							/>
						</div>
						<div>
							<label for="profile-last-name" class="block text-sm font-medium text-fg-2 mb-1">Last name</label>
							<input
								id="profile-last-name"
								type="text"
								bind:value={lastName}
								class="ui-field w-full px-3 py-2"
							/>
						</div>

						{#if editError}
							<p class="text-sm text-error">{editError}</p>
						{/if}

						<div class="flex gap-2 pt-2">
							<button
								type="button"
								onclick={handleNameEdit}
								data-variant="primary"
								class="ui-button px-4 py-2 text-sm"
							>
								Save
							</button>
							<button
								type="button"
								onclick={handleCancel}
								data-variant="secondary"
								class="ui-button px-4 py-2 text-sm"
							>
								Cancel
							</button>
						</div>
					</div>
				{:else if currentUser.data}
					<div class="mb-5 flex items-center gap-4">
						<div
							class="flex h-16 w-16 flex-shrink-0 items-center justify-center overflow-hidden rounded-full bg-navy text-lg font-semibold text-bone"
						>
							{#if avatarUrl}
								<img src={avatarUrl} alt="" class="h-full w-full object-cover" onerror={handleAvatarError} />
							{:else}
								{initials}
							{/if}
						</div>
						<div class="min-w-0">
							<p class="truncate text-base font-semibold text-fg-1">{displayName}</p>
							<p class="mt-0.5 truncate text-sm text-fg-4">{currentUser.data.email}</p>
						</div>
					</div>
					<div class="space-y-3 text-sm">
						<div class="flex justify-between">
							<span class="text-fg-4">Full name</span>
							<span class="text-fg-1"
								>{currentUser.data.first_name} {currentUser.data.last_name}</span
							>
						</div>
						<div class="flex justify-between">
							<span class="text-fg-4">Email</span>
							<span class="text-fg-1">{currentUser.data.email}</span>
						</div>
						<div class="flex justify-between">
							<span class="text-fg-4">Organization</span>
							<span class="text-fg-1">{currentUser.data.organization_name}</span>
						</div>
					</div>
				{:else}
					<p class="text-fg-4">Loading...</p>
				{/if}

				{#if editSuccess}
					<p class="mt-3 text-sm text-success">{editSuccess}</p>
				{/if}
			</div>

			<!-- Notifications Section -->
			<div class="ui-surface p-6">
				<h2 class="text-lg font-semibold text-fg-1 mb-4">Notifications</h2>
				<div class="space-y-4">
					<label class="flex items-center justify-between">
						<span class="text-fg-2">Email notifications</span>
						<input
							type="checkbox"
							checked
							class="w-5 h-5 accent-info rounded"
							disabled
						/>
					</label>
					<label class="flex items-center justify-between">
						<span class="text-fg-2">Weekly digest</span>
						<input
							type="checkbox"
							class="w-5 h-5 accent-info rounded"
							disabled
						/>
					</label>
				</div>
				<p class="text-sm text-fg-4 mt-4">Notification settings coming soon.</p>
			</div>

			<!-- Preferences Section -->
			<div class="ui-surface p-6">
				<h2 class="text-lg font-semibold text-fg-1 mb-4">Preferences</h2>
				<div class="space-y-4">
					<div class="flex items-center justify-between">
						<div>
							<span class="text-fg-2">Area unit</span>
							<p class="text-xs text-fg-4">Display areas in square meters or square feet</p>
						</div>
						<div class="ui-segmented flex items-center gap-1">
							<button
								type="button"
								onclick={() => (areaUnit.current = 'sqm')}
								data-active={areaUnit.current === 'sqm'}
								class="ui-segmented-item px-3 py-1.5 text-sm"
							>
								sq.m
							</button>
							<button
								type="button"
								onclick={() => (areaUnit.current = 'sqft')}
								data-active={areaUnit.current === 'sqft'}
								class="ui-segmented-item px-3 py-1.5 text-sm"
							>
								sq.ft
							</button>
						</div>
					</div>
					<div class="flex items-center justify-between gap-4">
						<div>
							<span class="text-fg-2">Theme</span>
							<p class="text-xs text-fg-4">Use your device setting or choose a fixed mode</p>
						</div>
						<ThemePreferenceControl />
					</div>
				</div>
			</div>

			<!-- Account Actions Section -->
			<div class="ui-surface p-6">
				<button
					type="button"
					onclick={() => logout()}
					class="rounded-md border border-[rgba(163,36,36,0.2)] px-4 py-2 text-sm font-medium text-error transition hover:bg-error-bg"
				>
					Sign out of your account
				</button>
			</div>
		</div>
