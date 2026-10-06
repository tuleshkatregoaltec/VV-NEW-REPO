<script lang="ts">
import DOMPurify from 'dompurify'
import { ArrowRight, Check, SendHorizontal, Sparkles, X } from 'lucide-svelte'
import { marked } from 'marked'
import { tick } from 'svelte'
import { browser } from '$app/environment'
import { feasibility } from '$lib/api/feasibility'
import type { FeasibilityAssumptions, UnitConfig } from '$lib/feasibility/workbook/models'
import { type FeasibilitySheetTab, workbookStore } from '$lib/feasibility/workbook/store.svelte'
import { formatNumber, titleCase, unitConfigMatchesKey } from '$lib/feasibility/workbook/utils'
import { feasibilityStudy } from '$lib/stores/feasibilityStudy.svelte'
import { feasibilityWorkspace, type PendingProposal } from '$lib/stores/feasibilityWorkspace.svelte'

marked.use({
	renderer: {
		link({ href, title, text }: any) {
			const titleAttr = title ? ` title="${title}"` : ''
			return `<a href="${href}"${titleAttr} target="_blank" rel="noopener noreferrer">${text}</a>`
		}
	}
})

const SANITIZE_CONFIG = {
	ALLOWED_TAGS: [
		'p',
		'br',
		'strong',
		'em',
		'a',
		'ul',
		'ol',
		'li',
		'blockquote',
		'code',
		'pre',
		'span'
	],
	ALLOWED_ATTR: ['href', 'title', 'target', 'rel']
}

const DECIMAL_PERCENT_FIELDS = new Set<string>([
	'acquisitionDebtLtv',
	'constructionDebtLtc',
	'debtSpreadPa',
	'financingFeePct',
	'exitFeePct',
	'preferredReturnPa',
	'sponsorPromotePct',
	'landTransferFeePct',
	'brokeragePct',
	'legalDdPct',
	'permitFeesPct',
	'softCostPct',
	'serviceBohPlantPct'
])

const ASSUMPTION_LABELS: Partial<Record<keyof FeasibilityAssumptions, string>> = {
	buaMultiplier: 'BUA multiple',
	nsaEfficiencyPct: 'NSA efficiency',
	constructionCostPsqmBua: 'Construction cost',
	landPricePsqm: 'Land price',
	landAcquisitionCostOverrideAed: 'Land acquisition cost',
	designSupervisionCostOverrideAed: 'Design and supervision',
	constructionCostOverrideAed: 'Construction cost override',
	marketingCostOverrideAed: 'Marketing cost',
	salesAgentFeesOverrideAed: 'Sales agent fees',
	contingencyCostOverrideAed: 'Contingency cost',
	contingencyPct: 'Contingency',
	demolitionCostAed: 'Demolition cost',
	infrastructureCostAed: 'Infrastructure cost',
	governmentFeesAed: 'Government fees',
	acquisitionDebtLtv: 'Land debt LTV',
	constructionDebtLtc: 'Construction debt LTC',
	landLoanSpreadBps: 'Land loan spread',
	constructionLoanSpreadBps: 'Construction loan spread',
	debtSpreadPa: 'Debt spread',
	financingFeePct: 'Financing fee',
	exitFeePct: 'Exit fee',
	preferredReturnPa: 'Preferred return',
	sponsorPromotePct: 'Sponsor promote',
	projectYears: 'Project term',
	residentialFloors: 'Residential floors',
	podiumFloors: 'Podium floors',
	basementParkingFloors: 'Basement parking floors',
	amenityRoofFloors: 'Amenity / roof floors',
	parkingAreaPerSpaceSqm: 'Parking area per space',
	serviceBohPlantPct: 'Service / BOH / plant',
	aboveGradeBuaFactor: 'Above-grade BUA factor',
	salesPeriodMonths: 'Sales period',
	landAcquisitionDate: 'Land acquisition date',
	constructionDate: 'Construction start',
	handoverDate: 'Handover date'
}

