import type { StreamCallback } from './client'
import { client } from './client'
import type {
	ConversationListResponse,
	ConversationResponse,
	CreateConversationRequest,
	MessageResponse,
	UpdateConversationRequest
} from './generated/hey-api/types.gen'

export type {
	ConversationListResponse,
	ConversationResponse,
	CreateConversationRequest,
	MessageResponse
}

export interface ConversationListParams {
	limit?: number
	offset?: number
}

export interface MessageListParams {
	limit?: number
}

export const chat = {
	createConversation: (data: CreateConversationRequest = {}) =>
		client.post<ConversationResponse>('/api/v1/chat/conversations', data),

	getConversations: ({ limit = 50, offset = 0 }: ConversationListParams = {}) =>
		client.get<ConversationListResponse>(
			client.withQuery('/api/v1/chat/conversations', { limit, offset })
		),

	updateConversation: (conversationId: number, title: string) =>
		client.patch<ConversationResponse, UpdateConversationRequest>(
			`/api/v1/chat/conversations/${conversationId}`,
			{ title }
		),

	deleteConversation: (conversationId: number) =>
		client.delete(`/api/v1/chat/conversations/${conversationId}`),

	getMessages: (conversationId: number, { limit = 100 }: MessageListParams = {}) =>
		client.get<MessageResponse[]>(
			client.withQuery(`/api/v1/chat/conversations/${conversationId}/messages`, { limit })
		),

	/** Streams AI response chunks via Server-Sent Events */
	sendMessage: (conversationId: number, message: string, onChunk: StreamCallback) =>
		client.stream(`/api/v1/chat/conversations/${conversationId}/messages/stream`, onChunk, {
			method: 'POST',
			body: { message }
		})
}
