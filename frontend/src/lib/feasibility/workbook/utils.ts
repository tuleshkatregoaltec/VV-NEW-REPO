import type { BtrUnitConfig, UnitConfig } from './models'

export function formatCurrency(value: number | null | undefined) {
	if (value === null || value === undefined || Number.isNaN(value)) return '—'
	return new Intl.NumberFormat('en-AE', {
		maximumFractionDigits: 0
	}).format(value)
}

export function formatNumber(value: number | null | undefined, digits = 0) {
	if (value === null || value === undefined || Number.isNaN(value)) return '—'
	return new Intl.NumberFormat('en-AE', {
		maximumFractionDigits: digits,
		minimumFractionDigits: digits
	}).format(value)
}

export function titleCase(value: string) {
	return value.replaceAll('_', ' ').replace(/\b\w/g, (char) => char.toUpperCase())
}

const UNIT_WORD_NUMBERS: Record<string, string> = {
	one: '1',
	two: '2',
	three: '3',
	four: '4',
	five: '5',
	six: '6'
}

export function normalizeUnitTypeKey(value: string): string {
	const lower = value.toLowerCase().replace(/[_-]+/g, ' ').replace(/\+/g, ' plus ')
	if (/\bstudios?\b/.test(lower)) return 'studio'

	const digitBedroom = lower.match(/\b(\d+)\s*(?:br|bdrm|bed|beds|bedroom|bedrooms)\b/)
	if (digitBedroom) {
		return `${digitBedroom[1]}br${/\b(plus|above)\b/.test(lower) ? 'plus' : ''}`
	}

	const wordBedroom = lower.match(
		/\b(one|two|three|four|five|six)\s*(?:br|bdrm|bed|beds|bedroom|bedrooms)\b/
	)
	if (wordBedroom) {
		return `${UNIT_WORD_NUMBERS[wordBedroom[1]]}br${/\b(plus|above)\b/.test(lower) ? 'plus' : ''}`
	}

	return lower.replace(/\b(apartments?|units?|residential|type)\b/g, ' ').replace(/[^a-z0-9]+/g, '')
}

export function unitTypeKeysMatch(left: string, right: string): boolean {
	const normalizedLeft = normalizeUnitTypeKey(left)
	const normalizedRight = normalizeUnitTypeKey(right)
	return Boolean(normalizedLeft && normalizedLeft === normalizedRight)
}

export function unitConfigMatchesKey(
	config: Pick<UnitConfig | BtrUnitConfig, 'id' | 'label'>,
	key: string
): boolean {
	return unitTypeKeysMatch(config.id, key) || unitTypeKeysMatch(config.label, key)
}

export function unitConfigIdFromLabel(label: string): string {
	return (
		normalizeUnitTypeKey(label) ||
		label
			.toLowerCase()
			.replace(/[^a-z0-9]+/g, '-')
			.replace(/^-|-$/g, '') ||
		'unit'
	)
}

export function displayUnitTypeLabel(value: string): string {
	const key = normalizeUnitTypeKey(value)
	if (key === 'studio') return 'Studio'
	const bedroom = key.match(/^(\d+)br(plus)?$/)
	if (bedroom) return `${bedroom[1]}BR${bedroom[2] ? '+' : ''}`
	return titleCase(value)
}
