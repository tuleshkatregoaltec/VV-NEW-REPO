<script lang="ts">
import type { Snippet } from 'svelte'
import AppFrame from '$lib/components/layout/AppFrame.svelte'

let { children }: { children: Snippet } = $props()
</script>

<AppFrame stableScrollGutter>
	{@render children()}
</AppFrame>
