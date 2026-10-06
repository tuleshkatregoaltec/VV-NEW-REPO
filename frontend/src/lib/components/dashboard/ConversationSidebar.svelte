<script lang="ts">
import { createQuery, useQueryClient } from '@tanstack/svelte-query'
import {
	AlertCircle,
	Clock3,
	Loader2,
	MessageSquare,
	MoreHorizontal,
	Pencil,
	Plus,
	Search,
	Trash2
} from 'lucide-svelte'
import { onMount } from 'svelte'
import { type ConversationListResponse, type ConversationResponse, chat } from '$lib/api/chat'
import ConfirmModal from '$lib/components/ui/ConfirmModal.svelte'
import { chatKeys, chatQueries } from '$lib/queries/chat'

let {
	selectedId = $bindable(null),
	onSelect = (_id: number) => {}
}: {
	selectedId: number | null
	onSelect?: (id: number) => void
} = $props()

const queryClient = useQueryClient()
const conversationsQuery = createQuery(() => chatQueries.conversations())

let creating = $state(false)
let error = $state<string | null>(null)
let openMenuId = $state<number | null>(null)
let renamingId = $state<number | null>(null)
let renameValue = $state('')
let searchValue = $state('')
let deleteConfirmOpen = $state(false)
let conversationToDelete = $state<number | null>(null)
let conversations = $derived(conversationsQuery.data?.conversations ?? [])
let loading = $derived(conversationsQuery.isLoading)
let displayError = $derived(
	error ?? (conversationsQuery.isError ? 'Failed to load conversations' : null)
)
let filteredConversations = $derived.by(() => {
	const query = searchValue.trim().toLowerCase()
	if (!query) return conversations
	return conversations.filter((conv) => displayTitle(conv.title).toLowerCase().includes(query))
})
let conversationCount = $derived(conversations.length)

function updateConversationCache(
	updater: (conversations: ConversationResponse[]) => ConversationResponse[]
) {
	queryClient.setQueryData<ConversationListResponse>(chatKeys.conversations(), (current) => {
		const nextConversations = updater(current?.conversations ?? [])
		return {
			conversations: nextConversations,
			total: nextConversations.length
		}
	})
}

function displayTitle(title?: string | null): string {
	if (!title || title === 'New Conversation') return 'New conversation'
	return title
}

onMount(() => {
	// Close menu when clicking outside
	const handleClickOutside = () => {
		if (openMenuId !== null) {
			openMenuId = null
		}
	}
	document.addEventListener('click', handleClickOutside)

	return () => {
		document.removeEventListener('click', handleClickOutside)
	}
})

async function retryLoadConversations() {
	error = null
	await conversationsQuery.refetch()
}

$effect(() => {
	const firstConversation = conversations[0]
	if (!selectedId && firstConversation) {
		selectedId = firstConversation.id
		onSelect(firstConversation.id)
	}
	if (firstConversation) {
		void queryClient.prefetchQuery(chatQueries.messages(firstConversation.id))
	}
})

$effect(() => {
	if (conversationsQuery.isSuccess) error = null
})

async function createNew() {
	creating = true
	error = null
	try {
		const newConv = await chat.createConversation({})
		updateConversationCache((current) => [newConv, ...current.filter((c) => c.id !== newConv.id)])
		queryClient.setQueryData(chatKeys.messages(newConv.id), [])
		selectedId = newConv.id
		onSelect(newConv.id)
		searchValue = ''
	} catch (err) {
		console.error('Failed to create conversation:', err)
		error = 'Failed to create conversation'
	} finally {
		creating = false
	}
}

function startRename(conv: ConversationResponse) {
	renamingId = conv.id
	renameValue = displayTitle(conv.title)
	openMenuId = null
}

async function saveRename(conv: ConversationResponse) {
	const trimmed = renameValue.trim()
	if (!trimmed || trimmed === displayTitle(conv.title)) {
		renamingId = null
		renameValue = ''
		return
	}

	try {
		const updated = await chat.updateConversation(conv.id, trimmed)
		updateConversationCache((current) => current.map((c) => (c.id === conv.id ? updated : c)))
		renamingId = null
		renameValue = ''
	} catch (err) {
		console.error('Failed to rename conversation:', err)
		error = 'Failed to rename conversation'
	}
}

function cancelRename() {
	renamingId = null
	renameValue = ''
}

function focusRenameInput(node: HTMLInputElement) {
	queueMicrotask(() => {
		node.focus()
		node.select()
	})
}

