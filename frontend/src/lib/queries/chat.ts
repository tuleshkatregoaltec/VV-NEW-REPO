import { chat } from '$lib/api/chat'

export const chatKeys = {
	all: ['chat'] as const,
	conversations: (limit = 50, offset = 0) =>
		[...chatKeys.all, 'conversations', { limit, offset }] as const,
	messages: (conversationId: number, limit = 100) =>
		[...chatKeys.all, 'messages', { conversationId, limit }] as const
}

export const chatQueries = {
	conversations: (limit = 50, offset = 0) => ({
		queryKey: chatKeys.conversations(limit, offset),
		queryFn: () => chat.getConversations({ limit, offset }),
		staleTime: 60 * 1000
	}),
	messages: (conversationId: number | null, limit = 100) => ({
		queryKey: chatKeys.messages(conversationId ?? 0, limit),
		queryFn: () => chat.getMessages(conversationId ?? 0, { limit }),
		enabled: conversationId !== null,
		staleTime: 5 * 60 * 1000
	})
}
