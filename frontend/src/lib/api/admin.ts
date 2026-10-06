import { client } from './client'
import type {
	CreateUserRequest,
	CreateUserResponse,
	OrganizationListResponse,
	OrgDetailResponse,
	OrgUserResponse
} from './generated/hey-api/types.gen'

export type {
	CreateUserRequest,
	CreateUserResponse,
	OrgDetailResponse,
	OrganizationListResponse,
	OrgUserResponse
}

export interface UserTokenStats {
	user_id: string
	tokens_used_today: number
	daily_limit: number
	usage_percentage: number
	remaining_tokens: number
}

export const admin = {
	organizations: {
		list: () => client.get<OrganizationListResponse[]>('/api/v1/admin/organizations'),
		get: (id: string) => client.get<OrgDetailResponse>(`/api/v1/admin/organizations/${id}`),
		update: (id: string, data: { max_users?: number }) =>
			client.put<OrganizationListResponse>(`/api/v1/admin/organizations/${id}`, data),
		delete: (id: string) => client.delete<void>(`/api/v1/admin/organizations/${id}`),
		setSubscription: (id: string, status: string) =>
			client.patch<OrganizationListResponse>(`/api/v1/admin/organizations/${id}/subscription`, {
				status
			})
	},

	users: {
		create: (data: CreateUserRequest) =>
			client.post<CreateUserResponse>('/api/v1/admin/users', data),
		updateTokenLimit: (id: string, daily_token_limit: number) =>
			client.patch<{ id: string }>(`/api/v1/admin/users/${id}`, { daily_token_limit }),
		delete: (id: string) => client.delete<void>(`/api/v1/admin/users/${id}`)
	}
}
