<script lang="ts">
import { createQuery } from '@tanstack/svelte-query'
import { RotateCcw } from 'lucide-svelte'
import type { ProjectSearchItem } from '$lib/api/analytics'
import {
	type TransactionExportFormat,
	type TransactionResponseOutput,
	transactions
} from '$lib/api/transactions'
import ProjectSelector from '$lib/components/analytics/ProjectSelector.svelte'
import SearchableDropdown from '$lib/components/dropdowns/SearchableDropdown.svelte'
import FilterPanel from '$lib/components/filters/FilterPanel.svelte'
import { propertyType, timeframe } from '$lib/components/filters/globalFilters.svelte'
import DataPanel from '$lib/components/transactions/DataPanel.svelte'
import TransactionDetailsModal from '$lib/components/transactions/TransactionDetailsModal.svelte'
import Pagination from '$lib/components/ui/Pagination.svelte'
import {
	COMMERCIAL_COLUMNS,
	DEFAULT_ITEMS_PER_PAGE,
	PROPERTY_USAGE,
	RESIDENTIAL_COLUMNS
} from '$lib/constants/transactions'
import { analyticsQueries } from '$lib/queries/analytics'
import { transactionQueries } from '$lib/queries/transactions'
import type { FilterDefinition } from '$lib/types/filters'
import {
	buildSalesApiFilters,
	buildSalesFilterParams,
	DEFAULT_SALES_LOCAL_FILTERS,
	SALES_AREA_OPTIONS,
	SALES_PRICE_OPTIONS,
	SALES_PRICE_SQM_OPTIONS,
	type SalesLocalFilters,
	withSelectedIds
} from '$lib/utils/transactionPages'

interface TransformedTransaction {
	transaction_id: string
	date: string
	area_name: string
	project: string
	building: string
	propertyType: string
	propertySubType: string
	bedrooms: string
	area: number
	price: number
	pricePerSqM: number
	registration: string
	trans_group: string
	procedure_name: string
	landmark: string
	metro: string
	mall: string
}

type FilterChip = {
	label: string
	value: string
}

// Dropdown context is provided by transactions/+layout.svelte

let currentPage = $state(1)
let selectedTransactionIds = $state(new Set<string>())
let selectedTransaction = $state<TransformedTransaction | null>(null)

// Project selection (outside FilterPanel — uses canonical groupings)
let selectedProject = $state<ProjectSearchItem | null>(null)
let selectedSubProject = $state<string | null>(null)

let localFilters = $state<SalesLocalFilters>({ ...DEFAULT_SALES_LOCAL_FILTERS })

// Sub-projects query — enabled when a master or virtual_master is selected
const subProjectsQuery = createQuery(() =>
	analyticsQueries.subProjects(selectedProject?.name ?? null, selectedProject?.filter_type ?? null)
)

const subProjectOptions = $derived(subProjectsQuery.data?.sub_projects.map((p) => p.name) ?? [])

function buildApiFilters() {
	return buildSalesApiFilters({
		propertyUsage: propertyType.current,
		timeframe: timeframe.current,
		currentPage,
		selectedProject,
		selectedSubProject,
		localFilters
	})
}

const salesApiFilters = $derived(buildApiFilters())

function buildFacetFilterParams(localFilterOverrides: Partial<SalesLocalFilters> = {}) {
	return buildSalesFilterParams({
		propertyUsage: propertyType.current,
		timeframe: timeframe.current,
		selectedProject,
		selectedSubProject,
		localFilters: { ...localFilters, ...localFilterOverrides }
	})
}

// Main transactions query
const transactionsQuery = createQuery(() => transactionQueries.sales(salesApiFilters))

// One shared facet payload avoids four concurrent full-table scans on first
// load. The selected value stays available in the control until the next
// filter refresh, while the table can render immediately.
const facetOptionsQuery = createQuery(() => transactionQueries.salesFilterOptions(buildFacetFilterParams()))

let columns = $derived(
	propertyType.current === PROPERTY_USAGE.RESIDENTIAL ? RESIDENTIAL_COLUMNS : COMMERCIAL_COLUMNS
)