const promptSuggestions = [
	'Explain the biggest drivers of the current equity IRR.',
	'Reduce sales pricing by 5% and show the impact.',
	'Make the payment plan more conservative.'
]

const BUDGET_ASSUMPTION_FIELDS = new Set<string>([
	'landPricePsqm',
	'landAcquisitionCostOverrideAed',
	'brokerageFeeAed',
	'legalDdCostAed',
	'constructionCostPsqmBua',
	'constructionCostOverrideAed',
	'midPointInflationPct',
	'designSupervisionPct',
	'designSupervisionCostOverrideAed',
	'marketingCostPct',
	'marketingCostOverrideAed',
	'salesAgentFeePct',
	'salesAgentFeesOverrideAed',
	'contingencyPct',
	'contingencyCostOverrideAed',
	'demolitionCostAed',
	'infrastructureCostAed',
	'governmentFeesAed',
	'masterCommunityFeesAed',
	'ffeOsePreopeningCostAed',
	'financingFeePct',
	'exitFeePct',
	'vatPct',
	'landAcquisitionDate',
	'demolitionEnablingDate',
	'constructionDate',
	'handoverDate'
])

interface ProposalLine {
	title: string
	from?: string
	to: string
	detail?: string
}

let draft = $state('')
let textareaRef = $state<HTMLTextAreaElement | null>(null)
let messagesEndRef = $state<HTMLDivElement | null>(null)

const pendingProposalLines = $derived(proposalLines(feasibilityWorkspace.pendingProposal))
const pendingProposalSummary = $derived(proposalSummary(feasibilityWorkspace.pendingProposal))
const scrollSignal = $derived(
	`${feasibilityWorkspace.chatMessages.length}:${feasibilityWorkspace.chatMessages.at(-1)?.content.length ?? 0}:${feasibilityWorkspace.streaming}:${feasibilityWorkspace.pendingProposal?.action ?? ''}`
)

function renderMarkdown(content: string): string {
	if (!browser) return content.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
	return DOMPurify.sanitize(marked.parse(content) as string, SANITIZE_CONFIG)
}

function mergeHistoryJson(current: string | null, next: string | null | undefined) {
	if (!next) return current
	if (!current) return next
	try {
		const currentMessages = JSON.parse(current)
		const nextMessages = JSON.parse(next)
		if (Array.isArray(currentMessages) && Array.isArray(nextMessages)) {
			return JSON.stringify([...currentMessages, ...nextMessages])
		}
	} catch {
		return next
	}
	return next
}

function isRecord(value: unknown): value is Record<string, unknown> {
	return Boolean(value && typeof value === 'object' && !Array.isArray(value))
}

function findUnitConfig(key: string): UnitConfig | undefined {
	return workbookStore.inputs.unitConfigs?.find((row) => unitConfigMatchesKey(row, key))
}

function labelForAssumption(key: string): string {
	return ASSUMPTION_LABELS[key as keyof FeasibilityAssumptions] ?? titleCase(key)
}

function formatProposalValue(key: string, value: unknown): string {
	if (value === null) return 'Auto'
	if (typeof value === 'boolean') return value ? 'Yes' : 'No'
	if (typeof value === 'number') {
		if (key.endsWith('Bps')) return `${formatNumber(value)} bps`
		if (DECIMAL_PERCENT_FIELDS.has(key)) return `${formatNumber(value * 100, 1)}%`
		if (key.endsWith('Pct') || key.includes('Occupancy') || key.includes('Vacancy')) {
			return `${formatNumber(value, value % 1 === 0 ? 0 : 1)}%`
		}
		if (key.endsWith('Aed')) return `AED ${formatNumber(value)}`
		if (key.includes('Psqm')) return `AED ${formatNumber(value)} / sqm`
		if (key.includes('Months')) return `${formatNumber(value)} mo`
		if (key.includes('Years')) return `${formatNumber(value)} yr`
		return formatNumber(value, value % 1 === 0 ? 0 : 2)
	}
	if (typeof value === 'string') return value
	if (Array.isArray(value)) return `${value.length} items`
	if (isRecord(value)) return `${Object.keys(value).length} settings`
	return String(value)
}

