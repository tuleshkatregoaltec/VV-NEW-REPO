import { beforeEach, describe, expect, it } from 'vitest'
import { createAssumptionsFromPlot } from '$lib/feasibility/workbook/defaults'
import type { FeasibilityAssumptions, PlotDetails } from '$lib/feasibility/workbook/models'
import { workbookStore } from '$lib/feasibility/workbook/store.svelte'

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

function loadUnitMix(unitConfigs: FeasibilityAssumptions['unitConfigs']) {
	workbookStore.loadStudy({
		plotData: plot,
		assumptions: {
			...createAssumptionsFromPlot(plot, { asOfDate: '2026-05-03' }),
			unitConfigs
		},
		study_context: {} as never,
		research: {} as never
	})
}

describe('feasibility unit mix proposal application', () => {
	beforeEach(() => {
		workbookStore.reset()
	})

	it('replaces the full unit mix and removes omitted unit types', () => {
		loadUnitMix([
			{
				id: 'onebr',
				label: '1BR',
				units: 10,
				avgSizeSqm: 70,
				sellingRatePsqm: 20_000,
				parkingRatio: 1
			},
			{
				id: 'twobr',
				label: '2BR',
				units: 8,
				avgSizeSqm: 110,
				sellingRatePsqm: 21_000,
				parkingRatio: 1.5
			},
			{
				id: 'threebr',
				label: '3BR',
				units: 4,
				avgSizeSqm: 160,
				sellingRatePsqm: 22_000,
				parkingRatio: 2
			}
		])

		const applied = workbookStore.applyProposal({
			action: 'replace_unit_mix',
			payload: [
				{ type: '1 bedroom', count: 12, avgSizeSqm: 72 },
				{ type: '2 bedroom', count: 9, avgSizeSqm: 112 }
			]
		})

		expect(applied).toBe(true)
		expect((workbookStore.assumptions?.unitConfigs ?? []).map((row) => row.label)).toEqual([
			'1BR',
			'2BR'
		])
		expect((workbookStore.assumptions?.unitConfigs ?? []).map((row) => row.units)).toEqual([12, 9])
	})

	it('partially updates listed unit types without removing omitted rows', () => {
		loadUnitMix([
			{
				id: 'onebr',
				label: '1BR',
				units: 10,
				avgSizeSqm: 70,
				sellingRatePsqm: 20_000,
				parkingRatio: 1
			},
			{
				id: 'twobr',
				label: '2BR',
				units: 8,
				avgSizeSqm: 110,
				sellingRatePsqm: 21_000,
				parkingRatio: 1.5
			},
			{
				id: 'threebr',
				label: '3BR',
				units: 4,
				avgSizeSqm: 160,
				sellingRatePsqm: 22_000,
				parkingRatio: 2
			}
		])

		const applied = workbookStore.applyProposal({
			action: 'update_unit_mix',
			payload: [{ type: '1 bedroom', count: 14 }]
		})

		expect(applied).toBe(true)
		expect((workbookStore.assumptions?.unitConfigs ?? []).map((row) => row.label)).toEqual([
			'1BR',
			'2BR',
			'3BR'
		])
		expect((workbookStore.assumptions?.unitConfigs ?? []).map((row) => row.units)).toEqual([
			14, 8, 4
		])
	})
})
