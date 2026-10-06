<script lang="ts">
import { createQuery } from '@tanstack/svelte-query'
import { analyticsQueries } from '$lib/queries/analytics'

type TimeRange = '30d' | '90d' | '6mo' | '1yr'
type Metric = 'price_sqm' | 'avg_price'

const RANGE_TO_DAYS: Record<TimeRange, number> = {
	'30d': 30,
	'90d': 90,
	'6mo': 180,
	'1yr': 365
}

let selectedRange = $state<TimeRange>('6mo')
let selectedMetric = $state<Metric>('price_sqm')

const trendQuery = createQuery(() => analyticsQueries.marketTrend(RANGE_TO_DAYS[selectedRange]))

const chartData = $derived(trendQuery.data?.data ?? [])

const values = $derived(
	chartData.map((d) => (selectedMetric === 'price_sqm' ? d.avg_price_sqm : d.avg_price))
)
const minValue = $derived(Math.min(...values))
const maxValue = $derived(Math.max(...values))
const valueRange = $derived(maxValue - minValue || 1)

const currentValue = $derived(values[values.length - 1] ?? 0)
const percentChange = $derived(() => {
	const pct =
		selectedMetric === 'price_sqm'
			? trendQuery.data?.avg_price_sqm_change_pct
			: trendQuery.data?.avg_price_change_pct
	return pct != null ? pct.toFixed(1) : null
})
const isPositive = $derived(percentChange() == null || Number(percentChange()) >= 0)

const PERIOD_LABEL: Record<TimeRange, string> = {
	'30d': 'prev 30 days',
	'90d': 'prev 90 days',
	'6mo': 'prev 6 months',
	'1yr': 'prev year'
}

const metricLabel = $derived(
	selectedMetric === 'price_sqm' ? 'Price per sq.m' : 'Average transaction price'
)
const metricUnit = $derived(selectedMetric === 'price_sqm' ? 'AED/sq.m' : 'AED')

const chartWidth = 1000
const chartHeight = 200
const padding = { top: 15, right: 20, bottom: 30, left: 60 }
const innerWidth = chartWidth - padding.left - padding.right
const innerHeight = chartHeight - padding.top - padding.bottom

function generatePath(data: typeof chartData): string {
	if (data.length < 2) return ''
	const points = data.map((point, i) => {
		const x = padding.left + (i / (data.length - 1)) * innerWidth
		const value = selectedMetric === 'price_sqm' ? point.avg_price_sqm : point.avg_price
		const normalizedValue = (value - minValue) / valueRange
		const y = padding.top + (1 - normalizedValue) * innerHeight
		return { x, y }
	})
	let path = `M ${points[0].x} ${points[0].y}`
	for (let i = 1; i < points.length; i++) {
		const prev = points[i - 1]
		const curr = points[i]
		const cp1x = prev.x + (curr.x - prev.x) / 3
		const cp2x = prev.x + ((curr.x - prev.x) * 2) / 3
		path += ` C ${cp1x} ${prev.y}, ${cp2x} ${curr.y}, ${curr.x} ${curr.y}`
	}
	return path
}

const linePath = $derived(generatePath(chartData))
const areaPath = $derived(
	linePath
		? `${linePath} L ${padding.left + innerWidth} ${padding.top + innerHeight} L ${padding.left} ${padding.top + innerHeight} Z`
		: ''
)

const yAxisTicks = $derived([
	{ value: maxValue, y: padding.top },
	{ value: (maxValue + minValue) / 2, y: padding.top + innerHeight / 2 },
	{ value: minValue, y: padding.top + innerHeight }
])

const xAxisTicks = $derived(
	chartData.length > 0
		? [0, 0.25, 0.5, 0.75, 1].map((ratio) => {
				const index = Math.min(Math.floor(ratio * (chartData.length - 1)), chartData.length - 1)
				const point = chartData[index]
				const d = new Date(point.date)
				return {
					label: d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
					x: padding.left + ratio * innerWidth
				}
			})
		: []
)

function formatNumber(num: number): string {
	return new Intl.NumberFormat('en-US').format(Math.round(num))
}
</script>