function formatUnitPrice(pricePsqm: number): string {
	return `AED ${formatNumber(pricePsqm)} / sqm`
}

function proposalSummary(proposal: PendingProposal | null): string {
	if (!proposal) return ''
	if (proposal.action === 'set_price_per_sqm') return 'Update unit pricing'
	if (proposal.action === 'set_unit_mix' || proposal.action === 'replace_unit_mix')
		return 'Replace unit mix'
	if (proposal.action === 'update_unit_mix') return 'Update unit mix'
	if (proposal.action === 'set_payment_plan') return 'Update payment plan'
	if (proposal.action === 'set_assumptions') return 'Update assumptions'
	return titleCase(proposal.action)
}

function proposalLines(proposal: PendingProposal | null): ProposalLine[] {
	if (!proposal) return []
	if (proposal.action === 'set_price_per_sqm' && isRecord(proposal.payload)) {
		return Object.entries(proposal.payload)
			.filter(([, value]) => typeof value === 'number')
			.map(([key, value]) => {
				const unit = findUnitConfig(key)
				const next = value as number
				return {
					title: unit?.label ?? titleCase(key),
					from: unit ? formatUnitPrice(unit.sellingRatePsqm) : undefined,
					to: formatUnitPrice(next),
					detail: `Approx. AED ${formatNumber(next * 0.092903)} / sq ft`
				}
			})
	}
	if (
		(proposal.action === 'set_unit_mix' ||
			proposal.action === 'replace_unit_mix' ||
			proposal.action === 'update_unit_mix') &&
		Array.isArray(proposal.payload)
	) {
		return proposal.payload.filter(isRecord).map((row) => {
			const key = String(row.type ?? '')
			const unit = findUnitConfig(key)
			const details = [
				typeof row.count === 'number' ? `${formatNumber(row.count)} units` : null,
				typeof row.avgSizeSqm === 'number' ? `${formatNumber(row.avgSizeSqm)} sqm avg` : null,
				typeof row.price_sqm === 'number' ? formatUnitPrice(row.price_sqm) : null,
				typeof row.parkingRatio === 'number' ? `${formatNumber(row.parkingRatio, 1)} parking` : null
			].filter(Boolean)
			return {
				title: unit?.label ?? titleCase(key),
				to: details.join(' · ')
			}
		})
	}
	if (proposal.action === 'set_payment_plan' && isRecord(proposal.payload)) {
		const labels: Record<string, string> = {
			depositPct: 'Deposit',
			constructionPct: 'Pre-handover',
			handoverPct: 'At handover'
		}
		const currentPlan = workbookStore.paymentPlan as unknown as Record<string, unknown>
		return Object.entries(proposal.payload).map(([key, value]) => ({
			title: labels[key] ?? titleCase(key),
			from: formatProposalValue(key, currentPlan[key]),
			to: formatProposalValue(key, value)
		}))
	}
	if (proposal.action === 'set_assumptions' && isRecord(proposal.payload)) {
		return Object.entries(proposal.payload).map(([key, value]) => ({
			title: labelForAssumption(key),
			from: formatProposalValue(
				key,
				(workbookStore.inputs as unknown as Record<string, unknown>)[key]
			),
			to: formatProposalValue(key, value)
		}))
	}
	return [{ title: proposalSummary(proposal), to: 'Ready to apply' }]
}

