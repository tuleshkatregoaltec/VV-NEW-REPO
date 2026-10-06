import type { ProjectSearchItem } from '$lib/api/analytics'
import type {
	RentalFacetFilters,
	RentalTransactionFilters,
	SalesFacetFilters,
	SalesTransactionFilters
} from '$lib/api/transactions'
import {
	DEFAULT_ITEMS_PER_PAGE,
	PROPERTY_USAGE,
	TIMEFRAME_MAPPING
} from '$lib/constants/transactions'

export const SALES_AREA_OPTIONS = ['All', '<50', '50-100', '100-200', '200-500', '>500'] as const
export const SALES_PRICE_OPTIONS = ['All', '<500k', '500k-1M', '1M-2M', '2M-5M', '>5M'] as const
export const SALES_PRICE_SQM_OPTIONS = [
	'All',
	'<10000',
	'10000-20000',
	'20000-30000',
	'>30000'
] as const
export const RENTAL_ANNUAL_RENT_OPTIONS = ['All', '<50k', '50k-100k', '100k-200k', '>200k'] as const

export interface SalesLocalFilters {
	selectedBuilding: string
	selectedPropertyType: string
	selectedBedroomsOrSubType: string
	selectedRegistration: string
	areaRange: string
	priceRange: string
	pricePerSqMRange: string
}

export interface RentalsLocalFilters {
	selectedPropertyType: string
	selectedPropertySubType: string
	selectedTenantType: string
	selectedRegistration: string
	areaRange: string
	rentRange: string
}

export const DEFAULT_SALES_LOCAL_FILTERS: SalesLocalFilters = {
	selectedBuilding: 'All',
	selectedPropertyType: 'All',
	selectedBedroomsOrSubType: 'All',
	selectedRegistration: 'All',
	areaRange: 'All',
	priceRange: 'All',
	pricePerSqMRange: 'All'
}

export const DEFAULT_RENTALS_LOCAL_FILTERS: RentalsLocalFilters = {
	selectedPropertyType: 'All',
	selectedPropertySubType: 'All',
	selectedTenantType: 'All',
	selectedRegistration: 'All',
	areaRange: 'All',
	rentRange: 'All'
}

interface BaseFilterContext {
	propertyUsage: string
	timeframe: string
	currentPage: number
	selectedProject: ProjectSearchItem | null
	selectedSubProject: string | null
}

const AREA_RANGES: Record<string, { min?: number; max?: number }> = {
	'<50': { max: 50 },
	'50-100': { min: 50, max: 100 },
	'100-200': { min: 100, max: 200 },
	'200-500': { min: 200, max: 500 },
	'>500': { min: 500 }
}

const SALES_PRICE_RANGES: Record<string, { min?: number; max?: number }> = {
	'<500k': { max: 500_000 },
	'500k-1M': { min: 500_000, max: 1_000_000 },
	'1M-2M': { min: 1_000_000, max: 2_000_000 },
	'2M-5M': { min: 2_000_000, max: 5_000_000 },
	'>5M': { min: 5_000_000 }
}

const SALES_PRICE_SQM_RANGES: Record<string, { min?: number; max?: number }> = {
	'<10000': { max: 10_000 },
	'10000-20000': { min: 10_000, max: 20_000 },
	'20000-30000': { min: 20_000, max: 30_000 },
	'>30000': { min: 30_000 }
}

const RENTAL_PRICE_RANGES: Record<string, { min?: number; max?: number }> = {
	'<50k': { max: 50_000 },
	'50k-100k': { min: 50_000, max: 100_000 },
	'100k-200k': { min: 100_000, max: 200_000 },
	'>200k': { min: 200_000 }
}

function isSelected(value: string | null | undefined): value is string {
	return Boolean(value && value !== 'All')
}

function applyProjectFilters(
	filters:
		| SalesTransactionFilters
		| RentalTransactionFilters
		| SalesFacetFilters
		| RentalFacetFilters,
	selectedProject: ProjectSearchItem | null,
	selectedSubProject: string | null
) {
	if (selectedSubProject) {
		filters.project = selectedSubProject
		filters.filter_type = 'project'
	} else if (selectedProject) {
		filters.project = selectedProject.name
		filters.filter_type = selectedProject.filter_type
	}
}

function applyRange(
	filters: object,
	selectedRange: string,
	ranges: Record<string, { min?: number; max?: number }>,
	minKey: string,
	maxKey: string
) {
	if (!isSelected(selectedRange)) return
	const range = ranges[selectedRange]
	if (!range) return
	const mutableFilters = filters as Record<string, number | string | undefined>
	if (range.min !== undefined) mutableFilters[minKey] = range.min
	if (range.max !== undefined) mutableFilters[maxKey] = range.max
}

