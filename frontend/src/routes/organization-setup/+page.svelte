<script lang="ts">
import { onMount } from 'svelte'
import { goto } from '$app/navigation'
import { resolve } from '$app/paths'

onMount(() => {
	const url = new URL(window.location.href)
	const destination = new URL(resolve('/setup'), window.location.origin)
	const tier = url.searchParams.get('tier')
	if (tier) {
		destination.searchParams.set('tier', tier)
	}

	// eslint-disable-next-line svelte/no-navigation-without-resolve
	goto(`${destination.pathname}${destination.search}`, { replaceState: true })
})
</script>
