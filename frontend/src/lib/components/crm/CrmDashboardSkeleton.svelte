<div class="space-y-3 pt-4" role="status" aria-live="polite" aria-label="Loading lease opportunities">
	<span class="sr-only">Loading lease opportunities</span>
	<div class="grid grid-cols-2 gap-3 lg:grid-cols-4">
		{#each Array(4) as _}
			<div class="ui-surface h-[110px] motion-safe:animate-pulse">
				<div class="m-4 h-3 w-20 rounded bg-panel"></div>
				<div class="mx-4 mt-5 h-7 w-28 rounded bg-panel"></div>
				<div class="mx-4 mt-2 h-3 w-32 rounded bg-panel"></div>
			</div>
		{/each}
	</div>
	<div class="ui-surface h-[132px] motion-safe:animate-pulse p-4">
		<div class="h-4 w-28 rounded bg-panel"></div>
		<div class="mt-4 grid grid-cols-3 gap-2">
			{#each Array(3) as _}<div class="h-16 rounded-lg bg-panel"></div>{/each}
		</div>
	</div>
	<div class="ui-surface motion-safe:animate-pulse p-4">
		<div class="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
			{#each Array(6) as _}<div class="h-10 rounded-md bg-panel"></div>{/each}
		</div>
	</div>
	<div class="ui-surface motion-safe:animate-pulse p-4">
		<div class="h-4 w-40 rounded bg-panel"></div>
		<div class="mt-4 space-y-3">
			{#each Array(5) as _}<div class="h-16 rounded-lg bg-panel"></div>{/each}
		</div>
	</div>
</div>
