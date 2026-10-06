<script lang="ts">
import {
	BarChart3,
	BedDouble,
	CheckCircle2,
	ExternalLink,
	Home,
	ImageIcon,
	Loader2,
	MapPin,
	Square,
	XCircle
} from 'lucide-svelte'
import { cubicOut } from 'svelte/easing'
import { fade, fly } from 'svelte/transition'
import type { ListingCardResponse } from '$lib/api/generated/hey-api/types.gen'
import type { ChatArtifact } from '$lib/chat/artifacts'
import ChatCustomChartArtifact from './ChatCustomChartArtifact.svelte'
import ChatMarketTrendArtifact from './ChatMarketTrendArtifact.svelte'

let { artifact }: { artifact: ChatArtifact } = $props()

function surfaceLabel(): string {
	if (artifact.status === 'loading')
		return artifact.type === 'listing_results' ? 'Finding matches' : 'Building view'
	if (artifact.status === 'error') return 'Could not load'
	if (artifact.type === 'listing_results') return 'Matches'
	return artifact.type === 'custom_chart' ? 'Chart view' : 'Market view'
}

function statusLabel(): string {
	if (artifact.status === 'loading') return 'Working'
	if (artifact.status === 'error') return 'Issue'
	return 'Ready'
}

function statusClass(): string {
	if (artifact.status === 'loading') return 'text-info'
	if (artifact.status === 'error') return 'text-error'
	return 'text-success'
}

function formatMoney(value: number | null | undefined, period?: string | null): string {
	if (value == null || value <= 0) return 'Price on request'
	let label: string
	if (value >= 1_000_000) label = `AED ${(value / 1_000_000).toFixed(value >= 10_000_000 ? 1 : 2)}M`
	else if (value >= 1_000) label = `AED ${(value / 1_000).toFixed(0)}K`
	else label = `AED ${value.toLocaleString()}`
	if (!period || period === 'sell') return label
	return `${label}/${period.replace('ly', '')}`
}

function formatArea(value: number | null | undefined, unit: string | null | undefined): string {
	if (value == null || value <= 0) return '-'
	return `${Math.round(value).toLocaleString()} ${unit ?? 'sqft'}`
}

function listingLocation(listing: ListingCardResponse): string {
	return [listing.tower_name, listing.subcommunity_name, listing.area_name]
		.filter(Boolean)
		.join(', ')
}

function listingImage(listing: ListingCardResponse): string | null {
	return listing.primary_image_url ?? null
}

function resultSummary(): string {
	if (artifact.type === 'listing_results') {
		const total = artifact.data?.total
		return typeof total === 'number' ? `${total.toLocaleString()} matches` : 'Matching records'
	}
	if (artifact.type === 'custom_chart') {
		const total = artifact.data?.summary?.total_records
		if (typeof total === 'number') return `${total.toLocaleString()} records`
		return `${artifact.data?.points?.length ?? 0} points`
	}
	const transactions = artifact.data?.total_transactions
	return typeof transactions === 'number'
		? `${transactions.toLocaleString()} transactions`
		: 'Market signal'
}
</script>

<section
	class="overflow-hidden rounded-lg border border-border bg-card shadow-sm"
	in:fly={{ y: 8, duration: 180, easing: cubicOut }}
	out:fade={{ duration: 100 }}
