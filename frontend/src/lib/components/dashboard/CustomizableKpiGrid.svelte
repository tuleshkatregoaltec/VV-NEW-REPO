<script lang="ts">
import { createQuery } from '@tanstack/svelte-query'
import {
	ArrowDownRight,
	ArrowUpRight,
	BarChart3,
	Building2,
	Check,
	Clock3,
	Columns3,
	GripVertical,
	Home,
	Plus,
	RotateCcw,
	SlidersHorizontal,
	TrendingUp,
	WalletCards,
	X
} from 'lucide-svelte'
import { browser } from '$app/environment'
import { analytics } from '$lib/api/analytics'
import { supply } from '$lib/api/supply'
import { transactions } from '$lib/api/transactions'
import { analyticsQueries } from '$lib/queries/analytics'
import { SQM_TO_SQFT } from '$lib/utils/units'

type CardId =
	| 'mtd-transactions'
	| 'avg-price-sqft'
	| 'completed-units-ytd'
	| 'active-offplan-projects'
	| 'gross-yield'
	| 'avg-sale-price'
	| 'transaction-volume-12m'
	| 'pipeline-units'
	| 'avg-annual-rent'

type KpiCard = {
	id: CardId
	title: string
	value: string
	subtitle: string
	trend?: { value: string; direction: 'up' | 'down' }
	isDefault?: boolean
	loading?: boolean
}

type CardDefinition = {
	id: CardId
	title: string
	description: string
	isDefault?: boolean
}

type DateRange = {
	start: string
	end: string
}

type DragSource = 'grid' | 'palette'

type DropTarget = {
	id: CardId | null
	position: 'before' | 'after'
}

const STORAGE_KEY = 'vitevue-dashboard-kpi-cards'

const DEFAULT_CARD_IDS: CardId[] = [
	'mtd-transactions',
	'avg-price-sqft',
	'completed-units-ytd',
	'active-offplan-projects',
	'gross-yield'
]

const CARD_CATALOG: CardDefinition[] = [
	{
		id: 'mtd-transactions',
		title: 'Latest month transactions',
		description: 'Count and AED value for the latest month available in DLD data.',
		isDefault: true
	},
	{
		id: 'avg-price-sqft',
		title: 'Avg price/sqft',
		description: 'Dubai-wide residential sale price converted to square feet.',
		isDefault: true
	},
	{
		id: 'completed-units-ytd',
		title: 'Completed units YTD',
		description: 'Completed unit movement through the latest available data month.',
		isDefault: true
	},
	{
		id: 'active-offplan-projects',
		title: 'Active off-plan projects',
		description: 'Active and upcoming project count from the supply catalogue.',
		isDefault: true
	},
	{
		id: 'gross-yield',
		title: 'Residential gross yield',
		description: 'Median registered rent divided by median sale price.',
		isDefault: true
	},
	{
		id: 'avg-sale-price',
		title: 'Avg sale price',
		description: 'Average residential sale ticket in the latest available data month.'
	},
	{
		id: 'transaction-volume-12m',
		title: '12m transactions',
		description: 'Residential transaction count across the trailing 12 months.'
	},
	{
		id: 'pipeline-units',
		title: 'Pipeline units',
		description: 'Forward units in the market delivery pipeline.'
	},
	{
		id: 'avg-annual-rent',
		title: 'Avg annual rent',
		description: 'Average registered residential annual rent over 12 months.'
	}
]

function isoDate(date: Date): string {
	return date.toISOString().slice(0, 10)
}

function parseIsoDate(value: string | null | undefined): Date | null {
	if (!value) return null
	const date = new Date(`${value.slice(0, 10)}T00:00:00.000Z`)
	return Number.isNaN(date.getTime()) ? null : date
}

function monthRangeForDate(value: string | null | undefined): DateRange | null {
	const date = parseIsoDate(value)
	if (!date) return null

	const start = new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), 1))
	const end = new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth() + 1, 0))
	return {
		start: isoDate(start),
		end: isoDate(end)
	}
}

