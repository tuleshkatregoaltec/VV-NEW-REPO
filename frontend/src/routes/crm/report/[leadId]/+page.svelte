<script lang="ts">
import { createQuery } from '@tanstack/svelte-query'
import { ArrowLeft, FileDown, ShieldCheck } from 'lucide-svelte'
import { page } from '$app/state'
import type { CrmPropertyReport } from '$lib/api/crm'
import CrmPanelSkeleton from '$lib/components/crm/CrmPanelSkeleton.svelte'
import { formatCrmMoney, formatCrmDate as shortDate } from '$lib/crm/format'
import { crmQueries } from '$lib/queries/crm'

const leadId = $derived(page.params.leadId ?? null)
const reportQuery = createQuery(() => crmQueries.report(leadId))
const report = $derived(reportQuery.data)

type IndexPoint = CrmPropertyReport['price_index']['points'][number]

function buildPriceChart(points: IndexPoint[]) {
	const width = 840
	const height = 250
	const left = 48
	const right = 18
	const top = 18
	const bottom = 34
	const values = points.flatMap((point) =>
		[point.dubai_index, point.segment_index, point.dld_index, point.transaction_index].filter(
			(value): value is number => value !== null
		)
	)
	const minimum = values.length ? Math.min(...values) : 90
	const maximum = values.length ? Math.max(...values) : 110
	const yMin = Math.floor((minimum - 5) / 10) * 10
	const yMax = Math.ceil((maximum + 5) / 10) * 10
	const x = (index: number) =>
		left + (index / Math.max(1, points.length - 1)) * (width - left - right)
	const y = (value: number) =>
		top + ((yMax - value) / Math.max(1, yMax - yMin)) * (height - top - bottom)
	const path = (getValue: (point: IndexPoint) => number | null) =>
		points
			.map((point, index) => {
				const value = getValue(point)
				return value === null ? null : `${x(index).toFixed(1)},${y(value).toFixed(1)}`
			})
			.filter((value): value is string => value !== null)
			.map((value, index) => `${index === 0 ? 'M' : 'L'}${value}`)
			.join(' ')
	const tickStep = Math.max(10, Math.ceil((yMax - yMin) / 4 / 10) * 10)
	const yTicks: number[] = []
	for (let value = yMin; value <= yMax; value += tickStep) yTicks.push(value)
	const xTicks = points
		.map((point, index) => ({ point, index }))
		.filter(({ index }) => index % 4 === 0 || index === points.length - 1)
	return {
		width,
		height,
		left,
		right,
		top,
		bottom,
		x,
		y,
		yTicks,
		xTicks,
		dubaiPath: path((point) => point.dubai_index),
		segmentPath: path((point) => point.segment_index),
		dldPath: path((point) => point.dld_index),
		transactionPath: path((point) => point.transaction_index)
	}
}

const priceChart = $derived(buildPriceChart(report?.price_index.points ?? []))

function money(value: number | null | undefined) {
	return formatCrmMoney(value)
}

function number(value: number | null | undefined, digits = 0) {
	if (value === null || value === undefined) return '—'
	return new Intl.NumberFormat('en-AE', { maximumFractionDigits: digits }).format(value)
}

function signedPercent(value: number | null | undefined) {
	if (value === null || value === undefined) return '—'
	return `${value > 0 ? '+' : ''}${value.toFixed(1)}%`
}

function compactQuarter(value: string) {
	const [quarter, year] = value.split(' ')
	return year ? `${quarter} ’${year.slice(-2)}` : value
}
</script>

<svelte:head>
	<title>Property opportunity report · Vitevue</title>
</svelte:head>

