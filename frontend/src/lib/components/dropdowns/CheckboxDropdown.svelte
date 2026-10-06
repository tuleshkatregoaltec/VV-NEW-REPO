<script lang="ts">
import { ListFilter } from 'lucide-svelte'
import BaseDropdown from './BaseDropdown.svelte'

let {
	id,
	ariaLabel,
	options = [],
	selected = $bindable({}),
	onchange
}: {
	id: string
	ariaLabel: string
	options?: Array<{ id: string; label: string }>
	selected?: Record<string, boolean>
	onchange?: (selected: Record<string, boolean>) => void
} = $props()

let selectedCount = $derived(Object.values(selected).filter(Boolean).length)

function toggleOption(optionId: string) {
	const newSelected = { ...selected, [optionId]: !selected[optionId] }
	selected = newSelected
	onchange?.(newSelected)
}
</script>

<BaseDropdown
	{id}
	{ariaLabel}
	displayValue=""
	align="right"
	variant="icon"
	buttonClass="ui-button relative h-10 w-10 cursor-pointer"
>
	{#snippet button()}
		<ListFilter size={16} strokeWidth={1.8} aria-hidden="true" />
		{#if selectedCount > 0}
			<span
				class="absolute -right-1 -top-1 flex h-5 w-5 items-center justify-center rounded-sm bg-navy text-xs font-medium text-on-navy"
			>
				{selectedCount}
			</span>
		{/if}
	{/snippet}

	{#snippet children({ close })}
		<div
			class="min-w-[220px] p-1.5"
			role="listbox"
			aria-multiselectable="true"
			tabindex="-1"
			data-dropdown-initial-focus="true"
		>
			{#each options as option (option.id)}
				<label
					class="group flex cursor-pointer items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors hover:bg-elevated"
				>
					<div class="relative flex items-center">
						<input
							type="checkbox"
							id="{id}-{option.id}"
							checked={selected[option.id] || false}
							onchange={() => toggleOption(option.id)}
							class="h-4 w-4 cursor-pointer rounded-sm border-strong accent-navy text-navy focus:ring-2 focus:ring-focus"
							aria-checked={selected[option.id] ? 'true' : 'false'}
							aria-labelledby="{id}-{option.id}-label"
						/>
					</div>
					<span
						id="{id}-{option.id}-label"
						class="select-none group-hover:text-fg-1 {selected[option.id]
							? 'font-medium text-fg-1'
							: 'text-fg-2'}"
					>
						{option.label}
					</span>
				</label>
			{/each}
		</div>
	{/snippet}
</BaseDropdown>
