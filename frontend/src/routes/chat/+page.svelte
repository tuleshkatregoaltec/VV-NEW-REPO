<script lang="ts">
import { PanelLeft, X } from 'lucide-svelte'
import { get } from 'svelte/store'
import { page } from '$app/stores'
import ChatBox from '$lib/components/dashboard/ChatBox.svelte'
import ConversationSidebar from '$lib/components/dashboard/ConversationSidebar.svelte'
import AppFrame from '$lib/components/layout/AppFrame.svelte'
import PageContainer from '$lib/components/layout/PageContainer.svelte'

type ChatNavigationState = {
	conversationId?: number
	initialMessage?: string
}

const initialState = get(page).state as ChatNavigationState

let selectedConversationId = $state<number | null>(initialState?.conversationId ?? null)
let initialMessage = $state<string | null>(initialState?.initialMessage ?? null)
let autoSendPending = $state(Boolean(initialState?.conversationId && initialState?.initialMessage))
let mobileHistoryOpen = $state(false)

function selectConversation(id: number) {
	selectedConversationId = id
	mobileHistoryOpen = false
}

function closeMobileHistory() {
	mobileHistoryOpen = false
}

// Handle navigation state for auto-initialization
$effect(() => {
	const state = $page.state as ChatNavigationState

	if (state?.conversationId && state?.initialMessage) {
		selectedConversationId = state.conversationId
		initialMessage = state.initialMessage
		autoSendPending = true
	}
})
</script>

<svelte:window
	onkeydown={(event) => {
		if (event.key === 'Escape') closeMobileHistory();
	}}
/>

<svelte:head>
	<title>Chat - Vitevue</title>
</svelte:head>

<AppFrame stableScrollGutter>
	<PageContainer variant="wide" class="h-full gap-2 lg:flex-row">
			<aside
				class="hidden w-full shrink-0 overflow-hidden rounded-lg border border-border bg-panel shadow-sm lg:block lg:h-full lg:min-h-0 lg:w-[240px] xl:w-[252px]"
				aria-label="Conversation history"
			>
				<ConversationSidebar
					bind:selectedId={selectedConversationId}
					onSelect={selectConversation}
				/>
			</aside>

			<section class="flex min-h-0 min-w-0 flex-1 flex-col">
				<header
					class="mb-3 flex min-w-0 items-start justify-between gap-3 rounded-lg border border-border bg-card px-3 py-3 shadow-sm sm:px-4"
				>
					<div class="min-w-0">
						<div class="flex items-center gap-2">
							<img src="/icon.svg" alt="" class="h-3.5 w-3.5" />
							<h1 class="text-sm font-semibold text-fg-1">Vitevue AI</h1>
						</div>
						<p class="mt-1 text-xs text-fg-4">
							Ask about transactions, yields, pricing, projects, and feasibility context.
						</p>
					</div>
					<button
						type="button"
						class="ui-button h-9 shrink-0 px-3 text-xs lg:hidden"
						onclick={() => (mobileHistoryOpen = true)}
						aria-label="Open conversation history"
					>
						<PanelLeft size={15} strokeWidth={1.8} />
						History
					</button>
				</header>

				<div
					class="min-h-0 flex-1 overflow-hidden rounded-lg border border-border bg-card shadow-sm"
				>
					<ChatBox
						bind:conversationId={selectedConversationId}
						{initialMessage}
						autoSend={autoSendPending}
						showHeader={false}
						onMessageSent={() => {
							autoSendPending = false;
							initialMessage = null;
						}}
					/>
				</div>
			</section>
	</PageContainer>
</AppFrame>

{#if mobileHistoryOpen}
	<div class="fixed inset-0 z-[80] lg:hidden" role="presentation">
		<button
			type="button"
			class="absolute inset-0 h-full w-full bg-black/35"
			onclick={closeMobileHistory}
			aria-label="Close conversation history"
		></button>
		<button
			type="button"
			class="absolute top-2.5 z-10 grid h-8 w-8 place-items-center rounded-md border border-border bg-card text-fg-3 shadow-sm transition hover:bg-elevated hover:text-fg-1"
			style="left: calc(min(86vw, 340px) + 0.5rem);"
			onclick={closeMobileHistory}
			aria-label="Close conversation history"
		>
			<X size={16} strokeWidth={1.8} />
		</button>
		<div
			class="absolute inset-y-0 left-0 flex w-[min(86vw,340px)] flex-col overflow-hidden bg-panel shadow-xl"
			role="dialog"
			aria-modal="true"
			aria-label="Conversation history"
		>
			<ConversationSidebar
				bind:selectedId={selectedConversationId}
				onSelect={selectConversation}
			/>
		</div>
	</div>
{/if}
