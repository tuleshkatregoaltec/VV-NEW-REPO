<script lang="ts">
import { logout } from '$lib/api/auth'

export let email: string | null | undefined = null
export let label = 'Signed in as'
export let compact = false
export let redirectTo = '/auth'
let loading = false

async function handleLogout() {
	loading = true
	await logout(redirectTo)
}
</script>

{#if email}
	<div
		class:rounded-xl={compact}
		class:px-3={compact}
		class:py-2.5={compact}
		class="flex items-center justify-between gap-3 rounded-md border border-border bg-slate-50 px-4 py-3"
	>
		<div class="min-w-0">
			<p class="font-mono text-[10px] font-medium uppercase tracking-[0.08em] text-fg-4">
				{label}
			</p>
			<p class="truncate text-sm font-medium text-fg-1">{email}</p>
		</div>
		<button
			type="button"
			onclick={handleLogout}
			disabled={loading}
			class:text-xs={compact}
			class:px-2.5={compact}
			class:py-1={compact}
			class="shrink-0 rounded-md border border-border bg-white px-3 py-1.5 text-sm font-medium text-fg-2 transition hover:border-[var(--color-navy-600)] hover:text-navy disabled:opacity-60"
		>
			{loading ? 'Signing out...' : 'Use a different account'}
		</button>
	</div>
{/if}
