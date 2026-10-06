<script lang="ts">
import { createInfiniteQuery, createQuery } from '@tanstack/svelte-query'
import {
	BadgeCheck,
	Building2,
	ChevronRight,
	Clock3,
	ExternalLink,
	Mail,
	Minus,
	Phone,
	RefreshCw,
	Search,
	TrendingDown,
	TrendingUp,
	TriangleAlert,
	X
} from 'lucide-svelte'
import type {
	ListingAssetClass,
	ListingCardResponse,
	ListingDetailResponse,
	ListingMarketPosition,
	ListingMode,
	ListingTrendPoint
} from '$lib/api/listings'
import AppFrame from '$lib/components/layout/AppFrame.svelte'
import PageContainer from '$lib/components/layout/PageContainer.svelte'
import { listingQueries } from '$lib/queries/listings'

const PAGE_SIZE = 40
const FILTER_DEBOUNCE_MS = 250

let mode = $state<ListingMode>('rent')
let assetClass = $state<ListingAssetClass>('residential')
let selectedListingId = $state<string | null>(null)
let search = $state('')
let selectedArea = $state('')
let selectedPropertyType = $state('')
let selectedBedrooms = $state('')
let priceMin = $state('')
let priceMax = $state('')
let debouncedSearch = $state('')
let debouncedPriceMin = $state('')
let debouncedPriceMax = $state('')
let sentinel = $state<HTMLDivElement | undefined>()

const listingFilters = $derived({
	mode,
	asset_class: assetClass,
	search: debouncedSearch || undefined,
	area: selectedArea || undefined,
	property_type: selectedPropertyType || undefined,
	bedrooms: selectedBedrooms || undefined,
	price_min: parsePriceFilter(debouncedPriceMin),
	price_max: parsePriceFilter(debouncedPriceMax)
})

const listingsQuery = createInfiniteQuery(() =>
	listingQueries.listInfinite(listingFilters, PAGE_SIZE)
)
const filtersQuery = createQuery(() => listingQueries.filters({ mode, asset_class: assetClass }))
const analyticsQuery = createQuery(() => listingQueries.analytics(listingFilters))
const detailQuery = createQuery(() => listingQueries.detail(selectedListingId))

const listingSummary = $derived(listingsQuery.data?.pages[0])
const listings = $derived(listingsQuery.data?.pages.flatMap((page) => page.listings) ?? [])
const filters = $derived(filtersQuery.data)
const analytics = $derived(analyticsQuery.data)
const trend = $derived(analytics?.trend ?? [])
const trendChangeValue = $derived(trendChange(trend))
const chartScale = $derived(buildChartScale(trend))
const askingPricePerSqftTrendPath = $derived(
	buildTrendPath(trend, 'median_price_per_sqft_aed', chartScale)
)
const achievedPricePerSqftTrendPath = $derived(
	buildTrendPath(trend, 'median_achieved_price_per_sqft_aed', chartScale)
)
const selectedListing = $derived<ListingDetailResponse | null>(detailQuery.data ?? null)
const selectedCard = $derived(
	listings.find((listing) => listing.listing_id === selectedListingId) ?? null
)
const selectedRecord = $derived(mergeListingRecord(selectedListing, selectedCard))
const hasFilters = $derived(
	Boolean(
		search.trim() ||
			selectedArea ||
			selectedPropertyType ||
			selectedBedrooms ||
			priceMin.trim() ||
			priceMax.trim()
	)
)

$effect(() => {
	if (!sentinel) return
	const scrollRoot = sentinel.closest('.app-scroll-root')
	const observer = new IntersectionObserver(
		(entries) => {
			if (
				entries[0].isIntersecting &&
				listingsQuery.hasNextPage &&
				!listingsQuery.isFetchingNextPage
			) {
				listingsQuery.fetchNextPage()
			}
		},
		{ root: scrollRoot, rootMargin: '900px 0px' }
	)
	observer.observe(sentinel)
	return () => observer.disconnect()
})

$effect(() => {
	if (listings.length === 0) {
		selectedListingId = null
		return
	}
	if (!selectedListingId || !listings.some((item) => item.listing_id === selectedListingId)) {
		selectedListingId = listings[0].listing_id
	}
})

$effect(() => {
	const nextSearch = search.trim()
	const nextPriceMin = priceMin.trim()
	const nextPriceMax = priceMax.trim()
	const timeout = setTimeout(() => {
		debouncedSearch = nextSearch
		debouncedPriceMin = nextPriceMin
		debouncedPriceMax = nextPriceMax
	}, FILTER_DEBOUNCE_MS)
	return () => clearTimeout(timeout)
})

function parsePriceFilter(value: string): number | undefined {
	const normalized = value.trim().replaceAll(',', '')
	if (!normalized) return undefined
	const parsed = Number(normalized)
	return Number.isFinite(parsed) && parsed >= 0 ? parsed : undefined
}

function setMode(nextMode: ListingMode) {
	if (mode === nextMode) return
	mode = nextMode
	selectedListingId = null
	clearFilters()
}

