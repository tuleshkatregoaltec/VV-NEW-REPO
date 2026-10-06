import { filters } from '$lib/api/filters'
import type {
	RentalContractListResponse,
	RentalFacetFilters,
	RentalTransactionFilters,
	SalesFacetFilters,
	SalesTransactionFilters,
	TransactionListResponse
} from '$lib/api/transactions'
import { transactions } from '$lib/api/transactions'

export const transactionKeys = {
	all: ['transactions'] as const,
	sales: (params: SalesTransactionFilters) => [...transactionKeys.all, 'sales', params] as const,
	rentals: (params: RentalTransactionFilters) =>
		[...transactionKeys.all, 'rentals', params] as const,
	filterOptions: (kind: 'sales' | 'rentals', params: SalesFacetFilters | RentalFacetFilters) =>
		[...transactionKeys.all, 'filterOptions', kind, params] as const
}

export const transactionQueries = {
	sales: (params: SalesTransactionFilters) => ({
		queryKey: transactionKeys.sales(params),
		queryFn: () => transactions.sales(params),
		placeholderData: (previousData: TransactionListResponse | undefined) => previousData
	}),
	rentals: (params: RentalTransactionFilters) => ({
		queryKey: transactionKeys.rentals(params),
		queryFn: () => transactions.rentals(params),
		placeholderData: (previousData: RentalContractListResponse | undefined) => previousData
	}),
	salesFilterOptions: (params: SalesFacetFilters) => ({
		queryKey: transactionKeys.filterOptions('sales', params),
		queryFn: () => filters.sales(params),
		staleTime: 5 * 60 * 1000
	}),
	rentalFilterOptions: (params: RentalFacetFilters) => ({
		queryKey: transactionKeys.filterOptions('rentals', params),
		queryFn: () => filters.rentals(params),
		staleTime: 5 * 60 * 1000
	})
}
