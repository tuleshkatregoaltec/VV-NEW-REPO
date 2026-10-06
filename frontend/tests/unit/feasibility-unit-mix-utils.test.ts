import { describe, expect, it } from 'vitest'
import {
	displayUnitTypeLabel,
	unitConfigIdFromLabel,
	unitConfigMatchesKey,
	unitTypeKeysMatch
} from '$lib/feasibility/workbook/utils'

describe('feasibility unit mix proposal helpers', () => {
	it('matches common agent wording to workbook unit labels', () => {
		expect(unitTypeKeysMatch('1BR', '1 bedroom apartments')).toBe(true)
		expect(unitTypeKeysMatch('onebr', '1 bedroom')).toBe(true)
		expect(unitTypeKeysMatch('2BR', '2 bed')).toBe(true)
		expect(unitTypeKeysMatch('Studio', 'studio apartment')).toBe(true)
		expect(unitTypeKeysMatch('4BR+', '4 bedroom plus')).toBe(true)
	})

	it('matches ids and labels used by generated workbook rows', () => {
		const config = {
			id: 'onebr',
			label: '1BR'
		}

		expect(unitConfigMatchesKey(config, '1 bedroom')).toBe(true)
		expect(unitConfigMatchesKey(config, 'one bed')).toBe(true)
		expect(unitConfigMatchesKey(config, '2 bedroom')).toBe(false)
	})

	it('creates stable ids and labels for new proposal rows', () => {
		expect(unitConfigIdFromLabel('1 bedroom apartments')).toBe('1br')
		expect(displayUnitTypeLabel('1 bedroom apartments')).toBe('1BR')
		expect(displayUnitTypeLabel('studio units')).toBe('Studio')
	})
})
