<script lang="ts">
import type { SalesAnalyticsResponse } from '$lib/api/analytics'
import TrendChart from '$lib/components/charts/TrendChart.svelte'

let { data }: { data: SalesAnalyticsResponse } = $props()

function formatCurrency(value: number): string {
	if (value >= 1_000_000_000) return `AED ${(value / 1_000_000_000).toFixed(1)}B`
	if (value >= 1_000_000) return `AED ${(value / 1_000_000).toFixed(1)}M`
	if (value >= 1_000) return `AED ${(value / 1_000).toFixed(0)}K`
	return `AED ${value.toFixed(0)}`
}

// Calculate stats from trends
const avgPrices = $derived(data.trends.map((t) => t.avg_sqft).filter((p) => p > 0))
const minPrice = $derived(avgPrices.length > 0 ? Math.min(...avgPrices) : 0)
const maxPrice = $derived(avgPrices.length > 0 ? Math.max(...avgPrices) : 0)
const avgPrice = $derived(
	avgPrices.length > 0 ? avgPrices.reduce((a, b) => a + b, 0) / avgPrices.length : 0
)
</script>

<div class="space-y-6">
	<!-- Summary Stats -->
	<div class="grid grid-cols-3 gap-4">
		<div class="rounded-xl border border-navy-pale bg-navy-pale p-4">
			<p class="mb-1 text-sm text-fg-4">Average</p>
			<p class="text-2xl font-bold text-fg-1">{formatCurrency(avgPrice)}</p>
			<p class="mt-1 text-xs text-fg-4">per sq.m</p>
		</div>
		<div class="rounded-xl border border-[rgba(17,122,72,0.2)] bg-success-bg p-4">
			<p class="mb-1 text-sm text-fg-4">Highest</p>
			<p class="text-2xl font-bold text-fg-1">{formatCurrency(maxPrice)}</p>
			<p class="mt-1 text-xs text-fg-4">per sq.m</p>
		</div>
		<div class="rounded-xl border border-[rgba(165,90,19,0.2)] bg-warning-bg p-4">
			<p class="mb-1 text-sm text-fg-4">Lowest</p>
			<p class="text-2xl font-bold text-fg-1">{formatCurrency(minPrice)}</p>
			<p class="mt-1 text-xs text-fg-4">per sq.m</p>
		</div>
	</div>

	<!-- Large Trend Chart -->
	<div>
		<TrendChart
			data={data.trends}
			title="Price per sq.ft Over Time"
			metric="avg_sqft"
			height={450}
		/>
	</div>

	<!-- Additional Info -->
	<div class="rounded-xl border border-border bg-slate-50 p-4">
		<div class="grid grid-cols-2 gap-4 text-sm">
			<div>
				<p class="text-fg-4">Time Period</p>
				<p class="font-semibold text-fg-1">Last {data.timeframe_days} days</p>
			</div>
			<div>
				<p class="text-fg-4">Data Points</p>
				<p class="font-semibold text-fg-1">{data.trends.length} days</p>
			</div>
			<div>
				<p class="text-fg-4">Total Transactions</p>
				<p class="font-semibold text-fg-1">
					{data.summary.transaction_count.toLocaleString()}
				</p>
			</div>
			<div>
				<p class="text-fg-4">Total Volume</p>
				<p class="font-semibold text-fg-1">{formatCurrency(data.summary.total_volume)}</p>
			</div>
		</div>
	</div>
</div>
