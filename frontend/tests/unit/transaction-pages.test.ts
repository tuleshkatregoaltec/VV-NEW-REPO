import { describe, expect, it } from 'vitest'

import type { ProjectSearchItem } from '$lib/api/analytics'
import { PROPERTY_USAGE } from '$lib/constants/transactions'
import {
	buildRentalsApiFilters,
	buildRentalsFilterParams,
	buildSalesApiFilters,
	buildSalesFilterParams,
	withSelectedIds
} from '$lib/utils/transactionPages'

function makeProject(overrides: Partial<ProjectSearchItem> = {}): ProjectSearchItem {
	return {
		name: 'Downtown Views',
		filter_type: 'master',
		...overrides
	}
}

describe('transaction page helpers', () => {
	it('builds sales filters for residential pages and selected transaction exports', () => {
		const filters = buildSalesApiFilters({
			propertyUsage: PROPERTY_USAGE.RESIDENTIAL,
			timeframe: 'Last Month',
			currentPage: 2,
			selectedProject: makeProject(),
			selectedSubProject: null,
			localFilters: {
				selectedBuilding: 'Tower A',
				selectedPropertyType: 'Apartment',
				selectedBedroomsOrSubType: '2BR',
				selectedRegistration: 'Freehold',
				areaRange: '100-200',
				priceRange: '1M-2M',
				pricePerSqMRange: '20000-30000'
			}
		})

		expect(filters).toEqual({
			property_usage: 'Residential',
			timeframe_days: 30,
			limit: 30,
			offset: 30,
			project: 'Downtown Views',
			filter_type: 'master',
			building: 'Tower A',
			property_type: 'Apartment',
			rooms: '2BR',
			registration_type: 'Freehold',
			area_min: 100,
			area_max: 200,
			price_min: 1000000,
			price_max: 2000000,
			price_per_sqm_min: 20000,
			price_per_sqm_max: 30000
		})

		expect(withSelectedIds(filters, 'transaction_ids', new Set(['tx-1', 'tx-2']))).toMatchObject({
			transaction_ids: 'tx-1,tx-2'
		})
	})

	it('builds sales filters for commercial pages and filter-option requests', () => {
		const selectedProject = makeProject({ name: 'Business Bay', filter_type: 'virtual_master' })
		const filters = buildSalesApiFilters({
			propertyUsage: PROPERTY_USAGE.COMMERCIAL,
			timeframe: 'Last Year',
			currentPage: 1,
			selectedProject,
			selectedSubProject: 'The Binary',
			localFilters: {
				selectedBuilding: 'All',
				selectedPropertyType: 'Office',
				selectedBedroomsOrSubType: 'Shell & Core',
				selectedRegistration: 'All',
				areaRange: 'All',
				priceRange: 'All',
				pricePerSqMRange: 'All'
			}
		})

		expect(filters).toEqual({
			property_usage: 'Commercial',
			timeframe_days: 365,
			limit: 30,
			offset: 0,
			project: 'The Binary',
			filter_type: 'project',
			property_type: 'Office',
			property_sub_type: 'Shell & Core'
		})

		expect(
			buildSalesFilterParams({
				propertyUsage: PROPERTY_USAGE.COMMERCIAL,
				timeframe: 'Last Year',
				selectedProject,
				selectedSubProject: 'The Binary',
				localFilters: {
					selectedBuilding: 'All',
					selectedPropertyType: 'Office',
					selectedBedroomsOrSubType: 'All',
					selectedRegistration: 'All',
					areaRange: 'All',
					priceRange: 'All',
					pricePerSqMRange: 'All'
				}
			})
		).toEqual({
			property_usage: 'Commercial',
			timeframe_days: 365,
			project: 'The Binary',
			filter_type: 'project',
			property_type: 'Office'
		})
	})

	it('builds rentals filters and selected contract exports', () => {
		const filters = buildRentalsApiFilters({
			propertyUsage: PROPERTY_USAGE.RESIDENTIAL,
			timeframe: 'Last 6 Months',
			currentPage: 3,
			selectedProject: makeProject({ name: 'Marina Gate', filter_type: 'project' }),
			selectedSubProject: null,
			localFilters: {
				selectedPropertyType: 'Apartment',
				selectedPropertySubType: 'Furnished',
				selectedTenantType: 'Individual',
				selectedRegistration: 'Ejari',
				areaRange: '50-100',
				rentRange: '50k-100k'
			}
		})

		expect(filters).toEqual({
			property_usage: 'Residential',
			timeframe_days: 180,
			limit: 30,
			offset: 60,
			project: 'Marina Gate',
			filter_type: 'project',
			property_type: 'Apartment',
			property_sub_type: 'Furnished',
			tenant_type: 'Individual',
			contract_reg_type: 'Ejari',
			area_min: 50,
			area_max: 100,
			rent_min: 50000,
			rent_max: 100000
		})

		expect(withSelectedIds(filters, 'contract_ids', new Set(['c-1']))).toMatchObject({
			contract_ids: 'c-1'
		})
		expect(
			buildRentalsFilterParams({
				propertyUsage: PROPERTY_USAGE.RESIDENTIAL,
				timeframe: 'Last 6 Months',
				selectedProject: makeProject({ name: 'Marina Gate', filter_type: 'project' }),
				selectedSubProject: null,
				localFilters: {
					selectedPropertyType: 'Apartment',
					selectedPropertySubType: 'All',
					selectedTenantType: 'All',
					selectedRegistration: 'All',
					areaRange: 'All',
					rentRange: 'All'
				}
			})
		).toEqual({
			property_usage: 'Residential',
			timeframe_days: 180,
			project: 'Marina Gate',
			filter_type: 'project',
			property_type: 'Apartment'
		})
	})
})