function showDeleteConfirm(convId: number) {
	conversationToDelete = convId
	deleteConfirmOpen = true
	openMenuId = null
}

async function confirmDelete() {
	if (conversationToDelete === null) return

	try {
		await chat.deleteConversation(conversationToDelete)
		const deletedId = conversationToDelete
		const remainingConversations = conversations.filter((c) => c.id !== deletedId)
		updateConversationCache(() => remainingConversations)
		queryClient.removeQueries({ queryKey: chatKeys.messages(deletedId) })

		// If deleted conversation was selected, select the first available one
		if (selectedId === deletedId) {
			if (remainingConversations.length > 0) {
				selectedId = remainingConversations[0].id
				onSelect(selectedId)
			} else {
				selectedId = null
			}
		}

		deleteConfirmOpen = false
		conversationToDelete = null
	} catch (err) {
		console.error('Failed to delete conversation:', err)
		error = 'Failed to delete conversation'
	}
}

function cancelDelete() {
	deleteConfirmOpen = false
	conversationToDelete = null
}

function toggleMenu(convId: number, event: MouseEvent) {
	event.stopPropagation()
	openMenuId = openMenuId === convId ? null : convId
}

function formatDate(dateString: string): string {
	const date = new Date(dateString)
	const now = new Date()
	const diff = now.getTime() - date.getTime()
	const days = Math.floor(diff / (1000 * 60 * 60 * 24))

	if (days === 0) return 'Today'
	if (days === 1) return 'Yesterday'
	if (days < 7) return `${days} days ago`
	return date.toLocaleDateString()
}
</script>