function proposalTargets(proposal: PendingProposal): string[] {
	const fields: string[] = []
	if (proposal.action === 'set_price_per_sqm' && isRecord(proposal.payload)) {
		for (const key of Object.keys(proposal.payload)) {
			const unit = findUnitConfig(key)
			if (unit) fields.push(`unitConfig:${unit.id}:sellingRatePsqm`)
		}
		if (fields.length === 0) fields.push('priceUpdate')
	}
	if (
		(proposal.action === 'set_unit_mix' ||
			proposal.action === 'replace_unit_mix' ||
			proposal.action === 'update_unit_mix') &&
		Array.isArray(proposal.payload)
	) {
		for (const row of proposal.payload.filter(isRecord)) {
			const unit = findUnitConfig(String(row.type ?? ''))
			if (!unit) continue
			fields.push(`unitConfig:${unit.id}:units`, `unitConfig:${unit.id}:avgSizeSqm`)
			if (typeof row.price_sqm === 'number') fields.push(`unitConfig:${unit.id}:sellingRatePsqm`)
			if (typeof row.parkingRatio === 'number') fields.push(`unitConfig:${unit.id}:parkingRatio`)
		}
		if (fields.length === 0) fields.push('unitMix')
	}
	if (proposal.action === 'set_payment_plan' && isRecord(proposal.payload)) {
		for (const key of Object.keys(proposal.payload)) fields.push(`paymentPlan:${key}`)
		if (fields.length === 0) fields.push('paymentPlan')
	}
	if (proposal.action === 'set_assumptions' && isRecord(proposal.payload)) {
		fields.push(...Object.keys(proposal.payload))
	}
	return fields
}

function proposalTargetTab(proposal: PendingProposal): FeasibilitySheetTab {
	if (proposal.action === 'set_assumptions' && isRecord(proposal.payload)) {
		const keys = Object.keys(proposal.payload)
		if (keys.some((key) => BUDGET_ASSUMPTION_FIELDS.has(key))) return 'budget'
	}
	return 'key_assumptions'
}

function roleLabel(role: string) {
	if (role === 'assistant') return 'Feasibility AI'
	if (role === 'system') return 'Update'
	return 'You'
}

function useSuggestion(prompt: string) {
	draft = prompt
	setTimeout(() => textareaRef?.focus(), 0)
}

function scrollToBottom(behavior: ScrollBehavior = 'smooth') {
	void tick().then(() => {
		messagesEndRef?.scrollIntoView({ behavior, block: 'end' })
	})
}

$effect(() => {
	scrollSignal
	if (feasibilityWorkspace.chatMessages.length === 0 && !feasibilityWorkspace.pendingProposal)
		return
	scrollToBottom(feasibilityWorkspace.streaming ? 'auto' : 'smooth')
})

async function sendMessage() {
	const plotData = workbookStore.plotData
	const research = workbookStore.research
	if (!draft.trim() || !plotData || !research || feasibilityWorkspace.streaming) return
	let bufferedProposal: PendingProposal | null = null
	const content = draft.trim()
	draft = ''
	feasibilityWorkspace.pushMessage({ role: 'user', content })
	const assistantIndex = feasibilityWorkspace.startAssistantMessage()
	feasibilityWorkspace.setStreaming(true)

	await feasibility.streamChat(
		[{ role: 'user', content }],
		{
			plot_data: plotData,
			assumptions: workbookStore.inputs,
			research,
			history_json: feasibilityWorkspace.historyJson
		},
		(chunk) => {
			try {
				const parsed = JSON.parse(chunk)
				if (parsed.type === 'text') {
					feasibilityWorkspace.appendAssistantChunk(assistantIndex, parsed.content)
				} else if (parsed.type === 'pending_action') {
					bufferedProposal = {
						action: parsed.action,
						payload: parsed.payload
					}
				} else if (parsed.type === 'show_research') {
					feasibilityWorkspace.setResearchEvent({
						tab: parsed.tab,
						data: parsed.data
					})
				} else if (parsed.type === 'done') {
					feasibilityWorkspace.setHistoryJson(
						mergeHistoryJson(feasibilityWorkspace.historyJson, parsed.new_messages_json)
					)
					feasibilityWorkspace.setStreaming(false)
					if (bufferedProposal) feasibilityWorkspace.setPendingProposal(bufferedProposal)
					void feasibilityStudy.persistChatState(feasibilityWorkspace.chatState)
				} else if (parsed.type === 'error') {
					feasibilityWorkspace.appendAssistantChunk(assistantIndex, `\n${parsed.error}`)
					feasibilityWorkspace.setStreaming(false)
				}
			} catch {
				feasibilityWorkspace.appendAssistantChunk(assistantIndex, chunk)
			}
		}
	)
}

