export type ResearchTab =
	| 'summary'
	| 'transactions'
	| 'analytics'
	| 'comparables'
	| 'map'
	| 'plot_sandbox'

const activeTab = $state({ value: 'summary' as ResearchTab })
const agentTransactions = $state({ value: null as Record<string, unknown> | null })
const agentAnalytics = $state({ value: null as Record<string, unknown> | null })

export const researchPanelStore = {
	get activeTab() {
		return activeTab.value
	},
	get agentTransactions() {
		return agentTransactions.value
	},
	get agentAnalytics() {
		return agentAnalytics.value
	},
	setActiveTab(tab: ResearchTab) {
		activeTab.value = tab
	},
	setAgentData(tab: 'transactions' | 'analytics', data: unknown) {
		if (tab === 'transactions') agentTransactions.value = data as Record<string, unknown>
		if (tab === 'analytics') agentAnalytics.value = data as Record<string, unknown>
	}
}
