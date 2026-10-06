import { describe, expect, it } from 'vitest'
import {
	createAssumptionsFromPlot,
	createDefaultAssumptions,
	hydrateAssumptions
} from '$lib/feasibility/workbook/defaults'
import { computeWorkbook } from '$lib/feasibility/workbook/engine'
import type { FeasibilityAssumptions, PlotDetails } from '$lib/feasibility/workbook/models'

const plot = {
	plot_number: 'L001',
	community_name: 'Business Bay',
	project_name: 'Business Bay Plot',
	master_developer: null,
	plot_area_sqm: 1000,
	max_gfa_sqm: 4000,
	max_gfa_sqft: 43055,
	max_height: 'G+20',
	max_coverage: '60%',
	gfa_type: 'Residential',
	far: 4,
	inferred_usage: 'residential',
	site_plan_issue_date: null,
	site_plan_expiry_date: null,
	is_verified: true,
	verify_comments: null,
	land_use: [],
	general_notes: [],
	setbacks: {},
	coordinates: [],
	warnings: []
} satisfies PlotDetails

describe('workbook assumption defaults', () => {
	it('preserves saved values and only fills missing defaults', () => {
		const hydrated = hydrateAssumptions(
			{
				landPricePsqm: 9000,
				vatPct: 7,
				paymentPlan: { depositPct: 25 } as FeasibilityAssumptions['paymentPlan'],
				landTransferFeePct: null as unknown as number,
				btrPermDebtSpreadBps: 190
			},
			plot,
			{
				land_cost_estimate_aed_low: 10_000_000,
				land_cost_estimate_aed_mid: 12_000_000
			}
		)

		expect(hydrated.landPricePsqm).toBe(9000)
		expect(hydrated.vatPct).toBe(7)
		expect(hydrated.paymentPlan).toEqual({
			depositPct: 25,
			constructionPct: 30,
			handoverPct: 60
		})
		expect(hydrated.landTransferFeePct).toBe(0.04)
		expect(hydrated.btrPermDebtSpreadBps).toBe(190)
		expect(hydrated.landAcquisitionCostOverrideAed).toBeNull()
	})

	it('resets deterministic generated fields while preserving market/product fields', () => {
		const generated = hydrateAssumptions(
			{
				landPricePsqm: 18_000,
				landAcquisitionCostOverrideAed: 18_000_000,
				constructionCostPsqmBua: 6250,
				brokerageFeeAed: 180_000,
				legalDdCostAed: 90_000,
				unitConfigs: [
					{
						id: 'onebr',
						label: '1BR',
						units: 80,
						avgSizeSqm: 72,
						sellingRatePsqm: 24_000,
						parkingRatio: 1
					}
				],
				paymentPlan: { depositPct: 90, constructionPct: 5, handoverPct: 5 },
				vatPct: 12,
				debtSpreadPa: 0.09,
				landLoanSpreadBps: 900,
				constructionLoanSpreadBps: 850,
				acquisitionDebtLtv: 0.2,
				constructionDebtLtc: 0.3,
				btrPermDebtSpreadBps: 500,
				numberOfTowers: 2,
				numberOfFloors: 40
			},
			plot,
			undefined,
			'build_to_sell_residential',
			{ mode: 'generated', asOfDate: '2026-05-03' }
		)

		expect(generated.landPricePsqm).toBe(18_000)
		expect(generated.landAcquisitionCostOverrideAed).toBe(18_000_000)
		expect(generated.constructionCostPsqmBua).toBe(6250)
		expect(generated.brokerageFeeAed).toBe(180_000)
		expect(generated.legalDdCostAed).toBe(90_000)
		expect(generated.unitConfigs[0].sellingRatePsqm).toBe(24_000)
		expect(generated.paymentPlan).toEqual({
			depositPct: 10,
			constructionPct: 30,
			handoverPct: 60
		})
		expect(generated.vatPct).toBe(5)
		expect(generated.debtSpreadPa).toBe(0.02)
		expect(generated.landLoanSpreadBps).toBe(200)
		expect(generated.constructionLoanSpreadBps).toBe(200)
		expect(generated.acquisitionDebtLtv).toBe(0.7)
		expect(generated.constructionDebtLtc).toBe(0.7)
		expect(generated.buaMultiplier).toBe(1.5)
		expect(generated.btrPermDebtSpreadBps).toBe(165)
		expect(generated.numberOfTowers).toBe(2)
		expect(generated.numberOfFloors).toBe(40)
		expect(generated.designSupervisionPct).toBe(6)
		expect(generated.marketingCostPct).toBe(1)
		expect(generated.salesAgentFeePct).toBe(5)
		expect(generated.contingencyPct).toBe(5)
		expect(generated.midPointInflationPct).toBe(4)
		expect(generated.infrastructureCostAed).toBe(8_000_000)
		expect(generated.governmentFeesAed).toBe(5_000_000)
		expect(generated.masterCommunityFeesAed).toBe(3_500_000)
		expect(generated.landAcquisitionDate).toBe('2026-05-03')
		expect(generated.salesCommencementDate).toBe('2026-08-03')
		expect(generated.handoverDate).toBe('2029-03-03')
	})

	it('uses the same default values for empty plot hydration', () => {
		const direct = createAssumptionsFromPlot(plot, { asOfDate: '2026-05-03' })
		const defaults = createDefaultAssumptions({ asOfDate: '2026-05-03' })

		expect(direct.paymentPlan).toEqual(defaults.paymentPlan)
		expect(direct.debtSpreadPa).toBe(defaults.debtSpreadPa)
		expect(direct.vatPct).toBe(defaults.vatPct)
		expect(direct.landTransferFeePct).toBe(defaults.landTransferFeePct)
		expect(direct.btrPermDebtSpreadBps).toBe(defaults.btrPermDebtSpreadBps)
		expect(direct.btrExitCapRatePct).toBe(defaults.btrExitCapRatePct)
		expect(direct.marketingCostPct).toBe(defaults.marketingCostPct)
		expect(direct.salesAgentFeePct).toBe(defaults.salesAgentFeePct)
		expect(direct.infrastructureCostAed).toBe(defaults.infrastructureCostAed)
	})

	it('treats zero generated massing controls as unset in workbook calculations', () => {
		const assumptions = {
			...createAssumptionsFromPlot(plot, { asOfDate: '2026-05-03' }),
			targetCoveragePct: 0,
			targetBuildingCount: 0,
			maxEfficientTowerFloorplateSqm: 0,
			minEfficientTowerFloorplateSqm: 0,
			landPricePsqm: 12_000,
			constructionCostPsqmBua: 5_200,
			unitConfigs: [
				{
					id: 'onebr',
					label: '1BR',
					units: 40,
					avgSizeSqm: 72,
					sellingRatePsqm: 24_000,
					parkingRatio: 1
				}
			]
		}

		const outputs = computeWorkbook(assumptions)

		expect(outputs.siteMassing.appliedCoveragePct).toBeGreaterThan(0)
		expect(outputs.siteMassing.buildingCount).toBeGreaterThan(0)
		expect(outputs.siteMassing.coveredFootprintSqm).toBeGreaterThan(0)
	})

	it('preserves generated physical test-fit fields instead of resetting to generic defaults', () => {
		const generated = hydrateAssumptions(
			{
				numberOfTowers: 2,
				numberOfFloors: 71,
				podiumFloors: 5,
				residentialFloors: 65,
				amenityRoofFloors: 1,
				targetCoveragePct: 45,
				targetBuildingCount: 2,
				maxEfficientTowerFloorplateSqm: 2000,
				minEfficientTowerFloorplateSqm: 700
			},
			plot,
			undefined,
			'build_to_sell_residential',
			{ mode: 'generated', asOfDate: '2026-05-03' }
		)

		expect(generated.numberOfTowers).toBe(2)
		expect(generated.numberOfFloors).toBe(71)
		expect(generated.podiumFloors).toBe(5)
		expect(generated.residentialFloors).toBe(65)
		expect(generated.amenityRoofFloors).toBe(1)
		expect(generated.targetCoveragePct).toBe(45)
		expect(generated.targetBuildingCount).toBe(2)
		expect(generated.maxEfficientTowerFloorplateSqm).toBe(2000)
		expect(generated.minEfficientTowerFloorplateSqm).toBe(700)
	})

	it('does not show single-building floorplate warning for multi-building massing', () => {
		const assumptions = {
			...createAssumptionsFromPlot(
				{
					...plot,
					plot_area_sqm: 5500,
					max_gfa_sqm: 175_000,
					far: 31.8,
					max_height: 'G+5P+UNLIMITED',
					max_coverage: 'N/A'
				},
				{ asOfDate: '2026-05-03' }
			),
			maxStoreys: 77,
			numberOfFloors: 77,
			podiumFloors: 5,
			residentialFloors: 71,
			amenityRoofFloors: 1,
			targetCoveragePct: 45,
			targetBuildingCount: 2,
			maxEfficientTowerFloorplateSqm: 2000,
			minEfficientTowerFloorplateSqm: 700,
			landPricePsqm: 170_000,
			constructionCostPsqmBua: 5900,
			unitConfigs: [
				{
					id: 'onebr',
					label: '1BR',
					units: 1700,
					avgSizeSqm: 82,
					sellingRatePsqm: 24_000,
					parkingRatio: 1
				}
			]
		}

		const outputs = computeWorkbook(assumptions)

		expect(outputs.siteMassing.buildingCount).toBe(2)
		expect(outputs.siteMassing.warnings).not.toContain(
			'Single-building floorplate is inefficient; multi-building massing is recommended.'
		)
	})

	it('caps basement parking BUA to modeled parking demand', () => {
		const assumptions = {
			...createAssumptionsFromPlot(plot, { asOfDate: '2026-05-03' }),
			plotAreaSqm: 7404.79,
			maxGfaSqm: 27_400,
			maxStoreys: 40,
			basementParkingFloors: 4,
			parkingAreaPerSpaceSqm: 30,
			constructionCostPsqmBua: 5850,
			unitConfigs: [
				{
					id: 'studio',
					label: 'Studio',
					units: 116,
					avgSizeSqm: 45,
					sellingRatePsqm: 28_800,
					parkingRatio: 1
				},
				{
					id: 'onebr',
					label: '1BR',
					units: 112,
					avgSizeSqm: 78,
					sellingRatePsqm: 24_200,
					parkingRatio: 1
				},
				{
					id: 'twobr',
					label: '2BR',
					units: 48,
					avgSizeSqm: 125,
					sellingRatePsqm: 24_500,
					parkingRatio: 1
				},
				{
					id: 'threebr',
					label: '3BR',
					units: 10,
					avgSizeSqm: 200,
					sellingRatePsqm: 30_500,
					parkingRatio: 2
				}
			]
		}

		const outputs = computeWorkbook(assumptions)

		expect(outputs.area.basementParkingBua).toBe(8880)
		expect(outputs.area.parkingBuaAllowanceSqm).toBe(8880)
		expect(outputs.area.notes).toContain('Basement parking BUA capped to modeled parking demand.')
		expect(outputs.area.costableBuaGfaRatio).toBeLessThan(1.5)
	})
})
