<script lang="ts">
import { Chart, registerables } from 'chart.js'
import { onMount } from 'svelte'
import type { DimensionBreakdown, RentalDimensionBreakdown } from '$lib/api/analytics'
import { colorTheme } from '$lib/stores/preferences.svelte'

interface Props {
	data: DimensionBreakdown[] | RentalDimensionBreakdown[]
	title?: string
	metric?: 'volume' | 'count'
	height?: number
	maxItems?: number
}

let { data, title = 'Breakdown', metric = 'volume', height = 350, maxItems = 10 }: Props = $props()

let canvasElement = $state<HTMLCanvasElement | undefined>()
let chart: Chart | null = null
const resolvedTheme = $derived(colorTheme.resolved)

Chart.register(...registerables)

function formatCurrency(value: number): string {
	if (value >= 1e9) return `${(value / 1e9).toFixed(1)}B`
	if (value >= 1e6) return `${(value / 1e6).toFixed(1)}M`
	if (value >= 1e3) return `${(value / 1e3).toFixed(1)}K`
	return value.toFixed(0)
}

function formatNumber(value: number): string {
	return value.toLocaleString()
}

function getMetricValue(item: DimensionBreakdown | RentalDimensionBreakdown): number {
	if (metric === 'count') {
		return 'transaction_count' in item ? item.transaction_count : item.contract_count
	}
	return 'total_volume' in item ? item.total_volume : item.total_annual_value
}

function getMetricLabel(): string {
	return metric === 'count' ? 'Count' : 'Volume (AED)'
}

function getFormatter() {
	return metric === 'count' ? formatNumber : formatCurrency
}

function createChart() {
	if (!canvasElement || !data || data.length === 0) return

	if (chart) {
		chart.destroy()
	}

	const ctx = canvasElement.getContext('2d')
	if (!ctx) return

	// Take top N items
	const chartData = data.slice(0, maxItems)
	const labels = chartData.map((d) => d.dimension_value || 'Unknown')
	const values = chartData.map(getMetricValue)
	const formatter = getFormatter()
	const styles = getComputedStyle(document.documentElement)
	const chartLine = styles.getPropertyValue('--color-chart-line').trim() || 'rgb(59, 130, 246)'
	const chartFill =
		styles.getPropertyValue('--color-chart-fill').trim() || 'rgba(59, 130, 246, 0.8)'
	const chartGrid = styles.getPropertyValue('--color-chart-grid').trim() || 'rgba(0, 0, 0, 0.05)'
	const chartMuted = styles.getPropertyValue('--color-chart-muted').trim() || '#9ca3af'
	const foreground = styles.getPropertyValue('--color-fg-1').trim() || '#111827'

	chart = new Chart(ctx, {
		type: 'bar',
		data: {
			labels,
			datasets: [
				{
					label: getMetricLabel(),
					data: values,
					backgroundColor: chartFill,
					borderColor: chartLine,
					borderWidth: 1,
					borderRadius: 4,
					hoverBackgroundColor: chartLine
				}
			]
		},
		options: {
			responsive: true,
			maintainAspectRatio: false,
			indexAxis: 'y', // Horizontal bars
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
					callbacks: {
						label: (context) => {
							const item = chartData[context.dataIndex]
							const value = formatter(Number(context.parsed.x ?? 0))
							const pct = item.pct_of_total ? ` (${item.pct_of_total}%)` : ''
							return `${getMetricLabel()}: ${value}${pct}`
						}
					}
				}
			},
			scales: {
				x: {
					beginAtZero: true,
					grid: {
						color: chartGrid
					},
					ticks: {
						color: chartMuted,
						callback: (value) => formatter(Number(value))
					}
				},
				y: {
					grid: {
						display: false
					},
					ticks: {
						color: chartMuted
					}
				}
			}
		}
	})
}

onMount(() => {
	createChart()
	return () => {
		if (chart) {
			chart.destroy()
		}
	}
})

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
			<p>No breakdown data available</p>
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
