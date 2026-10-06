import { beforeEach, describe, expect, it, vi } from 'vitest'

import { crm } from '$lib/api/crm'
import { inbound } from '$lib/api/inbound'
import { crmKeys, crmQueries } from '$lib/queries/crm'
import { inboundKeys, inboundQueries } from '$lib/queries/inbound'

describe('CRM query builders', () => {
	beforeEach(() => vi.restoreAllMocks())

	it('keeps dashboard data visible while cancelling obsolete filter requests', async () => {
		const dashboardSpy = vi.spyOn(crm, 'dashboard').mockResolvedValue({} as never)
		const params = { search: 'Marina', limit: 50, offset: 0 }
		const options = crmQueries.dashboard(params)
		const previous = { leads: [{ lead_id: 'lead-1' }] } as never
		const controller = new AbortController()

		expect(options.queryKey).toEqual(crmKeys.dashboard(params))
		expect(options.placeholderData(previous)).toBe(previous)
		await options.queryFn({ signal: controller.signal })
		expect(dashboardSpy).toHaveBeenCalledWith(params, controller.signal)
	})

	it('does not fetch owner-only datasets until their workspace is visible', () => {
		expect(crmQueries.contactImports(false).enabled).toBe(false)
		expect(crmQueries.ownerWorkspaces(false).enabled).toBe(false)
		expect(crmQueries.contactImports(true).enabled).toBe(true)
		expect(crmQueries.ownerWorkspaces(true).enabled).toBe(true)
	})

	it('centralizes inbound keys and cancels obsolete search requests', async () => {
		const listSpy = vi.spyOn(inbound, 'list').mockResolvedValue({} as never)
		const params = { intent_group: 'demand' as const, search: 'JBR' }
		const options = inboundQueries.list(params)
		const controller = new AbortController()

		expect(options.queryKey).toEqual(inboundKeys.list(params))
		await options.queryFn({ signal: controller.signal })
		expect(listSpy).toHaveBeenCalledWith(params, controller.signal)
		expect(inboundQueries.imports(false).enabled).toBe(false)
	})
})