>
	<header class="border-b border-border bg-panel px-3 py-2.5">
		<div class="flex items-start justify-between gap-3">
			<div class="flex min-w-0 items-start gap-2.5">
				<div class="grid h-8 w-8 shrink-0 place-items-center rounded-md border border-border bg-card text-fg-3">
					{#if artifact.status === 'loading'}
						<Loader2 size={16} strokeWidth={1.9} class="animate-spin" />
					{:else if artifact.type === 'market_trend' || artifact.type === 'custom_chart'}
						<BarChart3 size={16} strokeWidth={1.9} />
					{:else}
						<Home size={16} strokeWidth={1.9} />
					{/if}
				</div>
				<div class="min-w-0">
					<p class="font-mono text-[10px] font-semibold uppercase tracking-[0.12em] text-fg-4">
						{surfaceLabel()}
					</p>
					<p class="mt-0.5 truncate text-sm font-semibold text-fg-1">{artifact.title}</p>
				</div>
			</div>
			<div class="inline-flex shrink-0 items-center gap-1.5 font-mono text-[10px] font-semibold uppercase tracking-[0.08em] {statusClass()}">
				{#if artifact.status === 'loading'}
					<Loader2 size={13} strokeWidth={2} class="animate-spin" />
				{:else if artifact.status === 'error'}
					<XCircle size={13} strokeWidth={2} />
				{:else}
					<CheckCircle2 size={13} strokeWidth={2} />
				{/if}
				{statusLabel()}
			</div>
		</div>
		<div class="mt-2 flex flex-wrap items-center gap-2 text-xs text-fg-4">
			<span>{resultSummary()}</span>
			{#if artifact.subtitle}
				<span class="text-fg-5">/</span>
				<span class="min-w-0 truncate">{artifact.subtitle}</span>
			{/if}
		</div>
	</header>

	<div class="p-3">
		{#if artifact.status === 'loading'}
			{#if artifact.type === 'market_trend'}
				<div class="space-y-3">
					<div class="grid grid-cols-3 gap-2">
						<div class="h-16 animate-pulse rounded-md bg-elevated"></div>
						<div class="h-16 animate-pulse rounded-md bg-elevated"></div>
						<div class="h-16 animate-pulse rounded-md bg-elevated"></div>
					</div>
					<div class="h-[240px] animate-pulse rounded-md bg-elevated"></div>
				</div>
			{:else}
				<div class="space-y-2">
					{#each [0, 1, 2] as item (item)}
						<div class="grid grid-cols-[104px_minmax(0,1fr)] overflow-hidden rounded-md border border-border bg-card">
							<div class="h-[108px] animate-pulse bg-elevated"></div>
							<div class="space-y-2 p-3">
								<div class="h-4 w-4/5 animate-pulse rounded bg-elevated"></div>
								<div class="h-3 w-3/5 animate-pulse rounded bg-elevated"></div>
								<div class="h-4 w-1/3 animate-pulse rounded bg-elevated"></div>
								<div class="h-3 w-2/3 animate-pulse rounded bg-elevated"></div>
							</div>
						</div>
					{/each}
				</div>
			{/if}
		{:else if artifact.status === 'error'}
			<div class="rounded-md border border-error/20 bg-error-bg p-3 text-sm text-error">
				{artifact.error ?? 'This result could not be loaded.'}
			</div>
		{:else if artifact.type === 'custom_chart'}
			<ChatCustomChartArtifact artifact={artifact} />
		{:else if artifact.type === 'market_trend'}
			<ChatMarketTrendArtifact {artifact} />
		{:else if artifact.type === 'listing_results'}
			<div class="space-y-2">
				<div class="max-h-[560px] space-y-2 overflow-y-auto pr-1">
					{#if !artifact.data?.listings?.length}
						<div class="rounded-md border border-dashed border-border bg-card p-5 text-center">
							<p class="text-sm font-semibold text-fg-1">No matching records</p>
							<p class="mt-1 text-xs leading-5 text-fg-4">Try a broader area, budget, or bedroom range.</p>
						</div>
					{:else}
						{#each artifact.data.listings as listing (listing.listing_id)}
							{@const imageUrl = listingImage(listing)}
							<article class="overflow-hidden rounded-md border border-border bg-card">
								<div class="grid grid-cols-[104px_minmax(0,1fr)] sm:grid-cols-[128px_minmax(0,1fr)]">
									<div class="relative h-full min-h-[112px] bg-elevated">
										{#if imageUrl}
											<img src={imageUrl} alt="" class="h-full w-full object-cover" loading="lazy" />
										{:else}
											<div class="grid h-full place-items-center text-fg-5">
												<ImageIcon size={22} strokeWidth={1.6} />
											</div>
										{/if}
									</div>
									<div class="min-w-0 p-3">
										<div class="flex items-start justify-between gap-2">
											<div class="min-w-0">
												<p class="truncate text-sm font-semibold text-fg-1">{listing.title}</p>
												<p class="mt-1 truncate text-xs text-fg-4">
													{listingLocation(listing) || listing.location_name || 'Dubai'}
												</p>
											</div>
											{#if listing.share_url}
												<a
													href={listing.share_url}
													target="_blank"
													rel="noreferrer"
													class="grid h-7 w-7 shrink-0 place-items-center rounded-md border border-border text-fg-4 transition hover:bg-elevated hover:text-fg-1"
													aria-label="Open record"
													title="Open record"
												>
													<ExternalLink size={14} strokeWidth={1.8} />
												</a>
											{/if}
										</div>
										<p class="mt-2 text-sm font-semibold text-fg-1">
											{formatMoney(listing.price_value, listing.price_period)}
										</p>
										<div class="mt-2 flex flex-wrap items-center gap-2 text-xs text-fg-4">
											<span class="inline-flex items-center gap-1">
												<BedDouble size={13} strokeWidth={1.8} />
												{listing.bedrooms ?? '-'}
											</span>
											<span class="inline-flex items-center gap-1">
												<Square size={12} strokeWidth={1.8} />
												{formatArea(listing.size_value, listing.size_unit)}
											</span>
											{#if listing.area_name}
												<span class="inline-flex min-w-0 items-center gap-1">
													<MapPin size={13} strokeWidth={1.8} />
													<span class="truncate">{listing.area_name}</span>
												</span>
											{/if}
										</div>
									</div>
								</div>
							</article>
						{/each}
					{/if}
				</div>
				<div class="rounded-md border border-border bg-panel p-3 text-xs leading-5 text-fg-3">
					<span class="font-semibold text-fg-2">Source:</span>
					Listings import
					<span class="mx-1 text-fg-5">/</span>
					<span class="font-semibold text-fg-2">Scope:</span>
					current exact matches
				</div>
			</div>
		{/if}
	</div>
</section>
