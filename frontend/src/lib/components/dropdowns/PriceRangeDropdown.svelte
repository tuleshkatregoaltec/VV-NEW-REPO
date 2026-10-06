<script lang="ts">
import BaseDropdown from './BaseDropdown.svelte'

let {
	id,
	ariaLabel,
	value = $bindable({ min: '', max: '' }),
	placeholderMin = 'Min',
	placeholderMax = 'Max',
	onchange
}: {
	id: string
	ariaLabel: string
	value?: { min: string; max: string }
	placeholderMin?: string
	placeholderMax?: string
	onchange?: (newValue: { min: string; max: string }) => void
} = $props()

// Local state for inputs
let localMin = $state(value.min)
let localMax = $state(value.max)

// Sync local state with external changes
$effect(() => {
	localMin = value.min
	localMax = value.max
})

function handleInput() {
	value = { min: localMin, max: localMax }
	onchange?.(value)
}

let displayValue = $derived(
	value.min || value.max ? `${value.min || 'Any'} - ${value.max || 'Any'}` : ''
)
</script>

<BaseDropdown {id} {ariaLabel} {displayValue}>
	{#snippet children({ close })}
		<div class="p-3">
			<div class="flex gap-2">
				<input
					type="number"
					class="ui-field w-1/2 px-3 py-2 text-sm placeholder-fg-5"
					placeholder={placeholderMin}
					bind:value={localMin}
					oninput={handleInput}
					aria-label={`Minimum ${ariaLabel}`}
				/>
				<input
					type="number"
					class="ui-field w-1/2 px-3 py-2 text-sm placeholder-fg-5"
					placeholder={placeholderMax}
					bind:value={localMax}
					oninput={handleInput}
					aria-label={`Maximum ${ariaLabel}`}
				/>
			</div>
		</div>
	{/snippet}
</BaseDropdown>
