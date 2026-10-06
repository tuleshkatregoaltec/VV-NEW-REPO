<script lang="ts">
import { createQuery } from '@tanstack/svelte-query'
import { RotateCcw } from 'lucide-svelte'
import type { ProjectSearchItem } from '$lib/api/analytics'
import {
	type RentalContractResponseOutput,
	type TransactionExportFormat,
	transactions
} from '$lib/api/transactions'
import ProjectSelector from '$lib/components/analytics/ProjectSelector.svelte'
import SearchableDropdown from '$lib/components/dropdowns/SearchableDropdown.svelte'
import FilterPanel from '$lib/components/filters/FilterPanel.svelte'
import { propertyType, timeframe } from '$lib/components/filters/globalFilters.svelte'
import DataPanel from '$lib/components/transactions/DataPanel.svelte'
import Pagination from '$lib/components/ui/Pagination.svelte'
import { DEFAULT_ITEMS_PER_PAGE } from '$lib/constants/transactions'
import { analyticsQueries } from '$lib/queries/analytics'
import { transactionQueries } from '$lib/queries/transactions'
import type { FilterDefinition } from '$lib/types/filters'
import {
	buildRentalsApiFilters,
	buildRentalsFilterParams,
	DEFAULT_RENTALS_LOCAL_FILTERS,
	RENTAL_ANNUAL_RENT_OPTIONS,
	type RentalsLocalFilters,
	SALES_AREA_OPTIONS,
	withSelectedIds
} from '$lib/utils/transactionPages'

interface TransformedRental {
	contract_id: string
	startDate: string
	endDate: string
	area_name: string
	project: string
	propertyType: string
	propertySubType: string
	tenantType: string
	area: number
	annualRent: number
	registration: string
	contractAmount: number | null
	numProperties: number | null
	freehold: string
	landmark: string
	metro: string
	mall: string
}

type FilterChip = {
	label: string
	value: string
}

// Column configuration for rentals
const RENTAL_COLUMNS = [
	{ id: 'startDate', label: 'Start Date', align: 'left' as const, defaultVisible: true },
	{ id: 'endDate', label: 'End Date', align: 'left' as const, defaultVisible: true },
	{ id: 'area_name', label: 'Area', align: 'left' as const, defaultVisible: false },
	{ id: 'project', label: 'Project', align: 'left' as const, defaultVisible: true },
	{ id: 'propertyType', label: 'Property Type', align: 'left' as const, defaultVisible: true },
	{ id: 'propertySubType', label: 'Sub Type', align: 'left' as const, defaultVisible: true },
	{
		id: 'tenantType',
		label: 'Tenant Type',
		align: 'left' as const,
		badge: true,
		defaultVisible: true
	},
	{
		id: 'area',
		label: 'Area (sq.m)',
		align: 'right' as const,
		format: (val: number) => val.toLocaleString(),
		defaultVisible: true
	},
	{
		id: 'annualRent',
		label: 'Annual Rent (AED)',
		align: 'right' as const,
		highlighted: true,
		format: (val: number) => val.toLocaleString(),
		defaultVisible: true
	},
	{ id: 'registration', label: 'Reg Type', align: 'left' as const, defaultVisible: false },
	{
		id: 'contractAmount',
		label: 'Contract Amount (AED)',
		align: 'right' as const,
		format: (val: number) => val?.toLocaleString() ?? '-',
		defaultVisible: false
	},
	{ id: 'numProperties', label: '# Properties', align: 'right' as const, defaultVisible: false },
	{ id: 'freehold', label: 'Freehold', align: 'left' as const, defaultVisible: false },
	{ id: 'landmark', label: 'Landmark', align: 'left' as const, defaultVisible: false },
	{ id: 'metro', label: 'Nearest Metro', align: 'left' as const, defaultVisible: false },
	{ id: 'mall', label: 'Nearest Mall', align: 'left' as const, defaultVisible: false }
]

// Dropdown context is provided by transactions/+layout.svelte

// ========================================
// Local State
// ========================================
let currentPage = $state(1)
let selectedContractIds = $state(new Set<string>())

// Project selection (outside FilterPanel — uses canonical groupings)
let selectedProject = $state<ProjectSearchItem | null>(null)
let selectedSubProject = $state<string | null>(null)

let localFilters = $state<RentalsLocalFilters>({ ...DEFAULT_RENTALS_LOCAL_FILTERS })

