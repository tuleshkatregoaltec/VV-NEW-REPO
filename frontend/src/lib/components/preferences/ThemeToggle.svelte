<script lang="ts">
import { Moon, Sun } from 'lucide-svelte'
import { colorTheme } from '$lib/stores/preferences.svelte'

const nextMode = $derived(colorTheme.resolved === 'dark' ? 'light' : 'dark')
</script>

<button
	type="button"
	data-variant="secondary"
	data-size="icon"
	class="ui-button h-[34px] w-[34px]"
	onclick={() => colorTheme.toggle()}
	aria-label={`Switch to ${nextMode} mode`}
	aria-pressed={colorTheme.resolved === 'dark'}
	title={`Switch to ${nextMode} mode`}
>
	{#if colorTheme.resolved === 'dark'}
		<Sun size={14} strokeWidth={2} />
	{:else}
		<Moon size={14} strokeWidth={2} />
	{/if}
</button>
