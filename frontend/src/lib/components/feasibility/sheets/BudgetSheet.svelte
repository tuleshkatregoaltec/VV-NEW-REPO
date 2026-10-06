<script lang="ts">
import { workbookStore } from '$lib/feasibility/workbook/store.svelte'
import { toSqft } from '$lib/utils/units'
import AmountInput from '../AmountInput.svelte'

function fmt(value: number, digits = 0): string {
	return value.toLocaleString('en-AE', {
		minimumFractionDigits: digits,
		maximumFractionDigits: digits
	})
}

function fmtAed(value: number): string {
	return fmt(Math.round(value))
}

function fmtPct(value: number, digits = 1): string {
	return `${fmt(value, digits)}%`
}

function dateToQuarter(isoDate: string): string {
	if (!isoDate) return '—'
	const d = new Date(isoDate)
	if (Number.isNaN(d.getTime())) return isoDate
	const q = Math.ceil((d.getMonth() + 1) / 3)
	return `Q${q} ${d.getFullYear()}`
}

function monthsBetween(startIso: string, endIso: string): number | null {
	if (!startIso || !endIso) return null
	const s = new Date(startIso)
	const e = new Date(endIso)
	if (Number.isNaN(s.getTime()) || Number.isNaN(e.getTime())) return null
	return (e.getFullYear() - s.getFullYear()) * 12 + (e.getMonth() - s.getMonth())
}

function setNumber<K extends keyof typeof workbookStore.inputs>(key: K, raw: string) {
	const v = Number(raw)
	workbookStore.updateInputs({ [key]: Number.isFinite(v) ? v : 0 })
}

function setDecimalPct<K extends keyof typeof workbookStore.inputs>(key: K, raw: string) {
	const v = Number(raw)
	workbookStore.updateInputs({ [key]: Number.isFinite(v) ? v / 100 : 0 })
}

const s = workbookStore
const outputs = $derived(workbookStore.outputs)
const isBtr = $derived(workbookStore.assumptions?.developmentModel === 'build_to_rent_residential')
const btr = $derived(outputs?.btr)
const draftBudgetTiming = $derived(s.workbook?.budgetTiming ?? null)
const draftSourcesUses = $derived(s.workbook?.sourcesUses ?? null)

// ── Derived metrics ──────────────────────────────────────────────────────────

const constructionMonths = $derived(
	monthsBetween(s.inputs.constructionDate, s.inputs.handoverDate) ?? 0
)

// Finance costs — prefer draft case values when available
const totalInterestPaid = $derived(s.workbook?.returns?.totalInterestPaidAed ?? 0)
const financingFee = $derived(
	s.workbook?.returns?.financingFeeAed ??
		Math.round(s.totalDebtCapacity * ((s.inputs.financingFeePct ?? 0) / 100))
)
const exitFee = $derived(
	s.workbook?.returns?.exitFeeAed ??
		Math.round(s.totalDebtCapacity * ((s.inputs.exitFeePct ?? 0) / 100))
)
const totalFinanceCosts = $derived(totalInterestPaid + financingFee + exitFee)

// Cost base (pre-finance) — aligns with model ordering
const preFinanceCosts = $derived(
	s.totalLandCostAed +
		s.constructionCostInclInflation +
		s.designSupervisionCost +
		s.marketingCost +
		s.salesAgentFees +
		s.inputs.infrastructureCostAed +
		s.inputs.governmentFeesAed +
		s.inputs.masterCommunityFeesAed +
		(s.inputs.demolitionEnabled ? s.demolitionCost : 0) +
		s.inputs.ffeOsePreopeningCostAed +
		s.contingencyCost
)

// Per-unit / per-sqft metrics
const costPerUnitAed = $derived(s.totalUnits > 0 ? s.modelTotalCostsInclVat / s.totalUnits : 0)
const costPerSqftBua = $derived(
	s.totalBuaSqm > 0 ? s.modelTotalCostsInclVat / toSqft(s.totalBuaSqm) : 0
)
const revenuePerUnitAed = $derived(s.totalUnits > 0 ? s.totalConfiguredRevenue / s.totalUnits : 0)
const profitPerUnitAed = $derived(revenuePerUnitAed - costPerUnitAed)
const grossMarginPct = $derived(
	s.totalConfiguredRevenue > 0
		? ((s.totalConfiguredRevenue - s.modelTotalCostsInclVat) / s.totalConfiguredRevenue) * 100
		: 0
)

// All-in margin (includes finance costs)
const allInProfit = $derived(
	s.workbook?.returns?.allInProjectProfitAed ??
		s.totalConfiguredRevenue - s.modelTotalCostsInclVat - totalFinanceCosts
)
const allInMarginPct = $derived(
	s.workbook?.returns?.allInMarginPct ??
		(s.totalConfiguredRevenue > 0 ? (allInProfit / s.totalConfiguredRevenue) * 100 : 0)
)

// Returns
const equityIrrPct = $derived(s.workbook?.returns?.equityIrrPct ?? null)
const projectIrrPct = $derived(s.projectIrrPct)

// Pct of total
const pct = (amount: number) =>
	s.modelTotalCostsInclVat > 0 ? (amount / s.modelTotalCostsInclVat) * 100 : 0
const revPct = (amount: number) =>
	s.totalConfiguredRevenue > 0 ? (amount / s.totalConfiguredRevenue) * 100 : 0

// Styles — mirroring KeyAssumptionsSheet palette
const INPUT =
	'w-full text-right px-1 py-0 text-[#1565C0] bg-transparent focus:outline-none tabular-nums text-[11px]'
const ROW_STD = 'border-b border-[#D9D9D9]'
const ROW_TOTAL = 'border-t border-[#1F3864] border-b border-[#D9D9D9]'
const LABEL = 'px-2 py-[3px] text-slate-800'
const LABEL_INDENT = 'pl-6 pr-2 py-[3px] text-slate-600 italic text-[10px]'
const LABEL_SM = 'px-2 py-[3px] text-slate-600 text-[10px]'
const VALUE_BLACK = 'px-2 py-[3px] text-right tabular-nums text-slate-900 font-normal'
const VALUE_BOLD = 'px-2 py-[3px] text-right tabular-nums text-slate-900 font-semibold'
const VALUE_BLUE = 'px-2 py-[3px] text-right tabular-nums text-[#1565C0] font-normal'
const PCT_COL = 'px-2 py-[3px] text-right tabular-nums text-slate-400 text-[10px]'
const UNIT = 'px-2 py-[3px] text-slate-500 whitespace-nowrap text-[10px]'
const ROW_INDENT = 'border-b border-[#D9D9D9] bg-[#F9F9F9]'

let sheetScroller = $state<HTMLDivElement | null>(null)
let lastHighlightSequence = $state(0)

function fieldTokens(...fields: string[]): string {
	return fields.join(' ')
}

function hasHighlightedField(...fields: string[]): boolean {
	const active = s.highlightedFields
	return fields.some((field) => active.includes(field))
}

function highlightClass(...fields: string[]): string {
	return hasHighlightedField(...fields) ? 'feasibility-change-flash' : ''
}

function scrollToFirstHighlightedField(): void {
	const fields = s.highlightedFields
	if (!sheetScroller || fields.length === 0) return
	const nodes = Array.from(sheetScroller.querySelectorAll<HTMLElement>('[data-feasibility-field]'))
	const target = fields
		.map((field) =>
			nodes.find((node) => {
				const tokens = node.dataset.feasibilityField?.split(/\s+/) ?? []
				return tokens.includes(field)
			})
		)
		.find(Boolean)
	target?.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'nearest' })
}

$effect(() => {
	if (!sheetScroller || s.highlightSequence === lastHighlightSequence) return
	lastHighlightSequence = s.highlightSequence
	setTimeout(scrollToFirstHighlightedField, 80)
})
</script>

