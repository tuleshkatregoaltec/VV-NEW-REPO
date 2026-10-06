<script lang="ts">
import { createQuery } from '@tanstack/svelte-query'
import {
	Bot,
	Building2,
	Check,
	FileSpreadsheet,
	Home,
	Landmark,
	LoaderCircle,
	Search,
	X
} from 'lucide-svelte'
import { goto } from '$app/navigation'
import type { Plot } from '$lib/api/generated/hey-api/types.gen'
import type { DdaPlotFeature } from '$lib/api/projects'
import type { DevelopmentModel } from '$lib/feasibility/workbook/models'
import { getQueryClient } from '$lib/queries/client'
import {
	feasibilityKeys,
	feasibilityQueries,
	type PlotSearchParams
} from '$lib/queries/feasibility'
import { projectQueries } from '$lib/queries/projects'
import { feasibilityStudy } from '$lib/stores/feasibilityStudy.svelte'
import PlotParcelMap from './PlotParcelMap.svelte'

type UsageFilter = 'all' | 'residential' | 'commercial' | 'mixed'
type SortKey = 'verified' | 'largest' | 'highest_gfa'

let { onCancel }: { onCancel: () => void } = $props()

let name = $state('')
let developmentModel = $state<DevelopmentModel>('build_to_sell_residential')
let selectedPlot = $state<Plot | null>(null)
let pickerOpen = $state(false)
let plotSearch = $state('3460688')
let community = $state('')
let usageFilter = $state<UsageFilter>('all')
let verifiedOnly = $state(false)
let minPlotArea = $state('')
let sortBy = $state<SortKey>('verified')
let creating = $state(false)
let creationStepIndex = $state(0)
let error = $state('')
let plotSearchParams = $state<PlotSearchParams | null>(null)

const queryClient = getQueryClient()
const inactivePlotSearchParams: PlotSearchParams = { limit: 100 }
const plotsQuery = createQuery(() => ({
	...feasibilityQueries.searchPlots(plotSearchParams ?? inactivePlotSearchParams),
	enabled: Boolean(plotSearchParams)
}))
const loading = $derived(plotsQuery.isFetching)
const plotSearchError = $derived(
	plotsQuery.isError
		? plotsQuery.error instanceof Error
			? plotsQuery.error.message
			: 'Failed to search plots.'
		: ''
)
const plots = $derived<Plot[]>(plotsQuery.data ?? [])

const modelOptions: Array<{
	id: DevelopmentModel
	label: string
	descriptor: string
	description: string
	icon: typeof Home
	available: boolean
}> = [
	{
		id: 'build_to_sell_residential',
		label: 'Build to sell',
		descriptor: 'Residential exit',
		description: 'For-sale underwriting with unit mix, collections, debt draw, and return outputs.',
		icon: Home,
		available: true
	},
	{
		id: 'build_to_rent_residential',
		label: 'Build to rent',
		descriptor: 'Held asset',
		description:
			'Rental operating model with lease-up, stabilized NOI, exit cap, and permanent debt.',
		icon: Building2,
		available: true
	},
	{
		id: 'build_to_lease_commercial',
		label: 'Build to lease',
		descriptor: 'Commercial',
		description: 'Commercial lease-up path reserved for a later underwriting pass.',
		icon: Landmark,
		available: false
	}
]

const usageOptions: Array<{ id: UsageFilter; label: string }> = [
	{ id: 'all', label: 'All uses' },
	{ id: 'residential', label: 'Residential' },
	{ id: 'commercial', label: 'Commercial' },
	{ id: 'mixed', label: 'Mixed' }
]

const sortOptions: Array<{ id: SortKey; label: string }> = [
	{ id: 'verified', label: 'Verified' },
	{ id: 'largest', label: 'Largest plot' },
	{ id: 'highest_gfa', label: 'Highest GFA' }
]

const creationSteps = [
	'Reading the selected plot and zoning envelope',
	'Generating market-backed starting assumptions',
	'Building the workbook tabs and formulas',
	'Saving the study workspace',
	'Opening the editable model'
]

