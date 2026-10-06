<script lang="ts">
import { transactionMatching } from '$lib/api/transaction-matching'
import Modal from '$lib/components/ui/Modal.svelte'

// TransformedTransaction is the display format used in the table
// It's defined locally in each page (sales/rentals) that uses this modal
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
}

let {
	transaction,
	onClose
}: {
	transaction: TransformedTransaction | null
	onClose: () => void
} = $props()

// State for managing matching and comparable transactions loading
let isLoadingMatch = $state(false)
let matchError = $state<string | null>(null)
let matchResult = $state<any>(null)

let isLoadingComparable = $state(false)
let comparableError = $state<string | null>(null)
let comparableResult = $state<any>(null)

// Reset state when transaction changes
$effect(() => {
	if (transaction) {
		// Clear previous results when opening a new transaction
		matchError = null
		matchResult = null
		comparableError = null
		comparableResult = null
		isLoadingMatch = false
		isLoadingComparable = false
	}
})

async function handleFindUnit() {
	if (!transaction?.transaction_id) return

	isLoadingMatch = true
	matchError = null
	matchResult = null

	try {
		const result = await transactionMatching.matchUnits(transaction.transaction_id)
		matchResult = result
	} catch (error: any) {
		matchError = error?.message || 'Failed to match units'
	} finally {
		isLoadingMatch = false
	}
}

async function handleViewComparable(unitId: number) {
	isLoadingComparable = true
	comparableError = null
	comparableResult = null

	try {
		const result = await transactionMatching.getComparableTransactions(unitId)
		comparableResult = result
	} catch (error: any) {
		comparableError = error?.message || 'Failed to load comparable transactions'
	} finally {
		isLoadingComparable = false
	}
}

function getConfidenceBadgeClass(confidence: number): string {
	if (confidence >= 0.8) {
		return 'bg-success-bg text-success border-[rgba(17,122,72,0.2)]'
	}
	if (confidence >= 0.6) {
		return 'bg-warning-bg text-warning border-[rgba(165,90,19,0.2)]'
	}
	return 'bg-bone-muted text-fg-2 border-bone-border'
}

function formatNumber(num: number | null | undefined): string {
	if (num === null || num === undefined) return 'N/A'
	return num.toLocaleString()
}

function formatDate(dateStr: string | null | undefined): string {
	if (!dateStr) return 'N/A'
	try {
		return new Date(dateStr).toLocaleDateString('en-US', {
			year: 'numeric',
			month: 'short',
			day: 'numeric'
		})
	} catch {
		return dateStr
	}
}
</script>