function trailingRangeForDate(value: string | null | undefined, days: number): DateRange | null {
	const end = parseIsoDate(value)
	if (!end) return null

	const start = new Date(end)
	start.setUTCDate(start.getUTCDate() - days)
	return {
		start: isoDate(start),
		end: isoDate(end)
	}
}

function requireRange(range: DateRange | null): DateRange {
	if (!range) throw new Error('Latest dashboard data range unavailable')
	return range
}

function isCardId(value: unknown): value is CardId {
	return CARD_CATALOG.some((card) => card.id === value)
}

function normalizeCardIds(value: unknown): CardId[] {
	if (!Array.isArray(value)) return [...DEFAULT_CARD_IDS]

	const ids = value.filter(isCardId)
	const unique = Array.from(new Set(ids))
	return unique.length > 0 ? unique : [...DEFAULT_CARD_IDS]
}

function loadCardIds(): CardId[] {
	if (!browser) return [...DEFAULT_CARD_IDS]

	try {
		const stored = localStorage.getItem(STORAGE_KEY)
		return stored ? normalizeCardIds(JSON.parse(stored)) : [...DEFAULT_CARD_IDS]
	} catch (error) {
		console.warn('Failed to load dashboard card preferences:', error)
		return [...DEFAULT_CARD_IDS]
	}
}

function saveCardIds(cardIds: CardId[]) {
	if (!browser) return

	try {
		localStorage.setItem(STORAGE_KEY, JSON.stringify(cardIds))
	} catch (error) {
		console.warn('Failed to save dashboard card preferences:', error)
	}
}

function formatCompact(value: number | null | undefined, digits = 1): string {
	if (value == null || !Number.isFinite(value)) return '—'
	const formatter = new Intl.NumberFormat('en-US', {
		notation: 'compact',
		maximumFractionDigits: digits
	})
	return formatter.format(value)
}

function formatWhole(value: number | null | undefined): string {
	if (value == null || !Number.isFinite(value)) return '—'
	return new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 }).format(value)
}

function formatCurrencyCompact(value: number | null | undefined): string {
	const formatted = formatCompact(value)
	return formatted === '—' ? formatted : `AED ${formatted}`
}

function formatPct(value: number | null | undefined, signed = false): string | null {
	if (value == null || !Number.isFinite(value)) return null
	const prefix = signed && value >= 0 ? '+' : ''
	return `${prefix}${value.toFixed(1)}%`
}

function cardDefinition(id: CardId): CardDefinition {
	return CARD_CATALOG.find((card) => card.id === id) ?? CARD_CATALOG[0]
}

function pipelineCompletedUnitsYtd() {
	const points = pipelineQuery.data?.data ?? []
	const anchorDate = latestSalesAnchorDate
	if (points.length < 1 || !anchorDate) return null

	const currentYear = anchorDate.getUTCFullYear()
	const yearStart = new Date(Date.UTC(currentYear, 0, 1))
	const ytdPoints = points.filter((point) => {
		const date = parseIsoDate(point.period)
		return date && date.getUTCFullYear() === currentYear && date <= anchorDate
	})
	if (ytdPoints.length === 0) return null

	const priorPoint = points
		.filter((point) => {
			const date = parseIsoDate(point.period)
			return date && date < yearStart
		})
		.at(-1)
	const last = ytdPoints[ytdPoints.length - 1]
	const baselineUnits = priorPoint?.existing_stock_units ?? ytdPoints[0].existing_stock_units ?? 0
	return Math.max((last.existing_stock_units ?? 0) - baselineUnits, 0)
}

function pipelineForwardUnits() {
	const projects = activeProjectsQuery.data?.projects ?? []
	return projects.reduce((sum, project) => sum + (project.no_of_units ?? 0), 0)
}

function grossYieldPct() {
	const medianRent = annualRentQuery.data?.summary.min_annual_rent ?? 0
	const medianPrice = annualSalesQuery.data?.summary.min_price ?? 0
	if (medianRent <= 0 || medianPrice <= 0) return null
	return (medianRent / medianPrice) * 100
}

