<script lang="ts">
import { Settings2 } from 'lucide-svelte'
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
	if (selected[optionId] && selectedCount <= 1) return
	const newSelected = { ...selected, [optionId]: !selected[optionId] }
	selected = newSelected
	onchange?.(newSelected)
}

function showAll() {
	const newSelected: Record<string, boolean> = {}
	for (const opt of options) {
		newSelected[opt.id] = true
	}
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
>
	{#snippet button()}
		<Settings2 size={16} strokeWidth={1.8} aria-hidden="true" />
		<span class="text-sm font-medium">Columns</span>
	{/snippet}

	{#snippet children({ close })}
		<div
			class="min-w-[220px]"
			role="listbox"
			aria-multiselectable="true"
			tabindex="-1"
			data-dropdown-initial-focus="true"
		>
			<div class="flex items-center justify-between border-b border-border px-3 py-2">
				<span class="font-mono text-[10px] font-medium uppercase tracking-[0.08em] text-fg-4">Show Columns</span>
				<button
					type="button"
					onclick={showAll}
					class="cursor-pointer text-xs font-medium text-info transition-colors hover:text-fg-1"
				>
					Show all
				</button>
			</div>

			<div class="max-h-[300px] overflow-y-auto p-1.5">
				{#each options as option (option.id)}
					<label
						class="group flex cursor-pointer items-center gap-3 rounded-md px-3 py-2 transition-colors hover:bg-elevated has-[:disabled]:cursor-not-allowed has-[:disabled]:opacity-60"
					>
						<div class="relative flex items-center">
							<input
								type="checkbox"
								id="{id}-{option.id}"
								checked={selected[option.id] || false}
								disabled={selected[option.id] && selectedCount <= 1}
								onchange={() => toggleOption(option.id)}
								class="h-4 w-4 cursor-pointer rounded-sm border-strong accent-navy text-navy focus:ring-2 focus:ring-focus disabled:cursor-not-allowed"
								aria-checked={selected[option.id] ? 'true' : 'false'}
								aria-labelledby="{id}-{option.id}-label"
							/>
						</div>
						<span
							id="{id}-{option.id}-label"
							class="select-none text-sm group-hover:text-fg-1 {selected[option.id]
								? 'text-fg-1'
								: 'text-fg-4'}"
						>
							{option.label}
						</span>
					</label>
				{/each}
			</div>
		</div>
	{/snippet}
</BaseDropdown>
