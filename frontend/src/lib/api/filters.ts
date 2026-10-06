import { client } from './client'
import type { FilterOptionsResponse } from './generated/hey-api/types.gen'
import type { RentalFacetFilters, SalesFacetFilters } from './transactions'

export type { FilterOptionsResponse }

export const filters = {
	sales: (filterParams: SalesFacetFilters = {}) => {
		return client.get<FilterOptionsResponse>(
			client.withQuery('/api/v1/filters/sales', filterParams)
		)
	},

	rentals: (filterParams: RentalFacetFilters = {}) => {
		return client.get<FilterOptionsResponse>(
			client.withQuery('/api/v1/filters/rentals', filterParams)
		)
	}
}