// Sub-projects query — enabled when a master or virtual_master is selected
const subProjectsQuery = createQuery(() =>
	analyticsQueries.subProjects(selectedProject?.name ?? null, selectedProject?.filter_type ?? null)
)

const subProjectOptions = $derived(subProjectsQuery.data?.sub_projects.map((p) => p.name) ?? [])

// ========================================
// Build API Filters
// ========================================
function buildApiFilters() {
	return buildRentalsApiFilters({
		propertyUsage: propertyType.current,
		timeframe: timeframe.current,
		currentPage,
		selectedProject,
		selectedSubProject,
		localFilters
	})
}

// ========================================
// TanStack Queries
// ========================================

const rentalsApiFilters = $derived(buildApiFilters())

// Main rentals query
const rentalsQuery = createQuery(() => transactionQueries.rentals(rentalsApiFilters))

function buildFacetFilterParams(localFilterOverrides: Partial<RentalsLocalFilters> = {}) {
	return buildRentalsFilterParams({
		propertyUsage: propertyType.current,
		timeframe: timeframe.current,
		selectedProject,
		selectedSubProject,
		localFilters: { ...localFilters, ...localFilterOverrides }
	})
}

// Keep the filter controls responsive by fetching their shared facets once,
// rather than issuing four full rental-table scans beside the data request.
const facetOptionsQuery = createQuery(() => transactionQueries.rentalFilterOptions(buildFacetFilterParams()))

// ========================================
// Derived Values
// ========================================

const propertyTypeOptions = $derived(facetOptionsQuery.data)
const propertySubTypeOptions = $derived(facetOptionsQuery.data)
const tenantTypeOptions = $derived(facetOptionsQuery.data)
const registrationOptions = $derived(facetOptionsQuery.data)

let filterDefinitions = $derived<FilterDefinition[]>([
	{
		id: 'selectedPropertyType',
		label: 'Property Type',
		type: 'standard',
		options: ['All', ...(propertyTypeOptions?.property_types ?? [])]
	},
	{
		id: 'selectedPropertySubType',
		label: 'Sub Type',
		type: 'standard',
		options: ['All', ...(propertySubTypeOptions?.property_sub_types ?? [])]
	},
	{
		id: 'selectedTenantType',
		label: 'Tenant Type',
		type: 'standard',
		options: ['All', ...(tenantTypeOptions?.tenant_types ?? [])]
	},
	{
		id: 'selectedRegistration',
		label: 'Reg Type',
		type: 'standard',
		options: ['All', ...(registrationOptions?.contract_reg_types ?? [])]
	},
	{
		id: 'areaRange',
		label: 'Area (sq.m)',
		type: 'standard',
		options: [...SALES_AREA_OPTIONS]
	},
	{
		id: 'rentRange',
		label: 'Annual Rent (AED)',
		type: 'standard',
		options: [...RENTAL_ANNUAL_RENT_OPTIONS]
	}
])

function transformRental(r: RentalContractResponseOutput): TransformedRental {
	return {
		contract_id: r.contract_id,
		startDate: r.contract_start_date ?? '-',
		endDate: r.contract_end_date ?? '-',
		area_name: r.area_name_en ?? '-',
		project: r.project_name_en ?? '-',
		propertyType: r.ejari_property_type_en ?? '-',
		propertySubType: r.ejari_property_sub_type_en ?? '-',
		tenantType: r.tenant_type_en ?? '-',
		area: r.actual_area ?? 0,
		annualRent: r.annual_amount ?? 0,
		registration: r.contract_reg_type_en ?? '-',
		contractAmount: r.contract_amount ?? null,
		numProperties: r.no_of_prop ?? null,
		freehold: r.is_free_hold == null ? '-' : r.is_free_hold ? 'Yes' : 'No',
		landmark: r.nearest_landmark_en ?? '-',
		metro: r.nearest_metro_en ?? '-',
		mall: r.nearest_mall_en ?? '-'
	}
}

function getRowId(row: TransformedRental): string {
	return row.contract_id
}

let displayData = $derived(rentalsQuery.data?.contracts.map(transformRental) ?? [])

let totalRecords = $derived(rentalsQuery.data?.total ?? 0)
let totalPages = $derived(Math.ceil(totalRecords / DEFAULT_ITEMS_PER_PAGE))

const columns = RENTAL_COLUMNS

// ========================================
// Actions
// ========================================

