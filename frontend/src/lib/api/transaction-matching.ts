import { client } from './client'
import type { TransactionResponseOutput } from './transactions'

export interface MatchedUnit {
	unit_id: number
	unit_number: string
	building_number: string
	floor: string | null
	actual_area: number
	rooms: string | null
	confidence: number
	reasoning: string
}

export interface MatchedUnitsResponse {
	transaction_id: string
	transaction_details: TransactionResponseOutput
	matched: boolean
	matches: MatchedUnit[]
	total_candidates: number
	processing_time_seconds: number
}

export interface UnitDetails {
	unit_number: string
	building_number: string
	actual_area: number
	rooms: string | null
}

export interface ComparableTransactionItem {
	transaction_id: string
	instance_date: string | null
	actual_worth: number | null
	meter_sale_price: number | null
	building_name_en: string | null
	procedure_area: number | null
}

export interface ComparableTransactionsResponse {
	unit_id: number
	unit_details: UnitDetails
	transactions: ComparableTransactionItem[]
	total_transactions: number
}

export const transactionMatching = {
	/**
	 * Match a transaction to units using AI.
	 * Results are cached for 1 hour to save costs.
	 */
	matchUnits: (transactionId: string) =>
		client.get<MatchedUnitsResponse>(`/api/v1/transactions/${transactionId}/match-units`),

	/**
	 * Get comparable transactions for a specific unit (reverse lookup).
	 * These are transactions with similar characteristics but not guaranteed to be the exact same unit.
	 * Results are cached for 30 minutes.
	 */
	getComparableTransactions: (unitId: number) =>
		client.get<ComparableTransactionsResponse>(`/api/v1/transactions/units/${unitId}/comparable`)
}
