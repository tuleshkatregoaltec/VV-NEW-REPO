<script lang="ts">
interface Props {
	label: string
	type?: string
	value: string
	placeholder?: string
	error?: string
	disabled?: boolean
	required?: boolean
	autocomplete?: 'off' | 'on' | 'email' | 'username' | 'given-name' | 'family-name' | 'name'
	id?: string
}

let {
	label,
	type = 'text',
	value = $bindable(''),
	placeholder = '',
	error = '',
	disabled = false,
	required = false,
	autocomplete = 'off',
	id = `input-${Math.random().toString(36).substring(2, 11)}`
}: Props = $props()
</script>

<div class="w-full">
	<label for={id} class="mb-2 block text-sm font-medium text-fg-1">
		{label}
		{#if required}
			<span class="text-error">*</span>
		{/if}
	</label>
	<input
		{id}
		{type}
		bind:value
		{placeholder}
		{disabled}
		{required}
		{autocomplete}
		class="w-full rounded-md border bg-card px-3.5 py-3 text-sm text-fg-1 placeholder-fg-5 transition-all
               focus:outline-none focus:border-navy focus:ring-2 focus:ring-focus
               disabled:cursor-not-allowed disabled:bg-panel
               {error
			? 'border-[var(--color-error)] bg-error-bg'
			: 'border-border'}"
	/>
	{#if error}
		<p class="mt-2 text-sm text-error">{error}</p>
	{/if}
</div>
