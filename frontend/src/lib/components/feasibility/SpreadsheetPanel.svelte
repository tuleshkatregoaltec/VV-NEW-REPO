<script lang="ts">
import { Info } from 'lucide-svelte'
import { onMount } from 'svelte'
import { downloadFeasibilityWorkbook } from '$lib/feasibility/workbook/excelExport'
import { type FeasibilitySheetTab, workbookStore } from '$lib/feasibility/workbook/store.svelte'
import AreaBridgeSheet from './sheets/AreaBridgeSheet.svelte'
import BlankSheet from './sheets/BlankSheet.svelte'
import BtrOperatingSheet from './sheets/BtrOperatingSheet.svelte'
import BudgetSheet from './sheets/BudgetSheet.svelte'
import CashFlowSheet from './sheets/CashFlowSheet.svelte'
import ChecksSheet from './sheets/ChecksSheet.svelte'
import ColorLegend from './sheets/ColorLegend.svelte'
import EiborSheet from './sheets/EiborSheet.svelte'
import FinancingSheet from './sheets/FinancingSheet.svelte'
import KeyAssumptionsSheet from './sheets/KeyAssumptionsSheet.svelte'
import MassingSheet from './sheets/MassingSheet.svelte'
import MilestonesSheet from './sheets/MilestonesSheet.svelte'
import MonthlyCashFlowSheet from './sheets/MonthlyCashFlowSheet.svelte'
import PricingEvidenceSheet from './sheets/PricingEvidenceSheet.svelte'
import ReturnsSheet from './sheets/ReturnsSheet.svelte'
import RevenueSheet from './sheets/RevenueSheet.svelte'
import SourcesUsesSheet from './sheets/SourcesUsesSheet.svelte'
import SummarySheet from './sheets/SummarySheet.svelte'
import VatBridgeSheet from './sheets/VatBridgeSheet.svelte'
import WaterfallSheet from './sheets/WaterfallSheet.svelte'

const isBtr = $derived(workbookStore.assumptions?.developmentModel === 'build_to_rent_residential')

const btsTabs: { id: FeasibilitySheetTab; label: string }[] = [
	{ id: 'key_assumptions', label: 'Key Assumptions' },
	{ id: 'summary', label: 'Summary' },
	{ id: 'massing', label: 'Massing' },
	{ id: 'sales_collections', label: 'Sales & Collections' },
	{ id: 'budget', label: 'Budget' },
	{ id: 'sources_uses', label: 'Sources & Uses' },
	{ id: 'financing', label: 'Financing' },
	{ id: 'monthly_cf', label: 'Cash Flow' },
	{ id: 'returns', label: 'Returns' },
	{ id: 'eibor', label: 'EIBOR' },
	{ id: 'checks', label: 'Checks' },
	{ id: 'pricing_evidence', label: 'Pricing Evidence' }
]

const btrTabs: { id: FeasibilitySheetTab; label: string }[] = [
	{ id: 'key_assumptions', label: 'Assumptions' },
	{ id: 'summary', label: 'Summary' },
	{ id: 'massing', label: 'Massing' },
	{ id: 'btr_operating', label: 'Operating Model' },
	{ id: 'budget', label: 'Dev Budget' },
	{ id: 'sources_uses', label: 'Sources & Uses' },
	{ id: 'financing', label: 'Capital Stack' },
	{ id: 'monthly_cf', label: 'Dev Cash Flow' },
	{ id: 'eibor', label: 'EIBOR' },
	{ id: 'checks', label: 'Checks' },
	{ id: 'pricing_evidence', label: 'Rental Evidence' }
]

const tabs = $derived(isBtr ? btrTabs : btsTabs)

const activeTab = $derived(workbookStore.activeSheet)
let exportError = $state<string | null>(null)

onMount(() => {
	workbookStore.clearSheetDirty(activeTab)
})

function isTabDirty(tab: FeasibilitySheetTab) {
	return workbookStore.sheetDirty?.[tab] ?? false
}

function openTab(tab: FeasibilitySheetTab) {
	workbookStore.setActiveSheet(tab)
}

function exportWorkbook() {
	exportError = null
	const assumptions = workbookStore.assumptions
	const outputs = workbookStore.outputs
	if (!assumptions || !outputs) return
	try {
		downloadFeasibilityWorkbook({
			assumptions,
			outputs,
			research: workbookStore.research,
			studyContext: workbookStore.study_context,
			validation: workbookStore.validation
		})
	} catch (error) {
		exportError = error instanceof Error ? error.message : 'Failed to export workbook'
	}
}
</script>

