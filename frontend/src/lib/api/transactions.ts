import { client } from './client'
import type {
	RentalContractListResponse,
	RentalContractResponse,
	TransactionListResponse,
	TransactionResponse
} from './generated/hey-api/types.gen'

export type RentalContractResponseOutput = RentalContractResponse
export type TransactionResponseOutput = TransactionResponse
export type TransactionExportFormat = 'xlsx' | 'csv'
export type {
	RentalContractListResponse,
	TransactionListResponse,
	RentalContractResponse,
	TransactionResponse
}

interface BaseTransactionFilters {
	trans_group?: string
	property_usage?: string
	timeframe_days?: number
	project?: string
	filter_type?: string
	property_type?: string
	property_sub_type?: string
	area?: string
	area_min?: number
	area_max?: number
	limit?: number
	offset?: number
}

export interface SalesTransactionFilters extends BaseTransactionFilters {
	building?: string
	rooms?: string
	registration_type?: string
	price_min?: number
	price_max?: number
	price_per_sqm_min?: number
	price_per_sqm_max?: number
	transaction_ids?: string
}

export interface RentalTransactionFilters extends BaseTransactionFilters {
	tenant_type?: string
	contract_reg_type?: string
	rent_min?: number
	rent_max?: number
	contract_ids?: string
}

export type SalesFacetFilters = Omit<
	SalesTransactionFilters,
	'limit' | 'offset' | 'transaction_ids'
>
export type RentalFacetFilters = Omit<RentalTransactionFilters, 'limit' | 'offset' | 'contract_ids'>

function withFilters(
	endpoint: string,
	filters: BaseTransactionFilters & { format?: TransactionExportFormat }
) {
	return client.withQuery(
		endpoint,
		filters as Record<string, string | number | boolean | null | undefined>
	)
}

export const transactions = {
	sales: (filters: SalesTransactionFilters) =>
		client.get<TransactionListResponse>(withFilters('/api/v1/transactions/sales', filters)),

	rentals: (filters: RentalTransactionFilters) =>
		client.get<RentalContractListResponse>(withFilters('/api/v1/transactions/rentals', filters)),

	exportSales: (
		filters: SalesTransactionFilters,
		format: TransactionExportFormat = 'xlsx'
	): Promise<Blob> =>
		client.get<Blob>(withFilters('/api/v1/transactions/sales/export', { ...filters, format }), {
			returnBlob: true
		}),

	exportRentals: (
		filters: RentalTransactionFilters,
		format: TransactionExportFormat = 'xlsx'
	): Promise<Blob> =>
		client.get<Blob>(withFilters('/api/v1/transactions/rentals/export', { ...filters, format }), {
			returnBlob: true
		})
}
