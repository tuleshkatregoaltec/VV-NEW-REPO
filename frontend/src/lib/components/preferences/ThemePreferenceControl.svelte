<script lang="ts">
import { Monitor, Moon, Sun } from 'lucide-svelte'
import { colorTheme, type ThemePreference } from '$lib/stores/preferences.svelte'

const themeOptions: { value: ThemePreference; label: string }[] = [
	{ value: 'system', label: 'System' },
	{ value: 'light', label: 'Light' },
	{ value: 'dark', label: 'Dark' }
]
</script>

<div class="inline-flex rounded-md bg-panel p-0.5" aria-label="Theme preference">
	{#each themeOptions as option (option.value)}
		<button
			type="button"
			class="inline-flex items-center gap-1.5 rounded px-3 py-1.5 text-sm font-medium transition-colors {colorTheme.current ===
			option.value
				? 'bg-card text-fg-1 shadow-[var(--shadow-xs)]'
				: 'text-fg-3 hover:text-fg-1'}"
			onclick={() => (colorTheme.current = option.value)}
			aria-pressed={colorTheme.current === option.value}
		>
			{#if option.value === 'system'}
				<Monitor size={14} strokeWidth={1.8} />
			{:else if option.value === 'light'}
				<Sun size={14} strokeWidth={1.8} />
			{:else}
				<Moon size={14} strokeWidth={1.8} />
			{/if}
			<span>{option.label}</span>
		</button>
	{/each}
</div>
