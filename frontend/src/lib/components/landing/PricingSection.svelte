<script lang="ts">
import { storeSelectedTier } from '$lib/utils/onboarding'

type TierId = 'tier1' | 'tier2'
type Tier = {
	name: string
	price: string
	unit?: string
	description: string
	href: string
	tier?: TierId
	featured?: string
	features: string[]
}

function handleTierClick(tier: TierId) {
	storeSelectedTier(tier)
}

const tiers: Tier[] = [
	{
		name: 'Starter',
		price: '199',
		unit: 'AED · seat / mo',
		description: 'For independent brokers and analysts evaluating Dubai stock.',
		tier: 'tier1' as const,
		href: '/auth?view=signup&tier=tier1',
		features: [
			'Vitevue AI · 100 queries/mo',
			'Transaction explorer',
			'PDF evidence packs',
			'Email support'
		]
	},
	{
		name: 'Professional',
		price: '499',
		unit: 'AED · seat / mo',
		description: 'For producing teams running comps, pitches, and listings every week.',
		tier: 'tier2' as const,
		href: '/auth?view=signup&tier=tier2',
		featured: 'Most popular · -60%',
		features: [
			'Everything in Starter',
			'5x Vitevue AI usage + automated deliverables',
			'Auto comp-matching algorithm',
			'Priority support, shared workspaces'
		]
	},
	{
		name: 'Enterprise',
		price: 'Custom',
		description: 'For developers, investors, and advisory firms with desk-wide needs.',
		href: 'mailto:contact@vitevue.com',
		features: [
			'Everything in Professional',
			'Unlimited Vitevue AI',
			'API access + custom datasets',
			'Dedicated success manager'
		]
	}
]
</script>

<section id="pricing" class="bg-bone py-24 lg:py-28">
	<div class="mx-auto max-w-7xl px-5 sm:px-8 lg:px-10">
		<div class="max-w-3xl">
			<span class="eyebrow">Pricing</span>
			<h2 class="display-2 mt-6">
				Lock in our <span class="display-italic">launch pricing.</span>
			</h2>
			<p class="mt-5 max-w-2xl text-lg leading-[1.6] text-fg-2">
				Three plans, AED-priced, billed monthly per seat. Save 60% versus list during the early
				bird window.
			</p>
		</div>

		<div class="mt-16 grid gap-3 md:grid-cols-3">
			{#each tiers as tier (tier.name)}
				<article
					class="relative flex min-h-[520px] flex-col gap-6 rounded-lg border bg-white p-8 {tier.featured
						? 'border-2 border-primary'
						: 'border-bone-border'}"
				>
					<div class="flex min-h-6 items-center justify-between gap-4">
						<h3
							class="text-[13px] font-semibold uppercase tracking-[0.06em] text-fg-1"
						>
							{tier.name}
						</h3>
						{#if tier.featured}
							<span class="font-mono text-[10px] font-medium uppercase tracking-[0.08em] text-primary">
								{tier.featured}
							</span>
						{/if}
					</div>

					<p class="text-sm leading-[1.6] text-fg-3">{tier.description}</p>

					<div class="flex items-baseline gap-2">
						<span
							class="font-display text-[clamp(3rem,5vw,3.5rem)] font-normal leading-none tracking-[-0.025em] text-fg-1"
						>
							{tier.price}
						</span>
						{#if tier.unit}
							<span class="text-sm text-fg-4">{tier.unit}</span>
						{/if}
					</div>

					<ul class="flex flex-1 flex-col gap-3">
						{#each tier.features as feature (feature)}
							<li class="flex items-start gap-3 text-sm leading-relaxed text-fg-2">
								<svg
									class="mt-0.5 h-3.5 w-3.5 flex-none text-primary"
									fill="none"
									stroke="currentColor"
									viewBox="0 0 24 24"
								>
									<path
										stroke-linecap="round"
										stroke-linejoin="round"
										stroke-width="2.5"
										d="M5 13l4 4L19 7"
									/>
								</svg>
								<span>{feature}</span>
							</li>
						{/each}
					</ul>

					{#if tier.tier}
						<a
							href={tier.href}
							onclick={() => tier.tier && handleTierClick(tier.tier)}
							class="inline-flex justify-center rounded-md {tier.featured
								? 'bg-primary text-bone hover:bg-primary-light'
								: 'border border-primary text-primary hover:bg-primary hover:text-bone'} px-5 py-3 text-sm font-medium transition-colors duration-200"
						>
							Start with {tier.name}
						</a>
					{:else}
						<a
							href={tier.href}
							class="inline-flex justify-center rounded-md border border-primary px-5 py-3 text-sm font-medium text-primary transition-colors duration-200 hover:bg-primary hover:text-bone"
						>
							Contact sales
						</a>
					{/if}
				</article>
			{/each}
		</div>

		<div
			class="mt-8 flex items-center justify-center gap-2 font-mono text-[11px] font-medium uppercase tracking-[0.08em] text-warning"
		>
			<svg class="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3" />
				<circle cx="12" cy="12" r="9" stroke-width="2" fill="none" />
			</svg>
			Early bird - limited time
		</div>
	</div>
</section>
