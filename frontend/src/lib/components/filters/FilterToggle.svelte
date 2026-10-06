<script lang="ts">
let {
	options = ['Residential', 'Commercial'],
	selected = $bindable('Residential'),
	onchange
}: {
	options?: string[]
	selected?: string
	onchange?: (newValue: string) => void
} = $props()

function toggleOption(option: string) {
	selected = option
	onchange?.(option)
}
</script>

<div
	class="inline-flex items-center gap-2 rounded-lg border border-border bg-card p-1"
	role="group"
	aria-label="Property usage"
>
	{#each options as option (option)}
		<button
			type="button"
			onclick={() => toggleOption(option)}
			aria-pressed={selected === option}
			class="inline-flex min-w-[104px] items-center justify-center rounded-md border px-3 py-1.5 text-xs font-medium transition-all duration-150
				{selected === option
				? 'border-navy bg-navy text-on-navy shadow-xs'
				: 'border-transparent bg-card text-fg-2 hover:border-strong hover:bg-panel hover:text-fg-1'}"
		>
			{option}
		</button>
	{/each}
</div>
