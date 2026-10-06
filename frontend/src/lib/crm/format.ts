const currencyFormatter = new Intl.NumberFormat('en-AE', {
	style: 'currency',
	currency: 'AED',
	maximumFractionDigits: 0
})

const compactCurrencyFormatter = new Intl.NumberFormat('en-AE', {
	style: 'currency',
	currency: 'AED',
	notation: 'compact',
	maximumFractionDigits: 1
})

const dateFormatter = new Intl.DateTimeFormat('en-GB', {
	day: '2-digit',
	month: 'short',
	year: 'numeric'
})

export function formatCrmMoney(value: number | null | undefined, compact = false, empty = '—') {
	if (value === null || value === undefined || !Number.isFinite(value)) return empty
	return (compact ? compactCurrencyFormatter : currencyFormatter).format(value)
}

export function formatCrmNumber(value: number | null | undefined, digits = 0, empty = '0') {
	if (value === null || value === undefined || !Number.isFinite(value)) return empty
	return new Intl.NumberFormat('en-AE', { maximumFractionDigits: digits }).format(value)
}

export function formatCrmDate(value: string | null | undefined, empty = '—') {
	if (!value) return empty
	const datePrefix = value.match(/^\d{4}-\d{2}-\d{2}/)?.[0]
	const parsed = new Date(datePrefix ? `${datePrefix}T00:00:00` : value)
	return Number.isNaN(parsed.getTime()) ? empty : dateFormatter.format(parsed)
}

export function formatCrmStatus(value: string) {
	return value.replaceAll('_', ' ').replace(/^./, (letter) => letter.toUpperCase())
}
