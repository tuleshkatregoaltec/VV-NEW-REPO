<script lang="ts">
import { ArrowRight, Bot, Check, Database, FileSpreadsheet, MapPinned, Radar } from 'lucide-svelte'

const signupHref = '/auth?view=signup'
const demoHref = 'mailto:contact@vitevue.com?subject=Vitevue%20platform%20demo'

const highlights = [
	{
		title: 'Live market context',
		copy: 'Daily pricing, transaction velocity, and research context in the workspace your team opens first.',
		icon: Database
	},
	{
		title: 'Planning radar',
		copy: 'Business Bay DDA parcels, pipeline projects, and area-level supply signals in one map view.',
		icon: MapPinned
	},
	{
		title: 'AI feasibility support',
		copy: 'Agent-suggested workbook changes stay reviewable before they flow into the model.',
		icon: Bot
	}
]

const bullets = [
	'Dashboard view for the daily market picture',
	'Business Bay radar with DDA planning parcels enabled',
	'Feasibility worksheet moments where AI suggestions remain under team control'
]

const workflowCards = [
	{
		title: 'Live data',
		value: '10M+ indexed records',
		icon: Database
	},
	{
		title: 'Planning radar',
		value: 'Parcels, pipeline, supply',
		icon: Radar
	},
	{
		title: 'Review queue',
		value: 'AI changes stay gated',
		icon: FileSpreadsheet
	}
]

const signalRows = [
	{ label: 'Business Bay', metric: 'DDA parcels', value: '42' },
	{ label: 'JVC residential', metric: 'Comparable deals', value: '312' },
	{ label: 'Downtown', metric: 'Supply watch', value: '+8.4%' }
]

const reviewRows = [
	{ input: 'Saleable efficiency', current: '79.5%', suggested: '82.0%' },
	{ input: 'Average price', current: '2,960', suggested: '3,080' },
	{ input: 'Parking ratio', current: '1.25', suggested: '1.18' }
]
</script>

