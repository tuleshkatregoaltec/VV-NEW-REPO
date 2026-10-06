<script lang="ts">
import { Chart, registerables } from 'chart.js'
import { Download } from 'lucide-svelte'
import { onMount } from 'svelte'
import type { CustomChartArtifact, CustomChartPoint } from '$lib/chat/artifacts'
import { colorTheme } from '$lib/stores/preferences.svelte'
import { getChartTheme } from '$lib/utils/chartTheme'

Chart.register(...registerables)

let { artifact }: { artifact: CustomChartArtifact } = $props()

let canvas = $state<HTMLCanvasElement | undefined>()
let chart: Chart | null = null
const resolvedTheme = $derived(colorTheme.resolved)
const points = $derived(artifact.data?.points ?? [])
const series = $derived((artifact.data?.series ?? []).filter((item) => item.points?.length))
const chartPoints = $derived(series.length ? series.flatMap((item) => item.points ?? []) : points)
const pointSignature = $derived(
	series.length
		? series
				.map(
					(item) =>
						`${item.label}:${item.points.map((point) => `${point.label}:${point.value}`).join('|')}`
				)
				.join('||')
		: points.map((point) => `${point.label}:${point.value}`).join('|')
)

function formatValue(value: number | null | undefined): string {
	const amount = Number(value ?? 0)
	const metric = artifact.data?.metric ?? ''
	if (metric.includes('yield') || metric.includes('completion')) return `${amount.toFixed(1)}%`
	if (
		metric.includes('price') ||
		metric.includes('value') ||
		metric.includes('volume') ||
		metric.includes('rent')
	) {
		if (Math.abs(amount) >= 1_000_000_000) return `AED ${(amount / 1_000_000_000).toFixed(1)}B`
		if (Math.abs(amount) >= 1_000_000) return `AED ${(amount / 1_000_000).toFixed(1)}M`
		if (Math.abs(amount) >= 1_000) return `AED ${(amount / 1_000).toFixed(0)}K`
		return `AED ${Math.round(amount).toLocaleString()}`
	}
	return Math.round(amount).toLocaleString()
}

function formatNumber(value: number | null | undefined): string {
	return Math.round(Number(value ?? 0)).toLocaleString()
}

function pointKey(point: CustomChartPoint): string {
	return point.date || point.label
}

function displayLabelFromKey(label: string): string {
	if (/^\d{4}-\d{2}-\d{2}/.test(label)) {
		return new Date(label).toLocaleDateString(undefined, { month: 'short', year: '2-digit' })
	}
	return label
}

function chartLabelKeys(): string[] {
	const labels: string[] = []
	const seen = new Set<string>()
	for (const point of chartPoints) {
		const label = pointKey(point)
		if (!seen.has(label)) {
			seen.add(label)
			labels.push(label)
		}
	}
	return labels
}

