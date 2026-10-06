<script lang="ts">
import { createInfiniteQuery } from '@tanstack/svelte-query'
import { ImageIcon, MapPin, Search, ShieldCheck, X } from 'lucide-svelte'
import { goto } from '$app/navigation'
import { page } from '$app/state'
import type { SupplyCatalogueProjectCardResponse, SupplyCatalogueSort } from '$lib/api/supply'
import AppFrame from '$lib/components/layout/AppFrame.svelte'
import PageContainer from '$lib/components/layout/PageContainer.svelte'
import { supplyQueries } from '$lib/queries/supply'

const PAGE_SIZE = 36

let search = $state('')
let selectedArea = $state('')
let selectedStatus = $state('')
let selectedSort = $state<SupplyCatalogueSort>('recommended')
let sentinel = $state<HTMLDivElement | undefined>()
let developerStatusInitialized = $state(false)
const selectedDeveloper = $derived(page.url.searchParams.get('developer') ?? '')

const catalogueFilters = $derived({
	search: search.trim() || undefined,
	area: selectedArea || undefined,
	status: selectedStatus || undefined,
	developer: selectedDeveloper || undefined,
	sort: selectedSort === 'recommended' ? undefined : selectedSort
})

const catalogueQuery = createInfiniteQuery(() =>
	supplyQueries.catalogueInfinite(catalogueFilters, PAGE_SIZE)
)
const catalogueSummary = $derived(catalogueQuery.data?.pages[0])
const projects = $derived(catalogueQuery.data?.pages.flatMap((page) => page.projects) ?? [])
const heroProject = $derived(projects[0] ?? null)
const hasFilters = $derived(
	Boolean(
		search.trim() ||
			selectedArea ||
			selectedStatus ||
			selectedDeveloper ||
			selectedSort !== 'recommended'
	)
)
const developerScore = $derived(
	projects.find((project) => project.developer_score != null)?.developer_score ?? null
)
const averageProjectScore = $derived.by(() => {
	const scores = projects
		.map((project) => project.project_score)
		.filter((score): score is number => typeof score === 'number')
	if (!scores.length) return null
	return scores.reduce((sum, score) => sum + score, 0) / scores.length
})
const absorptionRates = $derived(
	projects
		.map((project) => project.sales_absorption_pct)
		.filter((rate): rate is number => typeof rate === 'number')
)
const averageAbsorption = $derived.by(() => {
	if (absorptionRates.length < 3 || absorptionRates.length / Math.max(projects.length, 1) < 0.2) {
		return null
	}
	return absorptionRates.reduce((sum, rate) => sum + rate, 0) / absorptionRates.length
})
const launchedProjectCount = $derived(projects.filter((project) => project.launch_date).length)
const reviewedProjectCount = $derived(
	projects.filter((project) => typeof project.project_score === 'number').length
)

$effect(() => {
	if (selectedDeveloper && !developerStatusInitialized) {
		selectedStatus = ''
		developerStatusInitialized = true
	}
	if (!selectedDeveloper) developerStatusInitialized = false
})

$effect(() => {
	if (!sentinel) return

	const scrollRoot = sentinel.closest('.app-scroll-root')
	const observer = new IntersectionObserver(
		(entries) => {
			if (
				entries[0].isIntersecting &&
				catalogueQuery.hasNextPage &&
				!catalogueQuery.isFetchingNextPage
			) {
				catalogueQuery.fetchNextPage()
			}
		},
		{ root: scrollRoot, rootMargin: '900px 0px' }
	)

	observer.observe(sentinel)
	return () => observer.disconnect()
})

function formatMoney(value: number | null | undefined): string {
	if (value == null || value <= 0) return 'Price on request'
	if (value >= 1_000_000) return `AED ${(value / 1_000_000).toFixed(value >= 10_000_000 ? 1 : 2)}M`
	if (value >= 1_000) return `AED ${(value / 1_000).toFixed(0)}K`
	return `AED ${value.toLocaleString()}`
}

function clearFilters() {
	const hadDeveloper = Boolean(selectedDeveloper)
	search = ''
	selectedArea = ''
	selectedStatus = ''
	selectedSort = 'recommended'
	if (hadDeveloper) void goto('/upcoming', { replaceState: true })
}

function setDeveloperFilter(value: string) {
	const url = new URL(page.url)
	if (value) url.searchParams.set('developer', value)
	else url.searchParams.delete('developer')
	void goto(`${url.pathname}${url.search}`, { replaceState: true, noScroll: true })
}

