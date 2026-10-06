import { beforeEach, describe, expect, it, vi } from 'vitest'

import { analytics } from '$lib/api/analytics'
import { feasibility } from '$lib/api/feasibility'
import { filters } from '$lib/api/filters'
import { news } from '$lib/api/news'
import * as organizationApi from '$lib/api/organization'
import { projects } from '$lib/api/projects'
import {
	type RentalContractListResponse,
	type TransactionListResponse,
	transactions
} from '$lib/api/transactions'
import { analyticsKeys, analyticsQueries } from '$lib/queries/analytics'
import { feasibilityKeys, feasibilityQueries } from '$lib/queries/feasibility'
import { newsKeys, newsQueries } from '$lib/queries/news'
import { organizationKeys, organizationQueries } from '$lib/queries/organization'
import { projectKeys, projectQueries } from '$lib/queries/projects'
import { transactionKeys, transactionQueries } from '$lib/queries/transactions'

describe('shared query builders', () => {
	beforeEach(() => {
		vi.restoreAllMocks()
	})

	it('builds analytics query options with stable keys and delegates fetches', async () => {
		const marketTrendSpy = vi.spyOn(analytics, 'marketTrend').mockResolvedValue({} as never)
		const projectSearchSpy = vi.spyOn(analytics, 'projectSearch').mockResolvedValue({} as never)
		const subProjectsSpy = vi.spyOn(analytics, 'subProjects').mockResolvedValue({} as never)

		const marketTrendQuery = analyticsQueries.marketTrend(365, 'residential')
		expect(marketTrendQuery.queryKey).toEqual(analyticsKeys.marketTrend(365, 'residential'))
		expect(marketTrendQuery.staleTime).toBe(5 * 60 * 1000)
		await marketTrendQuery.queryFn()
		expect(marketTrendSpy).toHaveBeenCalledWith({
			days: 365,
			property_usage: 'residential'
		})

		const projectSearchQuery = analyticsQueries.projectSearch('', 500)
		expect(projectSearchQuery.queryKey).toEqual(analyticsKeys.projectSearch('', 500))
		expect(projectSearchQuery.staleTime).toBe(Infinity)
		await projectSearchQuery.queryFn()
		expect(projectSearchSpy).toHaveBeenCalledWith('', 500)

		const subProjectsQuery = analyticsQueries.subProjects('Downtown', 'master')
		expect(subProjectsQuery.queryKey).toEqual(analyticsKeys.subProjects('Downtown', 'master'))
		expect(subProjectsQuery.enabled).toBe(true)
		await subProjectsQuery.queryFn()
		expect(subProjectsSpy).toHaveBeenCalledWith('Downtown', 'master')
		expect(analyticsQueries.subProjects(null, null).enabled).toBe(false)
		expect(analyticsQueries.subProjects('Dubai', 'market').enabled).toBe(false)
	})

	it('builds transaction query options with typed placeholder data and filter keys', async () => {
		const salesSpy = vi.spyOn(transactions, 'sales').mockResolvedValue({} as never)
		const rentalsSpy = vi.spyOn(transactions, 'rentals').mockResolvedValue({} as never)
		const salesFiltersSpy = vi.spyOn(filters, 'sales').mockResolvedValue({} as never)
		const rentalFiltersSpy = vi.spyOn(filters, 'rentals').mockResolvedValue({} as never)

		const params = {
			property_usage: 'residential',
			project: 'Downtown Views',
			filter_type: 'project',
			limit: 50,
			offset: 0
		}

		const salesQuery = transactionQueries.sales(params)
		expect(salesQuery.queryKey).toEqual(transactionKeys.sales(params))
		const previousSales = {
			total: 1,
			transactions: [],
			limit: 50,
			offset: 0
		} as TransactionListResponse
		expect(salesQuery.placeholderData(previousSales)).toBe(previousSales)
		await salesQuery.queryFn()
		expect(salesSpy).toHaveBeenCalledWith(params)

		const rentalsQuery = transactionQueries.rentals(params)
		expect(rentalsQuery.queryKey).toEqual(transactionKeys.rentals(params))
		const previousRentals = {
			total: 1,
			contracts: [],
			limit: 50,
			offset: 0
		} as RentalContractListResponse
		expect(rentalsQuery.placeholderData(previousRentals)).toBe(previousRentals)
		await rentalsQuery.queryFn()
		expect(rentalsSpy).toHaveBeenCalledWith(params)

		const filterParams = { property_usage: 'commercial', property_type: 'Office' }
		const salesFilterOptionsQuery = transactionQueries.salesFilterOptions(filterParams)
		expect(salesFilterOptionsQuery.queryKey).toEqual(
			transactionKeys.filterOptions('sales', filterParams)
		)
		await salesFilterOptionsQuery.queryFn()
		expect(salesFiltersSpy).toHaveBeenCalledWith(filterParams)

		const rentalFilterOptionsQuery = transactionQueries.rentalFilterOptions(filterParams)
		expect(rentalFilterOptionsQuery.queryKey).toEqual(
			transactionKeys.filterOptions('rentals', filterParams)
		)
		await rentalFilterOptionsQuery.queryFn()
		expect(rentalFiltersSpy).toHaveBeenCalledWith(filterParams)
	})

	it('builds news, project, organization, and feasibility query options', async () => {
		const newsSpy = vi.spyOn(news, 'list').mockResolvedValue({} as never)
		const projectsListSpy = vi.spyOn(projects, 'list').mockResolvedValue([] as never)
		const projectsMasterSpy = vi.spyOn(projects, 'getMaster').mockResolvedValue({} as never)
		const projectsDetailSpy = vi.spyOn(projects, 'getDetails').mockResolvedValue({} as never)
		const projectsBuildingSpy = vi.spyOn(projects, 'getBuilding').mockResolvedValue({} as never)
		const membersSpy = vi
			.spyOn(organizationApi, 'getOrganizationMembers')
			.mockResolvedValue([] as never)
		const subscriptionSpy = vi
			.spyOn(organizationApi, 'getOrganizationSubscription')
			.mockResolvedValue({} as never)
		const invitationsSpy = vi
			.spyOn(organizationApi, 'getOrganizationInvitations')
			.mockResolvedValue([] as never)
		const areasSpy = vi.spyOn(feasibility, 'getAreas').mockResolvedValue([] as never)
		const communitiesSpy = vi.spyOn(feasibility, 'getCommunities').mockResolvedValue([] as never)

		const newsQuery = newsQueries.listInfinite('dashboard', 10)
		expect(newsQuery.queryKey).toEqual(newsKeys.list('dashboard', 10))
		expect(newsQuery.getNextPageParam({ offset: 0, articles: new Array(10), total: 25 })).toBe(10)
		expect(newsQuery.getNextPageParam({ offset: 20, articles: new Array(5), total: 25 })).toBe(
			undefined
		)
		await newsQuery.queryFn({ pageParam: 20 })
		expect(newsSpy).toHaveBeenCalledWith({ limit: 10, offset: 20 })

		const projectsListQuery = projectQueries.list()
		expect(projectsListQuery.queryKey).toEqual(projectKeys.list())
		await projectsListQuery.queryFn()
		expect(projectsListSpy).toHaveBeenCalled()

		const projectsMasterQuery = projectQueries.master('Business Bay')
		expect(projectsMasterQuery.queryKey).toEqual(projectKeys.master('Business Bay'))
		expect(projectsMasterQuery.enabled).toBe(true)
		await projectsMasterQuery.queryFn()
		expect(projectsMasterSpy).toHaveBeenCalledWith('Business Bay')

		const projectsDetailQuery = projectQueries.detail(42)
		expect(projectsDetailQuery.queryKey).toEqual(projectKeys.detail(42))
		expect(projectsDetailQuery.enabled).toBe(true)
		await projectsDetailQuery.queryFn()
		expect(projectsDetailSpy).toHaveBeenCalledWith(42)

		const projectsBuildingQuery = projectQueries.building(77)
		expect(projectsBuildingQuery.queryKey).toEqual(projectKeys.building(77))
		expect(projectsBuildingQuery.enabled).toBe(true)
		await projectsBuildingQuery.queryFn()
		expect(projectsBuildingSpy).toHaveBeenCalledWith(77)

		const membersQuery = organizationQueries.members(true)
		expect(membersQuery.queryKey).toEqual(organizationKeys.members())
		expect(membersQuery.enabled).toBe(true)
		await membersQuery.queryFn()
		expect(membersSpy).toHaveBeenCalled()

		const subscriptionQuery = organizationQueries.subscription(false)
		expect(subscriptionQuery.queryKey).toEqual(organizationKeys.subscription())
		expect(subscriptionQuery.enabled).toBe(false)
		await subscriptionQuery.queryFn()
		expect(subscriptionSpy).toHaveBeenCalled()

		const invitationsQuery = organizationQueries.invitations(true)
		expect(invitationsQuery.queryKey).toEqual(organizationKeys.invitations())
		await invitationsQuery.queryFn()
		expect(invitationsSpy).toHaveBeenCalled()

		const areasQuery = feasibilityQueries.areas()
		expect(areasQuery.queryKey).toEqual(feasibilityKeys.areas())
		await areasQuery.queryFn()
		expect(areasSpy).toHaveBeenCalled()

		const communitiesQuery = feasibilityQueries.communities()
		expect(communitiesQuery.queryKey).toEqual(feasibilityKeys.communities())
		await communitiesQuery.queryFn()
		expect(communitiesSpy).toHaveBeenCalled()
	})
})