<div class="min-h-screen bg-app px-4 py-6 text-fg-1 sm:px-6">
	<div class="report-actions mx-auto mb-4 flex max-w-[960px] items-center justify-between">
		<a href="/crm" class="ui-button" data-variant="secondary" data-size="sm"><ArrowLeft size={14} /> Back to CRM</a>
		<button type="button" class="ui-button" data-variant="secondary" data-size="sm" disabled={!report} onclick={() => window.print()}><FileDown size={14} /> Save / print PDF</button>
	</div>

	{#if reportQuery.isLoading}
		<div class="mx-auto max-w-[960px] overflow-hidden rounded-lg border border-border bg-card"><CrmPanelSkeleton rows={7} /></div>
	{:else if reportQuery.isError}
		<div class="mx-auto max-w-2xl rounded-lg border border-error-border bg-error-bg p-5 text-sm text-error">The property report could not be generated: {reportQuery.error.message}</div>
	{:else if report}
		<article class="report-page mx-auto max-w-[960px] overflow-hidden rounded-lg border border-border bg-card shadow-lg">
			<header class="report-header bg-navy px-8 py-7 text-on-navy">
				<div class="flex items-start justify-between gap-8">
					<div>
						<img src="/logos/vitevue-navbar-bone.png" alt="Vitevue" class="h-7 w-auto" />
						<p class="mt-7 font-mono text-[10px] uppercase tracking-[0.16em] text-on-navy-muted">Property opportunity report</p>
						<h1 class="mt-2 text-3xl font-semibold tracking-tight">{report.lead.building_name}</h1>
						<p class="mt-2 text-sm text-on-navy-muted">{report.lead.project_name} · {report.lead.area_name}</p>
						<p class="mt-2 inline-flex rounded-full border border-white/20 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.08em] text-on-navy-muted">{report.lead.asset_class} · {report.lead.property_subtype}{report.lead.matched_sales_property_type ? ' · sale verified' : ''}</p>
					</div>
					<div class="text-right">
						<p class="font-mono text-[10px] uppercase tracking-[0.12em] text-on-navy-muted">Unit</p>
						<p class="mt-1 text-2xl font-semibold">{report.lead.unit_number ?? 'Unresolved'}</p>
						<p class="mt-5 text-xs text-on-navy-muted">Prepared {shortDate(report.period_end)}</p>
						<p class="mt-1 text-xs text-on-navy-muted">Evidence window {shortDate(report.period_start)}–{shortDate(report.period_end)}</p>
					</div>
				</div>
			</header>

			<div class="p-8">
				<section class="grid grid-cols-2 gap-3 sm:grid-cols-4">
					<div class="report-metric"><p>Indicated value</p><strong>{money(report.analysis.estimated_market_value_aed)}</strong><span>{money(report.analysis.estimated_value_low_aed)}–{money(report.analysis.estimated_value_high_aed)}</span></div>
					<div class="report-metric"><p>Market rent</p><strong>{money(report.analysis.estimated_market_rent_aed)}</strong><span>{signedPercent(report.analysis.current_rent_vs_market_pct)} current vs market</span></div>
					<div class="report-metric"><p>Capital change</p><strong class={report.analysis.indicated_capital_change_aed && report.analysis.indicated_capital_change_aed < 0 ? 'text-error' : 'text-success'}>{money(report.analysis.indicated_capital_change_aed)}</strong><span>{signedPercent(report.analysis.indicated_capital_change_pct)} since latest purchase</span></div>
					<div class="report-metric"><p>Market gross yield</p><strong>{report.analysis.estimated_market_gross_yield_pct !== null ? `${report.analysis.estimated_market_gross_yield_pct.toFixed(2)}%` : '—'}</strong><span class="capitalize">{report.analysis.confidence} evidence confidence</span></div>
				</section>

				<section class="mt-7 grid gap-4 sm:grid-cols-[1.15fr_0.85fr]">
					<div class="rounded-lg border border-success-border bg-success-bg p-5">
						<p class="font-mono text-[10px] font-bold uppercase tracking-[0.1em] text-success">Agent opportunity</p>
						<h2 class="mt-2 text-lg font-semibold leading-7 text-fg-1">{report.lead.recommended_action}</h2>
						<p class="mt-2 text-sm leading-6 text-fg-2">{report.lead.lead_reason}</p>
					</div>
					<div class="rounded-lg border border-border bg-panel p-5">
						<p class="font-mono text-[10px] font-bold uppercase tracking-[0.1em] text-fg-4">Unit snapshot</p>
						<dl class="mt-3 grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
							<div><dt class="text-xs text-fg-4">Latest purchase</dt><dd class="mt-0.5 font-semibold">{money(report.lead.matched_sale_price_aed)}</dd></div>
							<div><dt class="text-xs text-fg-4">Purchase date</dt><dd class="mt-0.5 font-semibold">{shortDate(report.lead.last_purchase_date)}</dd></div>
							<div><dt class="text-xs text-fg-4">Current rent</dt><dd class="mt-0.5 font-semibold">{money(report.lead.annual_rent_aed)}</dd></div>
							<div><dt class="text-xs text-fg-4">Lease expiry</dt><dd class="mt-0.5 font-semibold">{shortDate(report.lead.lease_end)}</dd></div>
							<div><dt class="text-xs text-fg-4">Asset type</dt><dd class="mt-0.5 font-semibold">{report.lead.property_subtype}</dd></div>
							<div><dt class="text-xs text-fg-4">Area</dt><dd class="mt-0.5 font-semibold">{number(report.lead.size_sqft)} sqft</dd></div>
						</dl>
					</div>
				</section>

				{#if report.agent_signals.length}
					<section class="mt-7">
						<div class="flex items-center gap-2"><ShieldCheck size={16} class="text-info" /><h2 class="text-base font-semibold">Verified agent signals</h2></div>
						<div class="mt-3 grid gap-2 sm:grid-cols-2">{#each report.agent_signals as signal}<div class="rounded-md border border-info-border bg-info-bg px-3 py-2.5 text-xs leading-5 text-fg-2">{signal}</div>{/each}</div>
					</section>
				{/if}

				<section class="report-section mt-8">
					<div class="flex items-end justify-between gap-4">
						<div><p class="report-kicker">Market context</p><h2>{report.price_index.name}</h2><p class="mt-1 text-[10px] leading-4 text-fg-4">Completed quarters · {shortDate(report.price_index.base_period)}–{shortDate(report.price_index.latest_period)} · Base = 100</p></div>
						<div class="flex items-center gap-3 text-[10px] text-fg-4"><span class="inline-flex items-center gap-1.5"><span class="h-0.5 w-4 bg-navy"></span>Dubai composite</span><span class="inline-flex items-center gap-1.5"><span class="h-0.5 w-4 bg-success"></span>{report.price_index.segment_name}</span></div>
					</div>
					<div class="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
						<div class="rounded-md border border-border bg-panel px-3 py-2.5"><p class="font-mono text-[9px] uppercase tracking-[0.05em] text-fg-4">Dubai index</p><p class="mt-1 text-lg font-semibold">{report.price_index.current_index.toFixed(1)}</p><p class="text-[10px] text-success">{signedPercent(report.price_index.change_since_base_pct)} since base</p></div>
						<div class="rounded-md border border-border bg-panel px-3 py-2.5"><p class="font-mono text-[9px] uppercase tracking-[0.05em] text-fg-4">Dubai annual change</p><p class="mt-1 text-lg font-semibold">{signedPercent(report.price_index.year_over_year_pct)}</p><p class="text-[10px] text-fg-4">year over year</p></div>
						<div class="rounded-md border border-border bg-panel px-3 py-2.5"><p class="font-mono text-[9px] uppercase tracking-[0.05em] text-fg-4">Dubai median</p><p class="mt-1 text-lg font-semibold">{money(report.price_index.current_median_psf_aed)}</p><p class="text-[10px] text-fg-4">per sqft · fixed mix</p></div>
						<div class="rounded-md border border-success-border bg-success-bg px-3 py-2.5"><p class="font-mono text-[9px] uppercase tracking-[0.05em] text-success">{report.price_index.segment_name}</p><p class="mt-1 text-lg font-semibold">{report.price_index.segment_current_index?.toFixed(1) ?? '—'}</p><p class="text-[10px] text-success">{signedPercent(report.price_index.segment_year_over_year_pct)} YoY · {money(report.price_index.segment_current_median_psf_aed)}/sqft</p></div>
					</div>
					<div class="mt-3 overflow-hidden rounded-lg border border-border bg-card p-3">
						<svg viewBox={`0 0 ${priceChart.width} ${priceChart.height}`} class="h-auto w-full" role="img" aria-label="Dubai and local property price index history">
							{#each priceChart.yTicks as tick}
								<line x1={priceChart.left} x2={priceChart.width - priceChart.right} y1={priceChart.y(tick)} y2={priceChart.y(tick)} stroke="var(--color-border)" stroke-width="1" />
								<text x={priceChart.left - 9} y={priceChart.y(tick) + 3} text-anchor="end" class="chart-label">{tick}</text>
							{/each}
							{#each priceChart.xTicks as tick}
								<text x={priceChart.x(tick.index)} y={priceChart.height - 9} text-anchor="middle" class="chart-label">{compactQuarter(tick.point.label)}</text>
							{/each}
							<path d={priceChart.dldPath} fill="none" stroke="var(--color-fg-4)" stroke-width="1.25" stroke-dasharray="4 4" opacity="0.55" />
							<path d={priceChart.transactionPath} fill="none" stroke="var(--color-warning)" stroke-width="1.25" stroke-dasharray="4 4" opacity="0.55" />
							<path d={priceChart.dubaiPath} fill="none" stroke="var(--color-navy)" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" />
							<path d={priceChart.segmentPath} fill="none" stroke="var(--color-success)" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" />
						</svg>
						<div class="mt-1 flex flex-wrap items-center justify-between gap-2 border-t border-border pt-2 text-[9px] leading-4 text-fg-4"><span>DLD registry <span class="mx-1 inline-block w-3 border-t border-dashed border-fg-4 align-middle"></span> Transaction series <span class="mx-1 inline-block w-3 border-t border-dashed border-warning align-middle"></span></span><span>Partial current quarter excluded</span></div>
					</div>
					<p class="mt-2 text-[9px] leading-4 text-fg-4">{report.price_index.methodology}</p>
				</section>

				<section class="report-section mt-8">
					<div class="flex items-end justify-between gap-4"><div><p class="report-kicker">Sales evidence</p><h2>Valuation sales · trailing 12 months</h2><p class="mt-1 max-w-2xl text-[10px] leading-4 text-fg-4">{report.analysis.sales_selection_basis}</p></div><p class="text-xs text-fg-4">{report.analysis.sales_comparables_used} used in valuation</p></div>
					<div class="mt-3 overflow-hidden rounded-lg border border-border">
						<table class="report-table"><thead><tr><th>Date</th><th>Property</th><th>Unit</th><th class="text-right">Size</th><th class="text-right">Price</th><th class="text-right">AED/sqft</th></tr></thead><tbody>
							{#each report.sales_comparables as comp}
								<tr><td>{shortDate(comp.transaction_date)}</td><td><strong>{comp.building_name}</strong><span>{comp.bedrooms || comp.property_type} · {comp.selection_reason}</span></td><td>{comp.unit_number}</td><td class="text-right">{number(comp.size_sqft)} sqft</td><td class="text-right font-semibold">{money(comp.sale_amount_aed)}</td><td class="text-right">{money(comp.price_per_sqft_aed)}</td></tr>
							{:else}<tr><td colspan="6" class="py-8 text-center text-fg-4">No qualifying sales comparables in the 12-month window.</td></tr>{/each}
						</tbody></table>
					</div>
				</section>

				<section class="report-section mt-8">
					<div class="flex items-end justify-between gap-4"><div><p class="report-kicker">Rental evidence</p><h2>Valuation leases · trailing 12 months</h2><p class="mt-1 max-w-2xl text-[10px] leading-4 text-fg-4">{report.analysis.rental_selection_basis}</p></div><p class="text-xs text-fg-4">{report.analysis.rental_comparables_used} used in valuation</p></div>
					<div class="mt-3 overflow-hidden rounded-lg border border-border">
						<table class="report-table"><thead><tr><th>Lease date</th><th>Property</th><th>Unit</th><th>Layout</th><th class="text-right">Size</th><th class="text-right">Annual rent</th><th class="text-right">Rent/sqft</th></tr></thead><tbody>
							{#each report.rental_comparables as comp}
								<tr><td>{shortDate(comp.lease_start)}</td><td><strong>{comp.building_name}</strong><span>{comp.property_type} · {comp.selection_reason}</span></td><td class:font-semibold={comp.unit_number}>{comp.unit_number ?? 'Unresolved'}{#if !comp.unit_number}<span>Needs title-deed match</span>{/if}</td><td>{comp.bedrooms}</td><td class="text-right">{number(comp.size_sqft)} sqft</td><td class="text-right font-semibold">{money(comp.annual_rent_aed)}</td><td class="text-right">{money(comp.rent_per_sqft_aed)}</td></tr>
							{:else}<tr><td colspan="7" class="py-8 text-center text-fg-4">No qualifying rental comparables in the 12-month window.</td></tr>{/each}
						</tbody></table>
					</div>
				</section>

				<section class="report-section mt-8 grid gap-4 sm:grid-cols-2">
					<div class="rounded-lg border border-border p-5">
						<p class="report-kicker">Indicative exit</p>
						<dl class="mt-3 space-y-2 text-sm"><div class="flex justify-between gap-4"><dt class="text-fg-3">Indicated sale value</dt><dd class="font-semibold">{money(report.analysis.estimated_market_value_aed)}</dd></div><div class="flex justify-between gap-4"><dt class="text-fg-3">Assumed selling costs</dt><dd>({money(report.analysis.indicative_selling_costs_aed)})</dd></div><div class="flex justify-between gap-4 border-t border-border pt-2"><dt class="font-semibold">Proceeds before debt</dt><dd class="font-semibold">{money(report.analysis.indicative_proceeds_before_debt_aed)}</dd></div></dl>
						<p class="mt-3 text-[10px] leading-4 text-fg-4">This is not a settlement statement. Mortgage balances and property-specific fees are excluded.</p>
					</div>
					<div class="rounded-lg border border-border p-5">
						<p class="report-kicker">Methodology and caveats</p>
						<ul class="mt-3 space-y-1.5 text-[10px] leading-4 text-fg-4">{#each report.methodology as item}<li class="flex gap-2"><span>•</span><span>{item}</span></li>{/each}</ul>
					</div>
				</section>
			</div>

			<footer class="flex items-center justify-between border-t border-border bg-panel px-8 py-4 text-[10px] text-fg-4"><span>Vitevue · Agent decision support</span><span>Source: sales and rental transaction evidence</span></footer>
		</article>
	{/if}
</div>

<style>
	.report-metric {
		border: 1px solid var(--color-border);
		border-radius: var(--radius-lg);
		background: var(--color-bg-panel);
		padding: 0.9rem;
	}
	.report-metric p,
	.report-kicker {
		font-family: var(--font-mono);
		font-size: 0.625rem;
		font-weight: 700;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		color: var(--color-fg-4);
	}
	.report-metric strong {
		display: block;
		margin-top: 0.45rem;
		font-size: 1rem;
	}
	.report-metric span {
		display: block;
		margin-top: 0.25rem;
		font-size: 0.625rem;
		color: var(--color-fg-4);
	}
	.report-section h2 {
		margin-top: 0.2rem;
		font-size: 1rem;
		font-weight: 650;
	}
	.report-table {
		width: 100%;
		border-collapse: collapse;
		font-size: 0.6875rem;
	}
	.report-table th {
		background: var(--color-bg-panel);
		padding: 0.55rem 0.7rem;
		text-align: left;
		font-family: var(--font-mono);
		font-size: 0.5625rem;
		font-weight: 600;
		letter-spacing: 0.05em;
		text-transform: uppercase;
		color: var(--color-fg-4);
	}
	.report-table td {
		border-top: 1px solid var(--color-border);
		padding: 0.55rem 0.7rem;
		vertical-align: top;
	}
	.report-table td span {
		display: block;
		margin-top: 0.15rem;
		font-size: 0.5625rem;
		color: var(--color-fg-4);
	}
	.chart-label {
		fill: var(--color-fg-4);
		font-family: var(--font-mono);
		font-size: 8px;
	}
	@media print {
		@page {
			size: A4;
			margin: 10mm;
		}
		:global(html),
		:global(body) {
			background: white !important;
			print-color-adjust: exact;
			-webkit-print-color-adjust: exact;
		}
		.report-actions {
			display: none !important;
		}
		.report-page {
			max-width: none;
			border: 0;
			border-radius: 0;
			box-shadow: none;
		}
		.report-header,
		.report-metric,
		.report-section {
			break-inside: avoid;
		}
	}
</style>