$effect(() => {
	if (!creating) {
		creationStepIndex = 0
		return
	}
	const timer = setInterval(() => {
		creationStepIndex = Math.min(creationStepIndex + 1, creationSteps.length - 1)
	}, 1300)
	return () => clearInterval(timer)
})

function inferUsage(plot: Plot): UsageFilter {
	const haystack = `${plot.gfa_type} ${(plot.land_use_summary ?? []).join(' ')}`.toLowerCase()
	const residential = ['residential', 'apartment', 'villa', 'townhouse'].some((token) =>
		haystack.includes(token)
	)
	const commercial = ['commercial', 'office', 'retail', 'hotel', 'industrial'].some((token) =>
		haystack.includes(token)
	)
	if (residential && commercial) return 'mixed'
	if (residential) return 'residential'
	if (commercial) return 'commercial'
	return 'all'
}

const visiblePlots = $derived.by(() => {
	const minAreaValue = Number(minPlotArea)
	let rows = plots.filter((plot) => {
		if (verifiedOnly && !plot.is_verified) return false
		if (usageFilter !== 'all') {
			const usage = inferUsage(plot)
			if (usageFilter === 'mixed' ? usage !== 'mixed' : usage !== usageFilter) return false
		}
		return !(Number.isFinite(minAreaValue) && minAreaValue > 0 && plot.plot_area_sqm < minAreaValue)
	})
	rows = [...rows].sort((a, b) => {
		if (sortBy === 'largest') return b.plot_area_sqm - a.plot_area_sqm
		if (sortBy === 'highest_gfa') return b.max_gfa_sqm - a.max_gfa_sqm
		if (a.is_verified !== b.is_verified) return Number(b.is_verified) - Number(a.is_verified)
		return b.max_gfa_sqm - a.max_gfa_sqm
	})
	return rows
})
const visiblePlotNumbers = $derived(new Set(visiblePlots.map((plot) => plot.plot_number)))
const availablePlotNumbers = $derived(new Set(plots.map((plot) => plot.plot_number)))
const plotsByNumber = $derived(new Map(plots.map((plot) => [plot.plot_number, plot])))
const selectedPlotNumber = $derived(selectedPlot?.plot_number ?? null)
const mapCommunity = $derived.by(() => {
	const explicitCommunity = community.trim()
	if (explicitCommunity) return explicitCommunity
	if (selectedPlot?.community_name) return selectedPlot.community_name
	const communities = [...new Set(visiblePlots.map((plot) => plot.community_name).filter(Boolean))]
	return communities.length === 1 ? communities[0] : ''
})
const ddaQueryParams = $derived(mapCommunity ? { area: mapCommunity, limit: 5000 } : null)
const ddaPlotsQuery = createQuery(() => projectQueries.ddaPlots(ddaQueryParams))
const ddaPlots = $derived<DdaPlotFeature[]>(ddaQueryParams ? (ddaPlotsQuery.data ?? []) : [])

function searchPlots() {
	error = ''
	const minPlotAreaSqm = Number(minPlotArea)
	plotSearchParams = {
		q: plotSearch.trim() || undefined,
		community: community.trim() || undefined,
		minPlotAreaSqm:
			Number.isFinite(minPlotAreaSqm) && minPlotAreaSqm > 0 ? minPlotAreaSqm : undefined,
		limit: 100
	}
}

function chooseDdaPlot(plot: DdaPlotFeature) {
	const match = plotsByNumber.get(plot.plot_number)
	if (!match) return
	selectedPlot = match
}

async function createStudy() {
	if (!name.trim() || !selectedPlot) return
	creating = true
	error = ''
	try {
		const saved = await feasibilityStudy.createSavedStudy({
			name: name.trim(),
			plot_number: selectedPlot.plot_number,
			development_model: developmentModel
		})
		await queryClient.invalidateQueries({ queryKey: feasibilityKeys.studies() })
		await goto(`/feasibility/${saved.id}`)
	} catch (err) {
		error = err instanceof Error ? err.message : 'Failed to create study.'
	} finally {
		creating = false
	}
}
</script>

