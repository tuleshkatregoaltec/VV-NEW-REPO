<script lang="ts">
import { workbookStore } from '$lib/feasibility/workbook/store.svelte'

const isBtr = $derived(workbookStore.assumptions?.developmentModel === 'build_to_rent_residential')
const study = $derived(
	workbookStore.research
		? {
				market_area: workbookStore.research.market_area,
				usage: workbookStore.research.usage,
				headline: workbookStore.study_context?.headline || workbookStore.research.headline,
				off_plan_unit_benchmarks: workbookStore.research.off_plan_unit_benchmarks,
				market_pricing: workbookStore.research.market_pricing,
				pricing_evidence: workbookStore.research.pricing_evidence,
				competition_evidence: workbookStore.research.competition_evidence,
				land_sales_evidence: workbookStore.research.land_sales_evidence,
				rental_market_summary: workbookStore.research.rental_market_summary,
				rental_comparables: workbookStore.research.rental_comparables,
				rental_rates_by_size_band: workbookStore.research.rental_rates_by_size_band
			}
		: null
)

const outputs = $derived(workbookStore.outputs)
const assumptions = $derived(workbookStore.assumptions)
const programRows = $derived(outputs?.program.rows ?? [])
const btsComparableRows = $derived(
	(study?.pricing_evidence ?? []).map((comp, index) => ({ comp, index })).slice(0, 10)
)

function fmt(n: number, digits = 0): string {
	return n.toLocaleString('en-AE', { minimumFractionDigits: digits, maximumFractionDigits: digits })
}
function rateToSqft(aedPerSqm: number) {
	return aedPerSqm * 0.092903
}
function annualRateToMonthlySqft(aedPerSqmYear: number) {
	return (aedPerSqmYear * 0.092903) / 12
}
function toSqft(sqm: number) {
	return sqm / 0.092903
}

const confidenceBadge: Record<string, string> = {
	high: 'bg-emerald-100 text-emerald-700',
	medium: 'bg-amber-100 text-amber-700',
	low: 'bg-rose-100 text-rose-700'
}

const HEADER = 'bg-[#1F3864] text-white px-2 py-[4px] font-bold text-[11px] tracking-wide'
const SUBHEADER =
	'bg-[#D6DCE4] px-2 py-[3px] text-slate-700 font-semibold text-[10px] tracking-wider uppercase'
const TH =
	'px-2 py-[4px] text-right text-[10px] font-semibold text-slate-600 uppercase tracking-wider border-b border-[#B8C4CE] bg-[#EEF2F7]'
const TH_LEFT =
	'px-2 py-[4px] text-left text-[10px] font-semibold text-slate-600 uppercase tracking-wider border-b border-[#B8C4CE] bg-[#EEF2F7]'
const TD = 'px-2 py-[3px] text-right tabular-nums text-slate-800 border-b border-[#EBEBEB]'
const TD_LEFT = 'px-2 py-[3px] text-left text-slate-800 border-b border-[#EBEBEB]'
</script>

