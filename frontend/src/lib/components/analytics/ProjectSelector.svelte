<script lang="ts">
import { createQuery } from '@tanstack/svelte-query'
import { browser } from '$app/environment'
import type { ProjectSearchItem } from '$lib/api/analytics'
import { analyticsQueries } from '$lib/queries/analytics'

let {
	value = $bindable<ProjectSearchItem | null>(null),
	placeholder = 'Search project...',
	onSelect
}: {
	value?: ProjectSearchItem | null
	placeholder?: string
	onSelect?: (project: ProjectSearchItem | null) => void
} = $props()

let inputValue = $state(value?.name ?? '')
let isOpen = $state(false)
const searchTerm = $derived(inputValue.trim())

function clickOutside(node: HTMLElement, callback: () => void) {
	function handle(e: MouseEvent) {
		if (!node.contains(e.target as Node)) callback()
	}
	document.addEventListener('mousedown', handle, true)
	return {
		destroy() {
			document.removeEventListener('mousedown', handle, true)
		}
	}
}

const projectsQuery = createQuery(() => ({
	...analyticsQueries.projectSearch(searchTerm, 50),
	enabled: browser && isOpen
}))

const filtered = $derived(projectsQuery.data?.projects ?? [])

function select(project: ProjectSearchItem) {
	value = project
	inputValue = project.name
	isOpen = false
	onSelect?.(project)
}

function clear() {
	value = null
	inputValue = ''
	isOpen = false
	onSelect?.(null)
}

function handleKeydown(e: KeyboardEvent) {
	if (e.key === 'Escape') {
		isOpen = false
	}
	if (e.key === 'Enter') {
		e.preventDefault()
		if (filtered.length > 0) select(filtered[0])
	}
}
</script>

<div class="relative" use:clickOutside={() => (isOpen = false)}>
	<div class="relative">
		<div class="pointer-events-none absolute inset-y-0 left-3 flex items-center">
			<svg class="h-4 w-4 text-fg-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
			</svg>
		</div>
		<input
			type="text"
			class="w-full rounded-md border border-border bg-white py-2 pl-9 pr-8 text-sm text-fg-1 placeholder-fg-5 transition-all focus:border-navy focus:outline-none focus:ring-2 focus:ring-focus"
			{placeholder}
			bind:value={inputValue}
			oninput={() => (isOpen = true)}
			onfocus={() => (isOpen = true)}
			onkeydown={handleKeydown}
		/>
		{#if value}
			<button
				type="button"
				class="absolute inset-y-0 right-2 flex items-center px-1 text-fg-5 hover:text-fg-2"
				onclick={clear}
				aria-label="Clear selection"
			>
				<svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
					<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
				</svg>
			</button>
		{/if}
	</div>

	{#if isOpen}
		<div class="absolute z-50 mt-2 max-h-72 w-full overflow-y-auto rounded-lg border border-border bg-white p-1.5 shadow-lg">
			{#if projectsQuery.isLoading}
				<div class="px-3 py-2 text-sm text-fg-5">Loading...</div>
			{:else if projectsQuery.isError}
				<div class="px-3 py-2 text-sm text-error">Failed to load projects</div>
			{:else if filtered.length === 0}
				<div class="px-3 py-2 text-sm text-fg-5">No projects found</div>
			{:else}
				{#each filtered as project}
					<button
						type="button"
						class="w-full rounded-md px-3 py-2 text-left text-sm transition-colors {project.name ===
						value?.name
							? 'bg-info-bg font-medium text-info'
							: 'text-fg-2 hover:bg-slate-50 hover:text-fg-1'}"
						onmousedown={() => select(project)}
					>
						{project.name}
					</button>
				{/each}
			{/if}
		</div>
	{/if}
</div>
