<script module lang="ts">
let nextId = 0
</script>

<script lang="ts">
import type { Snippet } from 'svelte'
import CheckboxDropdown from '$lib/components/dropdowns/CheckboxDropdown.svelte'
import SearchableDropdown from '$lib/components/dropdowns/SearchableDropdown.svelte'
import StandardDropdown from '$lib/components/dropdowns/StandardDropdown.svelte'
import type { FilterDefinition } from '$lib/types/filters'

let {
	filterDefinitions = [],
	filters = $bindable({}),
	onReset = () => {},
	onExport = () => {},
	selectedCount = 0,
	embedded = false,
	showHeader = true,
	idPrefix = `filter-panel-${nextId++}`,
	prefix
}: {
	filterDefinitions?: FilterDefinition[]
	filters?: Record<string, any>
	onReset?: () => void
	onExport?: () => void
	selectedCount?: number
	embedded?: boolean
	showHeader?: boolean
	idPrefix?: string
	prefix?: Snippet
} = $props()

function resetFilters() {
	filters = {}
	onReset()
}

// Helper to get filter value with fallback
function getFilterValue(id: string): string {
	return filters[id] ?? 'All'
}

// Helper to update filter value (supports both string and checkbox object values)
function setFilterValue(id: string, value: any) {
	filters = { ...filters, [id]: value }
}

function controlId(id: string) {
	return `${idPrefix}-${id}-input`
}
</script>

<div
	class={embedded
		? 'relative z-10'
		: 'ui-surface relative z-10 mb-5 p-4 sm:p-5'}
>
	{#if showHeader}
		<div class="mb-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
			<div class="flex flex-wrap items-center gap-3">
				<h2 class="text-xs font-semibold uppercase tracking-[0.18em] text-fg-4">
					Filters
				</h2>
				{#if selectedCount > 0}
					<div
						class="ui-selection-badge flex items-center gap-2 px-2.5 py-1 text-xs font-medium"
					>
						<span>{selectedCount} selected</span>
					</div>
				{/if}
			</div>
			<div class="flex items-center gap-2">
				<button
					onclick={resetFilters}
					data-variant="secondary"
					class="ui-button px-3 py-2 text-sm font-medium"
				>
					Reset
				</button>

				<button
					onclick={onExport}
					data-variant="primary"
					class="ui-button px-3 py-2 text-sm"
				>
					Export {selectedCount > 0 ? '(' + selectedCount + ')' : '(100 max)'}
				</button>
			</div>
		</div>
	{/if}

	<div class="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
		{#if prefix}
			{@render prefix()}
		{/if}
		{#each filterDefinitions as filter (filter.id)}
			<div class="flex flex-col gap-2">
				<!-- Reverted back to <label> tag -->
				<label for={controlId(filter.id)} class="block text-sm font-medium text-fg-1">
					{filter.label}
				</label>

				{#if filter.type === 'searchable'}
					<SearchableDropdown
						id={controlId(filter.id)}
						ariaLabel={filter.label}
						options={filter.options || []}
						value={getFilterValue(filter.id)}
						onchange={(v) => setFilterValue(filter.id, v)}
					/>
				{:else if filter.type === 'standard'}
					<StandardDropdown
						id={controlId(filter.id)}
						ariaLabel={filter.label}
						options={filter.options || []}
						value={getFilterValue(filter.id)}
						onchange={(v) => setFilterValue(filter.id, v)}
					/>
				{:else if filter.type === 'checkbox'}
					<CheckboxDropdown
						id={controlId(filter.id)}
						ariaLabel={filter.label}
						options={(filter.options || []).map((o) => ({ id: o, label: o }))}
						selected={filters[filter.id] ?? {}}
						onchange={(selected) => setFilterValue(filter.id, selected)}
					/>
				{/if}
			</div>
		{/each}
	</div>
</div>