<div class="overflow-auto flex-1 bg-white text-[11px] font-[Calibri,'Segoe_UI',Arial,sans-serif]">

	<!-- Header -->
	<div class="bg-[#1F3864] text-white px-4 py-2.5 flex items-start justify-between gap-4">
		<div>
			<div class="text-[13px] font-bold tracking-wide">PRICING EVIDENCE</div>
			<div class="text-[10px] text-blue-200 mt-0.5">
				{study
					? isBtr
						? `${study.market_area} — Rental evidence`
						: `${study.market_area} — Pricing comparables`
					: 'Pricing evidence'}
			</div>
		</div>
	</div>

	{#if !study}
		<div class="flex items-center justify-center h-40 text-slate-400 text-xs">
			No pricing evidence available.
		</div>
	{:else if isBtr}
		<table class="w-full border-collapse" style="border-spacing:0">
			<tbody>
				<tr><td colspan="8" class={HEADER}>BTR RENTAL EVIDENCE SUMMARY</td></tr>
			</tbody>
		</table>
		<table class="w-full border-collapse border-b border-[#D9D9D9]" style="border-spacing:0">
			<colgroup>
				<col style="width:25%"><col style="width:25%"><col style="width:25%"><col style="width:25%">
			</colgroup>
			<tbody>
				<tr>
					<td class="{TD_LEFT} font-semibold text-slate-500 text-[10px] uppercase tracking-wide border-r border-[#E8E8E8]">Market Area</td>
					<td class="{TD_LEFT} border-r border-[#E8E8E8] font-medium">{study.market_area}</td>
					<td class="{TD_LEFT} font-semibold text-slate-500 text-[10px] uppercase tracking-wide border-r border-[#E8E8E8]">Usage</td>
					<td class={TD_LEFT}>{study.usage.replace('_', ' ')}</td>
				</tr>
				<tr>
					<td class="{TD_LEFT} font-semibold text-slate-500 text-[10px] uppercase tracking-wide border-r border-[#E8E8E8]">Total Rental Units</td>
					<td class="{TD_LEFT} border-r border-[#E8E8E8]">{fmt(outputs?.btr?.program.totalUnits ?? 0, 0)}</td>
					<td class="{TD_LEFT} font-semibold text-slate-500 text-[10px] uppercase tracking-wide border-r border-[#E8E8E8]">Leasable Area (sqm)</td>
					<td class={TD_LEFT}>{fmt(outputs?.btr?.program.totalAreaSqm ?? 0)}</td>
				</tr>
				<tr>
					<td class="{TD_LEFT} font-semibold text-slate-500 text-[10px] uppercase tracking-wide border-r border-[#E8E8E8]">Avg Rent (AED/sqft/mo)</td>
					<td class="{TD_LEFT} border-r border-[#E8E8E8] font-medium text-[#1565C0]">
						{outputs?.btr ? fmt(outputs.btr.program.weightedAvgRentPsqmMonth * 0.092903, 2) : '—'}
					</td>
					<td class="{TD_LEFT} font-semibold text-slate-500 text-[10px] uppercase tracking-wide border-r border-[#E8E8E8]">Gross Potential Rent (AED/yr)</td>
					<td class="{TD_LEFT} font-medium">{fmt(outputs?.btr?.program.grossPotentialRentAed ?? 0)}</td>
				</tr>
			</tbody>
		</table>

		{#if (study.rental_rates_by_size_band?.length ?? 0) > 0}
		<table class="w-full border-collapse mt-0" style="border-spacing:0">
			<tbody>
				<tr><td colspan="6" class={HEADER}>0. &nbsp; RENTAL RATES BY UNIT TYPE</td></tr>
			</tbody>
		</table>
		<table class="w-full border-collapse border-b border-[#D9D9D9]" style="border-spacing:0">
			<thead>
				<tr>
					<th class="{TH_LEFT} border-r border-[#D9D9D9]">Unit Type</th>
					<th class="{TH_LEFT} border-r border-[#D9D9D9]">Size Band</th>
					<th class="{TH} border-r border-[#D9D9D9]">Contracts (12m)</th>
					<th class="{TH} border-r border-[#D9D9D9]">Median AED/sqm/yr</th>
					<th class="{TH} border-r border-[#D9D9D9]">Median AED/sqft/mo</th>
					<th class="{TH} border-r border-[#D9D9D9]">Median Annual AED</th>
					<th class={TH}>Modeled Monthly (AED)</th>
				</tr>
			</thead>
			<tbody>
				{#each study.rental_rates_by_size_band ?? [] as band}
					{@const btrRow = outputs?.btr?.program.rows.find(r => {
						const sz = r.avgSizeSqm ?? 0
						if (sz <= 0) return false
						return band.unit_type_proxy === 'studio' ? sz <= 55
							: band.unit_type_proxy === '1br' ? sz > 55 && sz <= 90
							: band.unit_type_proxy === '2br' ? sz > 90 && sz <= 140
							: band.unit_type_proxy === '3br' ? sz > 140 && sz <= 200
							: sz > 200
					})}
					<tr class="hover:bg-slate-50/60">
						<td class="{TD_LEFT} font-medium border-r border-[#E8E8E8] uppercase">{band.unit_type_proxy}</td>
						<td class="{TD_LEFT} border-r border-[#E8E8E8] text-slate-500">{band.size_band_label}</td>
						<td class="{TD} border-r border-[#E8E8E8]">{fmt(band.contract_count, 0)}</td>
						<td class="{TD} border-r border-[#E8E8E8] font-medium">{fmt(band.median_rent_psm_annual)}</td>
						<td class="{TD} border-r border-[#E8E8E8]">{fmt(annualRateToMonthlySqft(band.median_rent_psm_annual), 2)}</td>
						<td class="{TD} border-r border-[#E8E8E8]">{fmt(band.median_annual_rent)}</td>
						<td class="{TD} {btrRow ? 'text-[#1565C0] font-medium' : 'text-slate-400'}">
							{btrRow ? fmt(btrRow.monthlyRentAed ?? 0) : '—'}
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
		{/if}

		{#if study.rental_market_summary}
		<table class="w-full border-collapse mt-0" style="border-spacing:0">
			<tbody>
				<tr><td colspan="6" class={HEADER}>1. &nbsp; MASTER COMMUNITY RENTAL AVERAGES</td></tr>
			</tbody>
		</table>
		<table class="w-full border-collapse border-b border-[#D9D9D9]" style="border-spacing:0">
			<thead>
				<tr>
					<th class="{TH_LEFT} border-r border-[#D9D9D9]">Metric</th>
					<th class={TH}>Value</th>
					<th class={TH}>Metric</th>
					<th class={TH}>Value</th>
				</tr>
			</thead>
			<tbody>
				<tr class="hover:bg-slate-50/60">
					<td class="{TD_LEFT} font-medium border-r border-[#E8E8E8]">Rental contracts (12m)</td>
					<td class="{TD}">{fmt(study.rental_market_summary.rental_contract_count_12m, 0)}</td>
					<td class="{TD_LEFT} font-medium border-r border-[#E8E8E8]">Avg rent (AED/sqm/yr)</td>
					<td class="{TD}">{study.rental_market_summary.avg_rent_price_sqm_12m ? fmt(study.rental_market_summary.avg_rent_price_sqm_12m) : '—'}</td>
				</tr>
				<tr class="hover:bg-slate-50/60">
					<td class="{TD_LEFT} font-medium border-r border-[#E8E8E8]">Avg rent (AED/sqft/mo)</td>
					<td class="{TD}">{study.rental_market_summary.avg_rent_price_sqm_12m ? fmt(annualRateToMonthlySqft(study.rental_market_summary.avg_rent_price_sqm_12m), 2) : '—'}</td>
					<td class="{TD_LEFT} font-medium border-r border-[#E8E8E8]">Median annual rent</td>
					<td class="{TD}">{study.rental_market_summary.median_annual_rent ? fmt(study.rental_market_summary.median_annual_rent) : '—'}</td>
				</tr>
				<tr class="hover:bg-slate-50/60">
					<td class="{TD_LEFT} font-medium border-r border-[#E8E8E8]">Gross yield</td>
					<td class="{TD}">{study.rental_market_summary.gross_yield_pct ? fmt(study.rental_market_summary.gross_yield_pct, 2) + '%' : '—'}</td>
					<td class="{TD_LEFT} font-medium border-r border-[#E8E8E8]">Top developers</td>
					<td class="{TD_LEFT}">{study.rental_market_summary.top_developers?.slice(0, 3).join(', ') || '—'}</td>
				</tr>
			</tbody>
		</table>
		{/if}

		{#if (study.rental_comparables?.length ?? 0) > 0}
		<table class="w-full border-collapse mt-0" style="border-spacing:0">
			<tbody>
				<tr><td colspan="7" class={HEADER}>2. &nbsp; RENTAL COMPARABLE PROJECTS</td></tr>
			</tbody>
		</table>
		<table class="w-full border-collapse border-b border-[#D9D9D9]" style="border-spacing:0">
			<thead>
				<tr>
					<th class="{TH_LEFT} border-r border-[#D9D9D9]">Project</th>
					<th class="{TH_LEFT} border-r border-[#D9D9D9]">Area</th>
					<th class="{TH} border-r border-[#D9D9D9]">Similarity</th>
					<th class="{TH} border-r border-[#D9D9D9]">Rent AED/sqm/yr</th>
					<th class="{TH} border-r border-[#D9D9D9]">Rent AED/sqft/mo</th>
					<th class="{TH} border-r border-[#D9D9D9]">Median Annual Rent</th>
					<th class={TH}>Yield</th>
				</tr>
			</thead>
			<tbody>
				{#each study.rental_comparables ?? [] as comp}
					<tr class="hover:bg-slate-50/60">
						<td class="{TD_LEFT} font-medium border-r border-[#E8E8E8]">{comp.project_name}</td>
						<td class="{TD_LEFT} border-r border-[#E8E8E8]">{comp.area_name}</td>
						<td class="{TD} border-r border-[#E8E8E8]">{fmt(comp.score, 1)}</td>
						<td class="{TD} border-r border-[#E8E8E8]">{comp.avg_rent_price_sqm_12m ? fmt(comp.avg_rent_price_sqm_12m) : '—'}</td>
						<td class="{TD} border-r border-[#E8E8E8]">{comp.avg_rent_price_sqm_12m ? fmt(annualRateToMonthlySqft(comp.avg_rent_price_sqm_12m), 2) : '—'}</td>
						<td class="{TD} border-r border-[#E8E8E8]">{comp.median_annual_rent ? fmt(comp.median_annual_rent) : '—'}</td>
						<td class={TD}>{comp.gross_yield_pct ? fmt(comp.gross_yield_pct, 2) + '%' : '—'}</td>
					</tr>
				{/each}
			</tbody>
		</table>
		{/if}

		{#if (study.land_sales_evidence?.length ?? 0) > 0}
		<table class="w-full border-collapse mt-0" style="border-spacing:0">
			<tbody>
				<tr><td colspan="7" class={HEADER}>3. &nbsp; LAND SALES EVIDENCE</td></tr>
			</tbody>
		</table>
		<table class="w-full border-collapse border-b border-[#D9D9D9]" style="border-spacing:0">
			<thead>
				<tr>
					<th class="{TH_LEFT} border-r border-[#D9D9D9]">Date</th>
					<th class="{TH_LEFT} border-r border-[#D9D9D9]">Project</th>
					<th class="{TH} border-r border-[#D9D9D9]">Plot Area (sqm)</th>
					<th class="{TH} border-r border-[#D9D9D9]">Price AED</th>
					<th class="{TH} border-r border-[#D9D9D9]">AED/plot sqm</th>
					<th class="{TH} border-r border-[#D9D9D9]">AED/GFA sqm</th>
					<th class={TH}>Usage</th>
				</tr>
			</thead>
			<tbody>
				{#each study.land_sales_evidence ?? [] as row}
					<tr class="hover:bg-slate-50/60">
						<td class="{TD_LEFT} border-r border-[#E8E8E8]">{row.instance_date?.slice(0, 10) ?? '—'}</td>
						<td class="{TD_LEFT} border-r border-[#E8E8E8]">{row.project_name || row.procedure_name || '—'}</td>
						<td class="{TD} border-r border-[#E8E8E8]">{fmt(row.plot_area_sqm)}</td>
						<td class="{TD} border-r border-[#E8E8E8]">{fmt(row.price_aed)}</td>
						<td class="{TD} border-r border-[#E8E8E8]">{fmt(row.price_sqm)}</td>
						<td class="{TD} border-r border-[#E8E8E8] {row.price_per_gfa_sqm ? 'text-[#1565C0] font-medium' : 'text-slate-400'}">
							{row.price_per_gfa_sqm ? fmt(row.price_per_gfa_sqm) : '—'}
						</td>
						<td class={TD}>{row.property_usage || '—'}</td>
					</tr>
				{/each}
			</tbody>
		</table>
		{/if}
	{:else}
		<!-- ═══ SUBJECT PROPERTY SUMMARY ═══ -->
		<table class="w-full border-collapse" style="border-spacing:0">
			<tbody>
				<tr><td colspan="8" class={HEADER}>SUBJECT PROPERTY SUMMARY</td></tr>
			</tbody>
		</table>
		<table class="w-full border-collapse border-b border-[#D9D9D9]" style="border-spacing:0">
			<colgroup>
				<col style="width:25%"><col style="width:25%"><col style="width:25%"><col style="width:25%">
			</colgroup>
			<tbody>
				<tr>
					<td class="{TD_LEFT} font-semibold text-slate-500 text-[10px] uppercase tracking-wide border-r border-[#E8E8E8]">Market Area</td>
					<td class="{TD_LEFT} border-r border-[#E8E8E8] font-medium">{study.market_area}</td>
					<td class="{TD_LEFT} font-semibold text-slate-500 text-[10px] uppercase tracking-wide border-r border-[#E8E8E8]">Usage</td>
					<td class={TD_LEFT}>{study.usage.replace('_', ' ')}</td>
				</tr>
				<tr>
					<td class="{TD_LEFT} font-semibold text-slate-500 text-[10px] uppercase tracking-wide border-r border-[#E8E8E8]">Plot Area (sqm)</td>
					<td class="{TD_LEFT} border-r border-[#E8E8E8]">{outputs ? fmt(outputs.area.plotAreaSqm) : fmt(assumptions?.plotAreaSqm ?? 0)}</td>
					<td class="{TD_LEFT} font-semibold text-slate-500 text-[10px] uppercase tracking-wide border-r border-[#E8E8E8]">Max GFA (sqm)</td>
					<td class={TD_LEFT}>{outputs ? fmt(outputs.area.maxGfaSqm) : '—'}</td>
				</tr>
				<tr>
					<td class="{TD_LEFT} font-semibold text-slate-500 text-[10px] uppercase tracking-wide border-r border-[#E8E8E8]">Total Units</td>
					<td class="{TD_LEFT} border-r border-[#E8E8E8]">{outputs ? fmt(outputs.program.totalUnits, 0) : '0'}</td>
					<td class="{TD_LEFT} font-semibold text-slate-500 text-[10px] uppercase tracking-wide border-r border-[#E8E8E8]">Parking Spaces</td>
					<td class={TD_LEFT}>{fmt(outputs?.program.totalParkingSpaces ?? 0, 0)}</td>
				</tr>
				<tr>
					<td class="{TD_LEFT} font-semibold text-slate-500 text-[10px] uppercase tracking-wide border-r border-[#E8E8E8]">Wtd. Avg Price (AED/sqft)</td>
					<td class="{TD_LEFT} border-r border-[#E8E8E8] font-medium text-[#1565C0]">
						{outputs ? fmt(rateToSqft(outputs.program.weightedAvgSalesRatePsqm)) : '—'}
					</td>
					<td class="{TD_LEFT} font-semibold text-slate-500 text-[10px] uppercase tracking-wide border-r border-[#E8E8E8]">Gross Revenue (AED)</td>
					<td class="{TD_LEFT} font-medium">{outputs ? fmt(outputs.program.grossRevenueAed) : '0'}</td>
				</tr>
			</tbody>
		</table>

		<!-- Unit mix from program -->
		{#if outputs && programRows.length > 0}
		<table class="w-full border-collapse mt-0" style="border-spacing:0">
			<tbody><tr><td colspan="6" class={SUBHEADER}>Unit Configuration Mix</td></tr></tbody>
		</table>
		<table class="w-full border-collapse border-b border-[#D9D9D9]" style="border-spacing:0">
			<colgroup>
				<col style="width:20%"><col style="width:13%"><col style="width:13%"><col style="width:18%"><col style="width:18%"><col style="width:18%">
			</colgroup>
			<thead>
				<tr>
					<th class="{TH_LEFT} border-r border-[#D9D9D9]">Unit Type</th>
					<th class="{TH} border-r border-[#D9D9D9]">Units</th>
					<th class="{TH} border-r border-[#D9D9D9]">Share %</th>
					<th class="{TH} border-r border-[#D9D9D9]">Avg Size (sqft)</th>
					<th class="{TH} border-r border-[#D9D9D9]">AED/sqft</th>
					<th class={TH}>Gross Revenue</th>
				</tr>
			</thead>
			<tbody>
				{#each programRows as row}
					<tr class="hover:bg-slate-50/60">
						<td class="{TD_LEFT} font-medium border-r border-[#E8E8E8]">{row.label}</td>
						<td class="{TD} border-r border-[#E8E8E8]">{fmt(row.units)}</td>
						<td class="{TD} border-r border-[#E8E8E8]">{outputs.program.totalUnits > 0 ? ((row.units / outputs.program.totalUnits) * 100).toFixed(1) : '0.0'}%</td>
						<td class="{TD} border-r border-[#E8E8E8]">{fmt(toSqft(row.avgSizeSqm))}</td>
						<td class="{TD} border-r border-[#E8E8E8] text-[#1565C0] font-semibold">{fmt(rateToSqft(row.sellingRatePsqm))}</td>
						<td class={TD}>{fmt(row.revenueAed)}</td>
					</tr>
				{/each}
			</tbody>
		</table>
		{/if}

		<!-- ═══ SECTION 1: OFF-PLAN UNIT BENCHMARKS ═══ -->
		{#if (study.off_plan_unit_benchmarks?.length ?? 0) > 0}
		<table class="w-full border-collapse" style="border-spacing:0">
			<tbody>
				<tr><td colspan="7" class={HEADER}>1. &nbsp; OFF-PLAN PRICING BENCHMARKS</td></tr>
			</tbody>
		</table>
		<table class="w-full border-collapse border-b border-[#D9D9D9]" style="border-spacing:0">
			<colgroup>
				<col style="width:14%">
				<col style="width:13%">
				<col style="width:10%">
				<col style="width:10%">
				<col style="width:12%">
				<col style="width:12%">
				<col style="width:29%">
			</colgroup>
			<thead>
				<tr>
					<th class="{TH_LEFT} border-r border-[#D9D9D9]">Unit Type</th>
					<th class="{TH} border-r border-[#D9D9D9]">Horizon</th>
					<th class="{TH} border-r border-[#D9D9D9]">Avg Months</th>
					<th class="{TH} border-r border-[#D9D9D9]">Txn Count</th>
					<th class="{TH} border-r border-[#D9D9D9]">Median AED/sqm</th>
					<th class="{TH} border-r border-[#D9D9D9]">Median AED/sqft</th>
					<th class={TH}>Confidence</th>
				</tr>
			</thead>
			<tbody>
				{#each study.off_plan_unit_benchmarks ?? [] as b}
					<tr class="hover:bg-slate-50/60">
						<td class="{TD_LEFT} font-medium border-r border-[#E8E8E8]">{b.unit_type}</td>
						<td class="{TD} border-r border-[#E8E8E8]">{b.selected_horizon_bucket}</td>
						<td class="{TD} border-r border-[#E8E8E8]">{fmt(b.avg_months_to_completion, 0)}</td>
						<td class="{TD} border-r border-[#E8E8E8]">{fmt(b.transaction_count)}</td>
						<td class="{TD} border-r border-[#E8E8E8] font-semibold">{fmt(b.selected_price_sqm)}</td>
						<td class="{TD} border-r border-[#E8E8E8] font-semibold text-[#1565C0]">{fmt(rateToSqft(b.selected_price_sqm))}</td>
						<td class="px-2 py-[3px] border-b border-[#EBEBEB]">
							<span class="px-1.5 py-0.5 rounded text-[9px] font-semibold uppercase tracking-wide {confidenceBadge[b.confidence_label] ?? ''}">
								{b.confidence_label}
							</span>
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
		{/if}

		<!-- ═══ SECTION 2: MARKET PRICING (COMPLETED TRANSACTIONS) ═══ -->
		{#if (study.market_pricing?.length ?? 0) > 0}
		<table class="w-full border-collapse mt-0" style="border-spacing:0">
			<tbody>
				<tr><td colspan="5" class={HEADER}>2. &nbsp; MARKET PRICING</td></tr>
			</tbody>
		</table>
		<table class="w-full border-collapse border-b border-[#D9D9D9]" style="border-spacing:0">
			<colgroup>
				<col style="width:20%">
				<col style="width:20%">
				<col style="width:20%">
				<col style="width:20%">
				<col style="width:20%">
			</colgroup>
			<thead>
				<tr>
					<th class="{TH_LEFT} border-r border-[#D9D9D9]">Unit Type</th>
					<th class="{TH} border-r border-[#D9D9D9]">Transactions</th>
					<th class="{TH} border-r border-[#D9D9D9]">Median AED/sqm</th>
					<th class="{TH} border-r border-[#D9D9D9]">Median AED/sqft</th>
					<th class={TH}>Avg Area (sqft)</th>
				</tr>
			</thead>
			<tbody>
				{#each study.market_pricing ?? [] as row}
					<tr class="hover:bg-slate-50/60">
						<td class="{TD_LEFT} font-medium border-r border-[#E8E8E8]">{row.unit_type}</td>
						<td class="{TD} border-r border-[#E8E8E8]">{fmt(row.transaction_count)}</td>
						<td class="{TD} border-r border-[#E8E8E8]">{fmt(row.median_price_sqm)}</td>
						<td class="{TD} border-r border-[#E8E8E8] font-semibold text-[#1565C0]">{fmt(rateToSqft(row.median_price_sqm))}</td>
						<td class={TD}>{row.avg_area_sqm ? fmt(toSqft(row.avg_area_sqm)) : '—'}</td>
					</tr>
				{/each}
			</tbody>
		</table>
		{/if}

		<!-- ═══ SECTION 3: COMPARABLE PROJECTS ═══ -->
		{#if btsComparableRows.length > 0}
		<table class="w-full border-collapse mt-0" style="border-spacing:0">
			<tbody>
				<tr><td colspan="8" class={HEADER}>3. &nbsp; COMPARABLE PROJECTS</td></tr>
			</tbody>
		</table>
		<table class="w-full border-collapse border-b border-[#D9D9D9]" style="border-spacing:0">
			<colgroup>
				<col style="width:21%">
				<col style="width:13%">
				<col style="width:8%">
				<col style="width:8%">
				<col style="width:10%">
				<col style="width:14%">
				<col style="width:22%">
				<col style="width:4%">
			</colgroup>
			<thead>
				<tr>
					<th class="{TH_LEFT} border-r border-[#D9D9D9]">Project</th>
					<th class="{TH_LEFT} border-r border-[#D9D9D9]">Area</th>
					<th class="{TH} border-r border-[#D9D9D9]">Buildings</th>
					<th class="{TH} border-r border-[#D9D9D9]">Units</th>
					<th class="{TH} border-r border-[#D9D9D9]">AED/sqft</th>
					<th class="{TH_LEFT} border-r border-[#D9D9D9]">Dom. Type</th>
					<th class="{TH_LEFT} border-r border-[#D9D9D9]">Rationale</th>
					<th class={TH}>Remove</th>
				</tr>
			</thead>
			<tbody>
				{#each btsComparableRows as row (`${row.comp.project_id}-${row.index}`)}
					{@const comp = row.comp}
					<tr class="hover:bg-slate-50/60">
						<td class="{TD_LEFT} font-medium border-r border-[#E8E8E8]">{comp.project_name}</td>
						<td class="{TD_LEFT} text-slate-500 border-r border-[#E8E8E8]">{comp.area_name}</td>
						<td class="{TD} border-r border-[#E8E8E8]">{comp.no_of_buildings ?? '—'}</td>
						<td class="{TD} border-r border-[#E8E8E8]">{comp.no_of_units != null ? fmt(comp.no_of_units) : '—'}</td>
						<td class="{TD} border-r border-[#E8E8E8] font-semibold text-[#1565C0]">
							{comp.median_price_sqm != null ? fmt(rateToSqft(comp.median_price_sqm)) : '—'}
						</td>
						<td class="{TD_LEFT} text-slate-600 border-r border-[#E8E8E8]">{comp.dominant_unit_type ?? '—'}</td>
						<td class="px-2 py-[3px] text-slate-500 border-r border-[#E8E8E8] border-b border-[#EBEBEB] text-[9px] leading-relaxed">
							{(comp.rationale ?? []).join(' · ')}
						</td>
						<td class="px-2 py-[3px] text-center border-b border-[#EBEBEB]">
							<button
								type="button"
								class="inline-flex h-5 w-5 items-center justify-center rounded border border-rose-200 text-rose-600 hover:bg-rose-50 focus:outline-none focus:ring-1 focus:ring-rose-400"
								title="Remove comparable"
								aria-label={`Remove comparable ${comp.project_name}`}
								onclick={() => workbookStore.removePricingEvidenceAt(row.index)}
							>
								−
							</button>
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
		{/if}

		<!-- ═══ SECTION 4: COMPETITION / PIPELINE ═══ -->
		{#if (study.competition_evidence?.length ?? 0) > 0}
		<table class="w-full border-collapse mt-0" style="border-spacing:0">
			<tbody>
				<tr><td colspan="6" class={HEADER}>4. &nbsp; COMPETITION &amp; PIPELINE</td></tr>
			</tbody>
		</table>
		<table class="w-full border-collapse border-b border-[#D9D9D9]" style="border-spacing:0">
			<colgroup>
				<col style="width:22%"><col style="width:14%"><col style="width:8%"><col style="width:8%"><col style="width:10%"><col style="width:38%">
			</colgroup>
			<thead>
				<tr>
					<th class="{TH_LEFT} border-r border-[#D9D9D9]">Project</th>
					<th class="{TH_LEFT} border-r border-[#D9D9D9]">Area</th>
					<th class="{TH} border-r border-[#D9D9D9]">Status</th>
					<th class="{TH} border-r border-[#D9D9D9]">Units</th>
					<th class="{TH} border-r border-[#D9D9D9]">Score</th>
					<th class={TH_LEFT}>Rationale</th>
				</tr>
			</thead>
			<tbody>
				{#each study.competition_evidence ?? [] as comp}
					<tr class="hover:bg-slate-50/60">
						<td class="{TD_LEFT} font-medium border-r border-[#E8E8E8]">{comp.project_name}</td>
						<td class="{TD_LEFT} text-slate-500 border-r border-[#E8E8E8]">{comp.area_name}</td>
						<td class="{TD_LEFT} text-slate-500 border-r border-[#E8E8E8] text-[10px]">{comp.project_status ?? '—'}</td>
						<td class="{TD} border-r border-[#E8E8E8]">{comp.no_of_units != null ? fmt(comp.no_of_units) : '—'}</td>
						<td class="{TD} border-r border-[#E8E8E8]">{comp.score.toFixed(0)}</td>
						<td class="px-2 py-[3px] text-slate-500 border-b border-[#EBEBEB] text-[9px] leading-relaxed">{(comp.rationale ?? []).join(' · ')}</td>
					</tr>
				{/each}
			</tbody>
		</table>
		{/if}

		<!-- ═══ SECTION 5: LAND MARKET EVIDENCE ═══ -->
		{#if (study.land_sales_evidence?.length ?? 0) > 0}
		<table class="w-full border-collapse mt-0" style="border-spacing:0">
			<tbody>
				<tr><td colspan="8" class={HEADER}>5. &nbsp; LAND MARKET EVIDENCE</td></tr>
			</tbody>
		</table>
		<table class="w-full border-collapse border-b border-[#D9D9D9]" style="border-spacing:0">
			<colgroup>
				<col style="width:10%"><col style="width:14%"><col style="width:12%"><col style="width:11%"><col style="width:12%"><col style="width:12%"><col style="width:12%"><col style="width:17%">
			</colgroup>
			<thead>
				<tr>
					<th class="{TH_LEFT} border-r border-[#D9D9D9]">Date</th>
					<th class="{TH_LEFT} border-r border-[#D9D9D9]">Area</th>
					<th class="{TH_LEFT} border-r border-[#D9D9D9]">Usage</th>
					<th class="{TH} border-r border-[#D9D9D9]">Plot Area (sqm)</th>
					<th class="{TH} border-r border-[#D9D9D9]">Price (AED)</th>
					<th class="{TH} border-r border-[#D9D9D9]">AED/plot sqm</th>
					<th class="{TH} border-r border-[#D9D9D9]">AED/GFA sqm</th>
					<th class={TH_LEFT}>Landmark</th>
				</tr>
			</thead>
			<tbody>
				{#each study.land_sales_evidence ?? [] as lse}
					<tr class="hover:bg-slate-50/60">
						<td class="{TD_LEFT} text-slate-500 border-r border-[#E8E8E8]">{lse.instance_date?.slice(0, 10) ?? '—'}</td>
						<td class="{TD_LEFT} font-medium border-r border-[#E8E8E8]">{lse.area_name}</td>
						<td class="{TD_LEFT} text-slate-500 border-r border-[#E8E8E8] text-[10px]">{lse.property_usage}</td>
						<td class="{TD} border-r border-[#E8E8E8]">{fmt(lse.plot_area_sqm)}</td>
						<td class="{TD} border-r border-[#E8E8E8]">{fmt(lse.price_aed)}</td>
						<td class="{TD} border-r border-[#E8E8E8] font-semibold text-[#1565C0]">{fmt(lse.price_sqm)}</td>
						<td class="{TD} border-r border-[#E8E8E8] {lse.price_per_gfa_sqm ? 'font-medium text-slate-700' : 'text-slate-400'}">
							{lse.price_per_gfa_sqm ? fmt(lse.price_per_gfa_sqm) : '—'}
						</td>
						<td class="{TD_LEFT} text-slate-400 text-[10px]">{lse.nearest_landmark ?? '—'}</td>
					</tr>
				{/each}
			</tbody>
		</table>
		{/if}

		{#if (study.off_plan_unit_benchmarks?.length ?? 0) === 0 && (study.market_pricing?.length ?? 0) === 0 && (study.pricing_evidence?.length ?? 0) === 0}
			<div class="flex items-center justify-center h-32 text-slate-400 text-xs">
				No pricing evidence available.
			</div>
		{/if}

		<!-- bottom padding -->
		<div class="py-4"></div>
	{/if}
</div>