const buildingOptions = $derived(facetOptionsQuery.data)
const propertyTypeOptions = $derived(facetOptionsQuery.data)
const bedroomsOrSubTypeOptions = $derived(facetOptionsQuery.data)
const registrationOptions = $derived(facetOptionsQuery.data)

let filterDefinitions = $derived<FilterDefinition[]>([
	{
		id: 'selectedBuilding',
		label: 'Building',
		type: 'searchable',
		options: ['All', ...(buildingOptions?.buildings ?? [])]
	},
	{
		id: 'selectedPropertyType',
		label: 'Property Type',
		type: 'standard',
		options: ['All', ...(propertyTypeOptions?.property_types ?? [])]
	},
	{
		id: 'selectedBedroomsOrSubType',
		label: propertyType.current === PROPERTY_USAGE.RESIDENTIAL ? 'Bedrooms' : 'Sub Type',
		type: 'standard',
		options: [
			'All',
			...(propertyType.current === PROPERTY_USAGE.RESIDENTIAL
				? (bedroomsOrSubTypeOptions?.rooms ?? [])
				: (bedroomsOrSubTypeOptions?.property_sub_types ?? []))
		]
	},
	{
		id: 'selectedRegistration',
		label: 'Registration',
		type: 'standard',
		options: ['All', ...(registrationOptions?.registration_types ?? [])]
	},
	{
		id: 'areaRange',
		label: 'Area (sq.m)',
		type: 'standard',
		options: [...SALES_AREA_OPTIONS]
	},
	{
		id: 'priceRange',
		label: 'Price (AED)',
		type: 'standard',
		options: [...SALES_PRICE_OPTIONS]
	},
	{
		id: 'pricePerSqMRange',
		label: 'Price/sq.m (AED)',
		type: 'standard',
		options: [...SALES_PRICE_SQM_OPTIONS]
	}
])

function transformTransaction(t: TransactionResponseOutput): TransformedTransaction {
	return {
		transaction_id: t.transaction_id,
		date: t.instance_date ?? '-',
		area_name: t.area_name_en ?? '-',
		project: t.project_name_en ?? '-',
		building: t.building_name_en ?? '-',
		propertyType: t.property_type_en ?? '-',
		propertySubType: t.property_sub_type_en ?? '-',
		bedrooms: t.rooms_en ?? '-',
		area: t.procedure_area ?? 0,
		price: t.actual_worth ?? 0,
		pricePerSqM: t.meter_sale_price ?? 0,
		registration: t.reg_type_en ?? '-',
		trans_group: t.trans_group_en ?? '-',
		procedure_name: t.procedure_name_en ?? '-',
		landmark: t.nearest_landmark_en ?? '-',
		metro: t.nearest_metro_en ?? '-',
		mall: t.nearest_mall_en ?? '-'
	}
}

function getRowId(row: TransformedTransaction): string {
	return row.transaction_id
}

let displayData = $derived(transactionsQuery.data?.transactions.map(transformTransaction) ?? [])

let totalRecords = $derived(transactionsQuery.data?.total ?? 0)
let totalPages = $derived(Math.ceil(totalRecords / DEFAULT_ITEMS_PER_PAGE))

function resetFilters() {
	selectedProject = null
	selectedSubProject = null
	localFilters = { ...DEFAULT_SALES_LOCAL_FILTERS }
	currentPage = 1
}

function addSelectedChip(chips: FilterChip[], label: string, value: string) {
	if (value && value !== 'All') chips.push({ label, value })
}

function buildActiveFilterChips(): FilterChip[] {
	const chips: FilterChip[] = [
		{ label: 'Dataset', value: propertyType.current },
		{ label: 'Period', value: timeframe.current },
		{ label: 'Project', value: selectedSubProject ?? selectedProject?.name ?? 'All projects' }
	]

	addSelectedChip(chips, 'Building', localFilters.selectedBuilding)
	addSelectedChip(chips, 'Property type', localFilters.selectedPropertyType)
	addSelectedChip(
		chips,
		propertyType.current === PROPERTY_USAGE.RESIDENTIAL ? 'Bedrooms' : 'Sub type',
		localFilters.selectedBedroomsOrSubType
	)
	addSelectedChip(chips, 'Registration', localFilters.selectedRegistration)
	addSelectedChip(chips, 'Area', localFilters.areaRange)
	addSelectedChip(chips, 'Price', localFilters.priceRange)
	addSelectedChip(chips, 'Price/sq.m', localFilters.pricePerSqMRange)

	return chips
}

