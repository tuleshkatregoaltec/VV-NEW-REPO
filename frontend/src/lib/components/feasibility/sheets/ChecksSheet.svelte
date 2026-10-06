<script lang="ts">
import { workbookStore } from '$lib/feasibility/workbook/store.svelte'

function fmt(value: number | null | undefined, digits = 0) {
	if (value === null || value === undefined || !Number.isFinite(value)) return '0'
	return value.toLocaleString('en-AE', {
		minimumFractionDigits: digits,
		maximumFractionDigits: digits
	})
}

function fmtPct(value: number | null | undefined, digits = 1) {
	if (value === null || value === undefined || !Number.isFinite(value)) return '—'
	return `${fmt(value, digits)}%`
}

const outputs = $derived(workbookStore.outputs)
const assumptions = $derived(workbookStore.assumptions)
const validation = $derived(workbookStore.validation)
const hardFailures = $derived(validation?.hardFailures ?? 0)
const warnings = $derived(validation?.warnings ?? 0)
const missingEvidence = $derived(validation?.missingEvidence ?? 0)
const isBtr = $derived(assumptions?.developmentModel === 'build_to_rent_residential')
const btr = $derived(outputs?.btr)

function hasIssue(code: string) {
	return (validation?.issues ?? []).some((issue) => issue.code === code)
}

type CheckStatus = 'within_range' | 'warning' | 'outlier' | 'missing'

function pill(status: CheckStatus) {
	if (status === 'outlier') return 'bg-rose-100 text-rose-700'
	if (status === 'warning') return 'bg-amber-100 text-amber-700'
	if (status === 'missing') return 'bg-slate-200 text-slate-600'
	return 'bg-slate-100 text-slate-700'
}

// ── BTR checks ──────────────────────────────────────────────────────────────
const btrChecks = $derived<
	Array<{ label: string; value: string; status: CheckStatus; note: string }>
>(
	isBtr && btr
		? [
				{
					label: '1. Stabilized NOI',
					value: `AED ${fmt(btr.returns.stabilizedNoiAed)}`,
					status: btr.returns.stabilizedNoiAed > 0 ? 'within_range' : 'outlier',
					note: 'Stabilized NOI must be positive for a viable project'
				},
				{
					label: '2. DSCR at Origination',
					value: `${fmt(btr.permDebt.dscrAtOrigination, 2)}x`,
					status:
						btr.permDebt.dscrAtOrigination >= (assumptions?.btrDscrMinimum ?? 1.25)
							? 'within_range'
							: 'outlier',
					note: `Minimum ${fmt(assumptions?.btrDscrMinimum ?? 1.25, 2)}x required for debt sizing`
				},
				{
					label: '3. Exit Cap Rate',
					value: fmtPct(btr.exit.exitCapRatePct),
					status: btr.exit.exitCapRatePct > 0 ? 'within_range' : 'outlier',
					note: 'Exit cap rate must be greater than 0'
				},
				{
					label: '4. Rental Units Defined',
					value: `${btr.program.totalUnits} units`,
					status: btr.program.totalUnits > 0 ? 'within_range' : 'outlier',
					note: 'At least one rental unit configuration required'
				},
				{
					label: '5. Development Yield',
					value: fmtPct(btr.exit.devYieldPct),
					status:
						btr.exit.devYieldPct > 0
							? 'within_range'
							: hasIssue('btr_yield_not_positive')
								? 'warning'
								: 'outlier',
					note: 'Stabilized NOI / Total Dev Cost should be positive'
				},
				{
					label: '6. Levered MOIC',
					value: `${fmt(btr.returns.leveredMoic, 2)}x`,
					status:
						btr.returns.leveredMoic > 1
							? 'within_range'
							: btr.returns.leveredMoic > 0
								? 'warning'
								: 'outlier',
					note: 'Equity multiple should exceed 1.0x for a profitable investment'
				},
				{
					label: '7. Unlevered IRR',
					value: btr.returns.unleveredIrrPct != null ? fmtPct(btr.returns.unleveredIrrPct) : 'N/A',
					status:
						btr.returns.unleveredIrrPct == null
							? 'missing'
							: btr.returns.unleveredIrrPct < 0
								? 'outlier'
								: btr.returns.unleveredIrrPct > 50
									? 'warning'
									: 'within_range',
					note: 'All-cash project return; negative indicates unprofitable project'
				},
				{
					label: '8. Levered IRR',
					value: btr.returns.leveredIrrPct != null ? fmtPct(btr.returns.leveredIrrPct) : 'N/A',
					status:
						btr.returns.leveredIrrPct == null
							? 'missing'
							: btr.returns.leveredIrrPct < 0
								? 'outlier'
								: btr.returns.leveredIrrPct > 50
									? 'warning'
									: 'within_range',
					note: 'Equity return after debt; unusually high values (>50%) warrant review'
				},
				{
					label: '9. Land Cost',
					value:
						btr.devCosts.landAcquisitionAed > 0
							? `AED ${fmt(btr.devCosts.landAcquisitionAed)}`
							: 'Not set',
					status: hasIssue('btr_missing_land_cost') ? 'missing' : 'within_range',
					note: 'Land acquisition cost should be set for accurate feasibility'
				},
				{
					label: '10. Construction Cost',
					value: btr.devCosts.hardCostAed > 0 ? `AED ${fmt(btr.devCosts.hardCostAed)}` : 'Not set',
					status: hasIssue('btr_missing_construction_cost') ? 'missing' : 'within_range',
					note: 'Construction cost should be set for accurate feasibility'
				}
			]
		: []
)

