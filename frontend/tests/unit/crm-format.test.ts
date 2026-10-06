import { describe, expect, it } from 'vitest'

import { formatCrmDate, formatCrmMoney, formatCrmNumber, formatCrmStatus } from '$lib/crm/format'

describe('CRM display formatting', () => {
	it('uses consistent AED and numeric formatting across CRM views', () => {
		expect(formatCrmMoney(240000)).toContain('240,000')
		expect(formatCrmMoney(null)).toBe('—')
		expect(formatCrmNumber(12345)).toBe('12,345')
		expect(formatCrmNumber(null, 0, '—')).toBe('—')
	})

	it('renders registry dates without timezone day shifts', () => {
		expect(formatCrmDate('2026-03-30')).toBe('30 Mar 2026')
		expect(formatCrmDate(null)).toBe('—')
	})

	it('humanizes pipeline values consistently', () => {
		expect(formatCrmStatus('needs_review')).toBe('Needs review')
		expect(formatCrmStatus('closed_lost')).toBe('Closed lost')
	})
})