let activeFilterChips = $derived(buildActiveFilterChips())

function handleRowClick(row: TransformedTransaction) {
	selectedTransaction = row
}

// Track filter changes to reset page
let filterKey = $derived(
	JSON.stringify({
		project: selectedProject?.name,
		filterType: selectedProject?.filter_type,
		subProject: selectedSubProject,
		building: localFilters.selectedBuilding,
		propertyType: localFilters.selectedPropertyType,
		bedroomsOrSubType: localFilters.selectedBedroomsOrSubType,
		registration: localFilters.selectedRegistration,
		areaRange: localFilters.areaRange,
		priceRange: localFilters.priceRange,
		pricePerSqMRange: localFilters.pricePerSqMRange
	})
)

let lastFilterKey = ''

// Reset to page 1 when filters change
$effect(() => {
	if (filterKey !== lastFilterKey) {
		if (lastFilterKey !== '') {
			currentPage = 1
			selectedTransactionIds = new Set() // Clear selection on filter change
		}
		lastFilterKey = filterKey
	}
})

// Reset page and filters on global filter changes
$effect(() => {
	const _ = [propertyType.current, timeframe.current]
	currentPage = 1
	resetFilters()
	selectedTransactionIds = new Set() // Clear selection on global filter change
})

let exportingFormat = $state<TransactionExportFormat | null>(null)

async function handleExport(format: TransactionExportFormat) {
	exportingFormat = format
	try {
		const filters = withSelectedIds(buildApiFilters(), 'transaction_ids', selectedTransactionIds)
		const blob = await transactions.exportSales(filters, format)

		const url = window.URL.createObjectURL(blob)
		const a = document.createElement('a')
		a.href = url
		a.download = `sales_export_${Date.now()}.${format}`
		document.body.appendChild(a)
		a.click()
		window.URL.revokeObjectURL(url)
		document.body.removeChild(a)
	} catch (error) {
		console.error('Export failed:', error)
		alert(`Failed to export data: ${error instanceof Error ? error.message : 'Unknown error'}`)
	} finally {
		exportingFormat = null
	}
}
</script>

