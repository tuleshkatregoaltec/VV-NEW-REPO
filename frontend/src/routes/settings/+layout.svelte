<script lang="ts">
import type { Snippet } from 'svelte'
import AppFrame from '$lib/components/layout/AppFrame.svelte'
import PageContainer from '$lib/components/layout/PageContainer.svelte'

let { children }: { children: Snippet } = $props()
</script>

<AppFrame stableScrollGutter>
	<PageContainer variant="focused">
		{@render children()}
	</PageContainer>
</AppFrame>