function projectLocation(project: SupplyCatalogueProjectCardResponse): string {
	return project.area_name ?? project.region ?? 'Location TBD'
}

function hideBrokenImage(event: Event) {
	const image = event.currentTarget as HTMLImageElement | null
	image?.remove()
}

function formatScore(value: number | null | undefined): string {
	return value == null ? '~' : value.toFixed(1)
}

function formatInteger(value: number | null | undefined): string {
	return value == null ? '~' : Math.round(value).toLocaleString()
}

function formatPct(value: number | null | undefined): string {
	return value == null ? '~' : `${value.toFixed(1)}%`
}

function riskPillClass(badge: string | null | undefined): string {
	if (badge === 'Low') return 'border-teal-200 bg-teal-50 text-teal-700'
	if (badge === 'Medium') return 'border-amber-200 bg-amber-50 text-amber-700'
	if (badge === 'High') return 'border-rose-200 bg-rose-50 text-rose-700'
	return 'border-slate-200 bg-slate-50 text-slate-600'
}

function riskPillLabel(badge: string | null | undefined): string {
	if (badge === 'Low') return 'Low risk'
	if (badge === 'Medium') return 'Medium risk'
	if (badge === 'High') return 'High risk'
	return badge ?? 'Review'
}

function firstIndicatorValue(project: SupplyCatalogueProjectCardResponse, key: string): string {
	return project.risk_indicators?.find((indicator) => indicator.key === key)?.value ?? '~'
}

function inventoryLabel(project: SupplyCatalogueProjectCardResponse): string {
	if (project.units_sold != null && project.units_unsold != null) {
		return `${formatInteger(project.units_sold)} / ${formatInteger(project.units_unsold)}`
	}
	if (project.units_unsold != null) return `${formatInteger(project.units_unsold)} unsold`
	return firstIndicatorValue(project, 'sales')
}
</script>

<svelte:head>
	<title>Upcoming Supply - Vitevue</title>
</svelte:head>

