<script lang="ts">
let { rows = 4, compact = false }: { rows?: number; compact?: boolean } = $props()
</script>

<div
	class="motion-safe:animate-pulse {compact ? 'space-y-2 p-4' : 'space-y-4 p-5'}"
	role="status"
	aria-live="polite"
	aria-label="Loading CRM data"
>
	<span class="sr-only">Loading CRM data</span>
	<div class="h-5 w-40 rounded bg-panel"></div>
	<div class="h-3 w-3/5 rounded bg-panel"></div>
	{#each Array(rows) as _}
		<div class={compact ? 'h-14 rounded-lg bg-panel' : 'h-24 rounded-lg bg-panel'}></div>
	{/each}
</div>
