import { client } from './client'
import type {
	CheckoutSessionRequest,
	CheckoutSessionResponse,
	PaymentSyncResponse,
	SyncAfterCheckoutRequest
} from './generated/hey-api/types.gen'

export type { CheckoutSessionResponse, PaymentSyncResponse }

export async function createCheckoutSession(
	organizationId: CheckoutSessionRequest['organization_id'],
	seats: CheckoutSessionRequest['seats'],
	priceTier: 'tier1' | 'tier2'
): Promise<CheckoutSessionResponse> {
	return client.post<CheckoutSessionResponse>('/api/v1/billing/create-checkout', {
		organization_id: organizationId,
		seats,
		price_tier: priceTier
	})
}

export async function syncAfterCheckout(
	sessionId: SyncAfterCheckoutRequest['session_id']
): Promise<PaymentSyncResponse> {
	return client.post<PaymentSyncResponse>('/api/v1/billing/sync-after-checkout', {
		session_id: sessionId
	})
}