<AppFrame stableScrollGutter>
	<PageContainer variant="wide" class="gap-5">
		<section class="overflow-hidden rounded-lg border border-border bg-card shadow-sm">
			<div class="grid min-h-[280px] lg:grid-cols-[1.05fr_0.95fr]">
				<div class="flex flex-col justify-between gap-8 p-5 sm:p-7">
					<div>
						<p class="font-mono text-[11px] uppercase tracking-[0.08em] text-fg-4">
							Upcoming / Supply catalogue
						</p>
						<div class="mt-3 flex flex-wrap items-end gap-3">
							<h1 class="text-3xl font-semibold tracking-normal text-fg-1 sm:text-4xl">
								New launch desk
							</h1>
						</div>
						<p class="mt-3 max-w-2xl text-sm leading-6 text-fg-3">
							{#if selectedDeveloper}
								Review {selectedDeveloper} upcoming projects with project risk overlays,
								delivery timing, sales inventory, and internal monitoring signals.
							{:else}
								Browse active and upcoming supply with developer visuals, brochures, floorplans,
								payment plans, launch timing, and unit ranges.
							{/if}
						</p>
					</div>

					<div class="grid gap-2 sm:grid-cols-3">
						<div class="rounded-md border border-border bg-panel px-3 py-3">
							<p class="font-mono text-[10px] uppercase tracking-[0.08em] text-fg-4">Projects</p>
							<p class="mt-1 text-2xl font-semibold tabular-nums text-fg-1">
									{catalogueSummary?.total?.toLocaleString() ?? '...'}
							</p>
						</div>
						<div class="rounded-md border border-border bg-panel px-3 py-3">
							<p class="font-mono text-[10px] uppercase tracking-[0.08em] text-fg-4">Markets</p>
							<p class="mt-1 text-2xl font-semibold tabular-nums text-fg-1">
									{catalogueSummary?.areas?.length ?? '...'}
							</p>
						</div>
						<div class="rounded-md border border-border bg-panel px-3 py-3">
							<p class="font-mono text-[10px] uppercase tracking-[0.08em] text-fg-4">
								Launch dates
							</p>
							<p class="mt-1 text-2xl font-semibold tabular-nums text-fg-1">
								{launchedProjectCount.toLocaleString()}
							</p>
						</div>
					</div>
				</div>

				<div class="relative min-h-[280px] bg-navy-900">
					<div class="absolute inset-0 bg-[linear-gradient(135deg,#0b1b2b,#183c4a_55%,#0f513f)]"></div>
					{#if heroProject?.cover_image_url}
							<img
								src={heroProject.cover_image_url}
								alt=""
								decoding="async"
								class="absolute inset-0 h-full w-full object-cover"
								onerror={hideBrokenImage}
							/>
						<div class="absolute inset-0 bg-linear-to-t from-black/72 via-black/18 to-transparent"></div>
					{/if}
					{#if heroProject}
						<div class="absolute inset-x-0 bottom-0 p-5 text-white sm:p-7">
							<div class="flex items-end gap-3">
								{#if heroProject.developer_logo_url}
									<img
											src={heroProject.developer_logo_url}
											alt=""
											decoding="async"
											class="h-12 w-12 rounded-md border border-white/30 bg-white object-contain p-1 shadow-md"
											onerror={hideBrokenImage}
										/>
								{/if}
								<div class="min-w-0">
									<p class="text-xs font-medium text-white/72">{heroProject.developer_name}</p>
									<p class="truncate text-xl font-semibold">{heroProject.project_name}</p>
									<p class="mt-1 text-xs text-white/70">{projectLocation(heroProject)}</p>
								</div>
							</div>
						</div>
					{/if}
				</div>
			</div>
		</section>

		{#if selectedDeveloper}
			<section class="grid gap-3 lg:grid-cols-[minmax(0,1.35fr)_minmax(360px,0.65fr)]">
				<div class="rounded-lg border border-border bg-card p-5 shadow-sm">
					<div class="flex flex-wrap items-start justify-between gap-4">
						<div class="min-w-0">
							<p class="font-mono text-[10px] uppercase tracking-[0.08em] text-fg-4">
								Developer / Project risk
							</p>
							<div class="mt-3 flex min-w-0 items-center gap-3">
								{#if heroProject?.developer_logo_url}
									<img
										src={heroProject.developer_logo_url}
										alt=""
										decoding="async"
										class="h-12 w-12 rounded-md border border-border bg-white object-contain p-1"
										onerror={hideBrokenImage}
									/>
								{/if}
								<div class="min-w-0">
									<h2 class="truncate text-xl font-semibold text-fg-1">{selectedDeveloper}</h2>
									<p class="mt-1 text-sm text-fg-4">
										{catalogueSummary?.total?.toLocaleString() ?? '...'} linked projects · {reviewedProjectCount.toLocaleString()} scored
									</p>
								</div>
							</div>
						</div>

						<a href="/developers" class="ui-button h-9 px-3" data-variant="secondary">
							Back to rankings
						</a>
					</div>

					<div class="mt-5 grid gap-2 sm:grid-cols-4">
						<div class="rounded-md border border-border bg-panel px-3 py-3">
							<p class="text-xs text-fg-4">Developer score</p>
							<p class="mt-1 text-2xl font-semibold tabular-nums text-fg-1">
								{formatScore(developerScore)}
							</p>
						</div>
						<div class="rounded-md border border-border bg-panel px-3 py-3">
							<p class="text-xs text-fg-4">Avg project score</p>
							<p class="mt-1 text-2xl font-semibold tabular-nums text-fg-1">
								{formatScore(averageProjectScore)}
							</p>
						</div>
						<div class="rounded-md border border-border bg-panel px-3 py-3">
							<p class="text-xs text-fg-4">Avg absorption</p>
							<p class="mt-1 text-2xl font-semibold tabular-nums text-fg-1">
								{formatPct(averageAbsorption)}
							</p>
							<p class="mt-1 text-[11px] text-fg-4">
								{absorptionRates.length.toLocaleString()} / {projects.length.toLocaleString()} projects
							</p>
						</div>
						<div class="rounded-md border border-border bg-panel px-3 py-3">
							<p class="text-xs text-fg-4">Pending feed fields</p>
							<p class="mt-1 text-2xl font-semibold tabular-nums text-fg-1">~</p>
						</div>
					</div>
				</div>

				<div class="rounded-lg border border-border bg-card p-5 shadow-sm">
					<div class="flex items-center gap-2 text-sm font-semibold text-fg-1">
						<ShieldCheck size={17} strokeWidth={2} />
						Internal risk
					</div>
					<div class="mt-4 space-y-2 text-sm">
						<div class="flex items-center justify-between rounded-md bg-panel px-3 py-2">
							<span class="text-fg-4">Escrow balance</span>
							<span class="font-semibold text-fg-1">~</span>
						</div>
						<div class="flex items-center justify-between rounded-md bg-panel px-3 py-2">
							<span class="text-fg-4">Adequacy ratio</span>
							<span class="font-semibold text-fg-1">~</span>
						</div>
						<div class="flex items-center justify-between rounded-md bg-panel px-3 py-2">
							<span class="text-fg-4">Estimated project IRR</span>
							<span class="font-semibold text-fg-1">~</span>
						</div>
					</div>
				</div>
			</section>
		{/if}

		<section class="space-y-3">
			<div
				class="grid gap-2 md:grid-cols-2 xl:grid-cols-[minmax(260px,1fr)_210px_190px_170px_170px_auto]"
			>
				<label class="relative block">
					<Search
						size={15}
						strokeWidth={2}
						class="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-fg-4"
					/>
					<input
						bind:value={search}
						type="search"
						placeholder="Search projects, developers, areas"
						class="h-10 w-full rounded-md border border-border bg-card pl-9 pr-3 text-sm text-fg-1 outline-none transition-colors placeholder:text-fg-5 focus:border-border-focus"
					/>
				</label>

				<select
					value={selectedDeveloper}
					onchange={(event) => setDeveloperFilter(event.currentTarget.value)}
					class="h-10 rounded-md border border-border bg-card px-3 text-sm text-fg-2 outline-none transition-colors focus:border-border-focus"
					aria-label="Filter by developer"
				>
					<option value="">All developers</option>
					{#if selectedDeveloper && !(catalogueSummary?.developers ?? []).includes(selectedDeveloper)}
						<option value={selectedDeveloper}>{selectedDeveloper}</option>
					{/if}
					{#each catalogueSummary?.developers ?? [] as developer (developer)}
						<option value={developer}>{developer}</option>
					{/each}
				</select>

				<select
					bind:value={selectedArea}
					class="h-10 rounded-md border border-border bg-card px-3 text-sm text-fg-2 outline-none transition-colors focus:border-border-focus"
					aria-label="Filter by area"
				>
					<option value="">All areas</option>
					{#each catalogueSummary?.areas ?? [] as area (area)}
						<option value={area}>{area}</option>
					{/each}
				</select>

				<select
					bind:value={selectedStatus}
					class="h-10 rounded-md border border-border bg-card px-3 text-sm text-fg-2 outline-none transition-colors focus:border-border-focus"
					aria-label="Filter by status"
				>
					<option value="">All status</option>
					{#each catalogueSummary?.statuses ?? [] as status (status)}
						<option value={status}>{status}</option>
					{/each}
				</select>

				<select
					bind:value={selectedSort}
					class="h-10 rounded-md border border-border bg-card px-3 text-sm text-fg-2 outline-none transition-colors focus:border-border-focus"
					aria-label="Sort projects"
				>
					<option value="recommended">Recommended</option>
					<option value="newest">Most recent</option>
					<option value="price_low">Lowest price</option>
					<option value="price_high">Highest price</option>
					<option value="delivery_soon">Soonest delivery</option>
					<option value="delivery_latest">Latest delivery</option>
				</select>

				{#if hasFilters}
					<button
						type="button"
						onclick={clearFilters}
						class="ui-button h-10 px-3 md:justify-self-start xl:justify-self-auto"
						data-variant="secondary"
					>
						<X size={14} strokeWidth={2} />
						Clear
					</button>
				{/if}
			</div>

			{#if catalogueQuery.isPending}
				<div class="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
					{#each Array.from({ length: 12 }) as _, index (index)}
						<div class="h-[380px] animate-pulse rounded-lg border border-border bg-card"></div>
					{/each}
				</div>
			{:else if catalogueQuery.isError}
				<div class="rounded-lg border border-error-bg bg-error-bg p-6 text-sm text-error">
					Supply catalogue failed to load.
				</div>
			{:else if projects.length === 0}
				<div class="rounded-lg border border-border bg-card p-8 text-center">
					<p class="text-sm font-semibold text-fg-1">No matching projects</p>
					<p class="mt-1 text-sm text-fg-3">Try a broader area, status, or search term.</p>
				</div>
			{:else}
					<div class="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
						{#each projects as project (project.project_id)}
						{@const unitTypes = project.unit_types ?? []}
							<a
								href={`/upcoming/${project.project_id}`}
								class="group isolate flex min-h-[370px] cursor-pointer flex-col overflow-hidden rounded-lg border border-border bg-card text-left shadow-sm transition-colors hover:border-border-strong [contain-intrinsic-size:370px] [contain:layout_paint_style] [content-visibility:auto]"
							>
								<div class="relative isolate h-36 shrink-0 overflow-hidden bg-panel">
									<div class="absolute inset-0 z-0 flex items-center justify-center text-fg-5">
										<ImageIcon size={28} strokeWidth={1.8} />
									</div>
									{#if project.cover_image_url}
										<img
											src={project.cover_image_url}
											alt=""
											loading="lazy"
											decoding="async"
											class="relative z-0 h-full w-full object-cover"
											onerror={hideBrokenImage}
										/>
									{/if}
									<div class="absolute left-3 top-3 z-20 rounded-full bg-navy/90 px-2 py-1 text-xs font-semibold text-white shadow-sm">
										{project.sale_status ?? 'Supply'}
									</div>
									<div class="absolute right-3 top-3 z-20 rounded-full border px-2 py-1 text-xs font-semibold shadow-sm {riskPillClass(project.project_risk_badge)}">
										{riskPillLabel(project.project_risk_badge)} · {formatScore(project.project_score)}
									</div>
									{#if project.developer_logo_url}
									<img
										src={project.developer_logo_url}
											alt=""
											loading="lazy"
											decoding="async"
											class="absolute bottom-3 right-3 z-20 h-11 w-11 rounded-md border border-white/70 bg-white object-contain p-1 shadow-sm"
											onerror={hideBrokenImage}
										/>
								{/if}
							</div>

								<div class="flex min-h-0 flex-1 flex-col p-4">
								<div>
									<p class="truncate text-xs font-medium text-fg-4">{project.developer_name}</p>
									<h2 class="mt-1 line-clamp-2 text-base font-semibold leading-5 text-fg-1">
										{project.project_name}
									</h2>
									<div class="mt-2 flex items-center gap-1.5 text-xs text-fg-4">
										<MapPin size={13} strokeWidth={2} />
										<span class="truncate">{projectLocation(project)}</span>
									</div>
								</div>

								<div class="mt-3 flex flex-wrap gap-1.5">
									<span class="inline-flex max-w-full items-center gap-1 rounded-full bg-panel px-2 py-1 text-[11px] text-fg-4">
										Delivery
										<strong class="truncate font-semibold text-fg-1">
											{firstIndicatorValue(project, 'delivery')}
										</strong>
									</span>
									<span class="inline-flex items-center gap-1 rounded-full bg-panel px-2 py-1 text-[11px] text-fg-4">
										Progress
										<strong class="font-semibold text-fg-1">
											{firstIndicatorValue(project, 'progress')}
										</strong>
									</span>
									<span class="inline-flex max-w-full items-center gap-1 rounded-full bg-panel px-2 py-1 text-[11px] text-fg-4">
										Launch
										<strong class="truncate font-semibold text-fg-1">
											{project.launch_date ?? '~'}
										</strong>
									</span>
									<span class="inline-flex max-w-full items-center gap-1 rounded-full bg-panel px-2 py-1 text-[11px] text-fg-4">
										Sold/unsold
										<strong class="truncate font-semibold text-fg-1">
											{inventoryLabel(project)}
										</strong>
									</span>
								</div>

								<div class="mt-auto">
									<div class="mb-3 flex flex-wrap gap-1.5">
										{#each unitTypes.slice(0, 2) as unitType (unitType)}
											<span class="rounded-full bg-info-bg px-2 py-1 text-[11px] font-medium text-info">
												{unitType}
											</span>
										{/each}
										{#if unitTypes.length > 2}
											<span class="rounded-full bg-panel px-2 py-1 text-[11px] font-medium text-fg-4">
												+{unitTypes.length - 2}
											</span>
										{/if}
									</div>
									<div class="flex items-end justify-between gap-3 text-xs">
										<div>
											<p class="text-fg-4">From</p>
											<p class="font-semibold text-fg-1">{formatMoney(project.min_price_aed)}</p>
										</div>
										<span class="text-right text-fg-4">{project.completion_date ?? 'Completion TBD'}</span>
									</div>
								</div>
							</div>
							</a>
							{/each}
						</div>
						<div bind:this={sentinel} class="h-px"></div>
						{#if catalogueQuery.isFetchingNextPage}
							<div class="py-5 text-center text-sm text-fg-4">Loading more projects...</div>
						{/if}
					{/if}
		</section>
	</PageContainer>
</AppFrame>
