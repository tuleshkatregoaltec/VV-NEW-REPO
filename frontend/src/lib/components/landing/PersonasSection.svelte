<script lang="ts">
const personas = [
	{
		number: '/ 01',
		title: 'Brokers',
		accent: '& agents',
		description:
			'Verify your pricing with ease, generate leads, automate your listing descriptions and stand out to clients with commercial-grade analysis.'
	},
	{
		number: '/ 02',
		title: 'Developers',
		description:
			'Pressure-test projects against live supply, pricing dynamics, and configuration opportunities well before the feasibility study lands.'
	},
	{
		number: '/ 03',
		title: 'Investors',
		accent: '& advisory',
		description:
			'Build evidence packs, run sub-market screens, and ship client-ready narratives without rebuilding the comp set every time.'
	}
]
</script>

<section id="personas" class="bg-bone-surface py-24 lg:py-28">
	<div class="mx-auto max-w-7xl px-5 sm:px-8 lg:px-10">
		<div class="max-w-3xl">
			<span class="eyebrow">Who it is for</span>
			<h2 class="display-2 mt-6">
				Be the tip <span class="display-italic">of the spear.</span>
			</h2>
			<p class="mt-5 max-w-2xl text-lg leading-[1.6] text-fg-2">
				Equipping Dubai's elite real estate professionals, from advisory desks to development
				boards.
			</p>
		</div>

		<div class="mt-16 grid gap-6 md:grid-cols-3">
			{#each personas as persona (persona.number)}
				<article
					class="flex min-h-[260px] flex-col gap-4 rounded-lg border border-bone-border bg-card-warm p-8 transition-colors duration-200 hover:border-[var(--color-bone-300)]"
				>
					<span class="font-mono text-[11px] font-medium tracking-[0.06em] text-fg-4">
						{persona.number}
					</span>
					<h3
						class="font-display text-[2rem] font-normal leading-[1.05] tracking-[-0.02em] text-fg-1"
					>
						{persona.title}
						{#if persona.accent}
							<span class="display-italic">{persona.accent}</span>
						{/if}
					</h3>
					<p class="text-[15px] leading-[1.6] text-fg-3">{persona.description}</p>
				</article>
			{/each}
		</div>
	</div>
</section>
