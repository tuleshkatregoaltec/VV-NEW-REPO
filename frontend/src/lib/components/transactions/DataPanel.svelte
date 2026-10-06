<script lang="ts">
import { Download, X } from 'lucide-svelte'
import ColumnSettingsDropdown from '$lib/components/dropdowns/ColumnSettingsDropdown.svelte'

type ExportAction = {
	label: string
	onClick: () => void
	disabled?: boolean
	variant?: 'primary' | 'secondary'
}

let {
	title = 'Dataset',
	description = 'Visible columns and selected rows update this view.',
	columns = [],
	data = [],
	emptyMessage = 'No data available',
	loading = false,
	onrowclick,
	onExport,
	// Selection props
	selectable = false,
	selectedIds = $bindable(new Set<string>()),
	getRowId,
	exportLabel = 'Export',
	exportDisabled = false,
	exportActions = []
}: {
	title?: string
	description?: string
	columns?: Array<{
		id: string
		label: string
		align?: 'left' | 'center' | 'right'
		format?: (value: any, row: any) => string
		badge?: boolean
		highlighted?: boolean
		defaultVisible?: boolean
	}>
	data?: Array<Record<string, any>>
	emptyMessage?: string
	loading?: boolean
	onrowclick?: (row: any) => void
	onExport?: () => void
	// Selection
	selectable?: boolean
	selectedIds?: Set<string>
	getRowId?: (row: any) => string
	exportLabel?: string
	exportDisabled?: boolean
	exportActions?: ExportAction[]
} = $props()

// Track which columns are visible (using column id as key)
let columnVisibility: Record<string, boolean> = $state({})
let lastColumnsKey = ''

// Initialize column visibility from defaultVisible property when columns change
$effect(() => {
	// Create a key based on column IDs to detect when columns have changed
	const columnsKey = columns.map((c) => c.id).join(',')

	if (columnsKey !== lastColumnsKey) {
		// Columns have changed - reinitialize visibility
		const newVisibility: Record<string, boolean> = {}
		for (const col of columns) {
			// Preserve existing visibility preference if column still exists
			if (col.id in columnVisibility) {
				newVisibility[col.id] = columnVisibility[col.id]
			} else {
				newVisibility[col.id] = col.defaultVisible !== false
			}
		}
		columnVisibility = newVisibility
		lastColumnsKey = columnsKey
	}
})

// All columns are available for toggling
let allColumnOptions = $derived(columns.map((c) => ({ id: c.id, label: c.label })))

let visibleColumns = $derived(columns.filter((c) => columnVisibility[c.id]))

// Get all row IDs on current page
let allRowIds = $derived(data.map((row) => getRowId?.(row) ?? row.id))

// Check if all rows on current page are selected
let allSelected = $derived(
	selectable && data.length > 0 && allRowIds.every((id) => selectedIds.has(id))
)

// Check if some (but not all) rows on current page are selected
let someSelected = $derived(
	selectable && allRowIds.some((id) => selectedIds.has(id)) && !allSelected
)

let selectAllLabel = $derived(
	allSelected
		? `Deselect all ${data.length} rows on this page`
		: `Select all ${data.length} rows on this page`
)

function handleRowClick(row: any) {
	if (onrowclick) {
		onrowclick(row)
		return
	}

	if (selectable) {
		toggleRowSelection(row)
	}
}

function toggleSelectAll() {
	const newSet = new Set(selectedIds)
	if (allSelected) {
		// Deselect all on current page
		allRowIds.forEach((id) => {
			newSet.delete(id)
		})
	} else {
		// Select all on current page
		allRowIds.forEach((id) => {
			newSet.add(id)
		})
	}
	selectedIds = newSet
}

function toggleRowSelection(row: any) {
	const id = getRowId?.(row) ?? row.id
	const newSet = new Set(selectedIds)
	if (newSet.has(id)) {
		newSet.delete(id)
	} else {
		newSet.add(id)
	}
	selectedIds = newSet
}

function isRowSelected(row: any): boolean {
	const id = getRowId?.(row) ?? row.id
	return selectedIds.has(id)
}

function clearSelection() {
	selectedIds = new Set()
}

function getRenderKey(row: any, index: number): string {
	const baseId = String(getRowId?.(row) ?? row.id ?? 'row')
	return [
		baseId,
		row.transaction_id,
		row.contract_id,
		row.date,
		row.startDate,
		row.endDate,
		row.project,
		row.building,
		index
	]
		.filter((value) => value != null && value !== '')
		.join(':')
}
</script>