<div class="flex flex-col gap-5">
	{#if creating}
		<div class="ui-surface overflow-hidden">
			<div class="grid gap-5 border-b border-border bg-navy px-5 py-5 text-bone lg:grid-cols-[minmax(0,1fr)_auto] lg:items-center">
				<div>
					<p class="text-xs font-semibold uppercase tracking-[0.18em] text-on-navy-muted">
						Agent workspace
					</p>
					<h1 class="mt-2 font-display text-3xl leading-tight tracking-[var(--tracking-display)] text-bone">
						Creating your feasibility study
					</h1>
					<p class="mt-2 max-w-3xl text-sm leading-6 text-on-navy-muted">
						The agent is turning your plot selection into a saved workbook with seeded assumptions, model tabs, and an editable first pass.
					</p>
				</div>
				<div class="inline-flex items-center gap-2 rounded-md border border-bone/20 bg-bone/10 px-3 py-2 text-sm font-semibold text-bone">
					<LoaderCircle size={16} class="animate-spin" />
					Working
				</div>
			</div>

			<div class="grid gap-5 p-5 lg:grid-cols-[minmax(0,1fr)_320px] lg:p-6">
				<div class="rounded-lg border border-border bg-card p-5">
					<div class="flex items-start gap-4">
						<div class="grid h-11 w-11 shrink-0 place-items-center rounded-md bg-info-bg text-info">
							<Bot size={22} strokeWidth={1.8} />
						</div>
						<div class="min-w-0">
							<p class="text-base font-semibold text-fg-1">The feasibility agent is working</p>
							<p class="mt-1 text-sm leading-6 text-fg-3">
								This usually takes a moment while the backend creates the study record and prepares the workbook state.
							</p>
						</div>
					</div>

					<div class="mt-6 space-y-3">
						{#each creationSteps as step, index (step)}
							<div
								class="flex items-center gap-3 rounded-md border px-3 py-3 transition {index <=
								creationStepIndex
									? 'border-info bg-info-bg text-info'
									: 'border-border bg-panel text-fg-4'}"
							>
								<span
									class="grid h-6 w-6 shrink-0 place-items-center rounded-full {index < creationStepIndex
										? 'bg-info text-bone'
										: index === creationStepIndex
											? 'bg-info text-bone'
											: 'bg-card text-fg-5'}"
								>
									{#if index < creationStepIndex}
										<Check size={13} strokeWidth={2.4} />
									{:else if index === creationStepIndex}
										<LoaderCircle size={13} class="animate-spin" />
									{:else}
										<span class="h-1.5 w-1.5 rounded-full bg-current"></span>
									{/if}
								</span>
								<span class="text-sm font-medium">{step}</span>
							</div>
						{/each}
					</div>
				</div>

				<aside class="rounded-lg border border-border bg-panel p-5">
					<div class="flex items-center gap-2 text-sm font-semibold text-fg-1">
						<FileSpreadsheet size={16} strokeWidth={2} />
						Study being created
					</div>
					<div class="mt-4 grid gap-3 text-sm">
						<div class="rounded-md bg-card p-3">
							<p class="text-xs uppercase tracking-[0.14em] text-fg-4">Study</p>
							<p class="mt-1 font-semibold text-fg-1">{name.trim()}</p>
						</div>
						<div class="rounded-md bg-card p-3">
							<p class="text-xs uppercase tracking-[0.14em] text-fg-4">Model</p>
							<p class="mt-1 font-semibold text-fg-1">{modelOptions.find((option) => option.id === developmentModel)?.label}</p>
						</div>
						{#if selectedPlot}
							<div class="rounded-md bg-card p-3">
								<p class="text-xs uppercase tracking-[0.14em] text-fg-4">Plot</p>
								<p class="mt-1 font-semibold text-fg-1">{selectedPlot.plot_number}</p>
								<p class="mt-1 text-xs text-fg-4">{selectedPlot.community_name}</p>
							</div>
						{/if}
					</div>
				</aside>
			</div>
		</div>
	{:else}
	<div class="ui-surface overflow-hidden">
		<div class="grid gap-5 border-b border-border bg-navy px-5 py-5 text-bone lg:grid-cols-[minmax(0,1fr)_auto] lg:items-end">
			<div>
				<p class="text-xs font-semibold uppercase tracking-[0.18em] text-on-navy-muted">New study</p>
				<h1 class="mt-2 font-display text-3xl leading-tight tracking-[var(--tracking-display)] text-bone">
					Set up the underwriting workspace
				</h1>
				<p class="mt-2 max-w-3xl text-sm leading-6 text-on-navy-muted">
					Define the saved study shell, choose the development model, and attach the GIS plot before generation runs.
				</p>
			</div>
			<button type="button" class="h-10 rounded-md border border-bone/20 px-4 text-sm font-medium text-bone transition hover:border-bone/40 hover:bg-bone/10" onclick={onCancel}>
				Back to studies
			</button>
		</div>

		<section class="grid gap-0 lg:grid-cols-[minmax(0,1fr)_390px]">
			<div class="grid gap-6 p-5 lg:p-6">
				<label class="grid gap-2">
					<span class="text-sm font-semibold text-fg-1">Study name</span>
					<input bind:value={name} class="ui-field h-11 px-3 text-sm placeholder:text-fg-5" placeholder="Business Bay build-to-sell" />
				</label>

				<div class="grid gap-3">
					<div>
						<p class="text-sm font-semibold text-fg-1">Development model</p>
						<p class="mt-1 text-xs text-fg-4">Select the workbook path that should seed the first saved version.</p>
					</div>
					<div class="grid gap-3 md:grid-cols-3">
						{#each modelOptions as option}
							{@const Icon = option.icon}
							<button
								type="button"
								class="group relative min-h-[150px] rounded-lg border p-4 text-left shadow-sm transition {developmentModel === option.id
									? 'border-navy bg-navy text-bone shadow-md'
									: option.available
										? 'border-border bg-card text-fg-2 hover:border-strong hover:bg-elevated hover:shadow-md'
										: 'cursor-not-allowed border-border bg-panel text-fg-5'}"
								disabled={!option.available}
								aria-pressed={developmentModel === option.id}
								onclick={() => option.available && (developmentModel = option.id)}
							>
								<span class="flex items-start justify-between gap-3">
									<span class="grid h-10 w-10 place-items-center rounded-md {developmentModel === option.id ? 'bg-bone text-navy' : 'bg-panel text-fg-2 group-hover:bg-card'}">
										<Icon size={19} strokeWidth={1.9} />
									</span>
									{#if developmentModel === option.id}
										<span class="grid h-6 w-6 place-items-center rounded-full bg-bone text-navy">
											<Check size={14} strokeWidth={2.2} />
										</span>
									{:else if !option.available}
										<span class="rounded-md bg-card px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-fg-4">Next</span>
									{/if}
								</span>
								<span class="mt-4 block text-sm font-semibold {developmentModel === option.id ? 'text-bone' : 'text-fg-1'}">{option.label}</span>
								<span class="mt-1 block text-xs font-medium uppercase tracking-[0.12em] {developmentModel === option.id ? 'text-on-navy-muted' : 'text-fg-4'}">{option.descriptor}</span>
								<span class="mt-3 block text-xs leading-5 {developmentModel === option.id ? 'text-on-navy-muted' : 'text-fg-3'}">{option.description}</span>
							</button>
						{/each}
					</div>
				</div>

				<div class="ui-panel grid gap-3 p-4">
					<div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
						<div>
							<p class="text-sm font-semibold text-fg-1">Plot selection</p>
							<p class="mt-1 text-xs text-fg-4">Search GIS inventory and attach one verified plot snapshot.</p>
						</div>
						<button type="button" data-variant="primary" class="ui-button h-10 w-full px-4 text-sm sm:w-auto" onclick={() => (pickerOpen = true)}>
							<Search size={16} />
							<span>{selectedPlot ? 'Change plot' : 'Select plot'}</span>
						</button>
					</div>
					{#if selectedPlot}
						<div class="grid gap-3 rounded-md border border-border bg-card p-4 md:grid-cols-4">
							<div class="md:col-span-2">
								<p class="text-xs uppercase tracking-[0.14em] text-fg-4">Project</p>
								<p class="mt-1 text-sm font-semibold text-fg-1">{selectedPlot.project_name}</p>
							</div>
							<div>
								<p class="text-xs uppercase tracking-[0.14em] text-fg-4">Plot</p>
								<p class="mt-1 text-sm font-semibold text-fg-1">{selectedPlot.plot_number}</p>
							</div>
							<div>
								<p class="text-xs uppercase tracking-[0.14em] text-fg-4">Community</p>
								<p class="mt-1 text-sm font-semibold text-fg-1">{selectedPlot.community_name}</p>
							</div>
						</div>
					{/if}
				</div>
			</div>

			<aside class="border-t border-border bg-panel p-5 lg:border-l lg:border-t-0 lg:p-6">
				<div class="ui-surface p-5">
					<p class="text-sm font-semibold text-fg-1">Study summary</p>
					<div class="mt-4 grid gap-3">
						<div class="rounded-md bg-panel p-3">
							<p class="text-xs uppercase tracking-[0.14em] text-fg-4">Model</p>
							<p class="mt-1 text-sm font-semibold text-fg-1">{modelOptions.find((option) => option.id === developmentModel)?.label}</p>
						</div>
						{#if selectedPlot}
							<div class="grid grid-cols-2 gap-3">
								<div class="rounded-md bg-panel p-3">
									<p class="text-xs uppercase tracking-[0.14em] text-fg-4">Plot area</p>
									<p class="mt-1 text-sm font-semibold text-fg-1">{selectedPlot.plot_area_sqm.toLocaleString('en-AE', { maximumFractionDigits: 0 })} sqm</p>
								</div>
								<div class="rounded-md bg-panel p-3">
									<p class="text-xs uppercase tracking-[0.14em] text-fg-4">Max GFA</p>
									<p class="mt-1 text-sm font-semibold text-fg-1">{selectedPlot.max_gfa_sqm.toLocaleString('en-AE', { maximumFractionDigits: 0 })} sqm</p>
								</div>
							</div>
						{:else}
							<div class="rounded-md border border-dashed border-strong bg-panel p-4 text-sm text-fg-4">No plot selected.</div>
						{/if}
					</div>
					<button
						type="button"
						class="mt-5 h-11 w-full rounded-md px-4 text-sm font-medium transition {name.trim() && selectedPlot && !creating ? 'bg-navy text-bone hover:bg-primary-light' : 'cursor-not-allowed bg-panel text-fg-5'}"
						disabled={!name.trim() || !selectedPlot || creating}
						onclick={() => void createStudy()}
					>
						{creating ? 'Creating...' : 'Create study'}
					</button>
					{#if error}
						<p class="mt-3 text-sm text-rose-600">{error}</p>
					{/if}
				</div>
			</aside>
		</section>
	</div>
	{/if}
</div>

{#if pickerOpen}
	<div class="fixed inset-0 z-50 bg-black/30 p-2 sm:p-4" role="presentation">
		<div class="mx-auto flex h-full max-h-[820px] max-w-[1040px] flex-col overflow-hidden rounded-lg bg-card shadow-lg">
			<div class="flex items-start justify-between gap-3 border-b border-border bg-navy px-4 py-3 text-bone sm:px-5 sm:py-4">
				<div>
					<p class="text-sm font-semibold">Select plot</p>
					<p class="mt-1 text-xs text-on-navy-muted">Search by plot number, project, or community.</p>
				</div>
				<button type="button" class="grid h-8 w-8 place-items-center rounded-md border border-bone/20 text-on-navy-muted transition hover:border-bone/40 hover:bg-bone/10 hover:text-bone" onclick={() => (pickerOpen = false)} aria-label="Close plot picker">
					<X size={16} />
				</button>
			</div>
			<div class="grid gap-3 border-b border-border bg-panel p-3 sm:gap-4 sm:p-4">
				<div class="grid gap-3 md:grid-cols-[minmax(220px,1fr)_minmax(160px,220px)_120px_120px]">
					<input bind:value={plotSearch} placeholder="Plot, project, community" class="ui-field h-10 px-3 text-sm" onkeydown={(event) => event.key === 'Enter' && void searchPlots()} />
					<input bind:value={community} placeholder="Community" class="ui-field h-10 px-3 text-sm" />
					<input bind:value={minPlotArea} type="number" min="0" placeholder="Min area" class="ui-field h-10 px-3 text-sm" />
					<button type="button" data-variant="primary" class="ui-button h-10 px-4 text-sm" onclick={() => void searchPlots()}>{loading ? 'Searching...' : 'Search'}</button>
				</div>
				<div class="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
					<div class="flex flex-wrap gap-2">
						{#each usageOptions as option}
							<button type="button" class="h-8 shrink-0 rounded-md border px-3 text-xs font-medium transition {usageFilter === option.id ? 'border-navy bg-navy text-bone' : 'border-border bg-card text-fg-3 hover:border-strong'}" onclick={() => (usageFilter = option.id)}>
								{option.label}
							</button>
						{/each}
					</div>
						<div class="flex flex-wrap gap-2">
							{#each sortOptions as option}
								<button type="button" class="h-8 shrink-0 rounded-md border px-3 text-xs font-medium transition {sortBy === option.id ? 'border-navy bg-navy text-bone' : 'border-border bg-card text-fg-3 hover:border-strong'}" onclick={() => (sortBy = option.id)}>
									{option.label}
								</button>
							{/each}
							<button type="button" class="h-8 shrink-0 rounded-md border px-3 text-xs font-medium transition {verifiedOnly ? 'border-navy bg-navy text-bone' : 'border-border bg-card text-fg-3 hover:border-strong'}" aria-pressed={verifiedOnly} onclick={() => (verifiedOnly = !verifiedOnly)}>
								Verified only
							</button>
						</div>
					</div>
				</div>
				{#if plotSearchError}
					<p class="border-b border-border px-4 py-3 text-sm text-rose-600">{plotSearchError}</p>
				{/if}
				<div class="grid min-h-0 flex-1 md:grid-cols-[minmax(0,1fr)_320px]">
					<div class="min-h-0 overflow-auto">
							{#if loading}
								<p class="p-5 text-sm text-fg-4">Searching plots...</p>
							{:else if visiblePlots.length === 0}
								<p class="p-5 text-sm text-fg-4">Search by plot number, project, or community.</p>
							{:else}
								<div class="divide-y divide-slate-100">
									{#each visiblePlots as plot}
										<button type="button" class="flex w-full flex-col gap-1 px-5 py-3 text-left hover:bg-elevated {selectedPlot?.plot_number === plot.plot_number ? 'bg-info-bg' : ''}" onclick={() => (selectedPlot = plot)}>
											<div class="flex items-center justify-between gap-3">
												<span class="text-sm font-semibold text-fg-1">{plot.project_name}</span>
												<span class="rounded-md bg-panel px-2 py-0.5 text-xs text-fg-3">{plot.plot_number}</span>
											</div>
											<p class="text-sm text-fg-3">{plot.community_name}</p>
											<p class="text-xs text-fg-4">{plot.plot_area_sqm.toLocaleString('en-AE', { maximumFractionDigits: 0 })} sqm · {plot.max_gfa_sqm.toLocaleString('en-AE', { maximumFractionDigits: 0 })} sqm GFA · {inferUsage(plot)}</p>
										</button>
									{/each}
								</div>
							{/if}
						</div>
				<aside class="border-t border-border p-5 md:border-l md:border-t-0">
					<PlotParcelMap
						plots={ddaPlots}
						{selectedPlotNumber}
						{visiblePlotNumbers}
						{availablePlotNumbers}
						loading={ddaPlotsQuery.isFetching}
						onPlotSelect={chooseDdaPlot}
						className="h-64"
					/>
					<p class="mt-4 text-sm font-semibold text-fg-1">Preview</p>
					{#if selectedPlot}
						<div class="mt-4 grid gap-2 text-sm text-fg-3">
							<p class="font-medium text-fg-1">{selectedPlot.project_name}</p>
							<p>{selectedPlot.community_name}</p>
							<p>Plot {selectedPlot.plot_number}</p>
						</div>
						<button type="button" data-variant="primary" class="ui-button mt-5 h-10 w-full px-4 text-sm" onclick={() => (pickerOpen = false)}>Use plot</button>
					{:else}
						<p class="mt-4 text-sm text-fg-4">Select a result to preview it.</p>
					{/if}
				</aside>
			</div>
		</div>
	</div>
{/if}
