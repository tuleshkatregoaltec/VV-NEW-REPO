<script lang="ts">
import { createQuery } from '@tanstack/svelte-query'
import { Building2 } from 'lucide-svelte'
import type {
	DeveloperRankingMetric,
	DeveloperRankingPeriod,
	DeveloperRankingResponse
} from '$lib/api/supply'
import AppFrame from '$lib/components/layout/AppFrame.svelte'
import PageContainer from '$lib/components/layout/PageContainer.svelte'
import { supplyQueries } from '$lib/queries/supply'

const PERIOD_OPTIONS: { label: string; value: DeveloperRankingPeriod }[] = [
	{ label: 'YTD', value: 'ytd' },
	{ label: '1 year', value: '1y' },
	{ label: '3 years', value: '3y' },
	{ label: '5 years', value: '5y' }
]

const METRIC_OPTIONS: { label: string; value: DeveloperRankingMetric }[] = [
	{ label: 'Proprietary score', value: 'proprietary_score' },
	{ label: 'Units sold', value: 'units_sold' },
	{ label: 'Avg price / sqft', value: 'avg_price_sqft' },
	{ label: 'Sales volume', value: 'sales_volume' },
	{ label: 'Pipeline units', value: 'pipeline_units' },
	{ label: 'Active projects', value: 'active_projects' },
	{ label: 'Completed projects', value: 'completed_projects' },
	{ label: 'Avg completion', value: 'avg_completion_pct' }
]

let period = $state<DeveloperRankingPeriod>('1y')
let metric = $state<DeveloperRankingMetric>('proprietary_score')
let limit = $state(25)

const rankingParams = $derived({ period, metric, limit })
const rankingsQuery = createQuery(() => supplyQueries.developerRankings(rankingParams))
const rankings = $derived(rankingsQuery.data?.rankings ?? [])
const maxRankValue = $derived(Math.max(...rankings.map((item) => rankValue(item)), 1))

function formatInteger(value: number | null | undefined): string {
	return Math.round(Number(value ?? 0)).toLocaleString()
}

function formatMoney(value: number | null | undefined): string {
	const amount = Number(value ?? 0)
	if (!amount) return 'AED 0'
	if (amount >= 1_000_000_000) return `AED ${(amount / 1_000_000_000).toFixed(1)}B`
	if (amount >= 1_000_000) return `AED ${(amount / 1_000_000).toFixed(1)}M`
	if (amount >= 1_000) return `AED ${(amount / 1_000).toFixed(0)}K`
	return `AED ${Math.round(amount).toLocaleString()}`
}

function formatScore(value: number | null | undefined): string {
	return value == null ? 'n/a' : value.toFixed(1)
}

function formatPct(value: number | null | undefined): string {
	return value == null ? 'n/a' : `${value.toFixed(1)}%`
}

function rankValue(item: DeveloperRankingResponse): number {
	const values: Record<DeveloperRankingMetric, number | null | undefined> = {
		proprietary_score: item.proprietary_score,
		units_sold: item.units_sold,
		sales_volume: item.sales_volume_aed,
		avg_price_sqft: item.avg_price_sqft_aed,
		pipeline_units: item.pipeline_units,
		active_projects: item.active_projects,
		completed_projects: item.completed_projects,
		avg_completion_pct: item.avg_completion_pct
	}
	return Number(values[metric] ?? 0)
}

function rankValueLabel(item: DeveloperRankingResponse): string {
	if (metric === 'proprietary_score') return formatScore(item.proprietary_score)
	if (metric === 'sales_volume') return formatMoney(item.sales_volume_aed)
	if (metric === 'avg_price_sqft') return `${formatMoney(item.avg_price_sqft_aed)} / sqft`
	if (metric === 'avg_completion_pct') return formatPct(item.avg_completion_pct)
	return formatInteger(rankValue(item))
}

function riskPillClass(value: string): string {
	if (value === 'Low') return 'border-success/25 bg-success-bg text-success'
	if (value === 'Medium') return 'border-warning/25 bg-warning-bg text-warning'
	if (value === 'High') return 'border-error/25 bg-error-bg text-error'
	return 'border-border bg-panel text-fg-3'
}

function riskPillLabel(value: string): string {
	if (value === 'Low') return 'Low risk'
	if (value === 'Medium') return 'Medium risk'
	if (value === 'High') return 'High risk'
	return value
}

function hideBrokenImage(event: Event) {
	const image = event.currentTarget as HTMLImageElement | null
	image?.remove()
}
</script>

<svelte:head>
	<title>Developer Rankings - Vitevue</title>
</svelte:head>

