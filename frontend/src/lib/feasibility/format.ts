export function formatFeasibilityNumber(value: number | null | undefined, digits = 0): string {
	if (value === null || value === undefined || !Number.isFinite(value)) return '—'
	return value.toLocaleString('en-AE', {
		minimumFractionDigits: digits,
		maximumFractionDigits: digits
	})
}

export function formatFeasibilityInteger(value: number | null | undefined): string {
	if (value === null || value === undefined || !Number.isFinite(value)) return '—'
	return Math.round(value).toLocaleString('en-AE')
}

export function formatFeasibilityPercent(
	value: number | null | undefined,
	digits = 1,
	fallback = '—'
): string {
	if (value === null || value === undefined || !Number.isFinite(value)) return fallback
	return `${formatFeasibilityNumber(value, digits)}%`
}

export function formatMaybeNumber(
	value: number | null | undefined,
	digits = 1,
	suffix = '%',
	fallback = 'N/A'
): string {
	if (value === null || value === undefined || !Number.isFinite(value)) return fallback
	return `${formatFeasibilityNumber(value, digits)}${suffix}`
}

export function dateToQuarter(isoDate: string): string {
	if (!isoDate) return '—'
	const date = new Date(isoDate)
	if (Number.isNaN(date.getTime())) return isoDate
	const quarter = Math.ceil((date.getMonth() + 1) / 3)
	return `Q${quarter} ${date.getFullYear()}`
}

export function monthsBetween(startIso: string, endIso: string): number | null {
	if (!startIso || !endIso) return null
	const start = new Date(startIso)
	const end = new Date(endIso)
	if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) return null
	return (end.getFullYear() - start.getFullYear()) * 12 + (end.getMonth() - start.getMonth())
}

export function ratePerSqmToSqft(aedPerSqm: number): number {
	return aedPerSqm * 0.092903
}

export function areaSqmToSqft(sqm: number): number {
	return sqm / 0.092903
}