function setAssetClass(nextAssetClass: ListingAssetClass) {
	if (assetClass === nextAssetClass) return
	assetClass = nextAssetClass
	selectedListingId = null
	clearFilters()
}

function clearFilters() {
	search = ''
	selectedArea = ''
	selectedPropertyType = ''
	selectedBedrooms = ''
	priceMin = ''
	priceMax = ''
	debouncedSearch = ''
	debouncedPriceMin = ''
	debouncedPriceMax = ''
}

function text(value: string | null | undefined): string {
	return value?.trim() || '—'
}

function formatMoney(value: number | null | undefined, period?: string | null): string {
	if (value == null || value <= 0) return '—'
	const amount = `AED ${Math.round(value).toLocaleString()}`
	const normalizedPeriod = period?.trim().toLowerCase()
	if (!normalizedPeriod || normalizedPeriod === 'sell') return amount
	return `${amount} / ${normalizedPeriod.replace('yearly', 'year').replace('monthly', 'month')}`
}

function formatMetricMoney(value: number | null | undefined): string {
	if (value == null || value <= 0) return '—'
	if (value >= 1_000_000) return `AED ${(value / 1_000_000).toFixed(2)}M`
	return `AED ${Math.round(value).toLocaleString()}`
}

function formatSize(value: number | null | undefined, unit: string | null | undefined): string {
	if (value == null || value <= 0) return '—'
	return `${Math.round(value).toLocaleString()} ${unit || 'sqft'}`
}

function formatDate(value: string | null | undefined): string {
	if (!value) return '—'
	const parsed = new Date(value)
	if (Number.isNaN(parsed.valueOf())) return '—'
	return new Intl.DateTimeFormat('en-GB', {
		day: '2-digit',
		month: 'short',
		year: 'numeric'
	}).format(parsed)
}

function pricePerSqft(listing: ListingCardResponse | ListingDetailResponse | null): string {
	if (!listing?.price_per_sqft_aed) return '—'
	return `AED ${Math.round(listing.price_per_sqft_aed).toLocaleString()}`
}

function listingAge(value: number | null | undefined): string {
	if (value == null || value < 0) return '—'
	return `${Math.round(value)}d`
}

function marketLabel(position: ListingMarketPosition, delta: number | null | undefined): string {
	if (position === 'insufficient_data' || delta == null) return 'No benchmark'
	const percentage = `${Math.abs(delta * 100).toFixed(1)}%`
	if (position === 'below_market') return `${percentage} below`
	if (position === 'above_market') return `${percentage} above`
	return `Within market · ${percentage}`
}

function marketTone(position: ListingMarketPosition): string {
	if (position === 'below_market') return 'border-success-border bg-success-bg text-success'
	if (position === 'above_market') return 'border-error-border bg-error-bg text-error'
	if (position === 'near_market') return 'border-info-border bg-info-bg text-info'
	return 'border-border bg-panel text-fg-4'
}

function mergeListingRecord(
	detail: ListingDetailResponse | null,
	card: ListingCardResponse | null
): ListingDetailResponse | ListingCardResponse | null {
	if (!detail) return card
	if (!card) return detail
	return {
		...detail,
		asset_class: card.asset_class,
		listing_age_days: card.listing_age_days,
		price_per_sqft_aed: card.price_per_sqft_aed,
		market_median_price_per_sqft_aed: card.market_median_price_per_sqft_aed,
		market_estimate_aed: card.market_estimate_aed,
		market_delta_pct: card.market_delta_pct,
		market_position: card.market_position,
		comparable_count: card.comparable_count,
		benchmark_level: card.benchmark_level,
		urgency_signal: card.urgency_signal,
		urgency_terms: card.urgency_terms
	}
}

interface ChartScale {
	min: number
	max: number
	ticks: number[]
}

function buildTrendPath(
	points: ListingTrendPoint[],
	field: 'median_price_per_sqft_aed' | 'median_achieved_price_per_sqft_aed',
	scale: ChartScale
): string {
	if (points.length < 2 || scale.max <= scale.min) return ''
	let drawing = false
	return points
		.map((point, index) => {
			const value = point[field]
			if (value == null || value <= 0) {
				drawing = false
				return ''
			}
			const x = (index / Math.max(points.length - 1, 1)) * 100
			const y = 30 - ((value - scale.min) / (scale.max - scale.min)) * 26
			const command = drawing ? 'L' : 'M'
			drawing = true
			return `${command} ${x.toFixed(2)} ${y.toFixed(2)}`
		})
		.filter(Boolean)
		.join(' ')
}

function buildChartScale(points: ListingTrendPoint[]): ChartScale {
	const values = points.flatMap((point) =>
		[point.median_price_per_sqft_aed, point.median_achieved_price_per_sqft_aed].filter(
			(value): value is number => value != null && value > 0
		)
	)
	if (values.length === 0) return { min: 0, max: 1, ticks: [1, 0.75, 0.5, 0.25, 0] }
	const rawMin = Math.min(...values)
	const rawMax = Math.max(...values)
	const padding = Math.max((rawMax - rawMin) * 0.12, rawMax * 0.04, 1)
	const min = Math.max(0, rawMin - padding)
	const max = rawMax + padding
	return {
		min,
		max,
		ticks: Array.from({ length: 5 }, (_, index) => max - ((max - min) * index) / 4)
	}
}