function trendFromPct(value: number | null | undefined): KpiCard['trend'] {
	const formatted = formatPct(value, true)
	if (!formatted) return undefined
	return { value: `${formatted} YoY`, direction: (value ?? 0) >= 0 ? 'up' : 'down' }
}

let editMode = $state(false)
let selectedCardIds = $state<CardId[]>(loadCardIds())

const marketTrendQuery = createQuery(() => analyticsQueries.marketTrend(365))
const latestSalesTransactionQuery = createQuery(() => ({
	queryKey: ['dashboard', 'latest-sales-transaction', 'Residential'] as const,
	queryFn: () => transactions.sales({ property_usage: 'Residential', limit: 1 }),
	staleTime: 30 * 60 * 1000
}))
const marketTrendLastPoint = $derived(
	marketTrendQuery.data?.data?.length
		? marketTrendQuery.data.data[marketTrendQuery.data.data.length - 1]
		: null
)
const latestSalesDate = $derived(
	latestSalesTransactionQuery.data?.transactions[0]?.instance_date ??
		marketTrendLastPoint?.date ??
		null
)
const latestSalesAnchorDate = $derived(parseIsoDate(latestSalesDate))
const latestSalesMonthRange = $derived(monthRangeForDate(latestSalesDate))
const salesTrailingYearRange = $derived(trailingRangeForDate(latestSalesDate, 365))
const rentalTrailingYearRange = $derived(trailingRangeForDate(latestSalesDate, 365))
const monthlySalesQuery = createQuery(() => ({
	queryKey: [
		'dashboard',
		'sales-latest-month',
		latestSalesMonthRange?.start,
		latestSalesMonthRange?.end
	] as const,
	queryFn: () => {
		const range = requireRange(latestSalesMonthRange)
		return analytics.sales({
			property_usage: 'Residential',
			start_date: range.start,
			end_date: range.end
		})
	},
	enabled: Boolean(latestSalesMonthRange),
	staleTime: 5 * 60 * 1000
}))
const annualSalesQuery = createQuery(() => ({
	queryKey: [
		'dashboard',
		'sales-trailing-year',
		salesTrailingYearRange?.start,
		salesTrailingYearRange?.end
	] as const,
	queryFn: () => {
		const range = requireRange(salesTrailingYearRange)
		return analytics.sales({
			property_usage: 'Residential',
			start_date: range.start,
			end_date: range.end
		})
	},
	enabled: Boolean(salesTrailingYearRange),
	staleTime: 5 * 60 * 1000
}))
const annualRentQuery = createQuery(() => ({
	queryKey: [
		'dashboard',
		'rentals-trailing-year',
		rentalTrailingYearRange?.start,
		rentalTrailingYearRange?.end
	] as const,
	queryFn: () => {
		const range = requireRange(rentalTrailingYearRange)
		return analytics.rentals({
			property_usage: 'Residential',
			start_date: range.start,
			end_date: range.end
		})
	},
	enabled: Boolean(rentalTrailingYearRange),
	staleTime: 5 * 60 * 1000
}))
const pipelineQuery = createQuery(() => ({
	queryKey: ['dashboard', 'project-pipeline-latest-sales-v3'] as const,
	queryFn: () => analytics.projectPipeline({}),
	staleTime: 5 * 60 * 1000
}))
const activeProjectsQuery = createQuery(() => ({
	queryKey: ['dashboard', 'active-projects-as-of-latest-sales'] as const,
	queryFn: () => supply.getUpcomingProjects(),
	staleTime: 30 * 60 * 1000
}))