<Modal open={transaction !== null} {onClose} title="Transaction Details" size="xl">
	{#if transaction}
		<!-- Transaction Details Section -->
		<div class="mb-6">
			<h3 class="mb-3 text-lg font-semibold text-fg-1">Transaction Information</h3>
			<div class="grid grid-cols-2 gap-4 rounded-lg border border-border bg-slate-50 p-4 md:grid-cols-3">
				<div>
					<span class="text-sm text-fg-4">Transaction ID</span>
					<p class="font-medium text-fg-1">{transaction.transaction_id}</p>
				</div>
				<div>
					<span class="text-sm text-fg-4">Date</span>
					<p class="font-medium text-fg-1">{transaction.date}</p>
				</div>
				<div>
					<span class="text-sm text-fg-4">Area</span>
					<p class="font-medium text-fg-1">{transaction.area_name || 'N/A'}</p>
				</div>
				<div>
					<span class="text-sm text-fg-4">Project</span>
					<p class="font-medium text-fg-1">{transaction.project || 'N/A'}</p>
				</div>
				<div>
					<span class="text-sm text-fg-4">Building</span>
					<p class="font-medium text-fg-1">{transaction.building || 'N/A'}</p>
				</div>
				<div>
					<span class="text-sm text-fg-4">Property Type</span>
					<p class="font-medium text-fg-1">{transaction.propertyType || 'N/A'}</p>
				</div>
				<div>
					<span class="text-sm text-fg-4">Size</span>
					<p class="font-medium text-fg-1">{formatNumber(transaction.area)} m²</p>
				</div>
				<div>
					<span class="text-sm text-fg-4">Bedrooms</span>
					<p class="font-medium text-fg-1">{transaction.bedrooms || 'N/A'}</p>
				</div>
				<div>
					<span class="text-sm text-fg-4">Price</span>
					<p class="font-medium text-fg-1">{formatNumber(transaction.price)} AED</p>
				</div>
				<div>
					<span class="text-sm text-fg-4">Price/m²</span>
					<p class="font-medium text-fg-1">{formatNumber(transaction.pricePerSqM)} AED/m²</p>
				</div>
				<div>
					<span class="text-sm text-fg-4">Registration</span>
					<p class="font-medium text-fg-1">{transaction.registration || 'N/A'}</p>
				</div>
			</div>
		</div>

		<!-- Find Unit Button -->
		<div class="mb-6 rounded-lg border border-navy-pale bg-navy-pale p-4">
			<button
				onclick={handleFindUnit}
				disabled={isLoadingMatch}
				class="w-full rounded-md bg-navy px-6 py-3 font-medium text-on-navy transition-colors hover:bg-primary-hover disabled:cursor-not-allowed disabled:bg-slate-400 sm:w-auto"
			>
				{#if isLoadingMatch}
					<span class="inline-flex items-center gap-2">
						<svg
							class="animate-spin h-5 w-5"
							xmlns="http://www.w3.org/2000/svg"
							fill="none"
							viewBox="0 0 24 24"
						>
							<circle
								class="opacity-25"
								cx="12"
								cy="12"
								r="10"
								stroke="currentColor"
								stroke-width="4"
							></circle>
							<path
								class="opacity-75"
								fill="currentColor"
								d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
							></path>
						</svg>
						Finding matching units...
					</span>
				{:else}
					Find Matching Unit
				{/if}
			</button>

			<p class="mt-2 text-sm text-fg-3">
				Uses AI to identify which unit this transaction likely corresponds to. Results are
				suggestions, not definitive matches.
			</p>
		</div>

		<!-- Results Section -->
		{#if matchResult}
			{@const data = matchResult}

			{#if data.matches.length === 0}
				<div class="rounded-lg border border-[rgba(165,90,19,0.2)] bg-warning-bg p-4">
					<p class="text-warning">
						No matching units found. This transaction may not have enough data, or no units match
						the criteria.
					</p>
					<p class="mt-2 text-sm text-warning">
						Pre-filtered {data.total_candidates} candidates but found no high-confidence matches.
					</p>
				</div>
			{:else}
				<div>
					<div class="flex items-center justify-between mb-4">
						<h3 class="text-lg font-semibold text-fg-1">
							Found {data.matches.length} potential
							{data.matches.length === 1 ? 'match' : 'matches'}
						</h3>
						<span class="text-sm text-fg-4">
							Pre-filtered from {data.total_candidates} candidates in {data.processing_time_seconds.toFixed(
								1
							)}s
						</span>
					</div>

					<div class="space-y-3">
						{#each data.matches as match (match.unit_id)}
							<div class="rounded-lg border border-border p-4 transition-colors hover:bg-slate-50">
								<div class="flex justify-between items-start">
									<div class="flex-1">
										<h4 class="font-medium text-fg-1">
											Unit {match.unit_number} - Building {match.building_number}
										</h4>
										<p class="mt-1 text-sm text-fg-3">
											{#if match.floor}Floor {match.floor} •
											{/if}{formatNumber(match.actual_area)} m²
											{#if match.rooms}• {match.rooms}{/if}
										</p>
										<p class="mt-2 text-sm text-fg-2">{match.reasoning}</p>
									</div>

									<div class="ml-4">
										<span
											class="inline-block rounded-sm border px-3 py-1 text-sm font-medium {getConfidenceBadgeClass(
												match.confidence
											)}"
										>
											{(match.confidence * 100).toFixed(0)}%
										</span>
									</div>
								</div>

								<button
									onclick={() => handleViewComparable(match.unit_id)}
									class="mt-3 text-sm font-medium text-info hover:text-fg-1"
								>
									View Comparable Transactions →
								</button>
							</div>
						{/each}
					</div>
				</div>
			{/if}
		{/if}

		{#if matchError}
			<div class="rounded-lg border border-[rgba(163,36,36,0.2)] bg-error-bg p-4">
				<p class="text-error">Error matching units: {matchError}</p>
				<button
					onclick={handleFindUnit}
					class="mt-2 text-sm font-medium text-error hover:opacity-80"
				>
					Try again
				</button>
			</div>
		{/if}

		<!-- Comparable Transactions Section -->
		{#if comparableResult}
			{@const comparableData = comparableResult}

			<div class="mt-6 rounded-lg border border-border bg-slate-50 p-4">
				<h3 class="mb-3 text-lg font-semibold text-fg-1">
					Comparable Transactions for Unit {comparableData.unit_details.unit_number}
				</h3>

				<div class="mb-4 rounded border border-border bg-white p-3">
					<div class="grid grid-cols-2 gap-2 text-sm">
						<div>
							<span class="text-fg-4">Building:</span>
							<span class="font-medium ml-1">{comparableData.unit_details.building_number}</span>
						</div>
						<div>
							<span class="text-fg-4">Size:</span>
							<span class="font-medium ml-1"
								>{formatNumber(comparableData.unit_details.actual_area)} m²</span
							>
						</div>
						{#if comparableData.unit_details.rooms}
							<div>
								<span class="text-fg-4">Rooms:</span>
								<span class="font-medium ml-1">{comparableData.unit_details.rooms}</span>
							</div>
						{/if}
					</div>
				</div>

						{#if comparableData.transactions.length === 0}
							<p class="text-sm text-fg-3">No comparable transactions found for this unit.</p>
						{:else}
							<div class="space-y-2 max-h-64 overflow-y-auto">
								{#each comparableData.transactions as trans, index (`${trans.transaction_id}-${trans.instance_date}-${trans.building_name_en}-${index}`)}
									<div class="rounded border border-border bg-white p-3">
								<div class="flex justify-between items-start">
									<div class="flex-1">
										<p class="text-sm font-medium text-fg-1">
											{trans.transaction_id}
											{#if trans.transaction_id === transaction.transaction_id}
												<span class="ml-2 rounded-sm bg-info-bg px-2 py-1 text-xs text-info"
													>Current</span
												>
											{/if}
										</p>
										<p class="mt-1 text-xs text-fg-3">
											{formatDate(trans.instance_date)}
											{#if trans.building_name_en}
												• {trans.building_name_en}
											{/if}
											{#if trans.procedure_area}
												• {formatNumber(trans.procedure_area)} m²
											{/if}
										</p>
									</div>
									<div class="text-right ml-4">
										{#if trans.actual_worth}
											<p class="text-sm font-medium text-fg-1">
												{formatNumber(trans.actual_worth)} AED
											</p>
										{/if}
										{#if trans.meter_sale_price}
											<p class="text-xs text-fg-3">
												{formatNumber(trans.meter_sale_price)} AED/m²
											</p>
										{/if}
									</div>
								</div>
							</div>
						{/each}
					</div>

					<p class="mt-3 text-sm text-fg-3">
						Total: {comparableData.total_transactions} comparable transaction{comparableData.total_transactions !==
						1
							? 's'
							: ''}
					</p>
				{/if}
			</div>
		{/if}

		{#if isLoadingComparable}
			<div class="mt-6 rounded-lg border border-border bg-slate-50 p-4">
				<div class="flex items-center gap-2">
					<svg
						class="h-5 w-5 animate-spin text-fg-4"
						xmlns="http://www.w3.org/2000/svg"
						fill="none"
						viewBox="0 0 24 24"
					>
						<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"
						></circle>
						<path
							class="opacity-75"
							fill="currentColor"
							d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
						></path>
					</svg>
					<span class="text-fg-2">Loading comparable transactions...</span>
				</div>
			</div>
		{/if}

		{#if comparableError}
			<div class="mt-6 rounded-lg border border-[rgba(163,36,36,0.2)] bg-error-bg p-4">
				<p class="text-error">Error loading comparable transactions: {comparableError}</p>
			</div>
		{/if}
	{/if}
</Modal>