export function buildSalesApiFilters(
	context: BaseFilterContext & { localFilters: SalesLocalFilters }
): SalesTransactionFilters {
	const filters: SalesTransactionFilters = {
		property_usage: context.propertyUsage,
		timeframe_days: TIMEFRAME_MAPPING[context.timeframe],
		limit: DEFAULT_ITEMS_PER_PAGE,
		offset: (context.currentPage - 1) * DEFAULT_ITEMS_PER_PAGE
	}

	applyProjectFilters(filters, context.selectedProject, context.selectedSubProject)

	if (isSelected(context.localFilters.selectedBuilding)) {
		filters.building = context.localFilters.selectedBuilding
	}
	if (isSelected(context.localFilters.selectedPropertyType)) {
		filters.property_type = context.localFilters.selectedPropertyType
	}
	if (isSelected(context.localFilters.selectedBedroomsOrSubType)) {
		if (context.propertyUsage === PROPERTY_USAGE.RESIDENTIAL) {
			filters.rooms = context.localFilters.selectedBedroomsOrSubType
		} else {
			filters.property_sub_type = context.localFilters.selectedBedroomsOrSubType
		}
	}
	if (isSelected(context.localFilters.selectedRegistration)) {
		filters.registration_type = context.localFilters.selectedRegistration
	}

	applyRange(filters, context.localFilters.areaRange, AREA_RANGES, 'area_min', 'area_max')
	applyRange(filters, context.localFilters.priceRange, SALES_PRICE_RANGES, 'price_min', 'price_max')
	applyRange(
		filters,
		context.localFilters.pricePerSqMRange,
		SALES_PRICE_SQM_RANGES,
		'price_per_sqm_min',
		'price_per_sqm_max'
	)

	return filters
}

export function buildSalesFilterParams(
	context: Omit<BaseFilterContext, 'currentPage'> & { localFilters: SalesLocalFilters }
): SalesFacetFilters {
	const filters: SalesFacetFilters = {
		property_usage: context.propertyUsage,
		timeframe_days: TIMEFRAME_MAPPING[context.timeframe]
	}

	applyProjectFilters(filters, context.selectedProject, context.selectedSubProject)

	if (isSelected(context.localFilters.selectedBuilding)) {
		filters.building = context.localFilters.selectedBuilding
	}
	if (isSelected(context.localFilters.selectedPropertyType)) {
		filters.property_type = context.localFilters.selectedPropertyType
	}
	if (isSelected(context.localFilters.selectedBedroomsOrSubType)) {
		if (context.propertyUsage === PROPERTY_USAGE.RESIDENTIAL) {
			filters.rooms = context.localFilters.selectedBedroomsOrSubType
		} else {
			filters.property_sub_type = context.localFilters.selectedBedroomsOrSubType
		}
	}
	if (isSelected(context.localFilters.selectedRegistration)) {
		filters.registration_type = context.localFilters.selectedRegistration
	}

	applyRange(filters, context.localFilters.areaRange, AREA_RANGES, 'area_min', 'area_max')
	applyRange(filters, context.localFilters.priceRange, SALES_PRICE_RANGES, 'price_min', 'price_max')
	applyRange(
		filters,
		context.localFilters.pricePerSqMRange,
		SALES_PRICE_SQM_RANGES,
		'price_per_sqm_min',
		'price_per_sqm_max'
	)

	return filters
}

export function buildRentalsApiFilters(
	context: BaseFilterContext & { localFilters: RentalsLocalFilters }
): RentalTransactionFilters {
	const filters: RentalTransactionFilters = {
		property_usage: context.propertyUsage,
		timeframe_days: TIMEFRAME_MAPPING[context.timeframe],
		limit: DEFAULT_ITEMS_PER_PAGE,
		offset: (context.currentPage - 1) * DEFAULT_ITEMS_PER_PAGE
	}

	applyProjectFilters(filters, context.selectedProject, context.selectedSubProject)

	if (isSelected(context.localFilters.selectedPropertyType)) {
		filters.property_type = context.localFilters.selectedPropertyType
	}
	if (isSelected(context.localFilters.selectedPropertySubType)) {
		filters.property_sub_type = context.localFilters.selectedPropertySubType
	}
	if (isSelected(context.localFilters.selectedTenantType)) {
		filters.tenant_type = context.localFilters.selectedTenantType
	}
	if (isSelected(context.localFilters.selectedRegistration)) {
		filters.contract_reg_type = context.localFilters.selectedRegistration
	}

	applyRange(filters, context.localFilters.areaRange, AREA_RANGES, 'area_min', 'area_max')
	applyRange(filters, context.localFilters.rentRange, RENTAL_PRICE_RANGES, 'rent_min', 'rent_max')

	return filters
}

export function buildRentalsFilterParams(
	context: Omit<BaseFilterContext, 'currentPage'> & { localFilters: RentalsLocalFilters }
): RentalFacetFilters {
	const filters: RentalFacetFilters = {
		property_usage: context.propertyUsage,
		timeframe_days: TIMEFRAME_MAPPING[context.timeframe]
	}

	applyProjectFilters(filters, context.selectedProject, context.selectedSubProject)

	if (isSelected(context.localFilters.selectedPropertyType)) {
		filters.property_type = context.localFilters.selectedPropertyType
	}
	if (isSelected(context.localFilters.selectedPropertySubType)) {
		filters.property_sub_type = context.localFilters.selectedPropertySubType
	}
	if (isSelected(context.localFilters.selectedTenantType)) {
		filters.tenant_type = context.localFilters.selectedTenantType
	}
	if (isSelected(context.localFilters.selectedRegistration)) {
		filters.contract_reg_type = context.localFilters.selectedRegistration
	}

	applyRange(filters, context.localFilters.areaRange, AREA_RANGES, 'area_min', 'area_max')
	applyRange(filters, context.localFilters.rentRange, RENTAL_PRICE_RANGES, 'rent_min', 'rent_max')

	return filters
}

export function withSelectedIds<T extends SalesTransactionFilters | RentalTransactionFilters>(
	filters: T,
	key: 'transaction_ids' | 'contract_ids',
	selectedIds: Set<string>
): T {
	if (selectedIds.size === 0) return filters

	return {
		...filters,
		[key]: Array.from(selectedIds).join(',')
	} as T
}
