<script lang="ts">
export let title: string
export let value: string | number
export let trend: { value: string; direction: 'up' | 'down' } | null = null
</script>

<div
	class="ui-surface flex flex-col p-5 transition-colors hover:border-strong sm:p-6"
>
	<!-- Header with icon and title -->
	<div class="flex items-center justify-between mb-3">
		<h2 class="text-base font-semibold text-fg-1">{title}</h2>
		<div
			class="h-5 w-5 text-fg-4"
		>
			<slot name="icon" />
		</div>
	</div>

	<!-- Value -->
	{#if value}
		<p class="mb-auto font-display text-3xl font-normal leading-none tracking-normal text-fg-1 tabular-nums sm:text-4xl">{value}</p>
	{/if}
	<!-- Trend indicator -->
	{#if trend}
		<div
			class="mt-4 font-mono text-xs flex items-center {trend.direction === 'up'
				? 'text-trend-up'
				: 'text-trend-down'}"
		>
			<svg
				xmlns="http://www.w3.org/2000/svg"
				class="h-4 w-4 mr-2"
				viewBox="0 0 20 20"
				fill="currentColor"
			>
				{#if trend.direction === 'up'}
					<path
						fill-rule="evenodd"
						d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-8.707l-3-3a1 1 0 00-1.414 0l-3 3a1 1 0 001.414 1.414L9 9.414V13a1 1 0 102 0V9.414l1.293 1.293a1 1 0 001.414-1.414z"
						clip-rule="evenodd"
					/>
				{:else}
					<path
						fill-rule="evenodd"
						d="M10 18a8 8 0 100-16 8 8 0 000 16zm.707-10.293l3-3a1 1 0 00-1.414-1.414L10 8.586 7.707 6.293a1 1 0 00-1.414 1.414l3 3a1 1 0 001.414 0z"
						clip-rule="evenodd"
					/>
				{/if}
			</svg>
			<span>{trend.value}</span>
		</div>
	{/if}

	<!-- Additional content (charts, etc.) -->
	<slot />
</div>