<div class="flex h-full min-h-0 flex-col bg-panel">
	<div class="h-1 shrink-0 bg-navy"></div>
	<div class="border-b border-border bg-card p-2.5">
		<div class="flex items-center justify-between gap-2">
			<div class="min-w-0">
				<div class="flex min-w-0 items-center gap-2">
					<p
						class="truncate font-mono text-[10px] font-semibold uppercase tracking-[0.14em] text-fg-4"
					>
						History
					</p>
					{#if conversationCount > 0}
						<span
							class="rounded-full border border-border bg-panel px-1.5 py-0.5 font-mono text-[10px] font-semibold leading-none text-fg-3"
						>
							{conversationCount}
						</span>
					{/if}
				</div>
				<p class="mt-0.5 truncate text-sm font-semibold text-fg-1">Conversations</p>
			</div>
			<button
				type="button"
				onclick={() => void createNew()}
				disabled={creating}
				class="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-navy text-bone transition-colors hover:bg-primary-light disabled:cursor-wait disabled:opacity-70"
				aria-label="New chat"
				title="New chat"
			>
				{#if creating}
					<Loader2 size={16} strokeWidth={2} class="animate-spin" />
				{:else}
					<Plus size={17} strokeWidth={2} />
				{/if}
			</button>
		</div>

		<div class="relative mt-2.5">
			<Search
				size={15}
				strokeWidth={1.8}
				class="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-fg-5"
			/>
			<input
				type="search"
				bind:value={searchValue}
				placeholder="Search history"
				class="h-8 w-full rounded-md border border-border bg-elevated py-1.5 pl-9 pr-3 text-[13px] text-fg-1 outline-none transition placeholder:text-fg-5 focus:border-navy focus:ring-2 focus:ring-navy/10"
			/>
		</div>
	</div>

	<div class="min-h-0 flex-1 overflow-y-auto p-1.5">
		{#if loading}
			<div class="p-6 text-center">
				<Loader2
					size={28}
					strokeWidth={1.8}
					class="mx-auto mb-3 animate-spin text-fg-4"
				/>
				<p class="text-sm font-medium text-fg-3">Loading...</p>
			</div>
			{:else if displayError}
				<div class="p-6 text-center">
					<div
						class="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-lg bg-error-bg"
					>
						<AlertCircle size={21} strokeWidth={1.8} class="text-error" />
					</div>
					<p class="mb-3 text-sm text-error">{displayError}</p>
					<button
						type="button"
						onclick={() => void retryLoadConversations()}
						class="rounded-md bg-error px-3 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90"
					>
						Try again
					</button>
				</div>
		{:else if conversations.length === 0}
			<div class="p-6 text-center">
				<div
					class="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-lg border border-border bg-card"
				>
					<MessageSquare size={22} strokeWidth={1.8} class="text-fg-3" />
				</div>
				<p class="mb-1 text-sm font-semibold text-fg-1">No conversations yet</p>
				<p class="text-xs text-fg-4">Start a new chat to begin.</p>
			</div>
		{:else if filteredConversations.length === 0}
			<div class="px-4 py-8 text-center">
				<p class="text-sm font-semibold text-fg-1">No matching conversations</p>
				<p class="mt-1 text-xs text-fg-4">Try a different search.</p>
			</div>
		{:else}
			{#each filteredConversations as conv (conv.id)}
				<div
					class="group relative mb-1 w-full rounded-md border transition-colors {openMenuId === conv.id
						? 'z-30 overflow-visible'
						: 'overflow-hidden'} {selectedId === conv.id
						? 'border-strong bg-card shadow-xs'
						: 'border-transparent hover:border-border hover:bg-card'}"
				>
					{#if selectedId === conv.id}
						<span class="absolute bottom-2 left-0 top-2 w-0.5 rounded-r-full bg-navy"></span>
					{/if}
					{#if renamingId === conv.id}
						<div class="p-2">
							<input
								type="text"
								bind:value={renameValue}
								use:focusRenameInput
								onblur={() => void saveRename(conv)}
								onkeydown={(e) => {
									if (e.key === 'Enter') e.currentTarget.blur();
									if (e.key === 'Escape') cancelRename();
								}}
								class="h-9 w-full rounded-md border border-navy bg-elevated px-3 text-sm font-semibold text-fg-1 outline-none ring-2 ring-navy/10"
							/>
						</div>
					{:else}
						<button
							type="button"
							onclick={() => {
								selectedId = conv.id;
								onSelect(conv.id);
							}}
							ondblclick={() => startRename(conv)}
							class="flex w-full items-start gap-2 px-2.5 py-2 pr-9 text-left transition-colors"
							aria-label={`Select ${displayTitle(conv.title)}. Double-click to rename.`}
						>
							<span
								class="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded bg-panel text-fg-3"
							>
								<MessageSquare size={13} strokeWidth={1.8} />
							</span>
							<div class="min-w-0 flex-1">
								<div class="truncate text-[13px] font-semibold leading-5 text-fg-1">
									{displayTitle(conv.title)}
								</div>
								<div class="mt-0.5 flex items-center gap-1.5 text-[11px] text-fg-4">
									<Clock3 size={11} strokeWidth={1.8} />
									{formatDate(conv.updated_at)}
								</div>
							</div>
						</button>

						<button
							type="button"
							onclick={(e) => toggleMenu(conv.id, e)}
							class="absolute right-1.5 top-1.5 rounded-md p-1.5 text-fg-4 transition-colors hover:bg-elevated hover:text-fg-2 {selectedId ===
									conv.id
									? 'opacity-100'
									: 'opacity-100 lg:opacity-0 lg:group-hover:opacity-100'}"
							aria-label="Conversation options"
							aria-haspopup="menu"
							aria-expanded={openMenuId === conv.id}
						>
							<MoreHorizontal size={16} strokeWidth={2} />
						</button>

						{#if openMenuId === conv.id}
							<div
								class="absolute right-1.5 top-9 z-50 min-w-[152px] overflow-hidden rounded-lg border border-border bg-elevated shadow-md"
								role="menu"
							>
								<button
									type="button"
									onclick={() => startRename(conv)}
									class="flex w-full items-center gap-2 px-4 py-2.5 text-left text-sm text-fg-2 transition-colors hover:bg-panel"
									role="menuitem"
								>
									<Pencil size={15} strokeWidth={1.8} />
									<span class="font-medium">Rename</span>
								</button>
								<div class="h-px bg-border"></div>
								<button
									type="button"
									onclick={() => showDeleteConfirm(conv.id)}
									class="flex w-full items-center gap-2 px-4 py-2.5 text-left text-sm text-error transition-colors hover:bg-error-bg"
									role="menuitem"
								>
									<Trash2 size={15} strokeWidth={1.8} />
									<span class="font-medium">Delete</span>
								</button>
							</div>
						{/if}
					{/if}
				</div>
			{/each}
		{/if}
	</div>
</div>

<ConfirmModal
	open={deleteConfirmOpen}
	title="Delete conversation"
	message="Are you sure you want to delete this conversation? This action cannot be undone."
	confirmText="Delete"
	cancelText="Cancel"
	confirmVariant="danger"
	onConfirm={confirmDelete}
	onCancel={cancelDelete}
/>