<section id="preview" class="scroll-mt-24 overflow-hidden bg-bone py-24 lg:py-28">
	<div class="mx-auto max-w-7xl px-5 sm:px-8 lg:px-10">
		<div class="grid items-center gap-14 lg:grid-cols-[0.82fr_1.18fr] lg:gap-16">
			<div>
				<span class="eyebrow">Platform</span>
				<h2 class="display-2 mt-6">
					A market workspace with <span class="display-italic">AI in the loop.</span>
				</h2>
				<p class="mt-5 max-w-xl text-[17px] leading-[1.65] text-fg-2">
					Start from the daily dashboard, zoom into the planning layer around a target area,
					and let the feasibility agent prepare workbook changes your team can accept, edit, or
					reject.
				</p>

				<ul class="mt-7 space-y-3">
					{#each bullets as bullet (bullet)}
						<li class="flex items-start gap-3 text-[15px] leading-relaxed text-fg-2">
							<span class="mt-0.5 grid h-5 w-5 flex-none place-items-center rounded-md bg-primary text-bone">
								<Check class="h-3.5 w-3.5" aria-hidden="true" />
							</span>
							<span>{bullet}</span>
						</li>
					{/each}
				</ul>

				<div class="mt-8 flex flex-col gap-3 sm:flex-row">
					<a
						href={signupHref}
						class="inline-flex items-center justify-center gap-2 rounded-md bg-primary px-6 py-3.5 text-sm font-medium text-bone transition-colors duration-200 hover:bg-primary-light"
					>
						Get launch access
						<ArrowRight class="h-4 w-4" aria-hidden="true" />
					</a>
					<a
						href={demoHref}
						class="inline-flex items-center justify-center rounded-md border border-primary px-6 py-3.5 text-sm font-medium text-primary transition-colors duration-200 hover:bg-primary hover:text-bone"
					>
						Book a demo
					</a>
				</div>
			</div>

			<div class="grid gap-4">
				<div class="rounded-lg border border-bone-border bg-white p-4 shadow-[var(--shadow-md)]">
					<div class="flex items-center justify-between gap-4 border-b border-border pb-4">
						<div>
							<p class="font-mono text-[10px] uppercase tracking-[0.1em] text-fg-4">
								Workspace flow
							</p>
							<h3 class="mt-1 text-lg font-semibold text-fg-1">From market signal to model change</h3>
						</div>
						<span class="rounded-md bg-success-bg px-3 py-1 font-mono text-[10px] uppercase tracking-[0.08em] text-success">
							Reviewable
						</span>
					</div>

					<div class="mt-4 grid gap-3 sm:grid-cols-3">
						{#each workflowCards as card, i (card.title)}
							<div class="rounded-md bg-bone px-4 py-4">
								<div class="flex items-center justify-between gap-3">
									<span class="grid h-9 w-9 place-items-center rounded-full bg-white text-primary shadow-[var(--shadow-xs)]">
										<svelte:component this={card.icon} class="h-4 w-4" aria-hidden="true" />
									</span>
									<span class="font-mono text-[10px] text-fg-4">0{i + 1}</span>
								</div>
								<p class="mt-4 text-sm font-semibold text-fg-1">{card.title}</p>
								<p class="mt-1 text-xs leading-5 text-fg-3">{card.value}</p>
							</div>
						{/each}
					</div>
				</div>

				<div class="grid gap-4 sm:grid-cols-[0.92fr_1.08fr]">
					<article
						id="radar"
						class="scroll-mt-24 overflow-hidden rounded-lg border border-bone-border bg-white shadow-[var(--shadow-md)]"
					>
						<div class="flex items-center justify-between border-b border-border px-4 py-3">
							<div class="flex items-center gap-2">
								<span class="grid h-8 w-8 place-items-center rounded-full bg-primary-pale text-primary">
									<MapPinned class="h-4 w-4" aria-hidden="true" />
								</span>
								<span class="text-sm font-semibold text-fg-1">Planning radar</span>
							</div>
							<span class="font-mono text-[10px] uppercase tracking-[0.08em] text-fg-4">Business Bay</span>
						</div>
						<div class="p-4">
							<div
								class="relative h-48 overflow-hidden rounded-md border border-border bg-[linear-gradient(90deg,rgba(226,232,240,0.75)_1px,transparent_1px),linear-gradient(0deg,rgba(226,232,240,0.75)_1px,transparent_1px)] bg-[size:28px_28px]"
								aria-hidden="true"
							>
								<div class="absolute left-8 top-7 h-8 w-28 rotate-[-10deg] rounded-full bg-primary/12"></div>
								<div class="absolute left-24 top-20 h-9 w-36 rotate-[8deg] rounded-full bg-success/12"></div>
								<div class="absolute bottom-8 right-9 h-8 w-24 rotate-[-16deg] rounded-full bg-warning/14"></div>
								<span class="absolute left-[22%] top-[34%] h-3 w-3 rounded-full bg-primary shadow-[0_0_0_8px_rgba(11,27,43,0.08)]"></span>
								<span class="absolute right-[28%] top-[46%] h-3 w-3 rounded-full bg-success shadow-[0_0_0_8px_rgba(17,122,72,0.08)]"></span>
								<span class="absolute bottom-[28%] left-[52%] h-3 w-3 rounded-full bg-warning shadow-[0_0_0_8px_rgba(165,90,19,0.1)]"></span>
							</div>
							<div class="mt-4 space-y-2">
								{#each signalRows as row (row.label)}
									<div class="grid grid-cols-[1fr_auto] gap-3 rounded-md bg-bone px-3 py-2.5">
										<div>
											<p class="text-xs font-semibold text-fg-1">{row.label}</p>
											<p class="mt-0.5 font-mono text-[10px] uppercase tracking-[0.08em] text-fg-4">
												{row.metric}
											</p>
										</div>
										<span class="self-center font-mono text-sm font-semibold text-primary">{row.value}</span>
									</div>
								{/each}
							</div>
						</div>
					</article>

					<article
						id="ai"
						class="scroll-mt-24 overflow-hidden rounded-lg border border-bone-border bg-white shadow-[var(--shadow-md)]"
					>
						<div class="flex items-center justify-between border-b border-border px-4 py-3">
							<div class="flex items-center gap-2">
								<span class="grid h-8 w-8 place-items-center rounded-full bg-success-bg text-success">
									<Bot class="h-4 w-4" aria-hidden="true" />
								</span>
								<span class="text-sm font-semibold text-fg-1">AI feasibility</span>
							</div>
							<span class="rounded-md bg-success-bg px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.08em] text-success">
								Working
							</span>
						</div>

						<div
							id="feasibility"
							class="scroll-mt-24 bg-slate-50 p-4"
						>
							<div class="rounded-md border border-border bg-white p-4 shadow-[var(--shadow-xs)]">
								<div class="flex items-start gap-2.5">
									<span class="grid h-8 w-8 flex-none place-items-center rounded-full bg-primary text-bone">
										<FileSpreadsheet class="h-4 w-4" aria-hidden="true" />
									</span>
									<div class="min-w-0">
										<p class="text-xs font-semibold text-fg-1">Revenue worksheet queue</p>
										<p class="mt-1 text-[11px] leading-4 text-fg-3">
											Business Bay comps support three model changes, held for manual approval.
										</p>
									</div>
								</div>

								<div class="mt-4 overflow-hidden rounded-md border border-border">
									<div class="grid grid-cols-[1.1fr_0.8fr_0.8fr] bg-panel px-3 py-2 font-mono text-[9px] uppercase tracking-[0.08em] text-fg-4">
										<span>Input</span>
										<span>Current</span>
										<span>Suggested</span>
									</div>
									{#each reviewRows as row (row.input)}
										<div class="grid grid-cols-[1.1fr_0.8fr_0.8fr] border-t border-border bg-white px-3 py-2 text-[11px]">
											<span class="text-fg-3">{row.input}</span>
											<span class="font-mono text-fg-2">{row.current}</span>
											<span class="font-mono font-semibold text-success">{row.suggested}</span>
										</div>
									{/each}
								</div>
							</div>
						</div>
					</article>
				</div>
			</div>
		</div>

		<div class="mt-16 grid gap-4 border-y border-bone-border py-6 md:grid-cols-3">
			{#each highlights as item (item.title)}
				<div class="flex gap-4">
					<span
						class="grid h-10 w-10 flex-none place-items-center rounded-md bg-primary-pale text-primary"
					>
						<svelte:component this={item.icon} class="h-4 w-4" aria-hidden="true" />
					</span>
					<div>
						<h3 class="text-sm font-semibold text-fg-1">{item.title}</h3>
						<p class="mt-1 text-sm leading-relaxed text-fg-3">{item.copy}</p>
					</div>
				</div>
			{/each}
		</div>
	</div>
</section>
