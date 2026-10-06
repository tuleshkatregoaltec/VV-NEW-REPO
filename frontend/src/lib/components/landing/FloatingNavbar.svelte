<script lang="ts">
const navItems = [
	{ label: 'Platform', href: '#preview' },
	{ label: 'AI', href: '#ai' },
	{ label: 'Radar', href: '#radar' },
	{ label: 'Feasibility', href: '#feasibility' },
	{ label: 'For teams', href: '#personas' },
	{ label: 'Pricing', href: '#pricing' }
]
</script>

<nav class="fixed inset-x-0 top-0 z-50 border-b border-bone-border bg-bone">
	<div class="mx-auto flex max-w-[1440px] items-center justify-between gap-3 px-4 py-3.5 sm:px-8 sm:py-[18px]">
		<a href="/" aria-label="Vitevue home" class="shrink-0">
			<img
				src="/logos/vitevue-navbar-400.png"
				srcset="/logos/vitevue-navbar-800@2x.png 2x"
				alt="Vitevue"
				class="h-5 w-auto max-w-[126px] sm:h-[22px] sm:max-w-none"
			/>
		</a>

		<div class="flex min-w-0 items-center gap-3 sm:gap-6">
			<div class="hidden items-center gap-5 md:flex lg:gap-7">
				{#each navItems as item (item.href)}
					<a
						href={item.href}
						class="border-b border-transparent py-1 text-[13px] font-medium text-fg-1 transition-colors duration-150 hover:border-primary lg:text-sm"
					>
						{item.label}
					</a>
				{/each}
			</div>
			<a href="/auth" class="hidden text-sm font-medium text-fg-1 transition-colors hover:text-primary sm:inline">
				Sign in
			</a>
			<a
				href="/auth?view=signup"
				class="inline-flex shrink-0 items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-[13px] font-medium text-bone transition-colors duration-200 hover:bg-primary-light sm:gap-2 sm:px-4 sm:py-2 sm:text-sm"
			>
				Get launch access
				<svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
					<path
						stroke-linecap="round"
						stroke-linejoin="round"
						stroke-width="2"
						d="M13 7l5 5m0 0l-5 5m5-5H6"
					/>
				</svg>
			</a>
		</div>
	</div>
</nav>
<div class="h-[49px] sm:h-[59px]" aria-hidden="true"></div>
