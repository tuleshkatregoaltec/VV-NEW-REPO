export const SQM_TO_SQFT = 10.7639
export const SQFT_TO_SQM = 1 / SQM_TO_SQFT
export const SQM_PER_SQFT = SQFT_TO_SQM

export type AreaUnit = 'sqm' | 'sqft'

export function toSqft(sqm: number): number {
	return sqm * SQM_TO_SQFT
}

export function fromSqft(sqft: number): number {
	return sqft * SQFT_TO_SQM
}

export function convertArea(areaSqm: number, targetUnit: AreaUnit): number {
	return targetUnit === 'sqft' ? toSqft(areaSqm) : areaSqm
}

export function convertPricePerArea(priceSqm: number, targetUnit: AreaUnit): number {
	return targetUnit === 'sqft' ? priceSqm / SQM_TO_SQFT : priceSqm
}

export function getAreaUnitLabel(unit: AreaUnit): string {
	return unit === 'sqft' ? 'sq.ft' : 'sq.m'
}

export function getAreaLabel(unit: AreaUnit): string {
	return `Area (${getAreaUnitLabel(unit)})`
}

export function getPricePerAreaLabel(unit: AreaUnit): string {
	return `Price/${getAreaUnitLabel(unit)}`
}

export function formatArea(value: number, unit: AreaUnit): string {
	return convertArea(value, unit).toLocaleString(undefined, {
		minimumFractionDigits: 0,
		maximumFractionDigits: 2
	})
}

export function formatPricePerArea(value: number, unit: AreaUnit): string {
	return convertPricePerArea(value, unit).toLocaleString(undefined, {
		minimumFractionDigits: 0,
		maximumFractionDigits: 2
	})
}
