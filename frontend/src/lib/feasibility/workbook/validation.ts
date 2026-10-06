// ══════════════════════════════════════════════════════════════════════════════
// Workbook Validation — Template-aligned checks (9 checks)
// ══════════════════════════════════════════════════════════════════════════════
// Validates workbook outputs and assumptions, returns issues.
// ══════════════════════════════════════════════════════════════════════════════

import type { WorkbookOutputs } from './engine'
import type { FeasibilityAssumptions } from './models'

export type ValidationSeverity = 'hard_fail' | 'warning' | 'missing_evidence'
export type ValidationStatus = 'ready' | 'needs_review' | 'invalid'

export interface ValidationIssue {
	code: string
	severity: ValidationSeverity
	message: string
	field?: string
}

export interface ValidationResult {
	status: ValidationStatus
	hardFailures: number
	warnings: number
	missingEvidence: number
	issues: ValidationIssue[]
}

export function validateWorkbook(
	assumptions: FeasibilityAssumptions,
	outputs: WorkbookOutputs
): ValidationResult {
	const issues: ValidationIssue[] = []

	const isBtr = assumptions.developmentModel === 'build_to_rent_residential'

	// ── BTR-specific validation ─────────────────────────────────────────────
	if (isBtr && outputs.btr) {
		const btr = outputs.btr

		if (btr.returns.stabilizedNoiAed <= 0) {
			issues.push({
				code: 'btr_noi_not_positive',
				severity: 'hard_fail',
				message: 'Stabilized NOI is not positive',
				field: 'btr_operating'
			})
		}

		if (btr.permDebt.dscrAtOrigination < (assumptions.btrDscrMinimum ?? 1.25)) {
			issues.push({
				code: 'btr_dscr_below_min',
				severity: 'hard_fail',
				message: `DSCR (${btr.permDebt.dscrAtOrigination.toFixed(2)}x) is below minimum (${(assumptions.btrDscrMinimum ?? 1.25).toFixed(2)}x)`,
				field: 'btr_operating'
			})
		}

		const btrSourcesUsesGap = btr.sourcesUses.totalSourcesAed - btr.sourcesUses.totalUsesAed
		if (Math.abs(btrSourcesUsesGap) > 1000) {
			issues.push({
				code: 'btr_sources_uses_gap',
				severity: 'hard_fail',
				message: `BTR Sources & Uses gap of AED ${Math.round(btrSourcesUsesGap).toLocaleString()}`,
				field: 'sources_uses'
			})
		}

		if (btr.permDebt.refiProceedsAed < -1000) {
			issues.push({
				code: 'btr_refi_shortfall',
				severity: 'hard_fail',
				message: `Refinance shortfall / equity cure required: AED ${Math.round(Math.abs(btr.permDebt.refiProceedsAed)).toLocaleString()}`,
				field: 'financing'
			})
		}

		if (btr.exit.exitCapRatePct <= 0) {
			issues.push({
				code: 'btr_exit_cap_zero',
				severity: 'hard_fail',
				message: 'Exit cap rate must be greater than 0',
				field: 'btr_operating'
			})
		}

		if (btr.program.totalUnits === 0) {
			issues.push({
				code: 'btr_no_rental_units',
				severity: 'hard_fail',
				message: 'No rental unit configurations defined',
				field: 'btrUnitConfigs'
			})
		}

		if (btr.exit.devYieldPct <= 0) {
			issues.push({
				code: 'btr_yield_not_positive',
				severity: 'warning',
				message: 'Yield on cost is not positive',
				field: 'btr_operating'
			})
		}

		if (btr.returns.leveredMoic <= 0) {
			issues.push({
				code: 'btr_moic_not_positive',
				severity: 'hard_fail',
				message: 'Levered MOIC is not positive',
				field: 'btr_operating'
			})
		}

		if (btr.returns.unleveredIrrPct !== null && btr.returns.unleveredIrrPct < 0) {
			issues.push({
				code: 'btr_unlevered_irr_negative',
				severity: 'hard_fail',
				message: `Unlevered IRR is negative (${btr.returns.unleveredIrrPct.toFixed(1)}%)`,
				field: 'btr_operating'
			})
		}

		if (btr.returns.leveredIrrPct !== null && btr.returns.leveredIrrPct > 50) {
			issues.push({
				code: 'btr_levered_irr_too_high',
				severity: 'warning',
				message: `Levered IRR looks unusually high (${btr.returns.leveredIrrPct.toFixed(1)}%)`,
				field: 'btr_operating'
			})
		}

		// Dev cost checks
		if (
			btr.devCosts.landAcquisitionAed === 0 &&
			assumptions.landPricePsqm === 0 &&
			!assumptions.landAcquisitionCostOverrideAed
		) {
			issues.push({
				code: 'btr_missing_land_cost',
				severity: 'missing_evidence',
				message: 'Land acquisition cost not set',
				field: 'landPricePsqm'
			})
		}

		if (
			btr.devCosts.hardCostAed === 0 &&
			assumptions.constructionCostPsqmBua === 0 &&
			!assumptions.constructionCostOverrideAed
		) {
			issues.push({
				code: 'btr_missing_construction_cost',
				severity: 'missing_evidence',
				message: 'Construction cost not set',
				field: 'constructionCostPsqmBua'
			})
		}

		// Skip BTS-specific checks for BTR
		const hardFailures = issues.filter((i) => i.severity === 'hard_fail').length
		const warnings = issues.filter((i) => i.severity === 'warning').length
		const missingEvidence = issues.filter((i) => i.severity === 'missing_evidence').length
		let status: ValidationStatus = 'ready'
		if (hardFailures > 0) status = 'invalid'
		else if (warnings > 0 || missingEvidence > 0) status = 'needs_review'
		return { status, hardFailures, warnings, missingEvidence, issues }
	}

	// ── 1. Payment Plan = 100% ──────────────────────────────────────────────
	const ppTotal =
		(outputs.funding.depositPct ?? 0) +
		(outputs.funding.preHandoverPct ?? 0) +
		(outputs.funding.handoverPct ?? 0)
	if (Math.abs(ppTotal - 100) > 0.01) {
		issues.push({
			code: 'payment_plan_not_100',
			severity: 'hard_fail',
			message: `Payment plan sums to ${ppTotal.toFixed(1)}% (must be 100%)`,
			field: 'paymentPlan'
		})
	}

	// ── 2a. Cash reconciliation gap ─────────────────────────────────────────
	if (Math.abs(outputs.funding.cashReconGapAed) > 1000) {
		issues.push({
			code: 'funding_gap',
			severity: outputs.funding.cashReconGapAed > 0 ? 'hard_fail' : 'warning',
			message: `Cash reconciliation gap of AED ${Math.round(outputs.funding.cashReconGapAed).toLocaleString()}`,
			field: 'funding'
		})
	}

	// ── 2b. Capital stack S&U gap ───────────────────────────────────────────
	if (Math.abs(outputs.sourcesUses.gapAed) > 1000) {
		issues.push({
			code: 'su_gap',
			severity: 'warning',
			message: `Sources & Uses gap of AED ${Math.round(outputs.sourcesUses.gapAed).toLocaleString()}`,
			field: 'sources_uses'
		})
	}

	// ── 3. No Negative Total Debt ────────────────────────────────────────────
	const hasNegativeDebt = outputs.cashFlow.periods.some((p) => p.debtBalanceAed < -0.01)
	if (hasNegativeDebt) {
		issues.push({
			code: 'negative_debt',
			severity: 'hard_fail',
			message: 'Debt balance goes negative in at least one period',
			field: 'financing'
		})
	}

	// ── 4. Cash Flow Check ──────────────────────────────────────────────────
	const totalLeveredCf = outputs.cashFlow.periods.reduce((s, p) => s + p.leveredNetCashFlowAed, 0)
	if (Math.abs(totalLeveredCf) > 1000) {
		issues.push({
			code: 'cf_not_zero',
			severity: 'warning',
			message: `Levered CF nets to AED ${Math.round(totalLeveredCf).toLocaleString()} (should be ~0)`,
			field: 'cashflow'
		})
	}

	// ── 5. Acquisition Tranche Balance at end ───────────────────────────────
	const lastPeriod =
		outputs.cashFlow.periods.length > 0
			? outputs.cashFlow.periods[outputs.cashFlow.periods.length - 1]
			: null
	if (lastPeriod && Math.abs(lastPeriod.closingAcqDebtAed) > 1) {
		issues.push({
			code: 'acq_tranche_not_zero',
			severity: 'hard_fail',
			message: `Acquisition tranche closing balance: AED ${Math.round(lastPeriod.closingAcqDebtAed).toLocaleString()}`,
			field: 'financing'
		})
	}

	// ── 6. Construction Tranche Balance at end ──────────────────────────────
	if (lastPeriod && Math.abs(lastPeriod.closingConDebtAed) > 1) {
		issues.push({
			code: 'con_tranche_not_zero',
			severity: 'hard_fail',
			message: `Construction tranche closing balance: AED ${Math.round(lastPeriod.closingConDebtAed).toLocaleString()}`,
			field: 'financing'
		})
	}

	// ── 7. VAT Budget vs Monthly Paid ───────────────────────────────────────
	const budgetVat = outputs.costs.totalVatAed
	const monthlyVatPaid = outputs.vatBridge?.totalVatPaidMonthly ?? 0
	if (Math.abs(budgetVat - monthlyVatPaid) > 1000) {
		issues.push({
			code: 'vat_budget_mismatch',
			severity: 'warning',
			message: `VAT budget (${Math.round(budgetVat).toLocaleString()}) differs from monthly paid (${Math.round(monthlyVatPaid).toLocaleString()})`,
			field: 'vat'
		})
	}

	// ── 8. Net VAT Check ────────────────────────────────────────────────────
	const netVat = outputs.vatBridge?.netVatPosition ?? 0
	if (Math.abs(netVat) > 1000) {
		issues.push({
			code: 'net_vat_not_zero',
			severity: 'warning',
			message: `Net VAT position: AED ${Math.round(netVat).toLocaleString()} (should be ~0)`,
			field: 'vat'
		})
	}

	// ── 9. Negative Margin ──────────────────────────────────────────────────
	if (outputs.returns.grossMarginPct < 0) {
		issues.push({
			code: 'negative_margin',
			severity: 'hard_fail',
			message: 'Project has negative gross margin',
			field: 'returns'
		})
	}

	// ── 10. IRR range checks ────────────────────────────────────────────────
	const projectIrr = outputs.returns.projectIrrPct
	if (projectIrr !== null && projectIrr !== undefined) {
		if (projectIrr < 0) {
			issues.push({
				code: 'project_irr_negative',
				severity: 'hard_fail',
				message: `Project IRR is negative (${projectIrr.toFixed(1)}%)`,
				field: 'returns'
			})
		} else if (projectIrr > 50) {
			issues.push({
				code: 'project_irr_too_high',
				severity: 'warning',
				message: `Project IRR looks unusually high (${projectIrr.toFixed(1)}%)`,
				field: 'returns'
			})
		}
	}

	const equityIrr = outputs.returns.equityIrrPct
	if (equityIrr !== null && equityIrr !== undefined) {
		if (equityIrr < 0) {
			issues.push({
				code: 'equity_irr_negative',
				severity: 'hard_fail',
				message: `Equity IRR is negative (${equityIrr.toFixed(1)}%)`,
				field: 'returns'
			})
		} else if (equityIrr > 80) {
			issues.push({
				code: 'equity_irr_too_high',
				severity: 'warning',
				message: `Equity IRR looks unusually high (${equityIrr.toFixed(1)}%)`,
				field: 'returns'
			})
		}
	}

	// ── Additional evidence checks ──────────────────────────────────────────
	if (outputs.program.totalUnits === 0) {
		issues.push({
			code: 'no_units',
			severity: 'warning',
			message: 'No unit mix configured',
			field: 'unitConfigs'
		})
	}

	if (outputs.program.grossRevenueAed === 0 && outputs.program.totalUnits > 0) {
		issues.push({
			code: 'zero_revenue',
			severity: 'warning',
			message: 'Revenue is zero despite having units',
			field: 'unitConfigs'
		})
	}

	if (
		outputs.costs.landAcquisitionAed === 0 &&
		assumptions.landPricePsqm === 0 &&
		!assumptions.landAcquisitionCostOverrideAed
	) {
		issues.push({
			code: 'missing_land_cost',
			severity: 'missing_evidence',
			message: 'Land acquisition cost not set',
			field: 'landPricePsqm'
		})
	}

	if (
		outputs.costs.constructionCostAed === 0 &&
		assumptions.constructionCostPsqmBua === 0 &&
		!assumptions.constructionCostOverrideAed
	) {
		issues.push({
			code: 'missing_construction_cost',
			severity: 'missing_evidence',
			message: 'Construction cost not set',
			field: 'constructionCostPsqmBua'
		})
	}

	const hardFailures = issues.filter((i) => i.severity === 'hard_fail').length
	const warnings = issues.filter((i) => i.severity === 'warning').length
	const missingEvidence = issues.filter((i) => i.severity === 'missing_evidence').length

	let status: ValidationStatus = 'ready'
	if (hardFailures > 0) {
		status = 'invalid'
	} else if (warnings > 0 || missingEvidence > 0) {
		status = 'needs_review'
	}

	return {
		status,
		hardFailures,
		warnings,
		missingEvidence,
		issues
	}
}
