<script lang="ts">
import type { SalesAnalyticsResponse } from '$lib/api/analytics'
import BreakdownChart from '$lib/components/charts/BreakdownChart.svelte'

let { data }: { data: SalesAnalyticsResponse } = $props()

function formatNumber(value: number): string {
	return value.toLocaleString()
}

function getTrend(
	pct: number | null | undefined
): { value: string; direction: 'up' | 'down' } | null {
	if (pct == null) return null
	return {
		value: `${Math.abs(pct).toFixed(1)}% vs prev period`,
		direction: pct >= 0 ? 'up' : 'down'
	}
}

const trend = $derived(getTrend(data.summary.count_change_pct))
</script>

<div class="space-y-6">
	<!-- Summary Stats -->
	<div class="rounded-xl border border-navy-pale bg-navy-pale p-6">
		<div class="flex items-baseline justify-between">
			<div>
				<p class="mb-1 text-sm text-fg-4">Total Transactions</p>
				<p class="text-4xl font-bold text-fg-1">
					{formatNumber(data.summary.transaction_count)}
				</p>
			</div>
			{#if trend}
				<div
					class="flex items-center text-sm font-semibold {trend.direction === 'up'
						? 'text-trend-up'
						: 'text-trend-down'}"
				>
					<svg class="w-5 h-5 mr-1" fill="currentColor" viewBox="0 0 20 20">
						{#if trend.direction === 'up'}
							<path
								fill-rule="evenodd"
								d="M5.293 9.707a1 1 0 010-1.414l4-4a1 1 0 011.414 0l4 4a1 1 0 01-1.414 1.414L11 7.414V15a1 1 0 11-2 0V7.414L6.707 9.707a1 1 0 01-1.414 0z"
								clip-rule="evenodd"
							/>
						{:else}
							<path
								fill-rule="evenodd"
								d="M14.707 10.293a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 111.414-1.414L9 12.586V5a1 1 0 012 0v7.586l2.293-2.293a1 1 0 011.414 0z"
								clip-rule="evenodd"
							/>
						{/if}
					</svg>
					<span>{trend.value}</span>
				</div>
			{/if}
		</div>
		<p class="mt-2 text-sm text-fg-4">Last {data.timeframe_days} days</p>
	</div>

	<!-- Breakdowns -->
	<div class="space-y-6">
		<!-- By Property Type -->
		{#if data.by_property_type.length > 0}
			<div>
				<BreakdownChart
					data={data.by_property_type}
					title="By Property Type"
					metric="count"
					height={300}
					maxItems={8}
				/>
			</div>
		{/if}

		<!-- By Registration Type -->
		{#if data.by_reg_type.length > 0}
			<div>
				<BreakdownChart
					data={data.by_reg_type}
					title="By Registration Type"
					metric="count"
					height={200}
					maxItems={5}
				/>
			</div>
		{/if}

		<!-- Top Areas/Projects -->
		{#if data.by_master_project.length > 0}
			<div>
				<BreakdownChart
					data={data.by_master_project}
					title="Top Projects by Transaction Volume"
					metric="count"
					height={400}
					maxItems={10}
				/>
			</div>
		{/if}
	</div>
</div>
