<script module lang="ts">
let nextId = 0
</script>

<script lang="ts">
import { LogOut, Settings, User } from 'lucide-svelte'
import { getContext } from 'svelte'
import { quintOut } from 'svelte/easing'
import { fade, fly } from 'svelte/transition'
import { logout } from '$lib/api/auth'
import { currentUser } from '$lib/stores/user.svelte'

let initials = $derived(
	(() => {
		const user = currentUser.data
		return user ? `${user.first_name?.[0] ?? ''}${user.last_name?.[0] ?? ''}`.toUpperCase() : ''
	})()
)
let displayName = $derived(
	(() => {
		const user = currentUser.data
		if (!user) return 'Account'
		return `${user.first_name ?? ''} ${user.last_name ?? ''}`.trim() || user.email
	})()
)
let displayMeta = $derived(currentUser.data?.email ?? currentUser.data?.organization_name ?? 'Workspace')
let failedAvatarUrl = $state<string | null>(null)
let avatarUrl = $derived(
	(() => {
		const url = currentUser.data?.avatar_url
		return url && url !== failedAvatarUrl ? url : ''
	})()
)

const HOVER_DELAY = 150

// Use shared openDropdownId context so profile dropdown doesn't overlap with others
let localState = $state<string | null>(null)
let openDropdownIdContext = getContext<{ value: string | null }>('openDropdownId') ?? {
	get value() {
		return localState
	},
	set value(v: string | null) {
		localState = v
	}
}

const id = `profile-dropdown-${nextId++}`
let timeout: number | undefined
let isOpen = $derived(openDropdownIdContext.value === id)

function handleEnter() {
	clearTimeout(timeout)
	timeout = window.setTimeout(() => {
		openDropdownIdContext.value = id
	}, HOVER_DELAY)
}

function handleLeave() {
	clearTimeout(timeout)
	timeout = window.setTimeout(() => {
		if (openDropdownIdContext.value === id) openDropdownIdContext.value = null
	}, 200)
}

function handleLogout() {
	openDropdownIdContext.value = null
	logout()
}

function handleAvatarError() {
	failedAvatarUrl = currentUser.data?.avatar_url ?? null
}
</script>

<div class="relative" role="navigation" onmouseenter={handleEnter} onmouseleave={handleLeave}>
	<button
		class="flex h-[34px] w-[34px] items-center justify-center overflow-hidden rounded-full bg-navy text-xs font-semibold tracking-[0.02em] text-bone transition-colors hover:bg-primary-light"
		aria-label="Profile menu"
		aria-haspopup="true"
		aria-expanded={isOpen}
	>
		{#if avatarUrl}
			<img src={avatarUrl} alt="" class="h-full w-full object-cover" onerror={handleAvatarError} />
		{:else}
			{initials}
		{/if}
	</button>

	{#if isOpen}
		<div
			class="ui-menu absolute right-0 z-50 mt-2 w-64 overflow-hidden"
			in:fly={{ y: -10, duration: 200, easing: quintOut }}
			out:fade={{ duration: 150 }}
		>
			<div class="border-b border-border bg-panel px-3 py-3">
				<div class="flex items-center gap-3">
					<div
						class="flex h-9 w-9 items-center justify-center overflow-hidden rounded-full bg-navy text-xs font-semibold tracking-[0.02em] text-bone"
					>
						{#if avatarUrl}
							<img src={avatarUrl} alt="" class="h-full w-full object-cover" onerror={handleAvatarError} />
						{:else}
							{initials}
						{/if}
					</div>
					<div class="min-w-0">
						<p class="truncate text-sm font-semibold text-fg-1">{displayName}</p>
						<p class="mt-0.5 truncate text-xs text-fg-4">{displayMeta}</p>
					</div>
				</div>
			</div>
			<div class="p-1.5">
				<a
					href="/profile"
					class="flex items-center gap-2.5 rounded-md px-2.5 py-2 text-sm font-medium text-fg-3 transition-colors hover:bg-elevated hover:text-fg-1"
				>
					<User size={15} strokeWidth={1.9} />
					My profile
				</a>
				<a
					href="/settings/organization"
					class="flex items-center gap-2.5 rounded-md px-2.5 py-2 text-sm font-medium text-fg-3 transition-colors hover:bg-elevated hover:text-fg-1"
				>
					<Settings size={15} strokeWidth={1.9} />
					Settings
				</a>
			</div>
			<div class="mx-1.5 h-px bg-border"></div>
			<div class="p-1.5">
				<button
					type="button"
					onclick={handleLogout}
					class="flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-left text-sm font-medium text-error transition-colors hover:bg-error-bg"
				>
					<LogOut size={15} strokeWidth={1.9} />
					Sign out
				</button>
			</div>
		</div>
	{/if}
</div>