{#if transactionsQuery.isError}
	<div class="mb-6 rounded-lg border border-[rgba(163,36,36,0.2)] bg-error-bg p-6 text-center">
		<p class="font-semibold text-error">Error loading data</p>
		<p class="mt-2 text-error">{transactionsQuery.error?.message ?? 'Unknown error'}</p>
		<button
			onclick={() => transactionsQuery.refetch()}
			class="mt-4 rounded-md border border-navy bg-navy px-4 py-2 text-sm font-medium text-on-navy transition-colors hover:bg-primary-hover"
		>
			Retry
		</button>
	</div>
{/if}

{#snippet desktopProjectControls()}
	<div class="flex flex-col gap-2">
		<label for="sales-project-desktop" class="block text-sm font-medium text-fg-1">Project</label>
		<ProjectSelector
			bind:value={selectedProject}
			placeholder="Search project..."
			onSelect={() => {
				selectedSubProject = null;
				currentPage = 1;
			}}
		/>
	</div>
	{#if selectedProject && selectedProject.filter_type !== 'project'}
		<div class="flex flex-col gap-2">
			<label for="sales-sub-project-desktop-button" class="block text-sm font-medium text-fg-1">
				Sub-project
			</label>
			<SearchableDropdown
				id="sales-sub-project-desktop"
				ariaLabel="Sub-project"
				options={['All', ...subProjectOptions]}
				value={selectedSubProject ?? 'All'}
				onchange={(v) => {
					selectedSubProject = v === 'All' ? null : v;
					currentPage = 1;
				}}
			/>
		</div>
	{/if}
{/snippet}

<div class="ui-surface relative z-20 p-4 sm:p-5">
	<div class="mb-4 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
		<div>
			<p class="text-xs font-semibold uppercase tracking-[0.18em] text-fg-4">
				Market controls
			</p>
			<p class="mt-1 text-sm text-fg-3">
				Scope the dataset and apply local transaction filters.
			</p>
		</div>
		<button
			type="button"
			onclick={resetFilters}
			data-variant="secondary"
			class="ui-button h-9 w-fit shrink-0 gap-2 px-3 text-xs font-medium sm:h-10 sm:text-sm"
		>
			<RotateCcw size={15} strokeWidth={1.8} />
			Reset filters
		</button>
	</div>
	<div class="mb-4 grid grid-cols-1 gap-3 border-b border-border pb-4 sm:grid-cols-2 lg:hidden">
		<div class="flex flex-col gap-2">
			<label for="sales-project" class="block text-sm font-medium text-fg-1">Project</label>
			<ProjectSelector
				bind:value={selectedProject}
				placeholder="Search project..."
				onSelect={() => {
					selectedSubProject = null;
					currentPage = 1;
				}}
			/>
		</div>
		{#if selectedProject && selectedProject.filter_type !== 'project'}
			<div class="flex flex-col gap-2">
				<label for="sales-sub-project-button" class="block text-sm font-medium text-fg-1">
					Sub-project
				</label>
				<SearchableDropdown
					id="sales-sub-project"
					ariaLabel="Sub-project"
					options={['All', ...subProjectOptions]}
					value={selectedSubProject ?? 'All'}
					onchange={(v) => {
						selectedSubProject = v === 'All' ? null : v;
						currentPage = 1;
					}}
				/>
			</div>
		{/if}
	</div>
	<div class="hidden lg:block">
		<FilterPanel
			{filterDefinitions}
			bind:filters={localFilters}
			onReset={resetFilters}
			embedded={true}
			showHeader={false}
			idPrefix="sales-filters-desktop"
			prefix={desktopProjectControls}
		/>
	</div>
	<details class="ui-panel overflow-hidden lg:hidden">
		<summary class="cursor-pointer px-3 py-2.5 text-sm font-semibold text-fg-1">
			Local filters
		</summary>
		<div class="border-t border-border bg-card p-3">
			<FilterPanel
				{filterDefinitions}
				bind:filters={localFilters}
				onReset={resetFilters}
				embedded={true}
				showHeader={false}
				idPrefix="sales-filters-mobile"
			/>
		</div>
	</details>
</div>

<div
	class="mb-4 flex flex-col gap-3 rounded-md border border-border bg-card px-4 py-3 lg:flex-row lg:items-center lg:justify-between"
>
	<div class="min-w-0">
		<p class="text-xs font-semibold uppercase tracking-[0.18em] text-fg-4">Active filters</p>
		<div class="mt-2 flex flex-wrap gap-2">
			{#each activeFilterChips as chip (chip.label)}
				<span class="rounded-sm border border-border bg-elevated px-2 py-1 text-xs text-fg-2">
					<span class="font-medium text-fg-4">{chip.label}</span>
					<span class="ml-1 font-semibold text-fg-1">{chip.value}</span>
				</span>
			{/each}
		</div>
	</div>
	<div class="shrink-0 text-sm font-medium text-fg-2">
		{totalRecords.toLocaleString()} matching transactions
	</div>
</div>

<DataPanel
	title="Sales records"
	description={selectedTransactionIds.size > 0
		? `Exporting ${selectedTransactionIds.size} selected rows as Excel or raw CSV.`
		: 'Export filtered rows as DLD-metadata Excel or raw CSV, up to 50,000 rows.'}
	exportActions={[
		{
			label: 'Excel',
			onClick: () => handleExport('xlsx'),
			disabled: exportingFormat !== null
		},
		{
			label: 'CSV',
			onClick: () => handleExport('csv'),
			disabled: exportingFormat !== null,
			variant: 'secondary'
		}
	]}
	{columns}
	data={displayData}
	onrowclick={handleRowClick}
	loading={transactionsQuery.isPending && displayData.length === 0}
	selectable={true}
	bind:selectedIds={selectedTransactionIds}
	{getRowId}
/>

<div class="mt-2 px-1">
	<Pagination
		bind:currentPage
		{totalPages}
		totalItems={totalRecords}
		itemsPerPage={DEFAULT_ITEMS_PER_PAGE}
		itemLabel="transactions"
	/>
</div>

<TransactionDetailsModal
	transaction={selectedTransaction}
	onClose={() => (selectedTransaction = null)}
/>
