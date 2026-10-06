<script lang="ts">
const navItems = [
	{ label: 'Platform', href: '#preview' },
	{ label: 'Personas', href: '#personas' },
	{ label: 'Pricing', href: '#pricing' },
	{ label: 'Contact', href: '#contact' }
]
</script>

<nav class="sticky top-0 z-50 border-b border-bone-border bg-bone">
	<div class="mx-auto max-w-[1440px] px-5 py-[18px] sm:px-8">
		<div class="flex items-center justify-between">
			<a href="/" aria-label="Vitevue home">
				<img
					src="/logos/vitevue-navbar-400.png"
					srcset="/logos/vitevue-navbar-800@2x.png 2x"
					alt="Vitevue"
					class="h-[22px] w-auto"
				/>
			</a>

			<div class="flex items-center gap-6">
				{#each navItems as item (item.href)}
					<a
						href={item.href}
						class="border-b border-transparent py-1 text-sm font-medium text-fg-1 transition-colors duration-150 hover:border-primary"
					>
						{item.label}
					</a>
				{/each}
				<a
					href="/auth"
					class="inline-flex items-center gap-1.5 rounded-md bg-primary px-4 py-2 text-sm font-medium text-bone transition-colors hover:bg-primary-light"
				>
					Get started
					<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
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
	</div>
</nav>
