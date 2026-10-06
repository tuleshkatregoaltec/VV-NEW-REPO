<script lang="ts">
import {
	ArrowRight,
	ArrowUpRight,
	Bot,
	Building2,
	Database,
	FileSpreadsheet,
	MapPinned,
	Radar
} from 'lucide-svelte'

const marketSignals = [
	{
		label: 'Business Bay radar',
		value: 'DDA parcels',
		icon: MapPinned
	},
	{
		label: 'Comparable set',
		value: '312 deals',
		icon: Database
	},
	{
		label: 'Feasibility agent',
		value: '3 edits queued',
		icon: Bot
	}
]

const proofPoints = [
	{
		value: '10M+',
		label: 'transactions indexed'
	},
	{
		value: '3,000+',
		label: 'projects tracked'
	},
	{
		value: '15 yrs',
		label: 'macro history'
	}
]

function scrollToPreview() {
	document.getElementById('preview')?.scrollIntoView({ behavior: 'smooth' })
}
</script>

<section class="relative isolate overflow-hidden bg-bone">
	<div class="relative mx-auto max-w-7xl px-5 pb-14 pt-8 sm:px-8 sm:pb-16 sm:pt-10 lg:px-10 lg:pb-20 lg:pt-12">
		<div class="grid items-center gap-12 lg:grid-cols-[0.95fr_1.05fr] lg:gap-12">
			<div class="max-w-3xl lg:pb-14">
				<span class="eyebrow">Dubai real estate intelligence</span>
				<h1 class="display-1 mt-7 max-w-4xl">
					Read the market before the meeting.
				</h1>
				<p class="mt-7 max-w-2xl text-lg leading-[1.6] text-fg-2 sm:text-xl">
					Vitevue gives investment, advisory, and development teams one workspace for live
					Dubai transactions, planning radar, comparable evidence, and reviewable AI
					feasibility suggestions.
				</p>
				<div class="mt-9 flex flex-col gap-3 sm:flex-row">
					<a
						href="/auth?view=signup"
						class="inline-flex items-center justify-center gap-2 rounded-md bg-primary px-7 py-4 text-sm font-medium text-bone transition-colors duration-200 hover:bg-primary-light"
					>
						Get launch access
						<ArrowRight class="h-4 w-4" aria-hidden="true" />
					</a>
					<button
						type="button"
						onclick={scrollToPreview}
						class="inline-flex items-center justify-center rounded-md border border-primary bg-transparent px-7 py-4 text-sm font-medium text-primary transition-colors duration-200 hover:bg-primary hover:text-bone"
					>
						See platform
					</button>
				</div>

				<div class="mt-12 hidden max-w-xl grid-cols-3 border-y border-bone-border lg:grid">
					{#each proofPoints as point, i (point.label)}
						<div class:border-r={i < proofPoints.length - 1} class="border-bone-border py-5 pr-3 sm:pr-5">
							<div class="font-display text-3xl leading-none tracking-normal text-fg-1 sm:text-4xl">
								{point.value}
							</div>
							<div class="mt-2 text-[12px] leading-snug text-fg-3 sm:text-sm">{point.label}</div>
						</div>
					{/each}
				</div>
			</div>

			<div class="relative lg:min-h-[660px]">
				<div
					class="absolute -left-7 top-8 z-20 hidden w-44 rotate-[-2deg] rounded-lg border border-bone-border bg-white p-2 shadow-[var(--shadow-md)] lg:block"
					aria-hidden="true"
				>
					<div class="rounded-md bg-primary px-4 py-5 text-bone">
						<Radar class="h-5 w-5" aria-hidden="true" />
						<p class="mt-5 font-mono text-[10px] uppercase tracking-[0.1em] text-bone/58">
							Market pulse
						</p>
						<p class="mt-2 font-display text-4xl leading-none tracking-normal">+12.1%</p>
						<p class="mt-2 text-xs leading-5 text-bone/70">Business Bay sales PSF, Q1 signal</p>
					</div>
				</div>

				<div class="relative z-10 ml-auto max-w-4xl">
					<div
						class="rounded-lg border border-bone-border bg-white p-3 shadow-[var(--shadow-lg)]"
					>
						<div class="overflow-hidden rounded-md bg-white">
							<div class="flex items-center justify-between border-b border-border bg-panel px-4 py-3">
								<div class="flex items-center gap-1.5" aria-hidden="true">
									<span class="h-2.5 w-2.5 rounded-full bg-error"></span>
									<span class="h-2.5 w-2.5 rounded-full bg-warning"></span>
									<span class="h-2.5 w-2.5 rounded-full bg-success"></span>
								</div>
								<span class="font-mono text-[10px] uppercase tracking-[0.1em] text-fg-4">
									Live market workspace
								</span>
							</div>
							<div class="relative aspect-[16/10] overflow-hidden bg-slate-100">
								<img
									src="/images/platform-dashboard.png"
									alt="Vitevue dashboard showing market intelligence cards and charts"
									class="h-full w-full object-cover object-top"
									loading="eager"
								/>
								<div
									class="pointer-events-none absolute inset-x-0 bottom-0 h-1/3 bg-gradient-to-t from-white via-white/88 to-transparent"
									aria-hidden="true"
								></div>
							</div>
						</div>
					</div>

					<div
						class="mt-4 grid gap-3 rounded-lg border border-bone-border bg-white p-3 shadow-[var(--shadow-md)] sm:grid-cols-3 lg:hidden"
					>
						{#each marketSignals as signal (signal.label)}
							<div class="rounded-md bg-bone px-3 py-3">
								<div class="flex items-center gap-2">
									<span class="grid h-8 w-8 place-items-center rounded-full bg-white text-primary shadow-[var(--shadow-xs)]">
										<svelte:component this={signal.icon} class="h-4 w-4" aria-hidden="true" />
									</span>
									<p class="min-w-0 truncate text-xs font-semibold text-fg-1">{signal.label}</p>
								</div>
								<p class="mt-3 font-mono text-[11px] uppercase tracking-[0.08em] text-fg-4">
									{signal.value}
								</p>
							</div>
						{/each}
					</div>
				</div>

				<div
					class="relative z-20 mt-4 grid gap-4 sm:grid-cols-[0.92fr_1.08fr] lg:absolute lg:-bottom-4 lg:left-4 lg:right-10 lg:mt-0"
				>
					<div class="overflow-hidden rounded-lg border border-bone-border bg-white shadow-[var(--shadow-md)]">
						<div class="flex items-center justify-between border-b border-border px-3 py-2.5">
							<span class="flex items-center gap-2 text-xs font-semibold text-fg-1">
								<Building2 class="h-3.5 w-3.5 text-primary" aria-hidden="true" />
								Business Bay planning radar
							</span>
							<ArrowUpRight class="h-3.5 w-3.5 text-fg-4" aria-hidden="true" />
						</div>
						<div class="h-40 overflow-hidden sm:h-48">
							<img
								src="/images/platform-radar-business-bay.png"
								alt="Business Bay radar map with planning parcels"
								class="h-full w-full object-cover object-[48%_34%]"
								loading="eager"
							/>
						</div>
					</div>

					<div class="rounded-lg border border-bone-border bg-white p-4 shadow-[var(--shadow-md)]">
						<div class="flex items-center justify-between gap-3">
							<div class="flex items-center gap-2.5">
								<span class="grid h-9 w-9 place-items-center rounded-full bg-success-bg text-success">
									<FileSpreadsheet class="h-4 w-4" aria-hidden="true" />
								</span>
								<div>
									<p class="text-sm font-semibold text-fg-1">Feasibility update</p>
									<p class="mt-0.5 text-xs text-fg-4">AI suggestion waiting for review</p>
								</div>
							</div>
							<span class="rounded-md bg-success-bg px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.08em] text-success">
								Review
							</span>
						</div>

						<div class="mt-4 grid grid-cols-3 gap-2">
							<div class="rounded-md bg-bone px-3 py-2">
								<p class="font-mono text-[9px] uppercase tracking-[0.08em] text-fg-4">GDV</p>
								<p class="mt-1 font-mono text-xs font-semibold text-success">+18.6M</p>
							</div>
							<div class="rounded-md bg-bone px-3 py-2">
								<p class="font-mono text-[9px] uppercase tracking-[0.08em] text-fg-4">POC</p>
								<p class="mt-1 font-mono text-xs font-semibold text-primary">+140bps</p>
							</div>
							<div class="rounded-md bg-bone px-3 py-2">
								<p class="font-mono text-[9px] uppercase tracking-[0.08em] text-fg-4">Risk</p>
								<p class="mt-1 font-mono text-xs font-semibold text-warning">Review</p>
							</div>
						</div>
					</div>
				</div>

				<div class="mt-10 grid grid-cols-3 border-y border-bone-border lg:hidden">
					{#each proofPoints as point, i (point.label)}
						<div class:border-r={i < proofPoints.length - 1} class="border-bone-border py-5 pr-3">
							<div class="font-display text-3xl leading-none tracking-normal text-fg-1">
								{point.value}
							</div>
							<div class="mt-2 text-[12px] leading-snug text-fg-3">{point.label}</div>
						</div>
					{/each}
				</div>
			</div>
		</div>
	</div>
</section>
