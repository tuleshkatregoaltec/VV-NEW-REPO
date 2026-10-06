<script lang="ts">
import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from 'lucide-svelte'

let {
	currentPage = $bindable(1),
	totalPages,
	totalItems,
	itemsPerPage,
	itemLabel = 'results'
}: {
	currentPage?: number
	totalPages: number
	totalItems: number
	itemsPerPage: number
	itemLabel?: string
} = $props()

let startItem = $derived(totalItems === 0 ? 0 : (currentPage - 1) * itemsPerPage + 1)
let endItem = $derived(Math.min(currentPage * itemsPerPage, totalItems))

let canGoPrev = $derived(currentPage > 1)
let canGoNext = $derived(currentPage < totalPages)

function prev() {
	if (canGoPrev) currentPage--
}

function next() {
	if (canGoNext) currentPage++
}
</script>

{#if totalItems > 0}
	<nav class="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between" aria-label="Pagination">
		<p class="text-sm text-fg-3">
			<span class="font-medium">{startItem.toLocaleString()}</span>–<span class="font-medium"
				>{endItem.toLocaleString()}</span
			>
			of <span class="font-medium">{totalItems.toLocaleString()}</span>
			{itemLabel}
		</p>

		{#if totalPages > 1}
			<div class="flex items-center gap-1">
				<button
					type="button"
					onclick={() => (currentPage = 1)}
					disabled={!canGoPrev}
					class="ui-button h-8 w-8 p-0 text-fg-4 disabled:pointer-events-none disabled:opacity-30"
					aria-label="First page"
				>
					<ChevronsLeft size={16} strokeWidth={2} />
				</button>

				<button
					type="button"
					onclick={prev}
					disabled={!canGoPrev}
					class="ui-button h-8 w-8 p-0 text-fg-4 disabled:pointer-events-none disabled:opacity-30"
					aria-label="Previous page"
				>
					<ChevronLeft size={16} strokeWidth={2} />
				</button>

				<span class="min-w-14 px-2 text-center font-mono text-xs tabular-nums text-fg-4">
					{currentPage}/{totalPages}
				</span>

				<button
					type="button"
					onclick={next}
					disabled={!canGoNext}
					class="ui-button h-8 w-8 p-0 text-fg-4 disabled:pointer-events-none disabled:opacity-30"
					aria-label="Next page"
				>
					<ChevronRight size={16} strokeWidth={2} />
				</button>

				<button
					type="button"
					onclick={() => (currentPage = totalPages)}
					disabled={!canGoNext}
					class="ui-button h-8 w-8 p-0 text-fg-4 disabled:pointer-events-none disabled:opacity-30"
					aria-label="Last page"
				>
					<ChevronsRight size={16} strokeWidth={2} />
				</button>
			</div>
		{/if}
	</nav>
{/if}
