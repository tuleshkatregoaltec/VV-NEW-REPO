<script lang="ts">
import { Bell, Menu, Search, X } from 'lucide-svelte'
import ThemeToggle from '$lib/components/preferences/ThemeToggle.svelte'
import MobileNavigation from './MobileNavigation.svelte'
import NavLink from './NavLink.svelte'
import ProfileDropdown from './ProfileDropdown.svelte'

let showMobileMenu = $state(false)
const mobileMenuLabel = $derived(showMobileMenu ? 'Close navigation menu' : 'Open navigation menu')
</script>

<nav class="sticky top-0 z-50 border-b border-border bg-card">
	<div class="mx-auto max-w-[1440px] px-5 sm:px-8">
		<div class="flex py-3.5 items-center justify-between">
			<div class="flex min-w-0 items-center gap-10">
				<a href="/" class="flex-shrink-0" aria-label="Vitevue home">
					<img
						src="/logos/vitevue-navbar-400.png"
						srcset="/logos/vitevue-navbar-800@2x.png 2x"
						alt="Vitevue"
						class="brand-logo-light h-[22px] w-auto"
					/>
					<img
						src="/logos/vitevue-navbar-bone.png"
						alt="Vitevue"
						class="brand-logo-dark h-[22px] w-auto"
					/>
				</a>

				<div class="hidden items-center gap-1 lg:flex">
					<NavLink href="/dashboard" label="Dashboard" />
					<NavLink href="/crm" label="CRM" />
					<NavLink href="/workflows" label="Workflows" />
					<NavLink href="/chat" label="Chat" />
					<NavLink href="/transactions/sales" label="Transactions" activePrefix="/transactions" />
					<NavLink href="/analytics" label="Analytics" />
					<NavLink href="/radar" label="Radar" />
					<NavLink href="/upcoming" label="Upcoming" />
					<NavLink href="/developers" label="Developers" />
					<NavLink href="/listings" label="Listings" />
					<NavLink href="/feasibility" label="Feasibility" />
				</div>
			</div>

			<div class="flex flex-shrink-0 items-center gap-3">
				<div class="hidden items-center gap-3 lg:flex">
					<button
						type="button"
						disabled
						data-variant="ghost"
						data-size="icon"
						class="ui-button h-[34px] w-[34px] cursor-default"
						aria-label="Search coming soon"
						title="Search coming soon"
					>
						<Search size={14} strokeWidth={2} />
					</button>
					<button
						type="button"
						disabled
						data-variant="ghost"
						data-size="icon"
						class="ui-button h-[34px] w-[34px] cursor-default"
						aria-label="Notifications coming soon"
						title="Notifications coming soon"
					>
						<Bell size={14} strokeWidth={2} />
					</button>
				</div>
				<ThemeToggle />
				<div class="hidden lg:block">
					<ProfileDropdown />
				</div>

				<button
					onclick={() => (showMobileMenu = !showMobileMenu)}
					data-variant="secondary"
					data-size="icon"
					class="ui-button h-9 w-9 lg:hidden"
					aria-label={mobileMenuLabel}
					aria-expanded={showMobileMenu}
					aria-controls="mobile-navigation"
				>
					{#if showMobileMenu}
						<X size={16} strokeWidth={2} />
					{:else}
						<Menu size={16} strokeWidth={2} />
					{/if}
				</button>
			</div>
		</div>

		<MobileNavigation show={showMobileMenu} onNavigate={() => (showMobileMenu = false)} />
	</div>
</nav>
