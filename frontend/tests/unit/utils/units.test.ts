import { describe, expect, it } from 'vitest'
import {
	convertArea,
	convertPricePerArea,
	formatArea,
	formatPricePerArea,
	getAreaLabel,
	getAreaUnitLabel,
	getPricePerAreaLabel,
	SQFT_TO_SQM,
	SQM_TO_SQFT
} from '$lib/utils/units'

describe('constants', () => {
	it('SQM_TO_SQFT uses the shared market conversion factor', () => {
		expect(SQM_TO_SQFT).toBe(10.7639)
	})

	it('SQFT_TO_SQM is the inverse of SQM_TO_SQFT', () => {
		expect(SQFT_TO_SQM).toBeCloseTo(1 / SQM_TO_SQFT)
	})

	it('conversions are inverse of each other', () => {
		expect(SQM_TO_SQFT * SQFT_TO_SQM).toBeCloseTo(1)
	})
})

describe('convertArea', () => {
	it('returns sqm value unchanged', () => {
		expect(convertArea(100, 'sqm')).toBe(100)
	})

	it('converts sqm to sqft correctly', () => {
		expect(convertArea(1, 'sqft')).toBeCloseTo(SQM_TO_SQFT)
	})

	it('converts 100 sqm to sqft', () => {
		expect(convertArea(100, 'sqft')).toBeCloseTo(100 * SQM_TO_SQFT)
	})

	it('handles zero', () => {
		expect(convertArea(0, 'sqft')).toBe(0)
		expect(convertArea(0, 'sqm')).toBe(0)
	})
})

describe('convertPricePerArea', () => {
	it('returns price/sqm unchanged', () => {
		expect(convertPricePerArea(1000, 'sqm')).toBe(1000)
	})

	it('converts price/sqm to price/sqft by dividing', () => {
		const pricePerSqm = 1000 * SQM_TO_SQFT
		expect(convertPricePerArea(pricePerSqm, 'sqft')).toBeCloseTo(1000)
	})

	it('price per sqft is lower than price per sqm for same value', () => {
		const pricePerSqm = 15000
		const pricePerSqft = convertPricePerArea(pricePerSqm, 'sqft')
		expect(pricePerSqft).toBeLessThan(pricePerSqm)
	})

	it('handles zero', () => {
		expect(convertPricePerArea(0, 'sqft')).toBe(0)
	})
})

describe('getAreaUnitLabel', () => {
	it('returns sq.m for sqm', () => {
		expect(getAreaUnitLabel('sqm')).toBe('sq.m')
	})

	it('returns sq.ft for sqft', () => {
		expect(getAreaUnitLabel('sqft')).toBe('sq.ft')
	})
})

describe('getAreaLabel', () => {
	it('includes the unit in the label', () => {
		expect(getAreaLabel('sqm')).toBe('Area (sq.m)')
		expect(getAreaLabel('sqft')).toBe('Area (sq.ft)')
	})
})

describe('getPricePerAreaLabel', () => {
	it('includes the unit in the label', () => {
		expect(getPricePerAreaLabel('sqm')).toBe('Price/sq.m')
		expect(getPricePerAreaLabel('sqft')).toBe('Price/sq.ft')
	})
})

describe('formatArea', () => {
	it('formats sqm without conversion', () => {
		const result = formatArea(1000, 'sqm')
		expect(result).toBe('1,000')
	})

	it('formats sqft with conversion applied', () => {
		// 100 sqm -> 1076.4 sqft
		const result = formatArea(100, 'sqft')
		expect(result).toContain('1,076')
	})

	it('handles fractional values with max 2 decimal places', () => {
		const result = formatArea(10.555, 'sqm')
		const decimalPart = result.split('.')[1] ?? ''
		expect(decimalPart.length).toBeLessThanOrEqual(2)
	})
})

describe('formatPricePerArea', () => {
	it('formats price per sqm', () => {
		const result = formatPricePerArea(15000, 'sqm')
		expect(result).toBe('15,000')
	})

	it('formats price per sqft (divided value)', () => {
		// 15000 / 10.764 ≈ 1393
		const result = formatPricePerArea(15000, 'sqft')
		expect(result).toContain('1,39')
	})
})
