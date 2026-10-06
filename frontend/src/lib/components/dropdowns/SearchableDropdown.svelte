<script lang="ts">
import { onDestroy } from 'svelte'
import BaseDropdown from './BaseDropdown.svelte'

type DropdownVariant = 'field' | 'inverse' | 'icon'

let {
	id,
	ariaLabel,
	options,
	value = $bindable('All'),
	onchange,
	variant = 'field'
}: {
	id: string
	ariaLabel: string
	options: string[]
	value?: string
	onchange?: (newValue: string) => void
	variant?: DropdownVariant
} = $props()

let searchQuery = $state('')
let visibleCount = $state(50) // Start with 50 items
let loadingHandle: number | null = null

function scheduleIdle(callback: () => void): number {
	if (typeof requestIdleCallback === 'function') {
		return requestIdleCallback(callback)
	}
	return window.setTimeout(callback, 1)
}

function cancelIdle(handle: number) {
	if (typeof cancelIdleCallback === 'function') {
		cancelIdleCallback(handle)
		return
	}
	window.clearTimeout(handle)
}

// Cleanup on component destroy to prevent memory leaks
onDestroy(() => {
	if (loadingHandle) {
		cancelIdle(loadingHandle)
		loadingHandle = null
	}
})

function onOpen() {
	visibleCount = 50

	if (loadingHandle) {
		cancelIdle(loadingHandle)
	}

	const loadMore = () => {
		if (visibleCount < options.length) {
			visibleCount = Math.min(visibleCount + 100, options.length)

			if (visibleCount < options.length) {
				loadingHandle = scheduleIdle(loadMore)
			}
		}
	}

	loadingHandle = scheduleIdle(loadMore)
}

function onClose() {
	if (loadingHandle) {
		cancelIdle(loadingHandle)
		loadingHandle = null
	}
	searchQuery = ''
	visibleCount = 50
}

function select(option: string, close: () => void) {
	value = option
	onchange?.(option)
	close()
}

let resolvedOptions = $derived.by(() => {
	const ordered =
		value && value !== 'All' && !options.includes(value) ? ['All', value, ...options] : options
	return Array.from(new Set(ordered))
})

let filteredOptions = $derived(
	resolvedOptions.filter((option) => option.toLowerCase().includes(searchQuery.toLowerCase()))
)

let displayedOptions = $derived(filteredOptions.slice(0, visibleCount))

function optionClass(option: string) {
	return option === value
		? 'bg-info-bg font-semibold text-info'
		: 'text-fg-2 hover:bg-elevated hover:text-fg-1'
}
</script>

<BaseDropdown {id} {ariaLabel} displayValue={value} {variant} focusOnOpen {onOpen} {onClose}>
	{#snippet children({ close })}
		<div class="p-2">
			<input
				type="text"
				data-dropdown-initial-focus="true"
				class="ui-field mb-2 h-9 w-full px-3 text-sm placeholder-fg-5"
				placeholder="Search..."
				bind:value={searchQuery}
				aria-label={`Search options for ${ariaLabel}`}
			/>
			<ul class="max-h-80 overflow-y-auto">
				{#each displayedOptions as option (option)}
					<li>
						<button
							type="button"
							class="flex w-full items-center justify-between rounded-md px-3 py-2 text-left text-sm transition-colors focus:outline-none focus:ring-2 focus:ring-focus {optionClass(
								option
							)}"
							onclick={() => select(option, close)}
						>
							<span>{option}</span>
							{#if option === value}
								<span class="h-1.5 w-1.5 rounded-full bg-info"></span>
							{/if}
						</button>
					</li>
				{/each}
				{#if filteredOptions.length === 0}
					<li class="px-3 py-2 text-sm text-fg-5">No results found</li>
				{/if}
			</ul>
		</div>
	{/snippet}
</BaseDropdown>
