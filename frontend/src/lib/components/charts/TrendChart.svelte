<script lang="ts">
import { Chart, registerables } from 'chart.js'
import { onMount } from 'svelte'
import type { TrendPoint } from '$lib/api/analytics'
import { colorTheme } from '$lib/stores/preferences.svelte'

interface Props {
	data: TrendPoint[]
	title?: string
	metric?: 'volume' | 'count' | 'avg_price' | 'avg_sqft'
	height?: number
}

let { data, title = 'Trend', metric = 'volume', height = 300 }: Props = $props()

let canvasElement = $state<HTMLCanvasElement | undefined>()
let chart: Chart | null = null
const resolvedTheme = $derived(colorTheme.resolved)

// Register Chart.js components
Chart.register(...registerables)

// Format currency
function formatCurrency(value: number): string {
	if (value >= 1e9) return `AED ${(value / 1e9).toFixed(1)}B`
	if (value >= 1e6) return `AED ${(value / 1e6).toFixed(1)}M`
	if (value >= 1e3) return `AED ${(value / 1e3).toFixed(1)}K`
	return `AED ${value.toFixed(0)}`
}

// Format number
function formatNumber(value: number): string {
	return value.toLocaleString()
}

// Get metric data from trend points
function getMetricValue(point: TrendPoint): number {
	switch (metric) {
		case 'count':
			return point.count
		case 'avg_price':
			return point.avg_value
		case 'avg_sqft':
			return point.avg_sqft
		default:
			return point.total_value
	}
}

// Get metric label
function getMetricLabel(): string {
	switch (metric) {
		case 'count':
			return 'Transactions'
		case 'avg_price':
			return 'Avg Price'
		case 'avg_sqft':
			return 'Avg Price/sqft'
		default:
			return 'Volume'
	}
}

// Get formatter for metric
function getFormatter() {
	return metric === 'count' ? formatNumber : formatCurrency
}

function createChart() {
	if (!canvasElement || !data || data.length === 0) return

	// Destroy existing chart
	if (chart) {
		chart.destroy()
	}

	const ctx = canvasElement.getContext('2d')
	if (!ctx) return

	const labels = data.map((d) => {
		const date = new Date(d.date)
		return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
	})

	const values = data.map(getMetricValue)
	const formatter = getFormatter()
	const styles = getComputedStyle(document.documentElement)
	const chartLine = styles.getPropertyValue('--color-chart-line').trim() || 'rgb(59, 130, 246)'
	const chartFill =
		styles.getPropertyValue('--color-chart-fill').trim() || 'rgba(59, 130, 246, 0.1)'
	const chartGrid = styles.getPropertyValue('--color-chart-grid').trim() || 'rgba(0, 0, 0, 0.05)'
	const chartMuted = styles.getPropertyValue('--color-chart-muted').trim() || '#9ca3af'
	const foreground = styles.getPropertyValue('--color-fg-1').trim() || '#111827'

	chart = new Chart(ctx, {
		type: 'line',
		data: {
			labels,
			datasets: [
				{
					label: getMetricLabel(),
					data: values,
					borderColor: chartLine,
					backgroundColor: chartFill,
					borderWidth: 2,
					fill: true,
					tension: 0.3,
					pointRadius: 3,
					pointHoverRadius: 5,
					pointBackgroundColor: chartLine,
					pointBorderColor: foreground,
					pointBorderWidth: 2
				}
			]
		},
		options: {
			responsive: true,
			maintainAspectRatio: false,
			plugins: {
				legend: {
					display: false
				},
				title: {
					display: !!title,
					text: title,
					font: {
						size: 16,
						weight: 'bold'
					},
					color: foreground,
					padding: {
						bottom: 20
					}
				},
				tooltip: {
					mode: 'index',
					intersect: false,
					callbacks: {
						label: (context) =>
							`${context.dataset.label}: ${formatter(Number(context.parsed.y ?? 0))}`
					}
				}
			},
			scales: {
				x: {
					grid: {
						display: false
					},
					ticks: {
						color: chartMuted,
						maxRotation: 45,
						minRotation: 0
					}
				},
				y: {
					beginAtZero: true,
					grid: {
						color: chartGrid
					},
					ticks: {
						color: chartMuted,
						callback: (value) => formatter(Number(value))
					}
				}
			},
			interaction: {
				mode: 'nearest',
				axis: 'x',
				intersect: false
			}
		}
	})
}

// Create chart when component mounts and data changes
onMount(() => {
	createChart()
	return () => {
		if (chart) {
			chart.destroy()
		}
	}
})

// Recreate chart when data changes
$effect(() => {
	if (resolvedTheme && data) {
		createChart()
	}
})
</script>

<div class="chart-container" style="height: {height}px;">
	{#if data && data.length > 0}
		<canvas bind:this={canvasElement}></canvas>
	{:else}
		<div class="empty-state">
			<p>No trend data available</p>
		</div>
	{/if}
</div>

<style>
	.chart-container {
		position: relative;
		width: 100%;
		background: var(--color-bg-card, white);
		border-radius: 0.5rem;
		padding: 1rem;
	}

	.empty-state {
		display: flex;
		align-items: center;
		justify-content: center;
		height: 100%;
		color: var(--color-fg-5, #9ca3af);
	}
</style>