// ── BTS checks ──────────────────────────────────────────────────────────────
// Payment plan check (should sum to 100%)
const paymentPlanTotal = $derived(
	outputs
		? (outputs.funding.depositPct ?? 0) +
				(outputs.funding.preHandoverPct ?? 0) +
				(outputs.funding.handoverPct ?? 0)
		: 0
)
const paymentPlanOk = $derived(Math.abs(paymentPlanTotal - 100) < 0.01)

// Cash flow check (levered net CF should net to ~0 at end)
const totalLeveredCf = $derived(
	(outputs?.cashFlow.periods ?? []).reduce((s, p) => s + p.leveredNetCashFlowAed, 0)
)
const cfCheckOk = $derived(Math.abs(totalLeveredCf) < 1000)

// Closing debt balances should be zero
const closingAcqDebt = $derived(
	(outputs?.cashFlow.periods ?? []).length > 0
		? ((outputs?.cashFlow.periods ?? [])[(outputs?.cashFlow.periods ?? []).length - 1]
				.closingAcqDebtAed ?? 0)
		: 0
)
const closingConDebt = $derived(
	(outputs?.cashFlow.periods ?? []).length > 0
		? ((outputs?.cashFlow.periods ?? [])[(outputs?.cashFlow.periods ?? []).length - 1]
				.closingConDebtAed ?? 0)
		: 0
)

// Total debt negative check
const hasNegativeDebt = $derived(
	(outputs?.cashFlow.periods ?? []).some((p) => p.debtBalanceAed < -0.01)
)

// VAT budget vs monthly check
const budgetVat = $derived(outputs?.costs.totalVatAed ?? 0)
const monthlyVatPaid = $derived(outputs?.vatBridge?.totalVatPaidMonthly ?? 0)
const vatBudgetOk = $derived(Math.abs(budgetVat - monthlyVatPaid) < 1000)

// Net VAT check
const netVatOk = $derived(Math.abs(outputs?.vatBridge?.netVatPosition ?? 0) < 1000)

const btsChecks = $derived<
	Array<{ label: string; value: string; status: CheckStatus; note: string }>