function resetFilters() {
	selectedProject = null
	selectedSubProject = null
	localFilters = { ...DEFAULT_RENTALS_LOCAL_FILTERS }
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

	addSelectedChip(chips, 'Property type', localFilters.selectedPropertyType)
	addSelectedChip(chips, 'Sub type', localFilters.selectedPropertySubType)
	addSelectedChip(chips, 'Tenant type', localFilters.selectedTenantType)
	addSelectedChip(chips, 'Registration', localFilters.selectedRegistration)
	addSelectedChip(chips, 'Area', localFilters.areaRange)
	addSelectedChip(chips, 'Annual rent', localFilters.rentRange)

	return chips
}

let activeFilterChips = $derived(buildActiveFilterChips())

// ========================================
// Effects
// ========================================

// Track filter changes to reset page
let filterKey = $derived(
	JSON.stringify({
		project: selectedProject?.name,
		filterType: selectedProject?.filter_type,
		subProject: selectedSubProject,
		propertyType: localFilters.selectedPropertyType,
		propertySubType: localFilters.selectedPropertySubType,
		tenantType: localFilters.selectedTenantType,
		registration: localFilters.selectedRegistration,
		areaRange: localFilters.areaRange,
		rentRange: localFilters.rentRange
	})
)

let lastFilterKey = ''

// Reset to page 1 when filters change
$effect(() => {
	if (filterKey !== lastFilterKey) {
		if (lastFilterKey !== '') {
			currentPage = 1
			selectedContractIds = new Set() // Clear selection on filter change
		}
		lastFilterKey = filterKey
	}
})

// Reset page and filters on global filter changes
$effect(() => {
	const _ = [propertyType.current, timeframe.current]
	currentPage = 1
	resetFilters()
	selectedContractIds = new Set() // Clear selection on global filter change
})

// Export support (same logic as sales page)
let exportingFormat = $state<TransactionExportFormat | null>(null)

async function handleExport(format: TransactionExportFormat) {
	exportingFormat = format
	try {
		const filters = withSelectedIds(buildApiFilters(), 'contract_ids', selectedContractIds)
		const blob = await transactions.exportRentals(filters, format)

		const url = window.URL.createObjectURL(blob)
		const a = document.createElement('a')
		a.href = url
		a.download = `rentals_export_${Date.now()}.${format}`
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

{#if rentalsQuery.isError}
	<div class="mb-6 rounded-lg border border-[rgba(163,36,36,0.2)] bg-error-bg p-6 text-center">
		<p class="font-semibold text-error">Error loading data</p>
		<p class="mt-2 text-error">{rentalsQuery.error?.message ?? 'Unknown error'}</p>
		<button
			onclick={() => rentalsQuery.refetch()}
			class="mt-4 rounded-md border border-navy bg-navy px-4 py-2 text-sm font-medium text-on-navy transition-colors hover:bg-primary-hover"
		>
			Retry
		</button>
	</div>
{/if}

{#snippet desktopProjectControls()}
	<div class="flex flex-col gap-2">
		<label for="rentals-project-desktop" class="block text-sm font-medium text-fg-1">Project</label>
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
			<label for="rentals-sub-project-desktop-button" class="block text-sm font-medium text-fg-1">
				Sub-project
			</label>
			<SearchableDropdown
				id="rentals-sub-project-desktop"
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
				Scope the dataset and apply local rental filters.
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
			<label for="rentals-project" class="block text-sm font-medium text-fg-1">Project</label>
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
				<label for="rentals-sub-project-button" class="block text-sm font-medium text-fg-1">
					Sub-project
				</label>
				<SearchableDropdown
					id="rentals-sub-project"
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
			idPrefix="rentals-filters-desktop"
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
				idPrefix="rentals-filters-mobile"
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
		{totalRecords.toLocaleString()} matching contracts
	</div>
</div>

<DataPanel
	title="Rental contracts"
	description={selectedContractIds.size > 0
		? `Exporting ${selectedContractIds.size} selected rows as Excel or raw CSV.`
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
	loading={rentalsQuery.isPending && displayData.length === 0}
	selectable={true}
	bind:selectedIds={selectedContractIds}
	{getRowId}
/>

<div class="mt-2 px-1">
	<Pagination
		bind:currentPage
		{totalPages}
		totalItems={totalRecords}
		itemsPerPage={DEFAULT_ITEMS_PER_PAGE}
		itemLabel="contracts"
	/>
</div>