function buildCard(id: CardId): KpiCard {
	const definition = cardDefinition(id)
	const base = {
		id,
		title: definition.title,
		isDefault: definition.isDefault
	}

	if (id === 'mtd-transactions') {
		return {
			...base,
			value: formatWhole(monthlySalesQuery.data?.summary.transaction_count),
			subtitle: `${formatCurrencyCompact(monthlySalesQuery.data?.summary.total_volume)} value`,
			loading:
				latestSalesTransactionQuery.isPending ||
				(Boolean(latestSalesMonthRange) && monthlySalesQuery.isPending)
		}
	}

	if (id === 'avg-price-sqft') {
		const priceSqft = monthlySalesQuery.data?.summary.avg_price_sqft
			? monthlySalesQuery.data.summary.avg_price_sqft / SQM_TO_SQFT
			: null
		return {
			...base,
			value: priceSqft ? `AED ${formatWhole(priceSqft)}` : '—',
			subtitle: 'per sq.ft',
			trend: trendFromPct(marketTrendQuery.data?.avg_price_sqm_change_pct),
			loading:
				latestSalesTransactionQuery.isPending ||
				(Boolean(latestSalesMonthRange) && monthlySalesQuery.isPending)
		}
	}

	if (id === 'completed-units-ytd') {
		return {
			...base,
			value: formatWhole(pipelineCompletedUnitsYtd()),
			subtitle: 'Market delivery curve · YTD',
			loading: latestSalesTransactionQuery.isPending || pipelineQuery.isPending
		}
	}

	if (id === 'active-offplan-projects') {
		return {
			...base,
			value: formatWhole(activeProjectsQuery.data?.total),
			subtitle: 'Active and upcoming projects',
			loading: activeProjectsQuery.isPending
		}
	}

	if (id === 'gross-yield') {
		return {
			...base,
			value: formatPct(grossYieldPct()) ?? '—',
			subtitle: 'Latest 12m rent/sale evidence',
			loading:
				latestSalesTransactionQuery.isPending ||
				(Boolean(rentalTrailingYearRange) && annualRentQuery.isPending) ||
				(Boolean(salesTrailingYearRange) && annualSalesQuery.isPending)
		}
	}

	if (id === 'avg-sale-price') {
		return {
			...base,
			value: formatCurrencyCompact(monthlySalesQuery.data?.summary.avg_price),
			subtitle: 'Residential average sale ticket',
			trend: trendFromPct(marketTrendQuery.data?.avg_price_change_pct),
			loading:
				latestSalesTransactionQuery.isPending ||
				(Boolean(latestSalesMonthRange) && monthlySalesQuery.isPending)
		}
	}

	if (id === 'transaction-volume-12m') {
		return {
			...base,
			value: formatWhole(annualSalesQuery.data?.summary.transaction_count),
			subtitle: 'Trailing 12 months',
			loading:
				latestSalesTransactionQuery.isPending ||
				(Boolean(salesTrailingYearRange) && annualSalesQuery.isPending)
		}
	}

	if (id === 'pipeline-units') {
		return {
			...base,
			value: formatWhole(pipelineForwardUnits()),
			subtitle: 'Forward delivery pipeline',
			loading: activeProjectsQuery.isPending
		}
	}

	return {
		...base,
		value: formatCurrencyCompact(annualRentQuery.data?.summary.avg_annual_rent),
		subtitle: 'Registered residential contracts · trailing 12 months',
		loading:
			latestSalesTransactionQuery.isPending ||
			(Boolean(rentalTrailingYearRange) && annualRentQuery.isPending)
	}
}

let previewCardIds = $state<CardId[] | null>(null)
let visibleCardIds = $derived(previewCardIds ?? selectedCardIds)
let visibleCards = $derived(visibleCardIds.map(buildCard))
let selectedSet = $derived(new Set<CardId>(selectedCardIds))
let draggedCardId = $state<CardId | null>(null)
let dragSource = $state<DragSource | null>(null)
let dropTarget = $state<DropTarget | null>(null)
let paletteDropActive = $state(false)

$effect(() => {
	saveCardIds(selectedCardIds)
})