>([
	{
		label: '1. Payment Plan = 100%',
		value: outputs ? `${fmt(paymentPlanTotal, 1)}%` : 'N/A',
		status: !outputs ? 'missing' : paymentPlanOk ? 'within_range' : 'outlier',
		note: 'Deposit + Pre-Handover + On-Handover must total 100%'
	},
	{
		label: '2. Sources = Uses',
		value: outputs ? `Gap AED ${fmt(outputs.funding.cashReconGapAed)}` : 'N/A',
		status: !outputs ? 'missing' : hasIssue('funding_gap') ? 'warning' : 'within_range',
		note: 'Sources of funds should match uses of funds'
	},
	{
		label: '3. No Negative Debt',
		value: outputs ? (hasNegativeDebt ? 'FAIL' : 'OK') : 'N/A',
		status: !outputs ? 'missing' : hasNegativeDebt ? 'outlier' : 'within_range',
		note: 'Total debt balance should never go negative'
	},
	{
		label: '4. Cash Flow Check',
		value: outputs ? `AED ${fmt(totalLeveredCf)}` : 'N/A',
		status: !outputs ? 'missing' : cfCheckOk ? 'within_range' : 'warning',
		note: 'Levered net cash flow should net to approximately zero'
	},
	{
		label: '5. Acq Tranche Balance',
		value: outputs ? `AED ${fmt(closingAcqDebt)}` : 'N/A',
		status: !outputs ? 'missing' : Math.abs(closingAcqDebt) < 1 ? 'within_range' : 'outlier',
		note: 'Acquisition tranche balance should be zero at end of project'
	},
	{
		label: '6. Constr Tranche Balance',
		value: outputs ? `AED ${fmt(closingConDebt)}` : 'N/A',
		status: !outputs ? 'missing' : Math.abs(closingConDebt) < 1 ? 'within_range' : 'outlier',
		note: 'Construction tranche balance should be zero at end of project'
	},
	{
		label: '7. VAT Budget vs Monthly',
		value: outputs ? `Diff AED ${fmt(budgetVat - monthlyVatPaid)}` : 'N/A',
		status: !outputs ? 'missing' : vatBudgetOk ? 'within_range' : 'warning',
		note: 'Budget VAT should reconcile with monthly VAT paid'
	},
	{
		label: '8. Net VAT Check',
		value: outputs ? `AED ${fmt(outputs.vatBridge?.netVatPosition ?? 0)}` : 'N/A',
		status: !outputs ? 'missing' : netVatOk ? 'within_range' : 'warning',
		note: 'Net VAT position (paid - refunded) should be near zero'
	},
	{
		label: '9. Gross Margin',
		value: outputs ? `${fmt(outputs.returns.grossMarginPct, 1)}%` : 'N/A',
		status: !outputs
			? 'missing'
			: outputs.returns.grossMarginPct < 0
				? 'outlier'
				: outputs.returns.grossMarginPct < 10
					? 'warning'
					: 'within_range',
		note: 'Gross margin should be positive and reasonable'
	}
])

const modelChecks = $derived(isBtr ? btrChecks : btsChecks)
</script>