{#if isBtr && btr}
<div
	bind:this={sheetScroller}
	class="overflow-auto flex-1 bg-white text-[11px] font-[Calibri,'Segoe_UI',Arial,sans-serif] select-none"
>
	<div class="bg-[#1F3864] text-white px-4 py-2.5 flex items-start justify-between gap-4">
		<div>
			<div class="text-[13px] font-bold tracking-wide">BTR DEVELOPMENT BUDGET</div>
			<div class="text-[10px] text-blue-200 mt-0.5">AED unless stated</div>
		</div>
	</div>

	<div class="flex border-b border-[#B8C4CE] bg-[#EEF2F7] divide-x divide-[#D9D9D9]">
		<div class="px-2 py-1.5 flex-1">
			<div class="text-[9px] uppercase tracking-wider text-slate-500 font-semibold">Total Dev Cost</div>
			<div class="text-[11px] font-bold text-slate-900 tabular-nums">{fmtAed(btr.devCosts.totalDevCostInclVatAed)}</div>
		</div>
		<div class="px-2 py-1.5 flex-1">
			<div class="text-[9px] uppercase tracking-wider text-slate-500 font-semibold">Dev Financing</div>
			<div class="text-[11px] font-bold text-slate-900 tabular-nums">{fmtAed(btr.returns.totalDevFinancingCostsAed)}</div>
		</div>
		<div class="px-2 py-1.5 flex-1">
			<div class="text-[9px] uppercase tracking-wider text-slate-500 font-semibold">Total Project Cost</div>
			<div class="text-[11px] font-bold text-slate-900 tabular-nums">{fmtAed(btr.returns.totalProjectCostAed)}</div>
		</div>
		<div class="px-2 py-1.5 flex-1">
			<div class="text-[9px] uppercase tracking-wider text-slate-500 font-semibold">Stabilized Yield on Cost</div>
			<div class="text-[11px] font-bold text-slate-900 tabular-nums">{fmtPct(btr.returns.stabilizedYieldOnCostPct)}</div>
		</div>
	</div>

		<table class="w-full border-collapse" style="border-spacing:0">
			<thead>
				<tr class="bg-[#D6DCE4] border-b border-[#B8C4CE]">
					<th class="px-2 py-[4px] text-left text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Line Item</th>
					<th class="px-2 py-[4px] text-right text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Amount (AED)</th>
					<th class="px-2 py-[4px] text-right text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Input / Basis</th>
					<th class="px-2 py-[4px] text-right text-[9px] font-semibold text-slate-600 uppercase tracking-wider">% of Dev Cost</th>
				</tr>
			</thead>
			<tbody>
				<!-- A. Land Acquisition -->
				<tr class="bg-[#D6DCE4] border-b border-[#B8C4CE]">
					<td colspan="4" class="px-2 py-[3px] text-[10px] font-semibold text-slate-700 uppercase tracking-wider">A. Land Acquisition</td>
				</tr>
				<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
					<td class="px-4 py-[3px] text-left text-[10px] text-slate-700">Land acquisition</td>
					<td class="p-0">
						<AmountInput
							value={btr.devCosts.landAcquisitionAed}
							oncommit={(v) => s.updateInputs({ landAcquisitionCostOverrideAed: v > 0 ? v : null })}
							class={INPUT}
						/>
					</td>
					<td class="px-2 py-[3px] text-right tabular-nums text-[10px] text-slate-500">
						{btr.devCosts.landAcquisitionAed > 0 && s.inputs.plotAreaSqm > 0
							? `${fmt(btr.devCosts.landAcquisitionAed / s.inputs.plotAreaSqm, 0)} AED/sqm plot`
							: 'Manual AED'}
					</td>
					<td class="px-2 py-[3px] text-right tabular-nums text-[10px] text-slate-500">
						{btr.sourcesUses.totalUsesAed > 0 ? fmtPct((btr.devCosts.landAcquisitionAed / btr.sourcesUses.totalUsesAed) * 100) : '—'}
					</td>
				</tr>
				<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
					<td class="px-4 py-[3px] text-left text-[10px] text-slate-700">Land transfer fee</td>
					<td class="px-2 py-[3px] text-right tabular-nums text-[10px] text-slate-900">{fmtAed(btr.devCosts.landTransferFeeAed)}</td>
					<td class="p-0">
						<input
							type="number"
							step="0.1"
							min="0"
							class={INPUT}
							value={(s.inputs.landTransferFeePct ?? 0.04) * 100}
							oninput={(e) => setDecimalPct('landTransferFeePct', e.currentTarget.value)}
						/>
					</td>
					<td class="px-2 py-[3px] text-right tabular-nums text-[10px] text-slate-500">
						{btr.sourcesUses.totalUsesAed > 0 ? fmtPct((btr.devCosts.landTransferFeeAed / btr.sourcesUses.totalUsesAed) * 100) : '—'}
					</td>
				</tr>
				<tr class="border-b border-[#D9D9D9] bg-[#F9F9F9]">
					<td class="pl-8 pr-2 py-[3px] text-slate-500 italic text-[10px]">↳ Basis</td>
					<td></td>
					<td class="px-2 py-[3px] text-right tabular-nums text-[10px] text-slate-500">% of land cost</td>
					<td></td>
				</tr>
				<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
					<td class="px-4 py-[3px] text-left text-[10px] text-slate-700">Brokerage</td>
					<td class="px-2 py-[3px] text-right tabular-nums text-[10px] text-slate-900">{fmtAed(btr.devCosts.brokerageFeeAed)}</td>
					<td class="p-0">
						<input
							type="number"
							step="0.1"
							min="0"
							class={INPUT}
							value={(s.inputs.brokeragePct ?? 0.01) * 100}
							oninput={(e) => setDecimalPct('brokeragePct', e.currentTarget.value)}
						/>
					</td>
					<td class="px-2 py-[3px] text-right tabular-nums text-[10px] text-slate-500">
						{btr.sourcesUses.totalUsesAed > 0 ? fmtPct((btr.devCosts.brokerageFeeAed / btr.sourcesUses.totalUsesAed) * 100) : '—'}
					</td>
				</tr>
				<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
					<td class="px-4 py-[3px] text-left text-[10px] text-slate-700">Legal / due diligence</td>
					<td class="px-2 py-[3px] text-right tabular-nums text-[10px] text-slate-900">{fmtAed(btr.devCosts.legalDdCostAed)}</td>
					<td class="p-0">
						<input
							type="number"
							step="0.1"
							min="0"
							class={INPUT}
							value={(s.inputs.legalDdPct ?? 0.005) * 100}
							oninput={(e) => setDecimalPct('legalDdPct', e.currentTarget.value)}
						/>
					</td>
					<td class="px-2 py-[3px] text-right tabular-nums text-[10px] text-slate-500">
						{btr.sourcesUses.totalUsesAed > 0 ? fmtPct((btr.devCosts.legalDdCostAed / btr.sourcesUses.totalUsesAed) * 100) : '—'}
					</td>
				</tr>
				<!-- B. Construction -->
				<tr class="bg-[#D6DCE4] border-b border-[#B8C4CE]">
					<td colspan="4" class="px-2 py-[3px] text-[10px] font-semibold text-slate-700 uppercase tracking-wider">B. Construction</td>
				</tr>
				<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
					<td class="px-4 py-[3px] text-left text-[10px] text-slate-700">
						Hard cost <span class="text-slate-400 font-normal italic">(rate × costable BUA)</span>
					</td>
					<td class="px-2 py-[3px] text-right tabular-nums text-[10px] text-slate-900">{fmtAed(btr.devCosts.hardCostAed)}</td>
					<td class="p-0">
						<input
							type="number"
							step="10"
							min="0"
							class={INPUT}
							value={Math.round(s.inputs.constructionCostPsqmBua * 0.092903)}
							oninput={(e) => s.updateInputs({ constructionCostPsqmBua: (Number(e.currentTarget.value) || 0) / 0.092903, constructionCostOverrideAed: null })}
						/>
					</td>
					<td class="px-2 py-[3px] text-right tabular-nums text-[10px] text-slate-500">
						{btr.sourcesUses.totalUsesAed > 0 ? fmtPct((btr.devCosts.hardCostAed / btr.sourcesUses.totalUsesAed) * 100) : '—'}
					</td>
				</tr>
				<tr class="border-b border-[#D9D9D9] bg-[#F9F9F9]">
					<td class="pl-8 pr-2 py-[3px] text-slate-500 italic text-[10px]">↳ Costable BUA</td>
					<td class="px-2 py-[3px] text-right tabular-nums text-[10px] text-slate-500">{fmt(toSqft(s.totalBuaSqm), 0)} sqft</td>
					<td class="px-2 py-[3px] text-right tabular-nums text-[10px] text-slate-500">AED / sqft BUA</td>
					<td></td>
				</tr>
				<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
					<td class="px-4 py-[3px] text-left text-[10px] text-slate-700">Permit fees</td>
					<td class="px-2 py-[3px] text-right tabular-nums text-[10px] text-slate-900">{fmtAed(btr.devCosts.permitFeesAed)}</td>
					<td class="p-0">
						<input
							type="number"
							step="0.1"
							min="0"
							class={INPUT}
							value={(s.inputs.permitFeesPct ?? 0.02) * 100}
							oninput={(e) => setDecimalPct('permitFeesPct', e.currentTarget.value)}
						/>
					</td>
					<td class="px-2 py-[3px] text-right tabular-nums text-[10px] text-slate-500">
						{btr.sourcesUses.totalUsesAed > 0 ? fmtPct((btr.devCosts.permitFeesAed / btr.sourcesUses.totalUsesAed) * 100) : '—'}
					</td>
				</tr>
				<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
					<td class="px-4 py-[3px] text-left text-[10px] text-slate-700">Soft cost (design / supervision)</td>
					<td class="px-2 py-[3px] text-right tabular-nums text-[10px] text-slate-900">{fmtAed(btr.devCosts.softCostAed)}</td>
					<td class="p-0">
						<input
							type="number"
							step="0.1"
							min="0"
							class={INPUT}
							value={(s.inputs.softCostPct ?? 0.15) * 100}
							oninput={(e) => setDecimalPct('softCostPct', e.currentTarget.value)}
						/>
					</td>
					<td class="px-2 py-[3px] text-right tabular-nums text-[10px] text-slate-500">
						{btr.sourcesUses.totalUsesAed > 0 ? fmtPct((btr.devCosts.softCostAed / btr.sourcesUses.totalUsesAed) * 100) : '—'}
					</td>
				</tr>
				<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
					<td class="px-4 py-[3px] text-left text-[10px] text-slate-700">Contingency</td>
					<td class="p-0">
						<AmountInput
							value={btr.devCosts.contingencyCostAed}
							oncommit={(v) => s.updateInputs({ contingencyCostOverrideAed: v > 0 ? v : null })}
							class={INPUT}
						/>
					</td>
					<td class="p-0">
						<input
							type="number"
							step="0.5"
							min="0"
							class={INPUT}
							value={s.inputs.contingencyPct}
							oninput={(e) => {
								const v = Number(e.currentTarget.value)
								s.updateInputs({ contingencyPct: Number.isFinite(v) ? v : 0, contingencyCostOverrideAed: null })
							}}
						/>
					</td>
					<td class="px-2 py-[3px] text-right tabular-nums text-[10px] text-slate-500">
						{btr.sourcesUses.totalUsesAed > 0 ? fmtPct((btr.devCosts.contingencyCostAed / btr.sourcesUses.totalUsesAed) * 100) : '—'}
					</td>
				</tr>
				<tr class="border-b border-[#D9D9D9] bg-[#F9F9F9]">
					<td class="pl-8 pr-2 py-[3px] text-slate-500 italic text-[10px]">↳ Basis</td>
					<td class="px-2 py-[3px] text-right tabular-nums text-[10px] text-slate-500">Manual AED or %</td>
					<td class="px-2 py-[3px] text-right tabular-nums text-[10px] text-slate-500">% of hard cost</td>
					<td></td>
				</tr>
			<!-- C. Statutory & Development -->
				<tr class="bg-[#D6DCE4] border-b border-[#B8C4CE]">
					<td colspan="4" class="px-2 py-[3px] text-[10px] font-semibold text-slate-700 uppercase tracking-wider">C. Statutory &amp; Development</td>
				</tr>
				<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
					<td class="px-4 py-[3px] text-left text-[10px] text-slate-700">Infrastructure &amp; utilities</td>
					<td class="p-0">
						<AmountInput value={btr.devCosts.infrastructureCostAed ?? 0} oncommit={(v) => s.updateInputs({ infrastructureCostAed: v })} class={INPUT} />
					</td>
					<td class="px-2 py-[3px] text-right tabular-nums text-[10px] text-slate-500">Fixed AED</td>
					<td class="px-2 py-[3px] text-right tabular-nums text-[10px] text-slate-500">
						{btr.sourcesUses.totalUsesAed > 0 ? fmtPct(((btr.devCosts.infrastructureCostAed ?? 0) / btr.sourcesUses.totalUsesAed) * 100) : '—'}
					</td>
				</tr>
				<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
					<td class="px-4 py-[3px] text-left text-[10px] text-slate-700">Authority / government fees</td>
					<td class="p-0">
						<AmountInput value={btr.devCosts.governmentFeesAed ?? 0} oncommit={(v) => s.updateInputs({ governmentFeesAed: v })} class={INPUT} />
					</td>
					<td class="px-2 py-[3px] text-right tabular-nums text-[10px] text-slate-500">Fixed AED</td>
					<td class="px-2 py-[3px] text-right tabular-nums text-[10px] text-slate-500">
						{btr.sourcesUses.totalUsesAed > 0 ? fmtPct(((btr.devCosts.governmentFeesAed ?? 0) / btr.sourcesUses.totalUsesAed) * 100) : '—'}
					</td>
				</tr>
				<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
					<td class="px-4 py-[3px] text-left text-[10px] text-slate-700">Master community fees</td>
					<td class="p-0">
						<AmountInput value={btr.devCosts.masterCommunityFeesAed ?? 0} oncommit={(v) => s.updateInputs({ masterCommunityFeesAed: v })} class={INPUT} />
					</td>
					<td class="px-2 py-[3px] text-right tabular-nums text-[10px] text-slate-500">Fixed AED</td>
					<td class="px-2 py-[3px] text-right tabular-nums text-[10px] text-slate-500">
						{btr.sourcesUses.totalUsesAed > 0 ? fmtPct(((btr.devCosts.masterCommunityFeesAed ?? 0) / btr.sourcesUses.totalUsesAed) * 100) : '—'}
					</td>
				</tr>
				<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
					<td class="px-4 py-[3px] text-left text-[10px] text-slate-700">FFE / OS&amp;E / pre-opening</td>
					<td class="p-0">
						<AmountInput value={btr.devCosts.ffeOsePreopeningCostAed ?? 0} oncommit={(v) => s.updateInputs({ ffeOsePreopeningCostAed: v })} class={INPUT} />
					</td>
					<td class="px-2 py-[3px] text-right tabular-nums text-[10px] text-slate-500">Fixed AED</td>
					<td class="px-2 py-[3px] text-right tabular-nums text-[10px] text-slate-500">
						{btr.sourcesUses.totalUsesAed > 0 ? fmtPct(((btr.devCosts.ffeOsePreopeningCostAed ?? 0) / btr.sourcesUses.totalUsesAed) * 100) : '—'}
					</td>
				</tr>
				<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
					<td class="px-4 py-[3px] text-left text-[10px] text-slate-700">Demolition / enabling works</td>
					<td class="p-0">
						<AmountInput value={btr.devCosts.demolitionCostAed ?? s.inputs.demolitionCostAed ?? 0} oncommit={(v) => s.updateInputs({ demolitionEnabled: v > 0, demolitionCostAed: v })} class={INPUT} />
					</td>
					<td class="px-2 py-[3px] text-right tabular-nums text-[10px] text-slate-500">Fixed AED</td>
					<td class="px-2 py-[3px] text-right tabular-nums text-[10px] text-slate-500">
						{btr.sourcesUses.totalUsesAed > 0 ? fmtPct(((btr.devCosts.demolitionCostAed ?? 0) / btr.sourcesUses.totalUsesAed) * 100) : '—'}
					</td>
				</tr>
				<!-- D. Lease-Up -->
				<tr class="bg-[#D6DCE4] border-b border-[#B8C4CE]">
					<td colspan="4" class="px-2 py-[3px] text-[10px] font-semibold text-slate-700 uppercase tracking-wider">D. Lease-Up</td>
				</tr>
				<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
					<td class="px-4 py-[3px] text-left text-[10px] text-slate-700">Lease-up marketing budget</td>
					<td class="p-0">
						<AmountInput
							value={btr.devCosts.leaseUpMarketingAed}
							oncommit={(v) => s.updateInputs({ btrLeaseUpMarketingAed: v })}
							class={INPUT}
						/>
					</td>
					<td class="px-2 py-[3px] text-right tabular-nums text-[10px] text-slate-500">Fixed AED</td>
					<td class="px-2 py-[3px] text-right tabular-nums text-[10px] text-slate-500">
						{btr.sourcesUses.totalUsesAed > 0 ? fmtPct((btr.devCosts.leaseUpMarketingAed / btr.sourcesUses.totalUsesAed) * 100) : '—'}
					</td>
				</tr>
			<!-- VAT subtotal -->
				<tr class="bg-[#FFF9E6] border-b border-[#F0E6B0]">
					<td class="px-2 py-[3px] text-left text-[10px] font-semibold text-amber-800">VAT (gross paid, 5% recoverable)</td>
					<td class="px-2 py-[3px] text-right tabular-nums text-[10px] font-semibold text-amber-800">{fmtAed(btr.sourcesUses.totalVatAed)}</td>
					<td class="p-0">
						<input
							type="number"
							step="0.1"
							min="0"
							class="{INPUT} text-amber-700"
							value={s.inputs.vatPct}
							oninput={(e) => setNumber('vatPct', e.currentTarget.value)}
						/>
					</td>
					<td class="px-2 py-[3px] text-right tabular-nums text-[10px] text-amber-700">
						{btr.sourcesUses.totalUsesAed > 0 ? fmtPct((btr.sourcesUses.totalVatAed / btr.sourcesUses.totalUsesAed) * 100) : '—'}
					</td>
				</tr>
				<tr class="border-b border-[#F0E6B0] bg-[#FFFDF4]">
					<td class="pl-8 pr-2 py-[3px] text-amber-700 italic text-[10px]">↳ Basis</td>
					<td></td>
					<td class="px-2 py-[3px] text-right tabular-nums text-[10px] text-amber-700">% VAT rate</td>
					<td></td>
				</tr>
				<!-- E. Dev Financing -->
				<tr class="bg-[#D6DCE4] border-b border-[#B8C4CE]">
					<td colspan="4" class="px-2 py-[3px] text-[10px] font-semibold text-slate-700 uppercase tracking-wider">E. Dev Financing</td>
				</tr>
				<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
					<td class="px-4 py-[3px] text-left text-[10px] text-slate-700">Capitalized dev interest carry</td>
					<td class="px-2 py-[3px] text-right tabular-nums text-[10px] text-slate-900">{fmtAed(btr.sourcesUses.devFinancingCostsAed)}</td>
					<td class="px-2 py-[3px] text-right tabular-nums text-[10px] text-slate-500">Derived from dev CF</td>
					<td class="px-2 py-[3px] text-right tabular-nums text-[10px] text-slate-500">
						{btr.sourcesUses.totalUsesAed > 0 ? fmtPct((btr.sourcesUses.devFinancingCostsAed / btr.sourcesUses.totalUsesAed) * 100) : '—'}
					</td>
				</tr>
			<!-- Grand total -->
				<tr class="border-t-2 border-[#1F3864] bg-[#1F3864]">
					<td class="px-2 py-[4px] text-left text-[11px] font-bold text-white">TOTAL PROJECT COST (all-in)</td>
					<td class="px-2 py-[4px] text-right tabular-nums text-[11px] font-bold text-white">{fmtAed(btr.sourcesUses.totalUsesAed)}</td>
					<td class="px-2 py-[4px] text-right tabular-nums text-[10px] font-semibold text-blue-200">Includes dev financing</td>
					<td class="px-2 py-[4px] text-right tabular-nums text-[10px] font-semibold text-blue-200">100.0%</td>
				</tr>
		</tbody>
	</table>
</div>
{:else}
<div
	bind:this={sheetScroller}
	class="overflow-auto flex-1 bg-white text-[11px] font-[Calibri,'Segoe_UI',Arial,sans-serif] select-none"
>

	<!-- Header -->
	<div class="bg-[#1F3864] text-white px-4 py-2.5 flex items-start justify-between gap-4">
		<div>
			<div class="text-[13px] font-bold tracking-wide">DEVELOPMENT BUDGET</div>
			<div class="text-[10px] text-blue-200 mt-0.5">AED unless stated</div>
		</div>
	</div>

	<!-- Summary bar -->
	<div class="flex border-b border-[#B8C4CE] bg-[#EEF2F7] divide-x divide-[#D9D9D9]">
		<div class="px-2 py-1.5 flex-1">
			<div class="text-[9px] uppercase tracking-wider text-slate-500 font-semibold">Total Budget (incl. VAT)</div>
			<div class="text-[11px] font-bold text-slate-900 tabular-nums">{fmtAed(s.modelTotalCostsInclVat)}</div>
		</div>
		<div class="px-2 py-1.5 flex-1">
			<div class="text-[9px] uppercase tracking-wider text-slate-500 font-semibold">Gross Margin</div>
			<div class="text-[11px] font-bold text-slate-900 tabular-nums">{fmtPct(grossMarginPct)}</div>
		</div>
		<div class="px-2 py-1.5 flex-1">
			<div class="text-[9px] uppercase tracking-wider text-slate-500 font-semibold">All-in Margin</div>
			<div class="text-[11px] font-bold text-slate-900 tabular-nums">{fmtPct(allInMarginPct)}</div>
		</div>
		<div class="px-2 py-1.5 flex-1">
			<div class="text-[9px] uppercase tracking-wider text-slate-500 font-semibold">Construction Period</div>
			<div class="text-[11px] font-bold text-slate-900 tabular-nums">{constructionMonths > 0 ? constructionMonths : '—'} months</div>
		</div>
	</div>

	{#if draftBudgetTiming}
		<div class="flex border-b border-[#D9D9D9] bg-slate-50 divide-x divide-[#D9D9D9]">
			<div class="px-2 py-1.5 flex-1">
				<div class="text-[9px] uppercase tracking-wider text-slate-500 font-semibold">Timed Budget Total</div>
				<div class="text-[11px] font-bold text-slate-900 tabular-nums">{fmtAed(draftBudgetTiming.totalBudgetedCostsAed)}</div>
			</div>
			<div class="px-2 py-1.5 flex-1">
				<div class="text-[9px] uppercase tracking-wider text-slate-500 font-semibold">Source / Use Gap</div>
				<div class="text-[11px] font-bold {draftSourcesUses && Math.abs(draftSourcesUses.gapAed) > 1_000_000 ? 'text-amber-700' : 'text-slate-900'} tabular-nums">
					{fmtAed(draftSourcesUses?.gapAed ?? 0)}
				</div>
			</div>
			<div class="px-2 py-1.5 flex-1">
				<div class="text-[9px] uppercase tracking-wider text-slate-500 font-semibold">Selling Costs</div>
				<div class="text-[11px] font-bold text-slate-900 tabular-nums">
					{fmtAed(draftBudgetTiming.periods.reduce((sum: number, period: { sellingCostsAed: number }) => sum + period.sellingCostsAed, 0))}
				</div>
			</div>
			<div class="px-2 py-1.5 flex-1">
				<div class="text-[9px] uppercase tracking-wider text-slate-500 font-semibold">Construction-Related</div>
				<div class="text-[11px] font-bold text-slate-900 tabular-nums">
					{fmtAed(draftBudgetTiming.periods.reduce((sum: number, period: { constructionRelatedCostsAed: number }) => sum + period.constructionRelatedCostsAed, 0))}
				</div>
			</div>
		</div>

		<div class="border-b border-[#D9D9D9] bg-white">
			<div class="px-4 py-2 text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500 bg-slate-50 border-b border-[#E5E7EB]">
				Timed Budget
			</div>
			<div class="overflow-x-auto">
				<table class="w-full border-collapse text-[10px]">
					<thead>
						<tr class="bg-[#EEF2F7] border-b border-[#D9D9D9]">
							<th class="px-2 py-[4px] text-left text-slate-600 font-semibold uppercase tracking-[0.08em]">Period</th>
							<th class="px-2 py-[4px] text-right text-slate-600 font-semibold uppercase tracking-[0.08em]">Budgeted</th>
							<th class="px-2 py-[4px] text-right text-slate-600 font-semibold uppercase tracking-[0.08em]">Selling</th>
							<th class="px-2 py-[4px] text-right text-slate-600 font-semibold uppercase tracking-[0.08em]">Construction Rel.</th>
							<th class="px-2 py-[4px] text-right text-slate-600 font-semibold uppercase tracking-[0.08em]">VAT</th>
						</tr>
					</thead>
					<tbody>
						{#each draftBudgetTiming.periods as period (period.periodEndDate)}
							<tr class="border-b border-[#F1F5F9]">
								<td class="px-2 py-[3px] text-slate-700">{period.periodLabel}</td>
								<td class="px-2 py-[3px] text-right tabular-nums text-slate-900">{fmtAed(period.budgetedCostsAed)}</td>
								<td class="px-2 py-[3px] text-right tabular-nums text-slate-500">{period.sellingCostsAed > 0 ? fmtAed(period.sellingCostsAed) : '—'}</td>
								<td class="px-2 py-[3px] text-right tabular-nums text-slate-500">{period.constructionRelatedCostsAed > 0 ? fmtAed(period.constructionRelatedCostsAed) : '—'}</td>
								<td class="px-2 py-[3px] text-right tabular-nums text-slate-500">{period.vatCostsAed > 0 ? fmtAed(period.vatCostsAed) : '—'}</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		</div>
	{/if}

	<table class="w-full border-collapse" style="border-spacing:0">
		<colgroup>
			<col style="width:2.5%">    <!-- row ref -->
			<col style="width:32%">     <!-- label -->
			<col style="width:7%">      <!-- timing -->
			<col style="width:18%">     <!-- amount -->
			<col style="width:9%">      <!-- rate/pct -->
			<col style="width:7%">      <!-- % of total -->
			<col style="width:13%">     <!-- VAT -->
			<col style="width:11.5%">   <!-- unit -->
		</colgroup>

		<!-- Column headers -->
		<thead>
			<tr class="bg-[#D6DCE4] border-b border-[#B8C4CE]">
				<th class="px-1 py-[4px] text-center text-[9px] font-semibold text-slate-500 uppercase tracking-wider">#</th>
				<th class="px-2 py-[4px] text-left text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Line Item</th>
				<th class="px-2 py-[4px] text-center text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Timing</th>
				<th class="px-2 py-[4px] text-right text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Amount (AED)</th>
				<th class="px-2 py-[4px] text-right text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Rate</th>
				<th class="px-2 py-[4px] text-right text-[9px] font-semibold text-slate-600 uppercase tracking-wider">% Budget</th>
				<th class="px-2 py-[4px] text-right text-[9px] font-semibold text-slate-600 uppercase tracking-wider">VAT (AED)</th>
				<th class="px-2 py-[4px] text-left text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Basis</th>
			</tr>
		</thead>

		<tbody>

		<!-- ═══════════════════════════════════════════════════════════
		     SECTION A — LAND ACQUISITION
		     ═══════════════════════════════════════════════════════════ -->
		<tr class="bg-[#1F3864]">
			<td colspan="8" class="px-2 py-[4px] text-white font-bold text-[11px] tracking-wide">A. &nbsp; LAND ACQUISITION</td>
		</tr>

		<tr class={ROW_STD}>
			<td class="px-1 py-[3px] text-slate-400 text-[10px] text-center">1</td>
			<td class={LABEL}>Land Purchase Price</td>
			<td
				class={`p-0 relative ${highlightClass('landAcquisitionDate')}`}
				data-feasibility-field="landAcquisitionDate"
			>
				<div class="flex items-center justify-center px-1 py-[3px] pointer-events-none">
					<span class="text-[#1565C0] tabular-nums text-[10px]">{dateToQuarter(s.inputs.landAcquisitionDate)}</span>
					<span class="ml-0.5 text-[8px] text-slate-400 border border-slate-200 rounded px-0.5">▾</span>
				</div>
				<input type="date" class="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
					value={s.inputs.landAcquisitionDate}
					oninput={(e) => s.updateInputs({ landAcquisitionDate: e.currentTarget.value })} />
			</td>
			<td
				class={`p-0 ${highlightClass('landAcquisitionCostOverrideAed', 'landPricePsqm')}`}
				data-feasibility-field={fieldTokens('landAcquisitionCostOverrideAed', 'landPricePsqm')}
			>
				<AmountInput
					value={s.plotAcquisitionCost}
					oncommit={(v) => s.updateInputs({ landAcquisitionCostOverrideAed: v > 0 ? v : null })}
					class={INPUT}
				/>
			</td>
			<td class={VALUE_BLACK}>{s.maxGfaSqm > 0 ? fmt(s.plotAcquisitionCost / toSqft(s.maxGfaSqm), 0) : '—'}</td>
			<td class={PCT_COL}>{fmtPct(pct(s.plotAcquisitionCost))}</td>
			<td class={VALUE_BLACK}>{fmtAed(outputs?.costs.vatLandAed ?? 0)}</td>
			<td class={UNIT}>AED / sqft GFA</td>
		</tr>

		<tr class={ROW_INDENT}>
			<td></td>
			<td class={LABEL_INDENT}>↳ Transfer Fee (4% of purchase)</td>
			<td class="px-2 py-[3px] text-center text-[10px] text-slate-400">{dateToQuarter(s.inputs.landAcquisitionDate)}</td>
			<td class={VALUE_BLACK}>{fmtAed(s.landTransferFeeAed)}</td>
			<td class="px-2 py-[3px] text-right text-[10px] text-slate-400">4.0%</td>
			<td class={PCT_COL}>{fmtPct(pct(s.landTransferFeeAed))}</td>
			<td class={PCT_COL}>—</td>
			<td class={UNIT}>of purchase</td>
		</tr>

		<tr class={ROW_STD}>
			<td class="px-1 py-[3px] text-slate-400 text-[10px] text-center">2</td>
			<td class={LABEL}>Brokerage Fee</td>
			<td class="px-2 py-[3px] text-center text-[10px] text-slate-400">{dateToQuarter(s.inputs.landAcquisitionDate)}</td>
			<td
				class={`p-0 ${highlightClass('brokerageFeeAed')}`}
				data-feasibility-field="brokerageFeeAed"
			>
				<AmountInput value={s.inputs.brokerageFeeAed}
					oncommit={(v) => s.updateInputs({ brokerageFeeAed: v })} class={INPUT} />
			</td>
			<td class={PCT_COL}></td>
			<td class={PCT_COL}>{fmtPct(pct(s.inputs.brokerageFeeAed))}</td>
			<td class={PCT_COL}>—</td>
			<td class={UNIT}>fixed AED</td>
		</tr>

		<tr class={ROW_STD}>
			<td class="px-1 py-[3px] text-slate-400 text-[10px] text-center">3</td>
			<td class={LABEL}>Legal / Due Diligence</td>
			<td class="px-2 py-[3px] text-center text-[10px] text-slate-400">{dateToQuarter(s.inputs.landAcquisitionDate)}</td>
			<td
				class={`p-0 ${highlightClass('legalDdCostAed')}`}
				data-feasibility-field="legalDdCostAed"
			>
				<AmountInput value={s.inputs.legalDdCostAed}
					oncommit={(v) => s.updateInputs({ legalDdCostAed: v })} class={INPUT} />
			</td>
			<td class={PCT_COL}></td>
			<td class={PCT_COL}>{fmtPct(pct(s.inputs.legalDdCostAed))}</td>
			<td class={PCT_COL}>—</td>
			<td class={UNIT}>fixed AED</td>
		</tr>

		<tr class={ROW_TOTAL}>
			<td></td>
			<td class="px-2 py-[3px] font-semibold text-slate-900">Total Land Cost</td>
			<td></td>
			<td class={VALUE_BOLD}>{fmtAed(s.totalLandCostAed)}</td>
			<td></td>
			<td class="px-2 py-[3px] text-right tabular-nums text-slate-600 text-[10px] font-semibold">{fmtPct(pct(s.totalLandCostAed))}</td>
			<td class={VALUE_BOLD}>{fmtAed(outputs?.costs.vatLandAed ?? 0)}</td>
			<td class={UNIT}>AED</td>
		</tr>

		<!-- ═══════════════════════════════════════════════════════════
		     SECTION B — CONSTRUCTION
		     ═══════════════════════════════════════════════════════════ -->
		<tr class="bg-[#1F3864]">
			<td colspan="8" class="px-2 py-[4px] text-white font-bold text-[11px] tracking-wide">B. &nbsp; CONSTRUCTION</td>
		</tr>

		{#if s.inputs.demolitionEnabled}
		<tr class={ROW_STD}>
			<td class="px-1 py-[3px] text-slate-400 text-[10px] text-center">4</td>
			<td class={LABEL}>Demolition / Enabling Works</td>
			<td
				class={`p-0 relative ${highlightClass('demolitionEnablingDate')}`}
				data-feasibility-field="demolitionEnablingDate"
			>
				<div class="flex items-center justify-center px-1 py-[3px] pointer-events-none">
					<span class="text-[#1565C0] tabular-nums text-[10px]">{dateToQuarter(s.inputs.demolitionEnablingDate)}</span>
					<span class="ml-0.5 text-[8px] text-slate-400 border border-slate-200 rounded px-0.5">▾</span>
				</div>
				<input type="date" class="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
					value={s.inputs.demolitionEnablingDate}
					oninput={(e) => s.updateInputs({ demolitionEnablingDate: e.currentTarget.value })} />
			</td>
			<td
				class={`p-0 ${highlightClass('demolitionCostAed')}`}
				data-feasibility-field="demolitionCostAed"
			>
				<AmountInput value={s.inputs.demolitionCostAed}
					oncommit={(v) => s.updateInputs({ demolitionCostAed: v })} class={INPUT} />
			</td>
			<td class={PCT_COL}></td>
			<td class={PCT_COL}>{fmtPct(pct(s.demolitionCost))}</td>
			<td class={PCT_COL}>—</td>
			<td class={UNIT}>fixed AED</td>
		</tr>
		{/if}

		<tr class={ROW_STD}>
			<td class="px-1 py-[3px] text-slate-400 text-[10px] text-center">5</td>
			<td class={LABEL}>Construction Cost <span class="text-slate-400 font-normal italic">(Rate × BUA)</span></td>
			<td
				class={`p-0 relative ${highlightClass('constructionDate')}`}
				data-feasibility-field="constructionDate"
			>
				<div class="flex items-center justify-center px-1 py-[3px] pointer-events-none">
					<span class="text-[#1565C0] tabular-nums text-[10px]">{dateToQuarter(s.inputs.constructionDate)}</span>
					<span class="ml-0.5 text-[8px] text-slate-400 border border-slate-200 rounded px-0.5">▾</span>
				</div>
				<input type="date" class="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
					value={s.inputs.constructionDate}
					oninput={(e) => s.updateInputs({ constructionDate: e.currentTarget.value })} />
			</td>
			<td class={VALUE_BLACK}>{fmtAed(s.constructionCostInclInflation)}</td>
			<td
				class={`p-0 ${highlightClass('constructionCostPsqmBua', 'constructionCostOverrideAed')}`}
				data-feasibility-field={fieldTokens('constructionCostPsqmBua', 'constructionCostOverrideAed')}
			>
				<input type="number" step="10" class={INPUT}
					value={Math.round(s.inputs.constructionCostPsqmBua * 0.092903)}
					oninput={(e) => s.updateInputs({ constructionCostPsqmBua: (Number(e.currentTarget.value) || 0) / 0.092903 })} />
			</td>
			<td class={PCT_COL}>{fmtPct(pct(s.constructionCostInclInflation))}</td>
			<td class={VALUE_BLACK}>{fmtAed(outputs?.costs.vatHardCostAed ?? 0)}</td>
			<td class={UNIT}>AED / sqft BUA</td>
		</tr>

		<tr class={ROW_INDENT}>
			<td></td>
			<td class={LABEL_INDENT}>↳ BUA ({fmt(toSqft(s.totalBuaSqm), 0)} sqft = GFA × {s.inputs.buaMultiplier}x + parking)</td>
			<td></td>
			<td class={VALUE_BLACK}></td>
			<td class={PCT_COL}></td>
			<td></td>
			<td></td>
			<td class={UNIT}></td>
		</tr>

		{#if s.inputs.midPointInflationPct > 0}
		<tr class={ROW_INDENT}>
			<td></td>
			<td class={LABEL_INDENT}>↳ Inflation adjustment ({fmt(s.inputs.midPointInflationPct, 1)}%)</td>
			<td></td>
			<td class={VALUE_BLACK}>{fmtAed(s.inflationCost)}</td>
			<td
				class={`p-0 ${highlightClass('midPointInflationPct')}`}
				data-feasibility-field="midPointInflationPct"
			>
				<input type="number" step="0.1" min="0" class={INPUT}
					value={s.inputs.midPointInflationPct}
					oninput={(e) => setNumber('midPointInflationPct', e.currentTarget.value)} />
			</td>
			<td></td>
			<td></td>
			<td class={UNIT}>% of base cost</td>
		</tr>
		{/if}

		<tr class={ROW_STD}>
			<td class="px-1 py-[3px] text-slate-400 text-[10px] text-center">→</td>
			<td class={LABEL_SM}>Handover Date</td>
			<td
				class={`p-0 relative ${highlightClass('handoverDate')}`}
				data-feasibility-field="handoverDate"
			>
				<div class="flex items-center justify-center px-1 py-[3px] pointer-events-none">
					<span class="text-[#1565C0] tabular-nums text-[10px]">{dateToQuarter(s.inputs.handoverDate)}</span>
					<span class="ml-0.5 text-[8px] text-slate-400 border border-slate-200 rounded px-0.5">▾</span>
				</div>
				<input type="date" class="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
					value={s.inputs.handoverDate}
					oninput={(e) => s.updateInputs({ handoverDate: e.currentTarget.value })} />
			</td>
			<td class="px-2 py-[3px] text-right text-[10px] text-slate-500">
				{constructionMonths > 0 ? constructionMonths + ' month build' : '—'}
			</td>
			<td></td>
			<td></td>
			<td></td>
			<td class={UNIT}>Q &amp; Year</td>
		</tr>

		<!-- ═══════════════════════════════════════════════════════════
		     SECTION C — SOFT COSTS
		     ═══════════════════════════════════════════════════════════ -->
		<tr class="bg-[#1F3864]">
			<td colspan="8" class="px-2 py-[4px] text-white font-bold text-[11px] tracking-wide">C. &nbsp; SOFT COSTS</td>
		</tr>

		<tr class={ROW_STD}>
			<td class="px-1 py-[3px] text-slate-400 text-[10px] text-center">6</td>
			<td class={LABEL}>Design &amp; Supervision</td>
			<td class="px-2 py-[3px] text-center text-[10px] text-slate-400">Con→HO</td>
			<td
				class={`p-0 ${highlightClass('designSupervisionCostOverrideAed')}`}
				data-feasibility-field="designSupervisionCostOverrideAed"
			>
				<AmountInput value={s.designSupervisionCost}
					oncommit={(v) => s.updateInputs({ designSupervisionCostOverrideAed: v > 0 ? v : null })}
					class={INPUT} />
			</td>
			<td
				class={`p-0 ${highlightClass('designSupervisionPct')}`}
				data-feasibility-field="designSupervisionPct"
			>
				<input type="number" step="0.5" min="0" class={INPUT}
					value={s.inputs.designSupervisionPct}
					oninput={(e) => setNumber('designSupervisionPct', e.currentTarget.value)} />
			</td>
			<td class={PCT_COL}>{fmtPct(pct(s.designSupervisionCost))}</td>
			<td class={VALUE_BLACK}>{fmtAed(outputs?.costs.vatSoftCostAed ?? 0)}</td>
			<td class={UNIT}>% of construction</td>
		</tr>

		<tr class={ROW_STD}>
			<td class="px-1 py-[3px] text-slate-400 text-[10px] text-center">7</td>
			<td class={LABEL}>Marketing</td>
			<td class="px-2 py-[3px] text-center text-[10px] text-slate-400">Sales period</td>
			<td
				class={`p-0 ${highlightClass('marketingCostOverrideAed')}`}
				data-feasibility-field="marketingCostOverrideAed"
			>
				<AmountInput value={s.marketingCost}
					oncommit={(v) => s.updateInputs({ marketingCostOverrideAed: v > 0 ? v : null })}
					class={INPUT} />
			</td>
			<td
				class={`p-0 ${highlightClass('marketingCostPct')}`}
				data-feasibility-field="marketingCostPct"
			>
				<input type="number" step="0.1" min="0" class={INPUT}
					value={s.inputs.marketingCostPct}
					oninput={(e) => setNumber('marketingCostPct', e.currentTarget.value)} />
			</td>
			<td class={PCT_COL}>{fmtPct(pct(s.marketingCost))}</td>
			<td class={VALUE_BLACK}>{fmtAed(outputs?.costs.vatMarketingAed ?? 0)}</td>
			<td class={UNIT}>% of revenue</td>
		</tr>

		<tr class={ROW_STD}>
			<td class="px-1 py-[3px] text-slate-400 text-[10px] text-center">8</td>
			<td class={LABEL}>Sales Agent Fees</td>
			<td class="px-2 py-[3px] text-center text-[10px] text-slate-400">Sales period</td>
			<td
				class={`p-0 ${highlightClass('salesAgentFeesOverrideAed')}`}
				data-feasibility-field="salesAgentFeesOverrideAed"
			>
				<AmountInput value={s.salesAgentFees}
					oncommit={(v) => s.updateInputs({ salesAgentFeesOverrideAed: v > 0 ? v : null })}
					class={INPUT} />
			</td>
			<td
				class={`p-0 ${highlightClass('salesAgentFeePct')}`}
				data-feasibility-field="salesAgentFeePct"
			>
				<input type="number" step="0.1" min="0" class={INPUT}
					value={s.inputs.salesAgentFeePct}
					oninput={(e) => setNumber('salesAgentFeePct', e.currentTarget.value)} />
			</td>
			<td class={PCT_COL}>{fmtPct(pct(s.salesAgentFees))}</td>
			<td class={VALUE_BLACK}>{fmtAed(outputs?.costs.vatSalesAdminAed ?? 0)}</td>
			<td class={UNIT}>% of revenue</td>
		</tr>

		<tr class={ROW_STD}>
			<td class="px-1 py-[3px] text-slate-400 text-[10px] text-center">9</td>
			<td class={LABEL}>Contingency</td>
			<td class="px-2 py-[3px] text-center text-[10px] text-slate-400">Con→HO</td>
			<td
				class={`p-0 ${highlightClass('contingencyCostOverrideAed')}`}
				data-feasibility-field="contingencyCostOverrideAed"
			>
				<AmountInput value={s.contingencyCost}
					oncommit={(v) => s.updateInputs({ contingencyCostOverrideAed: v > 0 ? v : null })}
					class={INPUT} />
			</td>
			<td
				class={`p-0 ${highlightClass('contingencyPct')}`}
				data-feasibility-field="contingencyPct"
			>
				<input type="number" step="0.5" min="0" class={INPUT}
					value={s.inputs.contingencyPct}
					oninput={(e) => setNumber('contingencyPct', e.currentTarget.value)} />
			</td>
			<td class={PCT_COL}>{fmtPct(pct(s.contingencyCost))}</td>
			<td class={VALUE_BLACK}>{fmtAed(outputs?.costs.vatContingencyAed ?? 0)}</td>
			<td class={UNIT}>% of construction</td>
		</tr>

		<!-- ═══════════════════════════════════════════════════════════
		     SECTION D — STATUTORY & DEVELOPMENT COSTS
		     ═══════════════════════════════════════════════════════════ -->
		<tr class="bg-[#1F3864]">
			<td colspan="8" class="px-2 py-[4px] text-white font-bold text-[11px] tracking-wide">D. &nbsp; STATUTORY &amp; DEVELOPMENT COSTS</td>
		</tr>

		<tr class={ROW_STD}>
			<td class="px-1 py-[3px] text-slate-400 text-[10px] text-center">10</td>
			<td class={LABEL}>Infrastructure, Utilities &amp; Landscaping</td>
			<td class="px-2 py-[3px] text-center text-[10px] text-slate-400">Con→HO</td>
			<td
				class={`p-0 ${highlightClass('infrastructureCostAed')}`}
				data-feasibility-field="infrastructureCostAed"
			>
				<AmountInput value={s.inputs.infrastructureCostAed}
					oncommit={(v) => s.updateInputs({ infrastructureCostAed: v })} class={INPUT} />
			</td>
			<td class="px-2 py-[3px] text-right text-[10px] text-slate-400">
				{s.inputs.plotAreaSqm > 0 ? fmt(s.inputs.infrastructureCostAed / toSqft(s.inputs.plotAreaSqm), 0) : '—'}
			</td>
			<td class={PCT_COL}>{fmtPct(pct(s.inputs.infrastructureCostAed))}</td>
			<td class={PCT_COL}>—</td>
			<td class={UNIT}>AED / sqft plot</td>
		</tr>

		<tr class={ROW_STD}>
			<td class="px-1 py-[3px] text-slate-400 text-[10px] text-center">11</td>
			<td class={LABEL}>Authority &amp; Connection Fees</td>
			<td class="px-2 py-[3px] text-center text-[10px] text-slate-400">Pre-con</td>
			<td
				class={`p-0 ${highlightClass('governmentFeesAed')}`}
				data-feasibility-field="governmentFeesAed"
			>
				<AmountInput value={s.inputs.governmentFeesAed}
					oncommit={(v) => s.updateInputs({ governmentFeesAed: v })} class={INPUT} />
			</td>
			<td class="px-2 py-[3px] text-right text-[10px] text-slate-400">
				{s.maxGfaSqm > 0 ? fmt(s.inputs.governmentFeesAed / toSqft(s.maxGfaSqm), 0) : '—'}
			</td>
			<td class={PCT_COL}>{fmtPct(pct(s.inputs.governmentFeesAed))}</td>
			<td class={VALUE_BLACK}>{fmtAed(outputs?.costs.vatPermitFeesAed ?? 0)}</td>
			<td class={UNIT}>AED / sqft GFA</td>
		</tr>

		<tr class={ROW_STD}>
			<td class="px-1 py-[3px] text-slate-400 text-[10px] text-center">12</td>
			<td class={LABEL}>Master Community Fees</td>
			<td class="px-2 py-[3px] text-center text-[10px] text-slate-400">Pre-HO</td>
			<td
				class={`p-0 ${highlightClass('masterCommunityFeesAed')}`}
				data-feasibility-field="masterCommunityFeesAed"
			>
				<AmountInput value={s.inputs.masterCommunityFeesAed}
					oncommit={(v) => s.updateInputs({ masterCommunityFeesAed: v })} class={INPUT} />
			</td>
			<td class="px-2 py-[3px] text-right text-[10px] text-slate-400">
				{s.inputs.plotAreaSqm > 0 ? fmt(s.inputs.masterCommunityFeesAed / toSqft(s.inputs.plotAreaSqm), 0) : '—'}
			</td>
			<td class={PCT_COL}>{fmtPct(pct(s.inputs.masterCommunityFeesAed))}</td>
			<td class={PCT_COL}>—</td>
			<td class={UNIT}>AED / sqft plot</td>
		</tr>

		{#if s.inputs.ffeOsePreopeningCostAed > 0}
		<tr class={ROW_STD}>
			<td class="px-1 py-[3px] text-slate-400 text-[10px] text-center">13</td>
			<td class={LABEL}>FF&amp;E / Pre-Opening</td>
			<td class="px-2 py-[3px] text-center text-[10px] text-slate-400">Pre-HO</td>
			<td
				class={`p-0 ${highlightClass('ffeOsePreopeningCostAed')}`}
				data-feasibility-field="ffeOsePreopeningCostAed"
			>
				<AmountInput value={s.inputs.ffeOsePreopeningCostAed}
					oncommit={(v) => s.updateInputs({ ffeOsePreopeningCostAed: v })} class={INPUT} />
			</td>
			<td class={PCT_COL}></td>
			<td class={PCT_COL}>{fmtPct(pct(s.inputs.ffeOsePreopeningCostAed))}</td>
			<td class={PCT_COL}>—</td>
			<td class={UNIT}>fixed AED</td>
		</tr>
		{/if}

		<!-- Pre-finance sub-total -->
		<tr class={ROW_TOTAL}>
			<td></td>
			<td class="px-2 py-[3px] font-semibold text-slate-700">Pre-Finance Cost Sub-Total</td>
			<td></td>
			<td class={VALUE_BOLD}>{fmtAed(preFinanceCosts)}</td>
			<td></td>
			<td class="px-2 py-[3px] text-right tabular-nums text-slate-500 text-[10px] font-semibold">{fmtPct(pct(preFinanceCosts))}</td>
			<td class={VALUE_BOLD}>{fmtAed(outputs?.costs.totalVatAed ?? 0)}</td>
			<td class={UNIT}>AED</td>
		</tr>

		<!-- ═══════════════════════════════════════════════════════════
		     SECTION E — FINANCE COSTS
		     ═══════════════════════════════════════════════════════════ -->
		<tr class="bg-[#1F3864]">
			<td colspan="8" class="px-2 py-[4px] text-white font-bold text-[11px] tracking-wide">E. &nbsp; FINANCE COSTS</td>
		</tr>

			<tr class={ROW_STD}>
				<td class="px-1 py-[3px] text-slate-400 text-[10px] text-center">14</td>
				<td class={LABEL}>Financing Fee</td>
				<td class="px-2 py-[3px] text-center text-[10px] text-slate-400">Financial close</td>
				<td class={VALUE_BLACK}>{financingFee > 0 ? fmtAed(financingFee) : '—'}</td>
				<td
					class={`p-0 ${highlightClass('financingFeePct')}`}
					data-feasibility-field="financingFeePct"
				>
					<input type="number" step="0.1" min="0" class={INPUT}
						value={Math.round((s.inputs.financingFeePct ?? 0.01) * 10000) / 100}
						oninput={(e) => s.updateInputs({ financingFeePct: (Number(e.currentTarget.value) || 0) / 100 })} />
				</td>
				<td class={PCT_COL}>{financingFee > 0 ? fmtPct(pct(financingFee)) : '—'}</td>
				<td class={PCT_COL}>—</td>
				<td class={UNIT}>% of debt commitment</td>
			</tr>

			<tr class={ROW_STD}>
				<td class="px-1 py-[3px] text-slate-400 text-[10px] text-center">15</td>
				<td class={LABEL}>Exit Fee</td>
				<td class="px-2 py-[3px] text-center text-[10px] text-slate-400">At handover</td>
				<td class={VALUE_BLACK}>{exitFee > 0 ? fmtAed(exitFee) : '—'}</td>
				<td
					class={`p-0 ${highlightClass('exitFeePct')}`}
					data-feasibility-field="exitFeePct"
				>
					<input type="number" step="0.1" min="0" class={INPUT}
						value={Math.round((s.inputs.exitFeePct ?? 0.01) * 10000) / 100}
						oninput={(e) => s.updateInputs({ exitFeePct: (Number(e.currentTarget.value) || 0) / 100 })} />
				</td>
				<td class={PCT_COL}>{exitFee > 0 ? fmtPct(pct(exitFee)) : '—'}</td>
				<td class={PCT_COL}>—</td>
				<td class={UNIT}>% of opening debt</td>
			</tr>

			<tr class={ROW_STD}>
				<td class="px-1 py-[3px] text-slate-400 text-[10px] text-center">16</td>
				<td class={LABEL}>Interest Carry</td>
			<td class="px-2 py-[3px] text-center text-[10px] text-slate-400">Con→HO</td>
			<td class={VALUE_BLACK}>{totalInterestPaid > 0 ? fmtAed(totalInterestPaid) : '—'}</td>
			<td class="px-2 py-[3px] relative">
				<!-- Land and construction rates — derived from EIBOR sheet -->
				<div class="flex flex-col gap-0 text-right tabular-nums text-[10px]">
					<span class="text-emerald-700 border-b border-[#EBEBEB] pb-[1px]" title="Land loan rate (EIBOR + spread)">{fmtPct(s.landLoanRatePct, 2)}</span>
					<span class="text-emerald-700 pt-[1px]" title="Construction loan rate (EIBOR + spread)">{fmtPct(s.constructionLoanRatePct, 2)}</span>
				</div>
			</td>
			<td class={PCT_COL}>{totalInterestPaid > 0 ? fmtPct(pct(totalInterestPaid)) : '—'}</td>
			<td class={PCT_COL}>—</td>
			<td class="px-2 py-[3px] text-slate-400 text-[10px] whitespace-nowrap">↗ EIBOR sheet</td>
		</tr>

		<tr class={ROW_TOTAL}>
			<td></td>
			<td class="px-2 py-[3px] font-semibold text-slate-700">Total Finance Costs</td>
			<td></td>
			<td class={VALUE_BOLD}>{totalFinanceCosts > 0 ? fmtAed(totalFinanceCosts) : '—'}</td>
			<td></td>
			<td class="px-2 py-[3px] text-right tabular-nums text-slate-500 text-[10px] font-semibold">{totalFinanceCosts > 0 ? fmtPct(pct(totalFinanceCosts)) : '—'}</td>
			<td class={PCT_COL}>—</td>
			<td class={UNIT}>AED</td>
		</tr>

		<!-- ═══════════════════════════════════════════════════════════
		     SECTION F — VAT
		     ═══════════════════════════════════════════════════════════ -->
		<tr class="bg-[#D6DCE4]">
			<td colspan="8" class="px-2 py-[3px] text-slate-700 font-semibold text-[10px] tracking-wider uppercase">F. &nbsp; VAT</td>
		</tr>

		<tr class={ROW_STD}>
			<td class="px-1 py-[3px] text-slate-400 text-[10px] text-center">17</td>
			<td class={LABEL}>VAT <span class="text-slate-400 font-normal italic">(refundable at handover)</span></td>
			<td class="px-2 py-[3px] text-center text-[10px] text-slate-400">Con→HO</td>
			<td class={VALUE_BLACK}>{fmtAed(s.vatAmount)}</td>
			<td
				class={`p-0 ${highlightClass('vatPct')}`}
				data-feasibility-field="vatPct"
			>
				<input type="number" step="0.5" min="0" class={INPUT}
					value={s.inputs.vatPct}
					oninput={(e) => setNumber('vatPct', e.currentTarget.value)} />
			</td>
			<td class={PCT_COL}>{fmtPct(pct(s.vatAmount))}</td>
			<td class={VALUE_BOLD}>{fmtAed(outputs?.costs.totalVatAed ?? 0)}</td>
			<td class={UNIT}>% of pre-finance</td>
		</tr>

		</tbody>
	</table>

	<!-- Grand Total -->
	<div class="border-t-2 border-[#1F3864] bg-[#1F3864]">
		<div class="grid grid-cols-4 gap-0">
			<div class="px-3 py-2 border-r border-[#2D4D7A]">
				<div class="text-[9px] uppercase tracking-wider text-blue-200 font-semibold">Dev Cost excl. VAT</div>
				<div class="text-[11px] font-bold text-white tabular-nums mt-0.5">{fmtAed(s.totalCostsExclVat)}</div>
			</div>
			<div class="px-3 py-2 border-r border-[#2D4D7A]">
				<div class="text-[9px] uppercase tracking-wider text-blue-200 font-semibold">VAT (gross)</div>
				<div class="text-[11px] font-bold text-white tabular-nums mt-0.5">{fmtAed(s.vatAmount)}</div>
			</div>
			<div class="px-3 py-2 border-r border-[#2D4D7A]">
				<div class="text-[9px] uppercase tracking-wider text-blue-200 font-semibold">Finance Costs</div>
				<div class="text-[11px] font-bold text-white tabular-nums mt-0.5">{totalFinanceCosts > 0 ? fmtAed(totalFinanceCosts) : '—'}</div>
			</div>
			<div class="px-3 py-2">
				<div class="text-[9px] uppercase tracking-wider text-blue-200 font-semibold">TOTAL PROJECT COST (all-in)</div>
				<div class="text-[14px] font-bold text-white tabular-nums mt-0.5">{fmtAed(s.modelTotalCostsInclVat + totalFinanceCosts)}</div>
			</div>
		</div>
	</div>

	<!-- Per-unit metrics -->
	<div class="flex border-b border-[#B8C4CE] bg-[#EEF2F7] divide-x divide-[#D9D9D9]">
		<div class="px-2 py-1.5 flex-1">
			<div class="text-[9px] uppercase tracking-wider text-slate-500 font-semibold">Cost / Unit</div>
			<div class="text-[11px] font-bold text-slate-900 tabular-nums">{s.totalUnits > 0 ? fmtAed(costPerUnitAed) : '—'}</div>
		</div>
		<div class="px-2 py-1.5 flex-1">
			<div class="text-[9px] uppercase tracking-wider text-slate-500 font-semibold">Revenue / Unit</div>
			<div class="text-[11px] font-bold text-slate-900 tabular-nums">{s.totalUnits > 0 ? fmtAed(revenuePerUnitAed) : '—'}</div>
		</div>
		<div class="px-2 py-1.5 flex-1">
			<div class="text-[9px] uppercase tracking-wider text-slate-500 font-semibold">Profit / Unit</div>
			<div class="text-[11px] font-bold text-slate-900 tabular-nums">{s.totalUnits > 0 ? fmtAed(profitPerUnitAed) : '—'}</div>
		</div>
		<div class="px-2 py-1.5 flex-1">
			<div class="text-[9px] uppercase tracking-wider text-slate-500 font-semibold">Cost / sqft BUA</div>
			<div class="text-[11px] font-bold text-slate-900 tabular-nums">{s.totalBuaSqm > 0 ? fmt(costPerSqftBua, 0) : '—'} <span class="text-slate-400 font-normal">AED</span></div>
		</div>
		<div class="px-2 py-1.5 flex-1">
			<div class="text-[9px] uppercase tracking-wider text-slate-500 font-semibold">Budget / Revenue</div>
			<div class="text-[11px] font-bold text-slate-900 tabular-nums">{s.totalConfiguredRevenue > 0 ? fmt(s.modelTotalCostsInclVat / s.totalConfiguredRevenue * 100, 1) + '%' : '—'}</div>
		</div>
	</div>

	<!-- Returns summary -->
	<div class="bg-white border-b border-[#B8C4CE]">
		<div class="px-3 py-1.5 text-[10px] font-semibold text-slate-600 uppercase tracking-wider border-b border-[#D9D9D9] bg-[#EEF2F7]">Returns Summary</div>
		<table class="w-full border-collapse" style="border-spacing:0">
			<colgroup>
				<col style="width:2.5%">
				<col style="width:44%">
				<col style="width:28%">
				<col style="width:25%">
			</colgroup>
			<tbody>

			<tr class="border-b border-[#D9D9D9]">
				<td class="px-1 py-[3px] text-slate-400 text-[10px] text-center">a</td>
				<td class="px-2 py-[3px] text-slate-800">Gross Revenue</td>
				<td class="px-2 py-[3px] text-right tabular-nums text-emerald-700 font-semibold">{fmtAed(s.totalConfiguredRevenue)}</td>
				<td class="px-2 py-[3px] text-right text-slate-400 text-[10px]">AED</td>
			</tr>
			<tr class="border-b border-[#D9D9D9]">
				<td class="px-1 py-[3px] text-slate-400 text-[10px] text-center">b</td>
				<td class="px-2 py-[3px] text-slate-800">Total Cost (incl. VAT)</td>
				<td class="px-2 py-[3px] text-right tabular-nums text-emerald-700">{fmtAed(s.modelTotalCostsInclVat)}</td>
				<td class="px-2 py-[3px] text-right text-slate-400 text-[10px]">AED</td>
			</tr>
			<tr class="border-b border-[#D9D9D9]">
				<td class="px-1 py-[3px] text-slate-400 text-[10px] text-center">c</td>
				<td class="px-2 py-[3px] text-slate-800">Finance Costs <span class="text-slate-400 font-normal italic">(interest + fees)</span></td>
				<td class="px-2 py-[3px] text-right tabular-nums text-emerald-700">{totalFinanceCosts > 0 ? fmtAed(totalFinanceCosts) : s.workbook ? '0' : '—'}</td>
				<td class="px-2 py-[3px] text-right text-slate-400 text-[10px]">AED</td>
			</tr>
			<tr class="border-b border-[#D9D9D9] border-t border-[#1F3864]">
				<td class="px-1 py-[3px]"></td>
				<td class="px-2 py-[3px] text-slate-900 font-semibold">All-in Profit</td>
				<td class="px-2 py-[3px] text-right tabular-nums text-slate-900 font-semibold">{fmtAed(allInProfit)}</td>
				<td class="px-2 py-[3px] text-right text-slate-400 text-[10px]">AED</td>
			</tr>
			<tr class="border-b border-[#D9D9D9]">
				<td class="px-1 py-[3px]"></td>
				<td class="px-2 py-[3px] text-slate-700">All-in Margin</td>
				<td class="px-2 py-[3px] text-right tabular-nums font-semibold text-slate-900">{fmtPct(allInMarginPct)}</td>
				<td class="px-2 py-[3px] text-right text-slate-400 text-[10px]">of gross revenue</td>
			</tr>

			<tr class="border-b border-[#D9D9D9]">
				<td class="px-1 py-[3px] text-slate-400 text-[10px] text-center">d</td>
				<td class="px-2 py-[3px] text-slate-800">
					Project IRR
					<span class="ml-1 text-[9px] text-slate-400 font-normal italic">unlevered — excl. financing</span>
				</td>
				<td class="px-2 py-[3px] text-right tabular-nums font-bold text-[13px] text-slate-900">
					{projectIrrPct != null ? fmt(projectIrrPct, 1) + '%' : '—'}
				</td>
				<td class="px-2 py-[3px] text-right text-slate-400 text-[10px]">% p.a.</td>
			</tr>
			<tr class="border-b border-[#D9D9D9]">
				<td class="px-1 py-[3px] text-slate-400 text-[10px] text-center">e</td>
				<td class="px-2 py-[3px] text-slate-800">
					Equity IRR
					<span class="ml-1 text-[9px] text-slate-400 font-normal italic">levered — incl. interest carry</span>
				</td>
				<td class="px-2 py-[3px] text-right tabular-nums font-bold text-[13px] text-slate-900">
					{equityIrrPct != null ? fmt(equityIrrPct, 1) + '%' : '—'}
				</td>
				<td class="px-2 py-[3px] text-right text-slate-400 text-[10px]">% p.a.</td>
			</tr>
			<tr class="border-b border-[#D9D9D9]">
				<td class="px-1 py-[3px] text-slate-400 text-[10px] text-center">f</td>
				<td class="px-2 py-[3px] text-slate-800">MoIC</td>
				<td class="px-2 py-[3px] text-right tabular-nums font-bold text-[12px] text-slate-900">
					{fmt(s.workbook?.returns?.projectMoic ?? s.revenueMultiple, 2)}x
				</td>
				<td class="px-2 py-[3px] text-right text-slate-400 text-[10px]">revenue / cost</td>
			</tr>

			<tr>
				<td colspan="4" class="py-4"></td>
			</tr>

			</tbody>
		</table>
	</div>

</div>
{/if}

<style>
	:global(.feasibility-change-flash) {
		animation: feasibility-change-flash 2.4s ease-out;
	}

	@keyframes feasibility-change-flash {
		0%,
		100% {
			background-color: transparent;
			box-shadow: none;
		}
		12% {
			background-color: rgba(34, 197, 94, 0.18);
			box-shadow: inset 0 0 0 1px rgba(20, 184, 166, 0.35);
		}
		36% {
			background-color: rgba(56, 189, 248, 0.16);
			box-shadow: inset 0 0 0 1px rgba(14, 165, 233, 0.28);
		}
		68% {
			background-color: rgba(34, 197, 94, 0.1);
			box-shadow: inset 0 0 0 1px rgba(20, 184, 166, 0.18);
		}
	}

	@media (prefers-reduced-motion: reduce) {
		:global(.feasibility-change-flash) {
			animation: none;
			background-color: rgba(34, 197, 94, 0.14);
			box-shadow: inset 0 0 0 1px rgba(20, 184, 166, 0.24);
		}
	}
</style>
