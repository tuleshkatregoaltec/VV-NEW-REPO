import { describe, expect, it, vi } from 'vitest'

import { client } from '$lib/api/client'
import { feasibility, normalizePlotDataResponse } from '$lib/api/feasibility'
import type { PlotDetails } from '$lib/api/generated/hey-api/types.gen'

function makePlotDetails(overrides: Partial<PlotDetails> = {}): PlotDetails {
	return {
		plot_number: 'P-101',
		community_name: 'Business Bay',
		project_name: 'Canal Edge',
		master_developer: null,
		plot_area_sqm: 1000,
		max_gfa_sqm: 5000,
		max_gfa_sqft: 53819.55,
		max_height: 'G+12',
		max_coverage: '60%',
		gfa_type: 'Gross Floor Area',
		far: 5,
		inferred_usage: 'residential',
		site_plan_issue_date: null,
		site_plan_expiry_date: null,
		is_verified: true,
		verify_comments: null,
		land_use: [],
		general_notes: [],
		setbacks: {},
		coordinates: [],
		warnings: [],
		...overrides
	}
}

describe('feasibility api', () => {
	it('normalizes raw plot details into the wrapped plot data shape', () => {
		const plot = makePlotDetails()
		expect(normalizePlotDataResponse(plot)).toEqual({ plot_data: plot })
	})

	it('preserves the wrapped plot data shape', () => {
		const wrapped = { plot_data: makePlotDetails({ plot_number: 'P-202' }) }
		expect(normalizePlotDataResponse(wrapped)).toEqual(wrapped)
	})

	it('getPlotData accepts the backend plot details response shape', async () => {
		const plot = makePlotDetails()
		const getSpy = vi.spyOn(client, 'get').mockResolvedValue(plot)

		await expect(feasibility.getPlotData('P-101')).resolves.toEqual({ plot_data: plot })
		expect(getSpy).toHaveBeenCalledWith('/api/v1/feasibility/plots/P-101')
	})

	it('generateStudy forwards the selected development model', async () => {
		const postSpy = vi.spyOn(client, 'post').mockResolvedValue({} as never)

		await feasibility.generateStudy({
			plot_number: 'P-101',
			usage_override: 'residential',
			development_model: 'build_to_rent_residential'
		})

		expect(postSpy).toHaveBeenCalledWith('/api/v1/feasibility/generate-study', {
			plot_number: 'P-101',
			usage_override: 'residential',
			development_model: 'build_to_rent_residential'
		})
	})
})
