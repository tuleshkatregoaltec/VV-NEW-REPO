<script lang="ts">
import {
	BarChart3,
	Building2,
	Calculator,
	ContactRound,
	Home,
	LayoutDashboard,
	LogOut,
	MapPinned,
	MessageSquare,
	ReceiptText,
	Settings,
	ShieldCheck,
	User,
	Workflow
} from 'lucide-svelte'
import { page } from '$app/state'
import { logout } from '$lib/api/auth'

let {
	show,
	onNavigate = () => {}
}: {
	show: boolean
	onNavigate?: () => void
} = $props()

function isActive(href: string, activePrefix = href) {
	const pathname = page.url.pathname
	return (
		pathname === href ||
		pathname.startsWith(`${href}/`) ||
		pathname === activePrefix ||
		pathname.startsWith(`${activePrefix}/`)
	)
}

function linkClass(href: string, activePrefix = href) {
	return `flex items-center gap-3 rounded-md px-3 py-2.5 text-sm font-semibold transition-colors ${
		isActive(href, activePrefix)
			? 'bg-info-bg text-info'
			: 'text-fg-2 hover:bg-panel hover:text-fg-1'
	}`
}

function pillClass(href: string) {
	return `rounded-md px-3 py-2 text-center text-sm font-medium transition-colors ${
		isActive(href) ? 'bg-card text-fg-1 shadow-xs' : 'text-fg-3 hover:bg-card hover:text-fg-1'
	}`
}

function handleLogout() {
	onNavigate()
	void logout()
}
</script>

{#if show}
	<div id="mobile-navigation" class="border-t border-border pb-4 pt-3 lg:hidden">
		<div class="rounded-lg border border-border bg-card p-1.5 shadow-sm">
			<a href="/dashboard" onclick={onNavigate} class={linkClass('/dashboard')} aria-current={isActive('/dashboard') ? 'page' : undefined}>
				<LayoutDashboard size={16} strokeWidth={2} aria-hidden="true" />
				<span>Dashboard</span>
			</a>

			<a href="/crm" onclick={onNavigate} class={linkClass('/crm')} aria-current={isActive('/crm') ? 'page' : undefined}>
				<ContactRound size={16} strokeWidth={2} aria-hidden="true" />
				<span>CRM</span>
			</a>

			<a href="/workflows" onclick={onNavigate} class={linkClass('/workflows')} aria-current={isActive('/workflows') ? 'page' : undefined}>
				<Workflow size={16} strokeWidth={2} aria-hidden="true" />
				<span>Workflows</span>
			</a>

			<a href="/chat" onclick={onNavigate} class={linkClass('/chat')} aria-current={isActive('/chat') ? 'page' : undefined}>
				<MessageSquare size={16} strokeWidth={2} aria-hidden="true" />
				<span>Chat</span>
			</a>

			<a
				href="/transactions/sales"
				onclick={onNavigate}
				class={linkClass('/transactions/sales', '/transactions')}
				aria-current={isActive('/transactions/sales', '/transactions') ? 'page' : undefined}
			>
				<ReceiptText size={16} strokeWidth={2} aria-hidden="true" />
				<span>Transactions</span>
			</a>

			<div class="-mt-1 grid grid-cols-2 gap-1 rounded-md bg-panel p-1">
				<a href="/transactions/sales" onclick={onNavigate} class={pillClass('/transactions/sales')}>Sales</a>
				<a href="/transactions/rentals" onclick={onNavigate} class={pillClass('/transactions/rentals')}>Rentals</a>
			</div>

			<a href="/analytics" onclick={onNavigate} class={linkClass('/analytics')} aria-current={isActive('/analytics') ? 'page' : undefined}>
				<BarChart3 size={16} strokeWidth={2} aria-hidden="true" />
				<span>Analytics</span>
			</a>

			<a href="/radar" onclick={onNavigate} class={linkClass('/radar')} aria-current={isActive('/radar') ? 'page' : undefined}>
				<MapPinned size={16} strokeWidth={2} aria-hidden="true" />
				<span>Radar</span>
			</a>

			<a href="/upcoming" onclick={onNavigate} class={linkClass('/upcoming')} aria-current={isActive('/upcoming') ? 'page' : undefined}>
				<Building2 size={16} strokeWidth={2} aria-hidden="true" />
				<span>Upcoming</span>
			</a>

			<a href="/developers" onclick={onNavigate} class={linkClass('/developers')} aria-current={isActive('/developers') ? 'page' : undefined}>
				<ShieldCheck size={16} strokeWidth={2} aria-hidden="true" />
				<span>Developers</span>
			</a>

			<a href="/listings" onclick={onNavigate} class={linkClass('/listings')} aria-current={isActive('/listings') ? 'page' : undefined}>
				<Home size={16} strokeWidth={2} aria-hidden="true" />
				<span>Listings</span>
			</a>

			<a href="/feasibility" onclick={onNavigate} class={linkClass('/feasibility')} aria-current={isActive('/feasibility') ? 'page' : undefined}>
				<Calculator size={16} strokeWidth={2} aria-hidden="true" />
				<span>Feasibility</span>
			</a>
		</div>

		<div class="mt-2 rounded-lg border border-border bg-card p-1.5 shadow-sm">
			<a href="/profile" onclick={onNavigate} class={linkClass('/profile')} aria-current={isActive('/profile') ? 'page' : undefined}>
				<User size={16} strokeWidth={2} aria-hidden="true" />
				<span>My profile</span>
			</a>

			<a
				href="/settings/organization"
				onclick={onNavigate}
				class={linkClass('/settings/organization', '/settings')}
				aria-current={isActive('/settings/organization', '/settings') ? 'page' : undefined}
			>
				<Settings size={16} strokeWidth={2} aria-hidden="true" />
				<span>Settings</span>
			</a>

			<button
				type="button"
				onclick={handleLogout}
				class="flex w-full items-center gap-3 rounded-md px-3 py-2.5 text-left text-sm font-semibold text-error transition-colors hover:bg-error-bg"
			>
				<LogOut size={16} strokeWidth={2} aria-hidden="true" />
				<span>Sign out</span>
			</button>
		</div>
	</div>
{/if}