function acceptProposal() {
	const proposal = feasibilityWorkspace.pendingProposal
	if (!proposal) return
	const targetFields = proposalTargets(proposal)
	const targetTab = proposalTargetTab(proposal)
	const applied = workbookStore.applyProposal(proposal)
	feasibilityWorkspace.pushMessage({
		role: 'system',
		content: applied
			? `Applied ${proposalSummary(proposal).toLowerCase()}.`
			: `Could not apply ${proposalSummary(proposal).toLowerCase()}.`
	})
	feasibilityWorkspace.setPendingProposal(null)
	if (applied) {
		workbookStore.focusChangedFields(targetFields, targetTab)
		feasibilityStudy.markUnsaved()
		void feasibilityStudy.saveCurrentWorkbook(workbookStore.assumptions, {
			chatState: feasibilityWorkspace.chatState
		})
		return
	}
	void feasibilityStudy.persistChatState(feasibilityWorkspace.chatState)
}

function dismissProposal() {
	feasibilityWorkspace.setPendingProposal(null)
	void feasibilityStudy.persistChatState(feasibilityWorkspace.chatState)
}
</script>

<div class="ui-surface flex h-full flex-col overflow-hidden">
	<div class="border-b border-border bg-card px-4 py-4">
		<div class="flex items-start justify-between gap-3">
			<div>
				<div class="flex items-center gap-2">
					<Sparkles size={15} strokeWidth={1.8} class="text-primary-light" />
					<p class="text-sm font-semibold text-fg-1">Feasibility AI</p>
				</div>
				<p class="mt-1 text-xs leading-5 text-fg-4">Ask for underwriting explanations or approve structured changes.</p>
			</div>
			<span class="mt-0.5 rounded-full bg-success-bg px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.1em] text-success">
				Live
			</span>
		</div>
	</div>

	<div class="min-h-0 flex-1 space-y-3 overflow-auto bg-slate-50/60 px-4 py-4">
		{#if feasibilityWorkspace.chatMessages.length === 0}
			<div class="rounded-lg border border-dashed border-slate-200 bg-white p-4">
				<p class="text-sm font-medium text-fg-2">Start with a model question.</p>
				<p class="mt-1 text-xs leading-5 text-fg-4">The assistant can explain the workbook and stage changes for review before anything is applied.</p>
				<div class="mt-3 space-y-2">
					{#each promptSuggestions as prompt}
						<button
							type="button"
							class="w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-left text-xs leading-5 text-fg-3 transition hover:border-slate-300 hover:bg-slate-50 hover:text-fg-1"
							onclick={() => useSuggestion(prompt)}
						>
							{prompt}
						</button>
					{/each}
				</div>
			</div>
		{/if}
		{#each feasibilityWorkspace.chatMessages as message}
			<div class="flex {message.role === 'user' ? 'justify-end' : 'justify-start'}">
				<div
					class="max-w-[92%] rounded-lg px-3.5 py-2.5 text-[13px] leading-[1.55] shadow-sm {message.role === 'user'
						? 'bg-navy text-bone'
						: message.role === 'assistant'
							? 'border border-slate-200 bg-white text-fg-2'
							: 'border border-border bg-info-bg text-info'}"
				>
					<p class="mb-1.5 text-[10px] font-semibold uppercase tracking-[0.1em] opacity-70">{roleLabel(message.role)}</p>
					{#if message.role === 'assistant'}
						{#if message.content}
							<div
								class="leading-relaxed [&_p]:mb-2 [&_p:last-child]:mb-0 [&_strong]:font-semibold [&_em]:italic [&_a]:text-primary-light [&_a]:underline [&_a:hover]:text-fg-1 [&_ul]:mb-2 [&_ul]:list-disc [&_ul]:pl-5 [&_ol]:mb-2 [&_ol]:list-decimal [&_ol]:pl-5 [&_li]:mb-0.5 [&_blockquote]:my-2 [&_blockquote]:border-l-4 [&_blockquote]:border-slate-300 [&_blockquote]:pl-3 [&_blockquote]:italic [&_blockquote]:text-slate-600 [&_code]:rounded [&_code]:bg-slate-100 [&_code]:px-1 [&_code]:py-0.5 [&_code]:font-mono [&_code]:text-[12px] [&_pre]:my-2 [&_pre]:overflow-x-auto [&_pre]:rounded-lg [&_pre]:bg-slate-100 [&_pre]:p-3 [&_pre_code]:bg-transparent [&_pre_code]:p-0"
							>
								{@html renderMarkdown(message.content)}
							</div>
						{:else if feasibilityWorkspace.streaming}
							<p class="text-fg-4">Thinking...</p>
						{/if}
					{:else}
						<p class="whitespace-pre-wrap">{message.content}</p>
					{/if}
				</div>
			</div>
		{/each}

		{#if feasibilityWorkspace.pendingProposal}
			<div class="rounded-lg border border-emerald-200 bg-white p-4 text-sm shadow-sm">
				<div class="flex items-start justify-between gap-3">
					<div>
						<p class="text-xs font-semibold uppercase tracking-[0.12em] text-emerald-700">Suggested change</p>
						<p class="mt-1 font-semibold text-fg-1">{pendingProposalSummary}</p>
					</div>
					<span class="rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-semibold text-emerald-700">
						Review
					</span>
				</div>
				<div class="mt-3 divide-y divide-slate-100 rounded-md border border-slate-200 bg-slate-50/60">
					{#each pendingProposalLines as line}
						<div class="px-3 py-2.5">
							<div class="flex items-start justify-between gap-3">
								<p class="min-w-0 text-xs font-medium text-fg-2">{line.title}</p>
								<div class="flex shrink-0 items-center gap-1 text-right text-xs tabular-nums">
									{#if line.from}
										<span class="text-fg-4">{line.from}</span>
										<ArrowRight size={12} strokeWidth={1.8} class="text-fg-5" />
									{/if}
									<span class="font-semibold text-fg-1">{line.to}</span>
								</div>
							</div>
							{#if line.detail}
								<p class="mt-1 text-xs text-fg-4">{line.detail}</p>
							{/if}
						</div>
					{/each}
				</div>
				<div class="mt-3 flex gap-2">
					<button type="button" class="inline-flex items-center gap-1.5 rounded-md bg-emerald-700 px-3 py-2 text-xs font-medium text-white transition hover:bg-emerald-800" onclick={acceptProposal}>
						<Check size={14} strokeWidth={1.9} />
						Apply change
					</button>
					<button type="button" class="inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-fg-3 transition hover:bg-slate-50 hover:text-fg-1" onclick={dismissProposal}>
						<X size={14} strokeWidth={1.9} />
						Not now
					</button>
				</div>
			</div>
		{/if}
		<div bind:this={messagesEndRef}></div>
	</div>

	<div class="border-t border-border bg-card p-4">
		<textarea
			bind:this={textareaRef}
			bind:value={draft}
			rows="3"
			class="ui-field max-h-36 min-h-20 w-full resize-none px-3 py-2 text-sm"
			placeholder="Ask about returns, risks, pricing, or payment terms."
			onkeydown={(event) => {
				if (event.key === 'Enter' && !event.shiftKey) {
					event.preventDefault();
					void sendMessage();
				}
			}}
		></textarea>
		<button
			type="button"
			data-variant="primary"
			class="ui-button mt-3 w-full justify-center gap-2 px-4 py-2.5 text-sm disabled:cursor-not-allowed disabled:opacity-60"
			onclick={() => void sendMessage()}
			disabled={feasibilityWorkspace.streaming}
		>
			<SendHorizontal size={15} strokeWidth={1.9} />
			{feasibilityWorkspace.streaming ? 'Streaming…' : 'Send'}
		</button>
	</div>
</div>
