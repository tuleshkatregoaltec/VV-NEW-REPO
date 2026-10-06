import type { FeasibilityChatMessage, FeasibilityChatState } from '$lib/feasibility/workbook/models'

export interface PendingProposal {
	action: string
	payload: unknown
}

const chatMessages = $state<{ value: FeasibilityChatMessage[] }>({ value: [] })
const historyJson = $state<{ value: string | null }>({ value: null })
const pendingProposal = $state({ value: null as PendingProposal | null })
const streaming = $state({ value: false })
const loadingStepIndex = $state({ value: 0 })
const latestResearchEvent = $state<{ value: { tab: string; data: unknown } | null }>({
	value: null
})

function timestamped(message: FeasibilityChatMessage): FeasibilityChatMessage {
	return message.created_at ? message : { ...message, created_at: new Date().toISOString() }
}

export const loadingSteps = [
	'Reading plot data',
	'Researching market evidence',
	'Setting project assumptions',
	'Building financial model',
	'Finalizing study'
]

export const feasibilityWorkspace = {
	get chatMessages() {
		return chatMessages.value
	},
	get historyJson() {
		return historyJson.value
	},
	get chatState(): FeasibilityChatState {
		return {
			messages: chatMessages.value,
			history_json: historyJson.value
		}
	},
	get pendingProposal() {
		return pendingProposal.value
	},
	get streaming() {
		return streaming.value
	},
	get loadingStepIndex() {
		return loadingStepIndex.value
	},
	get latestResearchEvent() {
		return latestResearchEvent.value
	},
	setStreaming(next: boolean) {
		streaming.value = next
	},
	advanceLoadingStep() {
		loadingStepIndex.value = (loadingStepIndex.value + 1) % loadingSteps.length
	},
	resetLoading() {
		loadingStepIndex.value = 0
	},
	pushMessage(message: FeasibilityChatMessage) {
		chatMessages.value = [...chatMessages.value, timestamped(message)]
	},
	startAssistantMessage() {
		chatMessages.value = [
			...chatMessages.value,
			{ role: 'assistant', content: '', created_at: new Date().toISOString() }
		]
		return chatMessages.value.length - 1
	},
	appendAssistantChunk(index: number, chunk: string) {
		chatMessages.value = chatMessages.value.map((message, currentIndex) =>
			currentIndex === index ? { ...message, content: `${message.content}${chunk}` } : message
		)
	},
	setPendingProposal(proposal: PendingProposal | null) {
		pendingProposal.value = proposal
	},
	setHistoryJson(next: string | null) {
		historyJson.value = next
	},
	hydrate(chatState: FeasibilityChatState | null | undefined) {
		chatMessages.value = (chatState?.messages ?? []).map(timestamped)
		historyJson.value = chatState?.history_json ?? null
		pendingProposal.value = null
		streaming.value = false
		latestResearchEvent.value = null
	},
	setResearchEvent(event: { tab: string; data: unknown } | null) {
		latestResearchEvent.value = event
	},
	reset() {
		chatMessages.value = []
		historyJson.value = null
		pendingProposal.value = null
		streaming.value = false
		loadingStepIndex.value = 0
		latestResearchEvent.value = null
	}
}
