<script lang="ts">
import type { TrendPoint } from '$lib/api/analytics'

let { trends }: { trends: TrendPoint[] } = $props()

// Calculate min/max for scaling
const values = $derived(trends.map((t) => t.avg_sqft))
const minValue = $derived(Math.min(...values))
const maxValue = $derived(Math.max(...values))
const valueRange = $derived(maxValue - minValue || 1)

// Calculate percentage change
const firstValue = $derived(trends[0]?.avg_sqft ?? 0)
const lastValue = $derived(trends[trends.length - 1]?.avg_sqft ?? 0)
const percentChange = $derived(
	firstValue ? (((lastValue - firstValue) / firstValue) * 100).toFixed(1) : '0.0'
)
const isPositive = $derived(Number(percentChange) >= 0)

// Generate SVG path for trend line
const chartWidth = 200
const chartHeight = 64
const padding = 4

function generatePath(data: TrendPoint[]): string {
	if (data.length === 0) return ''

	const points = data.map((point, i) => {
		const x = (i / (data.length - 1)) * chartWidth
		const normalizedValue = (point.avg_sqft - minValue) / valueRange
		const y = chartHeight - padding - normalizedValue * (chartHeight - 2 * padding)
		return { x, y }
	})

	// Create smooth curve using cubic bezier
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

const linePath = $derived(generatePath(trends))
const areaPath = $derived(
	linePath ? `${linePath} L ${chartWidth} ${chartHeight} L 0 ${chartHeight} Z` : ''
)
</script>

<div class="mt-4">
	<!-- Percentage change badge -->
	<div class="flex items-center justify-between mb-2">
		<span class="text-sm text-fg-4">Last 30 days</span>
		<div
			class="flex items-center text-sm font-semibold {isPositive
				? 'text-trend-up'
				: 'text-trend-down'}"
		>
			{#if isPositive}
				<svg class="w-4 h-4 mr-1" fill="currentColor" viewBox="0 0 20 20">
					<path
						fill-rule="evenodd"
						d="M5.293 9.707a1 1 0 010-1.414l4-4a1 1 0 011.414 0l4 4a1 1 0 01-1.414 1.414L11 7.414V15a1 1 0 11-2 0V7.414L6.707 9.707a1 1 0 01-1.414 0z"
						clip-rule="evenodd"
					/>
				</svg>
			{:else}
				<svg class="w-4 h-4 mr-1" fill="currentColor" viewBox="0 0 20 20">
					<path
						fill-rule="evenodd"
						d="M14.707 10.293a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 111.414-1.414L9 12.586V5a1 1 0 012 0v7.586l2.293-2.293a1 1 0 011.414 0z"
						clip-rule="evenodd"
					/>
				</svg>
			{/if}
			<span>{percentChange}%</span>
		</div>
	</div>

	<!-- SVG Chart -->
	<div class="h-32 -mx-5 -mb-5 rounded-b-xl overflow-hidden">
		<svg
			class="w-full h-full"
			viewBox="0 0 {chartWidth} {chartHeight}"
			preserveAspectRatio="none"
			xmlns="http://www.w3.org/2000/svg"
		>
			<defs>
				<linearGradient id="trendGradient" x1="0" x2="0" y1="0" y2="1">
					<stop
						offset="0%"
						stop-color={isPositive ? 'var(--color-trend-up)' : 'var(--color-trend-down)'}
						stop-opacity="0.3"
					/>
					<stop
						offset="100%"
						stop-color={isPositive ? 'var(--color-trend-up)' : 'var(--color-trend-down)'}
						stop-opacity="0.05"
					/>
				</linearGradient>
			</defs>

			<!-- Area fill -->
			{#if areaPath}
				<path d={areaPath} fill="url(#trendGradient)" />
			{/if}

			<!-- Trend line -->
			{#if linePath}
				<path
					d={linePath}
					fill="none"
					stroke={isPositive ? 'var(--color-trend-up)' : 'var(--color-trend-down)'}
					stroke-width="2.5"
					stroke-linecap="round"
					stroke-linejoin="round"
					opacity="0.9"
				/>
			{/if}
		</svg>
	</div>
</div>
