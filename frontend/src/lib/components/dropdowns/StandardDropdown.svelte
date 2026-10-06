<script lang="ts">
import type { Snippet } from 'svelte'
import BaseDropdown from './BaseDropdown.svelte'

type DropdownVariant = 'field' | 'inverse' | 'icon'

let {
	id,
	ariaLabel,
	options,
	value = $bindable('All'),
	onchange,
	variant = 'field',
	button,
	buttonClass
}: {
	id: string
	ariaLabel: string
	options: string[]
	value?: string
	onchange?: (newValue: string) => void
	variant?: DropdownVariant
	button?: Snippet<[{ isOpen: boolean }]>
	buttonClass?: string
} = $props()

function select(option: string, close: () => void) {
	value = option
	onchange?.(option)
	close()
}

function optionClass(option: string) {
	return option === value
		? 'bg-info-bg font-semibold text-info'
		: 'text-fg-2 hover:bg-elevated hover:text-fg-1'
}

let resolvedOptions = $derived.by(() => {
	const ordered =
		value && value !== 'All' && !options.includes(value) ? ['All', value, ...options] : options
	return Array.from(new Set(ordered))
})
</script>

<BaseDropdown {id} {ariaLabel} displayValue={value} {variant} {button} {buttonClass}>
	{#snippet children({ close })}
		<ul class="max-h-64 overflow-y-auto p-1.5">
			{#each resolvedOptions as option (option)}
				<li>
					<button
						type="button"
						data-dropdown-initial-focus={option === value ? 'true' : undefined}
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
		</ul>
	{/snippet}
</BaseDropdown>