function formatAxisValue(value: number): string {
	if (value >= 1000) return `AED ${(value / 1000).toFixed(value >= 10000 ? 0 : 1)}K`
	return `AED ${Math.round(value).toLocaleString()}`
}

function benchmarkDescription(listing: ListingCardResponse | ListingDetailResponse): string {
	if (listing.benchmark_level === 'building_layout')
		return 'Same building, property type, bedrooms, and approximate size'
	if (listing.benchmark_level === 'project_layout')
		return 'Same project, property type, bedrooms, and approximate size'
	return 'Not enough exact peer evidence'
}

function trendChange(points: ListingTrendPoint[]): number | null {
	const values = points
		.map((point) => point.median_price_per_sqft_aed)
		.filter((value): value is number => value != null && value > 0)
	if (values.length < 2) return null
	return (values.at(-1) ?? values[0]) / values[0] - 1
}

function availabilityLabel(listing: ListingCardResponse | ListingDetailResponse): string {
	if (listing.is_available === false) return 'Unavailable'
	if (listing.is_verified) return 'Available · verified'
	return 'Available'
}
</script>

<svelte:head>
	<title>Listings - Vitevue</title>
</svelte:head>

<AppFrame stableScrollGutter>
	<PageContainer variant="wide" class="gap-4 pb-12">
		<header class="flex flex-col gap-4 border-b border-border pb-5 pt-5 lg:flex-row lg:items-end lg:justify-between">
			<div>
				<p class="font-mono text-[10px] uppercase tracking-[0.14em] text-fg-4">Inventory intelligence</p>
				<h1 class="mt-1 text-2xl font-semibold tracking-tight text-fg-1">Listings</h1>
				<p class="mt-1 text-sm text-fg-3">Structured supply, asking-price benchmarks, and listing velocity.</p>
			</div>
			<div class="w-full rounded-xl border border-border bg-panel p-1.5 sm:w-auto sm:min-w-[430px]">
				<nav class="grid grid-cols-2 gap-1" aria-label="Asset class">
					<button
						type="button"
						aria-pressed={assetClass === 'residential'}
						class="rounded-lg border px-4 py-2 text-sm font-semibold transition-colors {assetClass === 'residential' ? 'border-border bg-card text-fg-1 shadow-sm' : 'border-transparent text-fg-3 hover:bg-card hover:text-fg-1'}"
						onclick={() => setAssetClass('residential')}>Residential</button
					>
					<button
						type="button"
						aria-pressed={assetClass === 'commercial'}
						class="rounded-lg border px-4 py-2 text-sm font-semibold transition-colors {assetClass === 'commercial' ? 'border-border bg-card text-fg-1 shadow-sm' : 'border-transparent text-fg-3 hover:bg-card hover:text-fg-1'}"
						onclick={() => setAssetClass('commercial')}>Commercial</button
					>
				</nav>
				<div class="mt-1.5 flex items-center justify-between gap-3 border-t border-border px-2 pt-1.5">
					<span class="font-mono text-[9px] uppercase tracking-[0.1em] text-fg-4">{assetClass} inventory</span>
					<nav class="flex gap-1 rounded-lg bg-card p-1" aria-label={`${assetClass} transaction type`}>
						<button
							type="button"
							aria-pressed={mode === 'rent'}
							class="rounded-md px-3 py-1.5 text-xs font-semibold transition-colors {mode === 'rent' ? 'bg-fg-1 text-app shadow-sm' : 'text-fg-3 hover:bg-panel hover:text-fg-1'}"
							onclick={() => setMode('rent')}>For rent</button
						>
						<button
							type="button"
							aria-pressed={mode === 'sale'}
							class="rounded-md px-3 py-1.5 text-xs font-semibold transition-colors {mode === 'sale' ? 'bg-fg-1 text-app shadow-sm' : 'text-fg-3 hover:bg-panel hover:text-fg-1'}"
							onclick={() => setMode('sale')}>For sale</button
						>
					</nav>
				</div>
			</div>
		</header>

		<section class="grid grid-cols-2 gap-3 lg:grid-cols-3 2xl:grid-cols-6">
			<div class="ui-surface p-4"><p class="font-mono text-[10px] uppercase text-fg-4">Available inventory</p><p class="mt-2 text-2xl font-semibold tabular-nums">{analytics?.total?.toLocaleString() ?? '—'}</p></div>
			<div class="ui-surface p-4"><p class="font-mono text-[10px] uppercase text-fg-4">Median asking price</p><p class="mt-2 text-2xl font-semibold tabular-nums">{formatMetricMoney(analytics?.median_price_aed)}</p><p class="mt-1 text-xs text-fg-4">{mode === 'rent' ? 'Annualized' : 'Current asking'}</p></div>
			<div class="ui-surface p-4"><p class="font-mono text-[10px] uppercase text-fg-4">Median AED / sqft</p><p class="mt-2 text-2xl font-semibold tabular-nums">{analytics?.median_price_per_sqft_aed ? `AED ${Math.round(analytics.median_price_per_sqft_aed).toLocaleString()}` : '—'}</p><p class="mt-1 text-xs text-fg-4">{mode === 'rent' ? 'Per year' : 'Sale basis'}</p></div>
			<div class="ui-surface p-4"><p class="font-mono text-[10px] uppercase text-fg-4">Average age at capture</p><p class="mt-2 text-2xl font-semibold tabular-nums">{analytics?.average_listing_age_days != null ? `${Math.round(analytics.average_listing_age_days)} days` : '—'}</p><p class="mt-1 text-xs text-fg-4">Listed date → scrape date · median {analytics?.median_listing_age_days != null ? `${Math.round(analytics.median_listing_age_days)} days` : '—'}</p></div>
			<div class="ui-surface p-4"><p class="font-mono text-[10px] uppercase text-fg-4">New in 30 days</p><p class="mt-2 text-2xl font-semibold tabular-nums">{analytics?.newly_listed_30d?.toLocaleString() ?? '—'}</p><p class="mt-1 text-xs text-fg-4">At the inventory snapshot</p></div>
			<div class="ui-surface p-4"><p class="font-mono text-[10px] uppercase text-fg-4">Below-market signals</p><p class="mt-2 text-2xl font-semibold tabular-nums text-success">{analytics?.below_market_count?.toLocaleString() ?? '—'}</p><p class="mt-1 text-xs text-fg-4">More than 10% below benchmark</p></div>
		</section>

		<section class="grid gap-3 xl:grid-cols-[minmax(0,1.55fr)_minmax(340px,0.75fr)]">
			<div class="ui-surface p-5">
				<div class="flex flex-wrap items-start justify-between gap-3">
					<div><p class="font-mono text-[10px] uppercase tracking-[0.1em] text-fg-4">Asking versus achieved</p><h2 class="mt-1 text-sm font-semibold">Median AED / sqft by month</h2><p class="mt-1 text-xs text-fg-4">Current listing cohorts compared with registered {mode === 'rent' ? 'lease' : 'sale'} transactions in the same period.</p></div>
					{#if trendChangeValue != null}<span class="inline-flex items-center gap-1 rounded-full border border-border px-2.5 py-1 text-xs font-semibold {trendChangeValue < 0 ? 'text-error' : 'text-success'}">{#if trendChangeValue < 0}<TrendingDown size={13} />{:else}<TrendingUp size={13} />{/if}{Math.abs(trendChangeValue * 100).toFixed(1)}% AED/sqft</span>{/if}
				</div>
				{#if analyticsQuery.isPending}
					<div class="mt-5 h-36 animate-pulse rounded-lg bg-panel"></div>
				{:else if trend.length > 1}
					<div class="mt-4 rounded-lg border border-border bg-panel px-4 pb-3 pt-4">
						<div class="grid grid-cols-[68px_minmax(0,1fr)] gap-3">
							<div class="flex h-36 flex-col justify-between pb-1 pt-1 text-right font-mono text-[9px] tabular-nums text-fg-4">
								{#each chartScale.ticks as tick (tick)}<span>{formatAxisValue(tick)}</span>{/each}
							</div>
							<div class="relative h-36">
								<div class="pointer-events-none absolute inset-0 flex flex-col justify-between py-1">{#each chartScale.ticks as tick (tick)}<i class="block border-t border-border/80"></i>{/each}</div>
								<svg viewBox="0 0 100 34" preserveAspectRatio="none" class="absolute inset-0 h-full w-full overflow-visible" aria-label="Median asking and achieved price per square foot trend">
									<path d={askingPricePerSqftTrendPath} fill="none" class="stroke-info" stroke-width="1.6" vector-effect="non-scaling-stroke" />
									<path d={achievedPricePerSqftTrendPath} fill="none" class="stroke-success" stroke-width="1.6" stroke-dasharray="4 3" vector-effect="non-scaling-stroke" />
								</svg>
							</div>
						</div>
						<div class="ml-[81px] mt-2 flex items-center justify-between font-mono text-[9px] uppercase text-fg-4"><span>{trend[0]?.period}</span><span>{trend.at(-1)?.period}</span></div>
						<div class="mt-3 flex flex-wrap gap-4 text-[11px] text-fg-3"><span class="inline-flex items-center gap-1.5"><i class="h-0.5 w-4 bg-info"></i> Listing asking AED/sqft</span><span class="inline-flex items-center gap-1.5"><i class="h-0.5 w-4 border-t border-dashed border-success"></i> Registered {mode === 'rent' ? 'lease' : 'sale'} AED/sqft</span></div>
						<p class="mt-2 text-[10px] leading-4 text-fg-4">Listing cohorts are grouped by original listed month and may contain survivorship bias; achieved records are completed transactions.</p>
					</div>
				{:else}<div class="mt-5 grid h-36 place-items-center rounded-lg border border-dashed border-border text-xs text-fg-4">Not enough dated listings for a trend.</div>{/if}
			</div>

			<div class="ui-surface p-5">
				<p class="font-mono text-[10px] uppercase tracking-[0.1em] text-fg-4">Market positioning</p><h2 class="mt-1 text-sm font-semibold">Exact peer asking benchmark</h2><p class="mt-1 text-xs text-fg-4">Same building or landed project, property type, bedrooms, and approximate size.</p>
				<div class="mt-5 space-y-4">
					<div><div class="flex items-center justify-between text-xs"><span class="inline-flex items-center gap-2 font-medium"><TrendingDown size={14} class="text-success" /> Below market</span><strong class="tabular-nums">{analytics?.below_market_count?.toLocaleString() ?? '—'}</strong></div><div class="mt-2 h-1.5 overflow-hidden rounded-full bg-panel"><div class="h-full bg-success" style={`width: ${analytics?.benchmarked_count ? Math.min(100, (analytics.below_market_count / analytics.benchmarked_count) * 100) : 0}%`}></div></div></div>
					<div><div class="flex items-center justify-between text-xs"><span class="inline-flex items-center gap-2 font-medium"><Minus size={14} class="text-info" /> Within ±10%</span><strong class="tabular-nums">{analytics?.near_market_count?.toLocaleString() ?? '—'}</strong></div><div class="mt-2 h-1.5 overflow-hidden rounded-full bg-panel"><div class="h-full bg-info" style={`width: ${analytics?.benchmarked_count ? Math.min(100, (analytics.near_market_count / analytics.benchmarked_count) * 100) : 0}%`}></div></div></div>
					<div><div class="flex items-center justify-between text-xs"><span class="inline-flex items-center gap-2 font-medium"><TrendingUp size={14} class="text-error" /> Above market</span><strong class="tabular-nums">{analytics?.above_market_count?.toLocaleString() ?? '—'}</strong></div><div class="mt-2 h-1.5 overflow-hidden rounded-full bg-panel"><div class="h-full bg-error" style={`width: ${analytics?.benchmarked_count ? Math.min(100, (analytics.above_market_count / analytics.benchmarked_count) * 100) : 0}%`}></div></div></div>
				</div>
				<p class="mt-5 border-t border-border pt-3 text-[10px] leading-4 text-fg-4">Indicative peer asking-price signal, not a formal valuation. Implausible sizes are excluded and at least five matching records are required.</p>
			</div>
		</section>

		<section class="ui-surface p-3">
			<div class="grid gap-2 lg:grid-cols-4 xl:grid-cols-7">
				<label class="relative block">
					<Search size={15} class="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-fg-4" />
					<input bind:value={search} type="search" placeholder="Building, project, reference, agent" class="ui-field h-10 w-full pl-9 pr-3 text-sm" />
				</label>
				<select bind:value={selectedArea} class="ui-field h-10 px-3 text-sm" aria-label="Area or master project"><option value="">All areas / masters</option>{#each filters?.areas ?? [] as area (area)}<option value={area}>{area}</option>{/each}</select>
				<select bind:value={selectedPropertyType} class="ui-field h-10 px-3 text-sm" aria-label="Property type"><option value="">All property types</option>{#each filters?.property_types ?? [] as propertyType (propertyType)}<option value={propertyType}>{propertyType}</option>{/each}</select>
				{#if assetClass === 'residential'}<select bind:value={selectedBedrooms} class="ui-field h-10 px-3 text-sm" aria-label="Bedrooms"><option value="">All beds</option>{#each filters?.bedrooms ?? [] as bedroom (bedroom)}<option value={bedroom}>{bedroom === 'studio' ? 'Studio' : `${bedroom} bed`}</option>{/each}</select>{/if}
				<input bind:value={priceMin} type="text" inputmode="numeric" placeholder="Min price" class="ui-field h-10 px-3 text-sm" aria-label="Minimum price" />
				<input bind:value={priceMax} type="text" inputmode="numeric" placeholder="Max price" class="ui-field h-10 px-3 text-sm" aria-label="Maximum price" />
				{#if hasFilters}<button type="button" onclick={clearFilters} class="ui-button h-10 px-3" data-variant="secondary"><X size={14} /> Clear</button>{/if}
			</div>
		</section>

		<div class="grid min-w-0 gap-4 xl:grid-cols-[minmax(0,1fr)_390px]">
			<section class="ui-surface min-w-0 overflow-hidden">
				<header class="flex items-center justify-between border-b border-border px-4 py-3"><div><h2 class="text-sm font-semibold">{assetClass === 'commercial' ? 'Commercial' : 'Residential'} {mode === 'rent' ? 'rental' : 'sales'} inventory</h2><p class="mt-0.5 text-xs text-fg-4">{listingSummary?.total?.toLocaleString() ?? '—'} standardized records</p></div><button type="button" class="ui-button" data-variant="ghost" data-size="icon" aria-label="Refresh listings" onclick={() => { listingsQuery.refetch(); filtersQuery.refetch(); analyticsQuery.refetch() }}><RefreshCw size={14} class={listingsQuery.isFetching && !listingsQuery.isFetchingNextPage ? 'animate-spin' : ''} /></button></header>

				{#if listingsQuery.isPending}
					<div class="space-y-px bg-border">{#each Array.from({ length: 10 }) as _, index (index)}<div class="h-16 animate-pulse bg-card"></div>{/each}</div>
				{:else if listingsQuery.isError}
					<div class="p-8 text-center"><p class="text-sm font-semibold text-error">Listings failed to load</p><button type="button" class="ui-button mt-4" data-variant="secondary" data-size="sm" onclick={() => listingsQuery.refetch()}><RefreshCw size={13} /> Try again</button></div>
				{:else if listings.length === 0}
					<div class="p-10 text-center"><p class="text-sm font-semibold">No matching inventory</p><p class="mt-1 text-xs text-fg-4">Broaden the area, property type, bedroom, or price filters.</p></div>
				{:else}
					<div class="overflow-x-auto">
						<table class="w-full min-w-[1380px] border-collapse text-left">
							<thead class="sticky top-0 z-10 bg-panel"><tr class="border-b border-border font-mono text-[9px] uppercase tracking-[0.08em] text-fg-4"><th class="px-4 py-3 font-medium">Price</th><th class="px-3 py-3 font-medium">Market position</th><th class="px-3 py-3 font-medium">Area / master project</th><th class="px-3 py-3 font-medium">Project / phase</th><th class="px-3 py-3 font-medium">Building</th><th class="px-3 py-3 font-medium">Type</th><th class="px-3 py-3 text-right font-medium">Beds</th><th class="px-3 py-3 text-right font-medium">Baths</th><th class="px-3 py-3 text-right font-medium">Size</th><th class="px-3 py-3 text-right font-medium">AED / sqft</th><th class="px-3 py-3 text-right font-medium">Age at capture</th><th class="w-10 px-3 py-3"><span class="sr-only">Open</span></th></tr></thead>
							<tbody class="divide-y divide-border">
								{#each listings as listing (listing.listing_id)}
									<tr class="transition-colors {selectedListingId === listing.listing_id ? 'bg-info-bg' : 'bg-card hover:bg-panel'}">
										<td class="whitespace-nowrap px-4 py-3"><p class="text-sm font-semibold tabular-nums text-fg-1">{formatMoney(listing.price_value, listing.price_period)}</p>{#if listing.is_verified}<p class="mt-1 inline-flex items-center gap-1 text-[9px] font-semibold uppercase text-success"><BadgeCheck size={11} /> Verified</p>{/if}</td>
									<td class="whitespace-nowrap px-3 py-3"><span class="inline-flex rounded-full border px-2 py-1 text-[10px] font-semibold {marketTone(listing.market_position)}">{marketLabel(listing.market_position, listing.market_delta_pct)}</span><p class="mt-1 text-[9px] text-fg-4">{listing.comparable_count ? `${listing.comparable_count.toLocaleString()} exact peers` : 'Insufficient exact peers'}</p>{#if mode === 'sale' && listing.urgency_signal === 'explicit_urgency'}<p class="mt-1 inline-flex items-center gap-1 text-[9px] font-semibold text-warning"><TriangleAlert size={10} /> Seller urgency language</p>{/if}</td>
										<td class="max-w-48 px-3 py-3 text-xs font-medium text-fg-2"><span class="line-clamp-2">{text(listing.area_name)}</span></td>
										<td class="max-w-44 px-3 py-3 text-xs text-fg-3"><span class="line-clamp-2">{text(listing.subcommunity_name)}</span></td>
										<td class="max-w-44 px-3 py-3 text-xs font-semibold text-fg-1"><span class="line-clamp-2">{text(listing.tower_name)}</span></td>
										<td class="whitespace-nowrap px-3 py-3 text-xs text-fg-3">{text(listing.property_type)}</td>
										<td class="px-3 py-3 text-right text-xs tabular-nums text-fg-2">{text(listing.bedrooms)}</td>
										<td class="px-3 py-3 text-right text-xs tabular-nums text-fg-2">{text(listing.bathrooms)}</td>
										<td class="whitespace-nowrap px-3 py-3 text-right text-xs tabular-nums text-fg-2">{formatSize(listing.size_value, listing.size_unit)}</td>
										<td class="whitespace-nowrap px-3 py-3 text-right text-xs tabular-nums text-fg-2">{pricePerSqft(listing)}</td>
										<td class="whitespace-nowrap px-3 py-3 text-right text-xs text-fg-4"><span class="inline-flex items-center gap-1"><Clock3 size={12} /> {listingAge(listing.listing_age_days)}</span><p class="mt-1 text-[9px]">{formatDate(listing.listed_date)}</p></td>
										<td class="px-3 py-3"><button type="button" class="ui-button" data-variant="ghost" data-size="icon" aria-label={`Open ${listing.tower_name || listing.reference || 'listing'}`} onclick={() => (selectedListingId = listing.listing_id)}><ChevronRight size={14} /></button></td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
					<div bind:this={sentinel} class="h-px"></div>
					{#if listingsQuery.isFetchingNextPage}<div class="border-t border-border py-4 text-center text-xs text-fg-4">Loading more inventory…</div>{/if}
				{/if}
			</section>

			<aside class="ui-surface overflow-hidden xl:sticky xl:top-5 xl:max-h-[calc(100dvh-6rem)] xl:overflow-y-auto">
				{#if !selectedRecord}
					<div class="grid min-h-80 place-items-center p-8 text-center"><div><Building2 class="mx-auto text-fg-4" size={24} /><p class="mt-3 text-sm font-semibold">Select an inventory record</p></div></div>
				{:else}
					<header class="border-b border-border p-5"><div class="flex items-start justify-between gap-3"><div><p class="font-mono text-[9px] uppercase tracking-[0.1em] text-fg-4">{selectedRecord.asset_class} · {mode === 'rent' ? 'Rental record' : 'Sales record'} · {text(selectedRecord.reference)}</p><h2 class="mt-2 text-xl font-semibold leading-6">{selectedRecord.tower_name ?? selectedRecord.subcommunity_name ?? selectedRecord.area_name ?? 'Location not stated'}</h2><p class="mt-1 text-xs text-fg-4">{[selectedRecord.area_name, selectedRecord.subcommunity_name, selectedRecord.tower_name].filter(Boolean).join(' · ') || 'Location not stated'}</p></div>{#if selectedRecord.is_verified}<span class="inline-flex shrink-0 items-center gap-1 rounded-full border border-success-border bg-success-bg px-2 py-1 text-[9px] font-semibold uppercase text-success"><BadgeCheck size={12} /> Verified</span>{/if}</div></header>

					<div class="space-y-5 p-5">
						<section><p class="font-mono text-[9px] uppercase tracking-[0.1em] text-fg-4">Asking price</p><p class="mt-1 text-2xl font-semibold tabular-nums">{formatMoney(selectedRecord.price_value, selectedRecord.price_period)}</p><p class="mt-1 text-xs text-fg-4">{pricePerSqft(selectedRecord)} per sqft {mode === 'rent' ? 'annualized' : ''}</p></section>
						{#if mode === 'sale' && selectedRecord.urgency_signal !== 'none'}<section class="rounded-lg border border-warning-border bg-warning-bg p-3 text-warning"><p class="inline-flex items-center gap-1.5 text-xs font-semibold"><TriangleAlert size={14} /> {selectedRecord.urgency_signal === 'explicit_urgency' ? 'Possible seller urgency language' : 'Promotional value language'}</p><p class="mt-1 text-[10px] leading-4 opacity-80">Matched wording: {selectedRecord.urgency_terms.join(', ')}. Treat this as an outreach clue, not proof of distress.</p></section>{/if}

						<section class="rounded-lg border p-4 {marketTone(selectedRecord.market_position)}">
							<div class="flex items-start justify-between gap-3"><div><p class="font-mono text-[9px] uppercase tracking-[0.1em] opacity-70">Market benchmark</p><p class="mt-1 text-base font-semibold">{marketLabel(selectedRecord.market_position, selectedRecord.market_delta_pct)}</p></div>{#if selectedRecord.market_position === 'below_market'}<TrendingDown size={20} />{:else if selectedRecord.market_position === 'above_market'}<TrendingUp size={20} />{:else}<Minus size={20} />{/if}</div>
							<div class="mt-3 grid grid-cols-2 gap-3 border-t border-current/10 pt-3 text-xs"><div><p class="opacity-65">Indicative value</p><p class="mt-1 font-semibold tabular-nums">{formatMetricMoney(selectedRecord.market_estimate_aed)}</p></div><div><p class="opacity-65">Comparable median</p><p class="mt-1 font-semibold tabular-nums">{selectedRecord.market_median_price_per_sqft_aed ? `AED ${Math.round(selectedRecord.market_median_price_per_sqft_aed).toLocaleString()} / sqft` : '—'}</p></div></div>
							<p class="mt-3 text-[10px] opacity-65">{selectedRecord.comparable_count.toLocaleString()} peer listings · {benchmarkDescription(selectedRecord)}</p>
						</section>

						<section><h3 class="text-xs font-semibold uppercase tracking-[0.08em] text-fg-3">Location hierarchy</h3><dl class="mt-2 divide-y divide-border rounded-lg border border-border bg-panel text-xs"><div class="grid grid-cols-[130px_1fr] gap-3 px-3 py-2.5"><dt class="text-fg-4">Area / master project</dt><dd class="font-semibold text-fg-1">{text(selectedRecord.area_name)}</dd></div><div class="grid grid-cols-[130px_1fr] gap-3 px-3 py-2.5"><dt class="text-fg-4">Project / phase</dt><dd class="font-semibold text-fg-1">{text(selectedRecord.subcommunity_name)}</dd></div>{#if selectedRecord.tower_name}<div class="grid grid-cols-[130px_1fr] gap-3 px-3 py-2.5"><dt class="text-fg-4">Building</dt><dd class="font-semibold text-fg-1">{selectedRecord.tower_name}</dd></div>{/if}<div class="grid grid-cols-[130px_1fr] gap-3 px-3 py-2.5"><dt class="text-fg-4">City</dt><dd class="font-semibold text-fg-1">{text(selectedRecord.city_name)}</dd></div></dl></section>

						<section><h3 class="text-xs font-semibold uppercase tracking-[0.08em] text-fg-3">Property data</h3><dl class="mt-2 grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-border bg-border text-xs"><div class="bg-panel p-3"><dt class="text-fg-4">Property type</dt><dd class="mt-1 font-semibold">{text(selectedRecord.property_type)}</dd></div><div class="bg-panel p-3"><dt class="text-fg-4">Size</dt><dd class="mt-1 font-semibold tabular-nums">{formatSize(selectedRecord.size_value, selectedRecord.size_unit)}</dd></div><div class="bg-panel p-3"><dt class="text-fg-4">Bedrooms</dt><dd class="mt-1 font-semibold tabular-nums">{text(selectedRecord.bedrooms)}</dd></div><div class="bg-panel p-3"><dt class="text-fg-4">Bathrooms</dt><dd class="mt-1 font-semibold tabular-nums">{text(selectedRecord.bathrooms)}</dd></div>{#if selectedListing}<div class="bg-panel p-3"><dt class="text-fg-4">Furnished</dt><dd class="mt-1 font-semibold">{text(selectedListing.furnished)}</dd></div><div class="bg-panel p-3"><dt class="text-fg-4">Completion</dt><dd class="mt-1 font-semibold">{text(selectedListing.completion_status)}</dd></div>{/if}</dl></section>

						<section><h3 class="text-xs font-semibold uppercase tracking-[0.08em] text-fg-3">Listing data</h3><dl class="mt-2 divide-y divide-border rounded-lg border border-border text-xs"><div class="flex items-center justify-between gap-3 px-3 py-2.5"><dt class="text-fg-4">Status</dt><dd class="font-semibold">{availabilityLabel(selectedRecord)}</dd></div><div class="flex items-center justify-between gap-3 px-3 py-2.5"><dt class="text-fg-4">Listed date</dt><dd class="font-semibold">{formatDate(selectedRecord.listed_date)}</dd></div><div class="flex items-center justify-between gap-3 px-3 py-2.5"><dt class="text-fg-4">Age when captured</dt><dd class="font-semibold">{listingAge(selectedRecord.listing_age_days)}</dd></div><div class="flex items-center justify-between gap-3 px-3 py-2.5"><dt class="text-fg-4">Reference</dt><dd class="max-w-52 truncate font-mono text-[10px] font-semibold">{text(selectedRecord.reference)}</dd></div>{#if selectedListing}<div class="flex items-center justify-between gap-3 px-3 py-2.5"><dt class="text-fg-4">RERA</dt><dd class="max-w-52 truncate font-semibold">{text(selectedListing.rera)}</dd></div>{#if mode === 'rent'}<div class="flex items-center justify-between gap-3 px-3 py-2.5"><dt class="text-fg-4">Cheques</dt><dd class="font-semibold">{selectedListing.number_of_cheques ?? '—'}</dd></div>{/if}{/if}</dl><p class="mt-2 text-[10px] leading-4 text-fg-4">Age is measured from the source-listed date to the date this record was scraped. It is not a live count to today.</p></section>

						{#if selectedListing}
							<section><h3 class="text-xs font-semibold uppercase tracking-[0.08em] text-fg-3">Listing contact</h3><div class="mt-2 rounded-lg border border-border p-3"><p class="text-sm font-semibold">{selectedListing.agent?.name ?? selectedListing.broker?.name ?? 'Contact not stated'}</p><p class="mt-1 text-xs text-fg-4">{selectedListing.broker?.name ?? 'Broker not stated'}</p><div class="mt-3 flex flex-wrap gap-2">{#if selectedListing.share_url}<a href={selectedListing.share_url} target="_blank" rel="noreferrer" class="ui-button" data-variant="primary" data-size="sm"><ExternalLink size={13} /> Source record</a>{/if}{#if selectedListing.agent?.phone}<a href={`tel:${selectedListing.agent.phone}`} class="ui-button" data-variant="secondary" data-size="sm"><Phone size={13} /> Call</a>{/if}{#if selectedListing.agent?.email}<a href={`mailto:${selectedListing.agent.email}`} class="ui-button" data-variant="secondary" data-size="sm"><Mail size={13} /> Email</a>{/if}</div></div></section>
						{/if}

						{#if detailQuery.isFetching}<p class="text-center text-xs text-fg-4">Loading complete record…</p>{/if}
					</div>
				{/if}
			</aside>
		</div>
	</PageContainer>
</AppFrame>
