<script lang="ts">
const year = new Date().getFullYear()

const groups = [
	{
		title: 'Platform',
		links: [
			{ label: 'Platform preview', href: '/#preview' },
			{ label: 'Vitevue AI', href: '/#ai' },
			{ label: 'Radar', href: '/#radar' },
			{ label: 'Feasibility', href: '/#feasibility' },
			{ label: 'Pricing', href: '/#pricing' },
			{ label: 'Get launch access', href: '/auth?view=signup' }
		]
	},
	{
		title: 'Company',
		links: [
			{ label: 'Who it is for', href: '/#personas' },
			{
				label: 'Book a demo',
				href: 'mailto:contact@vitevue.com?subject=Vitevue%20platform%20demo'
			},
			{ label: 'Contact', href: 'mailto:contact@vitevue.com' }
		]
	},
	{
		title: 'Legal',
		links: [
			{ label: 'Privacy requests', href: 'mailto:contact@vitevue.com?subject=Privacy%20request' },
			{ label: 'Terms requests', href: 'mailto:contact@vitevue.com?subject=Terms%20request' },
			{ label: 'Data sources', href: 'mailto:contact@vitevue.com?subject=Data%20sources' }
		]
	}
]
</script>

<footer id="contact" class="border-t border-bone-border bg-bone">
	<div class="mx-auto max-w-[1440px] px-5 py-16 sm:px-8">
		<div class="grid gap-12 lg:grid-cols-[1.4fr_1fr_1fr_1fr] lg:gap-16">
			<div>
				<img
					src="/logos/vitevue-navbar-400.png"
					srcset="/logos/vitevue-navbar-800@2x.png 2x"
					alt="Vitevue"
					class="h-[22px] w-auto"
				/>
				<p class="mt-5 max-w-sm text-sm leading-relaxed text-fg-3">
					AI-native real estate intelligence for Dubai. Tactical comps, institutional outputs.
				</p>
			</div>

			{#each groups as group (group.title)}
				<div>
					<h2
						class="mb-5 text-[11px] font-medium uppercase tracking-[0.18em] text-fg-4"
					>
						{group.title}
					</h2>
					<ul class="space-y-3">
						{#each group.links as link (link.label)}
							<li>
								<a href={link.href} class="text-sm text-fg-2 transition-colors hover:text-fg-1">
									{link.label}
								</a>
							</li>
						{/each}
					</ul>
				</div>
			{/each}
		</div>

		<div
			class="mt-14 flex flex-col gap-3 border-t border-bone-border pt-6 text-xs text-fg-4 sm:flex-row sm:items-center sm:justify-between"
		>
			<span>&copy; {year} Vitevue L.L.C-FZ. All rights reserved.</span>
			<span>Dubai real estate intelligence</span>
		</div>
	</div>
</footer>