<!-- Card header -->
<div class="flex flex-col gap-4 mb-[18px] sm:flex-row sm:items-start sm:justify-between">
	<div>
		<h3 class="text-sm font-semibold tracking-normal text-fg-1">
			{metricLabel}
		</h3>
		{#if trendQuery.isLoading}
			<div class="mt-2 h-8 w-36 animate-pulse rounded bg-panel"></div>
		{:else}
			<div class="mt-1 flex items-baseline gap-2">
				<span class="font-display text-4xl font-normal leading-none tracking-normal text-fg-1 tabular-nums">
					{formatNumber(currentValue)}
				</span>
				<span class="text-sm text-fg-4">{metricUnit}</span>
			</div>
			{#if percentChange() != null}
				<p class="mt-1 font-mono text-xs {isPositive ? 'text-trend-up' : 'text-trend-down'}">
					{isPositive ? '▲' : '▼'} {isPositive ? '+' : ''}{percentChange()}% vs {PERIOD_LABEL[selectedRange]}
				</p>
			{/if}
		{/if}
	</div>

	<!-- Controls -->
	<div class="flex gap-2">
		<div class="inline-flex rounded-md bg-panel p-0.5">
			<button
				class="rounded px-3 py-[5px] text-xs font-medium transition-all {selectedMetric === 'price_sqm' ? 'bg-card text-fg-1 shadow-[var(--shadow-xs)]' : 'text-fg-3 hover:text-fg-1'}"
				onclick={() => (selectedMetric = 'price_sqm')}
			>
				Price/sq.m
			</button>
			<button
				class="rounded px-3 py-[5px] text-xs font-medium transition-all {selectedMetric === 'avg_price' ? 'bg-card text-fg-1 shadow-[var(--shadow-xs)]' : 'text-fg-3 hover:text-fg-1'}"
				onclick={() => (selectedMetric = 'avg_price')}
			>
				Avg price
			</button>
		</div>

		<div class="inline-flex rounded-md bg-panel p-0.5">
			{#each [{ label: '30D', value: '30d' }, { label: '90D', value: '90d' }, { label: '6M', value: '6mo' }, { label: '1Y', value: '1yr' }] as range (range.value)}
				<button
					class="rounded px-3 py-[5px] text-xs font-medium transition-all {selectedRange === range.value ? 'bg-card text-fg-1 shadow-[var(--shadow-xs)]' : 'text-fg-3 hover:text-fg-1'}"
					onclick={() => (selectedRange = range.value as TimeRange)}
				>
					{range.label}
				</button>
			{/each}
		</div>
	</div>
</div>

<!-- Chart -->
<div class="w-full overflow-x-auto">
	{#if trendQuery.isLoading}
		<div
			class="w-full min-w-[500px] animate-pulse rounded bg-panel"
			style="height: {chartHeight}px"
		></div>
	{:else if trendQuery.isError || chartData.length === 0}
		<div
			class="flex w-full min-w-[500px] items-center justify-center text-sm text-fg-4"
			style="height: {chartHeight}px"
		>
			No data available for this period
		</div>
	{:else}
		<svg
			class="w-full min-w-[500px]"
			viewBox="0 0 {chartWidth} {chartHeight}"
			preserveAspectRatio="xMidYMid meet"
			xmlns="http://www.w3.org/2000/svg"
		>
			<defs>
				<linearGradient id="areaGradient" x1="0" x2="0" y1="0" y2="1">
					<stop offset="0%" stop-color="var(--color-chart-line)" stop-opacity="0.16" />
					<stop offset="100%" stop-color="var(--color-chart-line)" stop-opacity="0" />
				</linearGradient>
			</defs>

			{#each yAxisTicks as tick (`grid-${tick.value}`)}
				<line
					x1={padding.left}
					y1={tick.y}
					x2={padding.left + innerWidth}
					y2={tick.y}
					stroke="var(--color-chart-grid)"
					stroke-width="1"
					stroke-dasharray="2 3"
				/>
			{/each}

			<line
				x1={padding.left}
				y1={padding.top + innerHeight}
				x2={padding.left + innerWidth}
				y2={padding.top + innerHeight}
				stroke="var(--color-chart-axis)"
				stroke-width="1"
			/>

			<path d={areaPath} fill="url(#areaGradient)" />

			<path
				d={linePath}
				fill="none"
				stroke="var(--color-chart-line)"
				stroke-width="1.75"
				stroke-linecap="round"
				stroke-linejoin="round"
			/>

			{#each yAxisTicks as tick (`label-${tick.value}`)}
				<text
					x={padding.left - 8}
					y={tick.y}
					text-anchor="end"
					dominant-baseline="middle"
					fill="var(--color-chart-muted)"
					font-size="10"
					font-family="ui-monospace, monospace"
				>
					{formatNumber(tick.value)}
				</text>
			{/each}

			{#each xAxisTicks as tick (tick.label)}
				<text
					x={tick.x}
					y={chartHeight - 8}
					text-anchor="middle"
					fill="var(--color-chart-muted)"
					font-size="10"
					font-family="ui-monospace, monospace"
				>
					{tick.label}
				</text>
			{/each}
		</svg>
	{/if}
</div>

<!-- Footer -->
<div class="mt-4 border-t border-border pt-3">
	<p class="font-mono text-[10px] uppercase tracking-[0.06em] text-fg-4">
		Based on {formatNumber(trendQuery.data?.total_transactions ?? 0)} transactions
	</p>
</div>

<style>
	/* Chart/trend tokens are missing from app.css; scoped here so only this chart is affected. */
	svg {
		--color-chart-line: var(--color-navy-900);
		--color-chart-grid: #e2e8f0;
		--color-chart-axis: #cbd5e1;
		--color-chart-muted: #94a3b8;
	}

	:global(:root[data-theme='dark']) svg {
		--color-chart-line: #d9e1ea;
		--color-chart-grid: rgba(148, 163, 184, 0.17);
		--color-chart-axis: rgba(148, 163, 184, 0.32);
	}

	.text-trend-up {
		color: var(--color-success);
	}

	.text-trend-down {
		color: var(--color-error);
	}
</style>