function csvCell(value: string | number | null | undefined): string {
	const text = String(value ?? '')
	return /[",\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text
}

function csvHref(): string {
	const rows = series.length
		? [
				[
					'Series',
					artifact.data?.dimension_label ?? 'Label',
					artifact.data?.metric_label ?? 'Value',
					'Records'
				],
				...series.flatMap((item) =>
					item.points.map((point) => [
						item.label,
						point.label,
						point.value,
						point.record_count ?? ''
					])
				)
			]
		: [
				[
					artifact.data?.dimension_label ?? 'Label',
					artifact.data?.metric_label ?? 'Value',
					'Records'
				],
				...points.map((point) => [point.label, point.value, point.record_count ?? ''])
			]
	const csv = rows.map((row) => row.map(csvCell).join(',')).join('\n')
	return `data:text/csv;charset=utf-8,${encodeURIComponent(csv)}`
}

function csvFilename(): string {
	const name = `${artifact.title}-${artifact.data?.dimension ?? 'chart'}`
		.toLowerCase()
		.replace(/[^a-z0-9]+/g, '-')
		.replace(/(^-|-$)/g, '')
	return `${name || 'vitevue-chart'}.csv`
}

function pngFilename(): string {
	return csvFilename().replace(/\.csv$/, '.png')
}

function downloadPng() {
	if (!chart) return
	const link = document.createElement('a')
	link.href = chart.toBase64Image('image/png', 1)
	link.download = pngFilename()
	link.click()
}

function periodLabel(): string | null {
	const start = artifact.data?.summary?.period_start
	const end = artifact.data?.summary?.period_end
	return start && end ? `${start} to ${end}` : null
}

function rankLabel(): string {
	if (artifact.data?.chart_type === 'line') return 'Latest'
	return artifact.data?.sort_direction === 'asc' ? 'Lowest' : 'Top'
}

function createChart() {
	if (!canvas || chartPoints.length === 0) return
	chart?.destroy()

	const context = canvas.getContext('2d')
	if (!context) return

	const theme = getChartTheme()
	const requestedType = artifact.data?.chart_type ?? 'horizontal_bar'
	const chartType = series.length && requestedType === 'doughnut' ? 'bar' : requestedType
	const tooltipMode = chartType === 'line' ? 'index' : 'nearest'
	const tooltipIntersect = chartType !== 'line'
	const labelKeys = chartLabelKeys()
	const labels = labelKeys.map(displayLabelFromKey)
	const values = points.map((point) => point.value)
	const palette = [theme.line, theme.lineAlt, theme.lineTertiary, '#6f8ea6', '#b98f5a', '#6c7a89']

	const datasets = series.length
		? series.map((item, index) => {
				const color = palette[index % palette.length]
				const pointByLabel = new Map(item.points.map((point) => [pointKey(point), point]))
				const data = labelKeys.map((label) => pointByLabel.get(label)?.value ?? 0)
				return chartType === 'line'
					? {
							label: item.label,
							data,
							borderColor: color,
							backgroundColor: color,
							borderWidth: 2,
							fill: false,
							tension: 0.35,
							pointRadius: 2,
							pointHoverRadius: 5,
							pointBackgroundColor: color,
							pointBorderColor: theme.panel,
							pointBorderWidth: 2
						}
					: {
							label: item.label,
							data,
							backgroundColor: color,
							borderColor: color,
							borderWidth: 1,
							borderRadius: 4,
							hoverBackgroundColor: color
						}
			})
		: [
				chartType === 'line'
					? {
							label: artifact.data?.metric_label ?? artifact.title,
							data: values,
							borderColor: theme.line,
							backgroundColor: theme.fill,
							borderWidth: 2,
							fill: true,
							tension: 0.35,
							pointRadius: 2,
							pointHoverRadius: 5,
							pointBackgroundColor: theme.line,
							pointBorderColor: theme.panel,
							pointBorderWidth: 2
						}
					: chartType === 'doughnut'
						? {
								label: artifact.data?.metric_label ?? artifact.title,
								data: values,
								backgroundColor: values.map((_, index) => palette[index % palette.length]),
								borderColor: theme.panel,
								borderWidth: 2,
								hoverOffset: 4
							}
						: {
								label: artifact.data?.metric_label ?? artifact.title,
								data: values,
								backgroundColor: theme.softFill,
								borderColor: theme.line,
								borderWidth: 1,
								borderRadius: 4,
								hoverBackgroundColor: theme.line
							}
			]

	chart = new Chart(context, {
		type: chartType === 'doughnut' ? 'doughnut' : chartType === 'line' ? 'line' : 'bar',
		data: {
			labels,
			datasets
		},
		options: {
			responsive: true,
			maintainAspectRatio: false,
			indexAxis: chartType === 'horizontal_bar' ? 'y' : 'x',
			interaction: {
				mode: tooltipMode,
				intersect: tooltipIntersect
			},
			plugins: {
				legend: { display: chartType === 'doughnut' || series.length > 1, position: 'bottom' },
				tooltip: {
					mode: tooltipMode,
					intersect: tooltipIntersect,
					backgroundColor: theme.tooltipBackground,
					titleColor: theme.tooltipText,
					bodyColor: theme.tooltipText,
					callbacks: {
						label: (context) => {
							const raw = chartType === 'horizontal_bar' ? context.parsed.x : context.parsed.y
							const value = chartType === 'doughnut' ? context.parsed : raw
							const label = series.length
								? context.dataset.label
								: (artifact.data?.metric_label ?? 'Value')
							return `${label}: ${formatValue(Number(value ?? 0))}`
						}
					}
				}
			},
			scales:
				chartType === 'doughnut'
					? {}
					: chartType === 'horizontal_bar'
						? {
								x: {
									beginAtZero: true,
									grid: { color: theme.grid },
									ticks: {
										color: theme.muted,
										callback: (value) => formatValue(Number(value))
									}
								},
								y: {
									grid: { display: false },
									ticks: { color: theme.muted }
								}
							}
						: {
								x: {
									grid: { display: false },
									ticks: {
										color: theme.muted,
										maxTicksLimit: chartType === 'line' ? 6 : undefined
									}
								},
								y: {
									beginAtZero: true,
									grid: { color: theme.grid },
									ticks: {
										color: theme.muted,
										callback: (value) => formatValue(Number(value))
									}
								}
							}
		}
	})
}

onMount(() => {
	createChart()
	return () => chart?.destroy()
})

$effect(() => {
	resolvedTheme
	artifact.id
	pointSignature
	createChart()
})
</script>

{#if chartPoints.length === 0}
	<div class="grid min-h-[240px] place-items-center rounded-md border border-dashed border-border bg-panel p-5 text-center">
		<div>
			<p class="text-sm font-semibold text-fg-1">No chart data</p>
			<p class="mt-1 text-xs leading-5 text-fg-4">Try a broader filter or a longer lookback window.</p>
		</div>
	</div>
{:else}
	<div class="grid gap-3">
		<div class="grid grid-cols-3 gap-2">
			<div class="rounded-md border border-border bg-card p-2.5">
				<p class="text-[10px] font-semibold uppercase tracking-[0.12em] text-fg-5">Points</p>
				<p class="mt-1 text-sm font-semibold text-fg-1">{formatNumber(chartPoints.length)}</p>
			</div>
			<div class="rounded-md border border-border bg-card p-2.5">
				<p class="text-[10px] font-semibold uppercase tracking-[0.12em] text-fg-5">Records</p>
				<p class="mt-1 text-sm font-semibold text-fg-1">
					{formatNumber(artifact.data?.summary?.total_records)}
				</p>
			</div>
			<div class="rounded-md border border-border bg-card p-2.5">
				<p class="text-[10px] font-semibold uppercase tracking-[0.12em] text-fg-5">
					{rankLabel()}
				</p>
				<p class="mt-1 truncate text-sm font-semibold text-fg-1">
					{formatValue(
						chartPoints[artifact.data?.chart_type === 'line' ? chartPoints.length - 1 : 0]?.value
					)}
				</p>
			</div>
		</div>

		<div class="h-[280px] rounded-md border border-border bg-card p-3">
			<canvas bind:this={canvas}></canvas>
		</div>

		<div class="flex flex-wrap items-center justify-between gap-2 rounded-md border border-border bg-panel p-3 text-xs leading-5 text-fg-3">
			<span>
				<span class="font-semibold text-fg-2">Source:</span>
				{artifact.data?.data_source ?? 'DLD data'}
				{#if periodLabel()}
					<span class="mx-1 text-fg-5">/</span>
					<span class="font-semibold text-fg-2">Period:</span>
					{periodLabel()}
				{/if}
			</span>
			<div class="flex items-center gap-2">
				<button type="button" class="ui-button h-8 px-2.5 text-xs" data-variant="secondary" onclick={downloadPng}>
					<Download size={13} strokeWidth={1.8} />
					PNG
				</button>
				<a
					href={csvHref()}
					download={csvFilename()}
					class="ui-button h-8 px-2.5 text-xs"
					data-variant="secondary"
				>
					<Download size={13} strokeWidth={1.8} />
					CSV
				</a>
			</div>
		</div>
	</div>
{/if}