function previewOrder(id: CardId, target: DropTarget | null = null): CardId[] {
	const nextCards = selectedCardIds.filter((cardId) => cardId !== id)
	if (!target?.id) {
		return [...nextCards, id]
	}

	const targetIndex = nextCards.indexOf(target.id)
	const insertIndex =
		targetIndex === -1 ? nextCards.length : targetIndex + (target.position === 'after' ? 1 : 0)
	return [...nextCards.slice(0, insertIndex), id, ...nextCards.slice(insertIndex)]
}

function previewInsert(id: CardId, target: DropTarget | null = null) {
	previewCardIds = previewOrder(id, target)
}

function insertCard(id: CardId, target: DropTarget | null = null) {
	selectedCardIds = previewCardIds?.includes(id) ? previewCardIds : previewOrder(id, target)
}

function addCard(id: CardId) {
	if (selectedSet.has(id)) return
	insertCard(id)
}

function removeCard(id: CardId) {
	if (selectedCardIds.length === 1) return
	selectedCardIds = selectedCardIds.filter((cardId) => cardId !== id)
}

function startDrag(event: DragEvent, id: CardId, source: DragSource) {
	draggedCardId = id
	dragSource = source
	dropTarget = null
	paletteDropActive = false
	previewCardIds = source === 'grid' ? [...selectedCardIds] : null
	event.dataTransfer?.setData('text/plain', id)
	if (event.dataTransfer) {
		event.dataTransfer.effectAllowed = source === 'palette' ? 'copyMove' : 'move'
	}
}

function dragPosition(event: DragEvent): DropTarget['position'] {
	const target = event.currentTarget
	if (!(target instanceof HTMLElement)) return 'after'
	const bounds = target.getBoundingClientRect()
	return event.clientX < bounds.left + bounds.width / 2 ? 'before' : 'after'
}

function handleCardDragOver(event: DragEvent, id: CardId) {
	if (!draggedCardId) return
	event.preventDefault()
	event.stopPropagation()
	if (id === draggedCardId) return
	dropTarget = { id, position: dragPosition(event) }
	paletteDropActive = false
	previewInsert(draggedCardId, dropTarget)
	if (event.dataTransfer) event.dataTransfer.dropEffect = 'move'
}

function handleGridDragOver(event: DragEvent) {
	if (!draggedCardId) return
	event.preventDefault()
	paletteDropActive = false
	if (event.currentTarget === event.target) previewInsert(draggedCardId)
	if (event.dataTransfer) event.dataTransfer.dropEffect = 'move'
}

function handleDrop(event: DragEvent, target: DropTarget | null = null) {
	event.preventDefault()
	event.stopPropagation()
	const rawCardId = draggedCardId ?? event.dataTransfer?.getData('text/plain')
	if (!isCardId(rawCardId)) {
		clearDragState()
		return
	}

	if (dragSource === 'palette' && selectedSet.has(rawCardId)) {
		clearDragState()
		return
	}

	insertCard(rawCardId, target ?? dropTarget)
	clearDragState()
}

function handlePaletteDragOver(event: DragEvent) {
	if (!draggedCardId || dragSource !== 'grid') return
	event.preventDefault()
	event.stopPropagation()
	paletteDropActive = true
	dropTarget = null
	if (selectedCardIds.length > 1) {
		previewCardIds = selectedCardIds.filter((cardId) => cardId !== draggedCardId)
	}
	if (event.dataTransfer)
		event.dataTransfer.dropEffect = selectedCardIds.length > 1 ? 'move' : 'none'
}

function handlePaletteDrop(event: DragEvent) {
	event.preventDefault()
	event.stopPropagation()
	const rawCardId = draggedCardId ?? event.dataTransfer?.getData('text/plain')
	if (dragSource === 'grid' && isCardId(rawCardId)) {
		removeCard(rawCardId)
	}
	clearDragState()
}

function handlePaletteDragLeave(event: DragEvent) {
	const nextTarget = event.relatedTarget
	if (nextTarget instanceof Node && event.currentTarget instanceof Node) {
		if (event.currentTarget.contains(nextTarget)) return
	}
	paletteDropActive = false
}

function clearDragState() {
	draggedCardId = null
	dragSource = null
	dropTarget = null
	previewCardIds = null
	paletteDropActive = false
}