<div class="h-full flex flex-col overflow-hidden bg-white">
	<div class="flex flex-shrink-0 items-center justify-between gap-3 border-b border-slate-200 bg-white px-4 py-2.5">
		<div class="flex items-center gap-2">
			<span class="text-xs font-semibold text-slate-700">Feasibility Model</span>
			{#if exportError}
				<span class="text-[10px] font-medium text-rose-600">{exportError}</span>
			{/if}
		</div>
		<div class="flex items-center gap-2">
			<details class="relative">
				<summary class="flex h-8 cursor-pointer list-none items-center gap-1.5 rounded-md border border-slate-200 bg-white px-2.5 text-[11px] font-medium text-slate-600 transition hover:border-slate-300 hover:bg-slate-50 hover:text-slate-900">
					<Info size={14} strokeWidth={1.8} />
					Legend
				</summary>
				<div class="absolute right-0 top-10 z-40 w-max max-w-[calc(100vw-2rem)] rounded-md border border-slate-200 bg-white p-3 shadow-lg">
					<ColorLegend />
				</div>
			</details>
			<button
				type="button"
				class="h-8 rounded-md border border-slate-300 bg-white px-3 text-[10px] font-semibold text-slate-600 shadow-sm transition hover:border-navy hover:text-navy disabled:cursor-not-allowed disabled:opacity-50"
				disabled={!workbookStore.outputs || !isBtr}
				title={isBtr ? 'Export BTR workbook to Excel' : 'BTR Excel export is currently available for build-to-rent studies'}
				onclick={exportWorkbook}
			>
				Export Excel
			</button>
		</div>
	</div>

	<div class="flex-1 overflow-hidden flex flex-col min-h-0">
		{#if activeTab === 'key_assumptions'}
			<KeyAssumptionsSheet />
		{:else if activeTab === 'summary'}
			<SummarySheet />
		{:else if activeTab === 'massing'}
			<MassingSheet />
		{:else if activeTab === 'sales_collections'}
			<RevenueSheet />
		{:else if activeTab === 'area_bridge'}
			<AreaBridgeSheet />
		{:else if activeTab === 'budget'}
			<BudgetSheet />
		{:else if activeTab === 'sources_uses'}
			<SourcesUsesSheet />
		{:else if activeTab === 'financing'}
			<FinancingSheet />
		{:else if activeTab === 'monthly_cf'}
			<MonthlyCashFlowSheet />
		{:else if activeTab === 'cashflow'}
			<CashFlowSheet />
		{:else if activeTab === 'returns'}
			<ReturnsSheet />
		{:else if activeTab === 'waterfall'}
			<WaterfallSheet />
		{:else if activeTab === 'vat_bridge'}
			<VatBridgeSheet />
		{:else if activeTab === 'milestones'}
			<MilestonesSheet />
		{:else if activeTab === 'btr_operating'}
			<BtrOperatingSheet />
		{:else if activeTab === 'eibor'}
			<EiborSheet />
		{:else if activeTab === 'pricing_evidence'}
			<PricingEvidenceSheet />
		{:else if activeTab === 'checks'}
			<ChecksSheet />
		{:else}
			<BlankSheet />
		{/if}
	</div>

	<div class="relative z-30 flex-shrink-0 flex items-end gap-0.5 overflow-x-auto border-t border-slate-300 bg-slate-200/60 px-2 pt-1 shadow-[0_-1px_0_rgba(148,163,184,0.18)]">
		{#each tabs as tab (tab.id)}
				<button
					type="button"
					class="relative z-10 px-3 py-1 text-[11px] font-medium rounded-t border border-b-0 border-slate-300 -mb-px whitespace-nowrap transition-colors {activeTab === tab.id
						? 'bg-white text-teal-700 border-t-2 border-t-teal-500'
						: isTabDirty(tab.id)
							? 'bg-teal-50/80 text-teal-600 hover:text-teal-700'
							: 'bg-slate-100/80 text-slate-500 hover:text-slate-700'}"
					onclick={() => openTab(tab.id)}
				>
					{tab.label}
					{#if isTabDirty(tab.id) && activeTab !== tab.id}
						<span class="ml-1 inline-block w-1.5 h-1.5 rounded-full bg-teal-400 align-middle -mt-0.5"></span>
					{/if}
				</button>
		{/each}
	</div>
</div>