{#if !outputs || !validation}
<div class="h-full flex items-center justify-center px-6 text-sm text-slate-400">
Generate an HBU study to build the draft checks view.
</div>
{:else}
<div class="overflow-auto flex-1 bg-white text-[11px] font-[Calibri,'Segoe_UI',Arial,sans-serif] select-none">

	<div class="bg-[#1F3864] border-b-2 border-[#1F3864] text-white px-4 py-2.5 flex items-center justify-between gap-4">
		<div class="text-[13px] font-bold tracking-wide">MODEL CHECKS</div>
		<div class="text-[10px] shrink-0 {validation.status === 'ready' ? 'text-slate-200' : validation.status === 'invalid' ? 'text-rose-300' : 'text-amber-300'}">
			{validation.status.replace('_', ' ').toUpperCase()} — {fmt(hardFailures)} fail · {fmt(warnings)} warn · {fmt(missingEvidence)} missing
		</div>
	</div>

	<table class="w-full border-collapse" style="border-spacing:0">
		<tbody>

		<!-- Model checks -->
		<tr class="bg-[#1F3864]">
			<td colspan="4" class="px-2 py-[4px] text-white font-bold text-[11px] tracking-wide">A.&nbsp;&nbsp;UNDERWRITING CHECKS</td>
		</tr>
		<tr class="bg-[#D6DCE4] border-b border-[#B8C4CE]">
			<th class="px-2 py-[4px] text-left text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Check</th>
			<th class="px-2 py-[4px] text-right text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Value</th>
			<th class="px-2 py-[4px] text-center text-[9px] font-semibold text-slate-600 uppercase tracking-wider w-20">Status</th>
			<th class="px-2 py-[4px] text-left text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Note</th>
		</tr>
		{#each modelChecks as check (check.label)}
			<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
				<td class="px-2 py-[3px] text-left text-[10px] text-slate-800">{check.label}</td>
				<td class="px-2 py-[3px] text-right tabular-nums text-[10px] font-medium text-slate-900">{check.value}</td>
				<td class="px-2 py-[3px] text-center">
					{#if check.status === 'outlier'}
						<span class="inline-block px-2 py-0.5 text-[9px] font-semibold uppercase rounded-sm bg-[#FCE4D6] text-[#843C0C]">FAIL</span>
					{:else if check.status === 'warning'}
						<span class="inline-block px-2 py-0.5 text-[9px] font-semibold uppercase rounded-sm bg-[#FFF2CC] text-[#7F6000]">WARN</span>
					{:else if check.status === 'missing'}
						<span class="inline-block px-2 py-0.5 text-[9px] font-semibold uppercase rounded-sm bg-[#D9D9D9] text-[#595959]">N/A</span>
					{:else}
						<span class="inline-block px-2 py-0.5 text-[9px] font-semibold uppercase rounded-sm bg-[#E7EAF0] text-[#334155]">OK</span>
					{/if}
				</td>
				<td class="px-2 py-[3px] text-left text-[9px] text-slate-500">{check.note}</td>
			</tr>
		{/each}

		<!-- Validation issues detail -->
		<tr class="bg-[#1F3864]">
			<td colspan="4" class="px-2 py-[4px] text-white font-bold text-[11px] tracking-wide">B.&nbsp;&nbsp;VALIDATION ISSUES</td>
		</tr>
		<tr class="bg-[#D6DCE4] border-b border-[#B8C4CE]">
			<th class="px-2 py-[4px] text-left text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Severity</th>
			<th class="px-2 py-[4px] text-left text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Code</th>
			<th class="px-2 py-[4px] text-left text-[9px] font-semibold text-slate-600 uppercase tracking-wider" colspan="2">Message</th>
		</tr>
		{#if validation.issues.length}
			{#each validation.issues as issue (`${issue.code}-${issue.field ?? ''}`)}
				<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
					<td class="px-2 py-[3px] text-left text-[10px] font-medium {issue.severity === 'hard_fail' ? 'text-rose-700' : issue.severity === 'warning' ? 'text-amber-700' : 'text-slate-500'}">
						{issue.severity.replace('_', ' ')}
					</td>
					<td class="px-2 py-[3px] text-left text-[10px] text-slate-500">{issue.code}</td>
					<td class="px-2 py-[3px] text-left text-[10px] text-slate-800" colspan="2">
						{issue.message}{#if issue.field} <span class="text-slate-400">({issue.field})</span>{/if}
					</td>
				</tr>
			{/each}
		{:else}
			<tr class="border-b border-[#D9D9D9]">
				<td class="px-2 py-[3px] text-left text-[10px] text-slate-500" colspan="4">No validation issues on current draft.</td>
			</tr>
		{/if}

		</tbody>
	</table>

	<div class="py-3"></div>
</div>
{/if}