function cardDragClass(id: CardId) {
	if (!editMode) return ''
	if (draggedCardId === id) {
		return 'border-dashed border-strong bg-elevated opacity-55 shadow-none'
	}
	if (dropTarget?.id !== id) return ''
	return 'shadow-[inset_0_0_0_1px_var(--color-border-strong)]'
}

function resetCards() {
	selectedCardIds = [...DEFAULT_CARD_IDS]
	clearDragState()
}
</script>

<section class="mb-3">
	<div class="mb-3 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
		<div>
			<p class="font-mono text-[11px] uppercase tracking-[0.08em] text-fg-4">Market KPIs</p>
			<h2 class="mt-1 text-base font-semibold text-fg-1">Default DLD dashboard</h2>
		</div>
		<div class="flex flex-wrap items-center gap-2">
			<button
				type="button"
				class="ui-button h-9 px-3 text-xs"
				data-variant={editMode ? 'primary' : 'secondary'}
				onclick={() => (editMode = !editMode)}
			>
				<SlidersHorizontal size={15} strokeWidth={1.8} />
				{editMode ? 'Done' : 'Edit cards'}
			</button>
			{#if editMode}
				<button
					type="button"
					class="ui-button h-9 px-3 text-xs"
					data-variant="secondary"
					onclick={resetCards}
				>
					<RotateCcw size={15} strokeWidth={1.8} />
					Reset DLD defaults
				</button>
			{/if}
		</div>
	</div>

	<div>
		{#if editMode}
			<aside
				ondragover={handlePaletteDragOver}
				ondrop={handlePaletteDrop}
				ondragleave={handlePaletteDragLeave}
				class="mb-3 rounded-md border p-3 transition-colors {paletteDropActive
					? 'border-strong bg-elevated'
					: 'border-border bg-card'}"
			>
				<div class="mb-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
					<div>
						<p class="font-mono text-[11px] uppercase tracking-[0.08em] text-fg-4">
							Card library
						</p>
						<h3 class="mt-1 text-sm font-semibold text-fg-1">
							{paletteDropActive ? 'Release to remove' : 'Drag cards into the dashboard'}
						</h3>
					</div>
					<span class="font-mono text-[10px] uppercase tracking-[0.08em] text-fg-4">
						{selectedCardIds.length}/{CARD_CATALOG.length}
					</span>
				</div>
				<div
					class="grid auto-cols-[minmax(220px,1fr)] grid-flow-col gap-2 overflow-x-auto pb-1"
					role="list"
				>
					{#each CARD_CATALOG as card (card.id)}
						{@const selected = selectedSet.has(card.id)}
						<div
							role="listitem"
							draggable={!selected}
							ondragstart={(event) => startDrag(event, card.id, 'palette')}
							ondragend={clearDragState}
							class="flex min-h-[76px] items-start gap-2 rounded-md border border-border bg-elevated px-3 py-2.5 transition-colors {selected
								? 'opacity-60'
								: 'cursor-grab hover:border-strong active:cursor-grabbing'}"
						>
							<div class="mt-0.5 text-fg-4">
								{#if selected}
									<Check size={15} strokeWidth={1.8} />
								{:else}
									<GripVertical size={15} strokeWidth={1.8} />
								{/if}
							</div>
							<div class="min-w-0 flex-1">
								<div class="flex items-center gap-2">
									<p class="truncate text-sm font-semibold text-fg-1">{card.title}</p>
									{#if card.isDefault}
										<span
											class="rounded-sm border border-border bg-card px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-[0.08em] text-fg-4"
										>
											DLD
										</span>
									{/if}
								</div>
								<p class="mt-1 line-clamp-2 text-xs leading-4 text-fg-4">{card.description}</p>
							</div>
							<button
								type="button"
								class="rounded p-1 text-fg-4 transition-colors hover:bg-card hover:text-fg-1 disabled:cursor-default disabled:opacity-40"
								aria-label={selected ? 'Card already visible' : 'Add card'}
								onclick={() => addCard(card.id)}
								disabled={selected}
							>
								{#if selected}
									<Check size={14} strokeWidth={1.8} />
								{:else}
									<Plus size={14} strokeWidth={1.8} />
								{/if}
							</button>
						</div>
					{/each}
				</div>
			</aside>
		{/if}

		<div
			role="list"
			class="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-5"
			ondragover={handleGridDragOver}
			ondrop={(event) => handleDrop(event, { id: null, position: 'after' })}
		>
			{#each visibleCards as card (card.id)}
				<article
					role="listitem"
					draggable={editMode}
					ondragstart={(event) => startDrag(event, card.id, 'grid')}
					ondragover={(event) => handleCardDragOver(event, card.id)}
					ondrop={(event) => handleDrop(event, { id: card.id, position: dragPosition(event) })}
					ondragend={clearDragState}
					class="ui-metric-card min-h-[154px] transition-[background-color,border-color,box-shadow,opacity] duration-150 {editMode
						? 'cursor-grab active:cursor-grabbing'
						: ''} {cardDragClass(card.id)}"
				>
					<div class="mb-4 flex items-start justify-between gap-3">
						<div>
							<span class="font-mono text-[11px] uppercase tracking-[0.08em] text-fg-4">
								{card.title}
							</span>
							{#if card.isDefault}
								<span
									class="mt-1 block w-fit rounded-sm border border-border px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-[0.08em] text-fg-4"
								>
									DLD default
								</span>
							{/if}
						</div>
						<div class="flex items-center gap-2 text-fg-4">
							{#if editMode}
								<button
									type="button"
									class="rounded p-1 text-fg-4 transition-colors hover:bg-panel hover:text-fg-1 disabled:cursor-not-allowed disabled:opacity-40"
									aria-label="Remove card"
									onclick={() => removeCard(card.id)}
									disabled={selectedCardIds.length === 1}
								>
									<X size={14} strokeWidth={1.8} />
								</button>
								<GripVertical size={15} strokeWidth={1.8} />
							{:else if card.id === 'mtd-transactions'}
								<WalletCards size={16} strokeWidth={1.8} />
							{:else if card.id === 'avg-price-sqft'}
								<BarChart3 size={16} strokeWidth={1.8} />
							{:else if card.id === 'completed-units-ytd'}
								<Home size={16} strokeWidth={1.8} />
							{:else if card.id === 'active-offplan-projects'}
								<Building2 size={16} strokeWidth={1.8} />
							{:else if card.id === 'gross-yield'}
								<TrendingUp size={16} strokeWidth={1.8} />
							{:else}
								<Columns3 size={16} strokeWidth={1.8} />
							{/if}
						</div>
					</div>

					{#if card.loading}
						<div class="h-9 w-28 animate-pulse rounded bg-panel"></div>
						<div class="mt-2 h-4 w-36 animate-pulse rounded bg-panel"></div>
					{:else}
						<div
							class="font-display text-3xl font-normal leading-none tracking-normal text-fg-1 tabular-nums"
						>
							{card.value}
						</div>
						<p class="mt-2 min-h-8 text-xs leading-4 text-fg-4">{card.subtitle}</p>
						{#if card.trend}
							<p
								class="mt-2 inline-flex items-center gap-1.5 font-mono text-xs {card.trend
									.direction === 'up'
									? 'text-trend-up'
									: 'text-trend-down'}"
							>
								{#if card.trend.direction === 'up'}
									<ArrowUpRight size={14} strokeWidth={1.8} />
								{:else}
									<ArrowDownRight size={14} strokeWidth={1.8} />
								{/if}
								{card.trend.value}
							</p>
						{/if}
					{/if}
				</article>
			{/each}

		</div>
	</div>

	<div class="mt-2 flex items-center gap-1.5 text-xs text-fg-4">
		<Clock3 size={13} strokeWidth={1.8} />
		<span>Card selection is saved on this device.</span>
	</div>
</section>
