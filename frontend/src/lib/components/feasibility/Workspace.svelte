<script lang="ts">
import { ChevronLeft, MessageSquare, PanelLeftOpen, X } from 'lucide-svelte'
import { onMount } from 'svelte'
import { goto } from '$app/navigation'
import { workbookStore } from '$lib/feasibility/workbook/store.svelte'
import { feasibilityStudy } from '$lib/stores/feasibilityStudy.svelte'

import ChatPanel from './ChatPanel.svelte'
import StudyContextPanel from './StudyContextPanel.svelte'
import WorkbookPanel from './WorkbookPanel.svelte'

let contextCollapsed = $state(true)
let chatCollapsed = $state(false)
let drawer = $state<'context' | 'chat' | null>(null)
let isWide = $state(false)
let renameValue = $state('')

const studyTitle = $derived(
	feasibilityStudy.savedStudyName ||
		(feasibilityStudy.study?.study_context?.headline ??
			feasibilityStudy.study?.plot_data?.project_name ??
			'Feasibility Study')
)

$effect(() => {
	renameValue = studyTitle
})

onMount(() => {
	const query = window.matchMedia('(min-width: 1280px)')
	const sync = () => {
		isWide = query.matches
		if (isWide) drawer = null
	}
	sync()
	query.addEventListener('change', sync)
	return () => query.removeEventListener('change', sync)
})

function resetStudy() {
	void goto('/feasibility')
}

function renameStudy() {
	void feasibilityStudy.renameSavedStudy(renameValue)
}

function isWorkbookField(target: EventTarget | null) {
	return (
		target instanceof HTMLInputElement ||
		target instanceof HTMLTextAreaElement ||
		target instanceof HTMLSelectElement
	)
}

function markWorkbookDirty(event: Event) {
	if (!isWorkbookField(event.target)) return
	feasibilityStudy.markUnsaved()
}

function saveWorkbookOnBlur(event: FocusEvent) {
	if (!isWorkbookField(event.target)) return
	void feasibilityStudy.saveCurrentWorkbook(workbookStore.assumptions)
}

function toggleContext() {
	if (isWide) {
		contextCollapsed = !contextCollapsed
		return
	}
	drawer = drawer === 'context' ? null : 'context'
}

function toggleChat() {
	if (isWide) {
		chatCollapsed = !chatCollapsed
		return
	}
	drawer = drawer === 'chat' ? null : 'chat'
}
</script>

{#if feasibilityStudy.study}
	<div class="flex h-full min-h-0 flex-col overflow-hidden bg-app">
		<div class="flex flex-shrink-0 flex-wrap items-center justify-between gap-3 border-b border-border bg-card px-4 py-3 shadow-xs">
			<div class="flex min-w-0 items-center gap-3">
				<button
					type="button"
					data-variant="secondary"
					class="ui-button h-9 px-2.5 text-sm"
					onclick={resetStudy}
				>
					<ChevronLeft size={16} strokeWidth={1.8} />
					<span class="hidden sm:inline">Plot search</span>
				</button>
				<div class="min-w-0">
					<input
						bind:value={renameValue}
						class="h-7 max-w-[320px] rounded-md border border-transparent bg-transparent px-1 text-sm font-semibold text-fg-1 outline-none hover:border-border focus:border-focus focus:bg-card"
						aria-label="Study name"
						onblur={renameStudy}
						onkeydown={(event) => {
							if (event.key === 'Enter') {
								event.currentTarget.blur()
							}
						}}
					/>
					<p class="px-1 text-xs text-fg-4">Workbook</p>
				</div>
			</div>
			<div class="flex items-center gap-2">
				<span class="ui-badge px-2.5 py-1 text-xs font-medium">
					{feasibilityStudy.saveState === 'failed' ? 'Save failed' : feasibilityStudy.saveState === 'saving' ? 'Saving' : feasibilityStudy.saveState === 'unsaved' ? 'Unsaved' : 'Saved'}
				</span>
				<button
					type="button"
					data-variant={(isWide ? !contextCollapsed : drawer === 'context') ? 'primary' : 'secondary'}
					class="ui-button h-9 px-3 text-sm"
					onclick={toggleContext}
					aria-pressed={isWide ? !contextCollapsed : drawer === 'context'}
				>
					<PanelLeftOpen size={16} strokeWidth={1.8} />
					<span>Context</span>
				</button>
				<button
					type="button"
					data-variant={(isWide ? !chatCollapsed : drawer === 'chat') ? 'primary' : 'secondary'}
					class="ui-button h-9 px-3 text-sm"
					onclick={toggleChat}
					aria-pressed={isWide ? !chatCollapsed : drawer === 'chat'}
				>
					<MessageSquare size={16} strokeWidth={1.8} />
					<span>Chat</span>
				</button>
			</div>
		</div>

		<div class="flex min-h-0 flex-1 gap-3 overflow-hidden px-4 py-4">
			{#if !contextCollapsed}
				<div class="hidden min-h-0 w-[300px] min-w-[240px] max-w-[420px] resize-x overflow-auto xl:block">
					<StudyContextPanel />
				</div>
			{/if}
			<div
				class="min-w-0 flex-1 overflow-hidden"
				oninput={markWorkbookDirty}
				onchange={markWorkbookDirty}
				onfocusout={saveWorkbookOnBlur}
			>
				<WorkbookPanel />
			</div>
			{#if !chatCollapsed}
				<div class="hidden min-h-0 w-[340px] min-w-[280px] max-w-[460px] resize-x overflow-hidden xl:block">
					<ChatPanel />
				</div>
			{/if}
		</div>

		{#if drawer}
			<div class="fixed inset-0 z-40 bg-black/25 xl:hidden" role="presentation" onclick={() => (drawer = null)}></div>
			<div class="fixed inset-y-0 right-0 z-50 flex w-full max-w-[420px] flex-col bg-card shadow-lg xl:hidden">
				<div class="flex h-14 flex-shrink-0 items-center justify-between border-b border-border px-4">
					<p class="text-sm font-semibold text-fg-1">{drawer === 'context' ? 'Context' : 'Chat'}</p>
					<button
						type="button"
						data-variant="secondary"
						data-size="icon"
						class="ui-button h-8 w-8"
						onclick={() => (drawer = null)}
						aria-label="Close panel"
					>
						<X size={16} strokeWidth={1.8} />
					</button>
				</div>
				<div class="min-h-0 flex-1 overflow-auto p-4">
					{#if drawer === 'context'}
						<StudyContextPanel />
					{:else}
						<ChatPanel />
					{/if}
				</div>
			</div>
		{/if}
	</div>
{/if}
