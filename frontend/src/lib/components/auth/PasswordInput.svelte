<script lang="ts">
import { zxcvbn, zxcvbnOptions } from '@zxcvbn-ts/core'
import { onMount } from 'svelte'

interface Props {
	label: string
	value: string
	placeholder?: string
	error?: string
	disabled?: boolean
	required?: boolean
	autocomplete?: 'new-password' | 'current-password' | 'off'
	showStrength?: boolean
	id?: string
}

let {
	label,
	value = $bindable(''),
	placeholder = '',
	error = '',
	disabled = false,
	required = false,
	autocomplete = 'new-password',
	showStrength = false,
	id = `password-${Math.random().toString(36).substring(2, 11)}`
}: Props = $props()

let showPassword = $state(false)

const strengthLevels = ['Very Weak', 'Weak', 'Fair', 'Good', 'Strong']
const strengthColors = [
	'bg-error',
	'bg-warning',
	'bg-[var(--color-slate-400)]',
	'bg-info',
	'bg-success'
]

function calculatePasswordStrength(password: string): number {
	if (!password) return 0

	try {
		const result = zxcvbn(password)
		// zxcvbn returns score 0-4, we want 1-5 for display
		return (result.score + 1) as 1 | 2 | 3 | 4 | 5
	} catch {
		return 0
	}
}

let strength = $derived(showStrength ? calculatePasswordStrength(value) : 0)
</script>

<div class="w-full">
	<label for={id} class="mb-2 block text-sm font-medium text-fg-1">
		{label}
		{#if required}
			<span class="text-error">*</span>
		{/if}
	</label>
	<div class="relative">
		<input
			{id}
			type={showPassword ? 'text' : 'password'}
			bind:value
			{placeholder}
			{disabled}
			{required}
			{autocomplete}
			class="w-full rounded-md border bg-card px-3.5 py-3 pr-12 text-sm text-fg-1 placeholder-fg-5 transition-all
                   focus:outline-none focus:border-navy focus:ring-2 focus:ring-focus
                   disabled:cursor-not-allowed disabled:bg-panel
                   {error
				? 'border-[var(--color-error)] bg-error-bg'
				: 'border-border'}"
		/>
		<button
			type="button"
			onclick={() => (showPassword = !showPassword)}
			class="absolute right-3 top-1/2 -translate-y-1/2 text-fg-4 transition-colors hover:text-fg-2"
			tabindex="-1"
		>
			{#if showPassword}
				<svg
					xmlns="http://www.w3.org/2000/svg"
					class="h-5 w-5"
					fill="none"
					viewBox="0 0 24 24"
					stroke="currentColor"
				>
					<path
						stroke-linecap="round"
						stroke-linejoin="round"
						stroke-width="2"
						d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21"
					/>
				</svg>
			{:else}
				<svg
					xmlns="http://www.w3.org/2000/svg"
					class="h-5 w-5"
					fill="none"
					viewBox="0 0 24 24"
					stroke="currentColor"
				>
					<path
						stroke-linecap="round"
						stroke-linejoin="round"
						stroke-width="2"
						d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
					/>
					<path
						stroke-linecap="round"
						stroke-linejoin="round"
						stroke-width="2"
						d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"
					/>
				</svg>
			{/if}
		</button>
	</div>

	{#if showStrength && value}
		<div class="mt-2">
			<div class="flex gap-1 mb-1">
				{#each Array(5) as _, i (`strength-${i}`)}
					<div
						class="h-1 flex-1 rounded-sm transition-all {i < strength
							? strengthColors[strength - 1]
							: 'bg-[var(--color-slate-200)]'}"
					></div>
				{/each}
			</div>
			{#if strength > 0}
				<p class="text-xs text-fg-4">
					Strength: <span class="font-medium">{strengthLevels[strength - 1]}</span>
				</p>
			{/if}
		</div>
	{/if}

	{#if error}
		<p class="mt-2 text-sm text-error">{error}</p>
	{/if}
</div>