<div class="ui-surface">
	<!-- Column settings dropdown in upper right -->
	<div class="flex flex-col gap-3 border-b border-border px-4 py-3 lg:flex-row lg:items-center lg:justify-between">
		<div>
			<p class="text-xs font-semibold uppercase tracking-[0.18em] text-fg-4">
				{title}
			</p>
			<p class="mt-1 text-sm text-fg-3">{description}</p>
		</div>
		<div class="flex flex-wrap items-center gap-2">
			{#if selectable && selectedIds.size > 0}
				<div
					class="ui-selection-badge flex items-center gap-2 px-2.5 py-1.5 text-xs font-medium"
				>
					<span>{selectedIds.size} selected</span>
					<button
						type="button"
						onclick={clearSelection}
						class="inline-flex h-6 items-center gap-1 rounded-sm px-1.5 transition-colors hover:bg-elevated hover:text-fg-1"
						aria-label="Clear selection"
					>
						<X size={14} strokeWidth={2} />
						<span class="text-[11px]">Clear</span>
					</button>
				</div>
			{/if}

			{#if exportActions.length > 0}
				{#each exportActions as action, index (action.label)}
					<button
						type="button"
						onclick={action.onClick}
						disabled={action.disabled}
						data-variant={action.variant ?? (index === 0 ? 'primary' : 'secondary')}
						class="ui-button h-10 px-3 text-sm disabled:cursor-not-allowed disabled:opacity-60"
					>
						<Download size={15} strokeWidth={1.8} />
						{action.label}
					</button>
				{/each}
			{:else if onExport}
				<button
					type="button"
					onclick={onExport}
					disabled={exportDisabled}
					data-variant="primary"
					class="ui-button h-10 px-3 text-sm disabled:cursor-not-allowed disabled:opacity-60"
				>
					<Download size={15} strokeWidth={1.8} />
					{exportLabel}
				</button>
			{/if}

			<ColumnSettingsDropdown
				id="column-visibility"
				ariaLabel="Column Settings"
				options={allColumnOptions}
				bind:selected={columnVisibility}
			/>
		</div>
	</div>

	<div class="overflow-x-auto rounded-b-lg">
		<table class="w-full">
			<thead class="ui-table-head">
				<tr>
					{#if selectable}
						<th class="w-14 px-4 py-3">
							<div class="flex items-center justify-center">
								<input
									type="checkbox"
									checked={allSelected}
									indeterminate={someSelected}
									disabled={loading || data.length === 0}
									onchange={toggleSelectAll}
									class="h-[18px] w-[18px] cursor-pointer rounded-sm border-strong accent-navy text-navy focus:outline-none focus-visible:ring-2 focus-visible:ring-focus disabled:cursor-not-allowed disabled:opacity-40"
									aria-label={selectAllLabel}
								/>
							</div>
						</th>
					{/if}
					{#each visibleColumns as column (column.id)}
						<th
							class="whitespace-nowrap px-4 py-3 text-{column.align ||
								'left'} text-[11px] font-semibold uppercase tracking-[0.12em] text-fg-4"
						>
							{column.label}
						</th>
					{/each}
				</tr>
			</thead>
			<tbody class="divide-y divide-slate-100">
				{#if loading}
					<tr>
						<td
							colspan={visibleColumns.length + (selectable ? 1 : 0)}
							class="px-6 py-16 text-center"
						>
							<div class="flex flex-col items-center gap-3">
								<div
									class="inline-block h-8 w-8 animate-spin rounded-full border-b-2 border-navy"
								></div>
								<span class="text-sm text-fg-4">Loading...</span>
							</div>
						</td>
					</tr>
				{:else if data.length === 0}
					<tr>
						<td
							colspan={visibleColumns.length + (selectable ? 1 : 0)}
							class="px-6 py-12 text-center text-sm text-fg-4"
						>
							{emptyMessage}
						</td>
					</tr>
				{:else}
					{#each data as row, index (getRenderKey(row, index))}
						<tr
							onclick={() => handleRowClick(row)}
							class="ui-table-row {onrowclick || selectable ? 'cursor-pointer' : ''}"
						>
							{#if selectable}
								<td class="w-14 px-4 py-3.5">
									<div class="flex items-center justify-center">
										<input
											type="checkbox"
											checked={isRowSelected(row)}
											onchange={() => toggleRowSelection(row)}
											onclick={(event) => event.stopPropagation()}
											class="h-[18px] w-[18px] cursor-pointer rounded-sm border-strong accent-navy text-navy focus:outline-none focus-visible:ring-2 focus-visible:ring-focus"
											aria-label="Select row"
										/>
									</div>
								</td>
							{/if}
							{#each visibleColumns as column (column.id)}
								<td
									class="whitespace-nowrap px-4 py-3.5 text-{column.align ||
										'left'} text-[13px] tabular-nums {column.highlighted
										? 'font-semibold text-info'
										: 'text-fg-1'}"
								>
									{#if column.badge}
										<span
											class="ui-badge px-2.5 py-1 font-mono text-[11px] font-medium tracking-[0.02em]"
										>
											{column.format ? column.format(row[column.id], row) : row[column.id]}
										</span>
									{:else}
										{column.format ? column.format(row[column.id], row) : row[column.id]}
									{/if}
								</td>
							{/each}
						</tr>
					{/each}
				{/if}
			</tbody>
		</table>
	</div>
</div>