<AppFrame stableScrollGutter>
	<PageContainer variant="wide" class="gap-5">
		<section>
			<div class="rounded-lg border border-border bg-card p-5 shadow-sm sm:p-6">
				<div class="flex flex-wrap items-start justify-between gap-4">
					<div>
						<p class="font-mono text-[11px] uppercase tracking-[0.08em] text-fg-4">
							Developers / Ranking engine
						</p>
						<h1 class="mt-2 text-2xl font-semibold tracking-normal text-fg-1 sm:text-3xl">
							Developer leaderboard
						</h1>
						<p class="mt-2 max-w-2xl text-sm leading-6 text-fg-3">
							Rank branded developer groups and open their upcoming project pipeline.
						</p>
					</div>

					<div class="grid w-full gap-2 sm:w-auto sm:grid-cols-3">
						<label class="grid gap-1.5">
							<span class="font-mono text-[10px] uppercase tracking-[0.08em] text-fg-4">Period</span>
							<select
								bind:value={period}
								class="h-10 rounded-md border border-border bg-panel px-3 text-sm text-fg-1 outline-none focus:border-border-focus"
							>
								{#each PERIOD_OPTIONS as option (option.value)}
									<option value={option.value}>{option.label}</option>
								{/each}
							</select>
						</label>
						<label class="grid gap-1.5">
							<span class="font-mono text-[10px] uppercase tracking-[0.08em] text-fg-4">Rank by</span>
							<select
								bind:value={metric}
								class="h-10 rounded-md border border-border bg-panel px-3 text-sm text-fg-1 outline-none focus:border-border-focus"
							>
								{#each METRIC_OPTIONS as option (option.value)}
									<option value={option.value}>{option.label}</option>
								{/each}
							</select>
						</label>
						<label class="grid gap-1.5">
							<span class="font-mono text-[10px] uppercase tracking-[0.08em] text-fg-4">Rows</span>
							<select
								bind:value={limit}
								class="h-10 rounded-md border border-border bg-panel px-3 text-sm text-fg-1 outline-none focus:border-border-focus"
							>
								<option value={15}>15</option>
								<option value={25}>25</option>
								<option value={50}>50</option>
							</select>
						</label>
					</div>
				</div>
			</div>
		</section>

		{#if rankingsQuery.isPending}
			<div class="grid gap-3">
				{#each Array.from({ length: 8 }) as _, index (index)}
					<div class="h-24 animate-pulse rounded-lg border border-border bg-card"></div>
				{/each}
			</div>
		{:else if rankingsQuery.isError}
			<div class="rounded-lg border border-error/25 bg-error-bg p-5 text-sm text-error">
				Developer rankings could not be loaded.
			</div>
		{:else}
			<section>
				<div class="overflow-hidden rounded-lg border border-border bg-card shadow-sm">
					<div class="overflow-x-auto">
						<div class="min-w-[900px]">
							<div class="grid grid-cols-[minmax(240px,1fr)_160px_160px_130px_140px] gap-4 border-b border-border bg-panel px-4 py-3 text-xs font-semibold uppercase tracking-[0.06em] text-fg-4">
								<span>Developer</span>
								<span>Score</span>
								<span>Rank metric</span>
								<span>Units sold</span>
								<span>Pipeline</span>
							</div>

							<div class="divide-y divide-border">
								{#each rankings as developer (developer.rank)}
									<a
										href={`/upcoming?developer=${encodeURIComponent(developer.developer_name)}`}
										class="grid grid-cols-[minmax(240px,1fr)_160px_160px_130px_140px] items-center gap-4 px-4 py-3 transition-colors hover:bg-panel/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-border-focus"
										title={`Open ${developer.developer_name} upcoming projects`}
									>
								<div class="flex min-w-0 items-center gap-3">
									<span class="w-7 shrink-0 text-right font-mono text-xs text-fg-5">
										#{developer.rank}
									</span>
									<div class="grid h-10 w-10 shrink-0 place-items-center rounded-md border border-border bg-panel">
										{#if developer.developer_logo_url}
											<img
												src={developer.developer_logo_url}
												alt=""
												decoding="async"
												class="h-full w-full rounded-md object-contain p-1"
												onerror={hideBrokenImage}
											/>
										{:else}
											<Building2 size={16} strokeWidth={2} class="text-fg-4" />
										{/if}
									</div>
									<div class="min-w-0">
										<p class="truncate text-sm font-semibold text-fg-1">{developer.developer_name}</p>
										<p class="mt-0.5 text-xs text-fg-4">
											{developer.total_projects} projects · {developer.completed_projects} completed
										</p>
									</div>
								</div>

								<div>
									<div class="flex items-center gap-2">
										<p class="text-lg font-semibold tabular-nums text-fg-1">
										{formatScore(developer.proprietary_score)}
										</p>
										<span class="rounded-full border px-2 py-0.5 text-[10px] font-semibold {riskPillClass(developer.risk_badge)}">
											{riskPillLabel(developer.risk_badge)}
										</span>
									</div>
									<p class="mt-0.5 text-xs text-fg-4">
										Composite score
									</p>
								</div>

								<div>
									<p class="text-sm font-semibold tabular-nums text-fg-1">{rankValueLabel(developer)}</p>
									<div class="mt-1 h-1.5 rounded-full bg-panel">
										<div
											class="h-full rounded-full bg-info"
											style={`width: ${Math.max(4, (rankValue(developer) / maxRankValue) * 100)}%`}
										></div>
									</div>
								</div>

								<p class="text-sm font-semibold tabular-nums text-fg-1">
									{formatInteger(developer.units_sold)}
								</p>

								<div>
									<p class="text-sm font-semibold tabular-nums text-fg-1">
										{formatInteger(developer.pipeline_units)}
									</p>
								</div>
							</a>
								{/each}
							</div>
						</div>
					</div>
				</div>
			</section>
		{/if}
	</PageContainer>
</AppFrame>
