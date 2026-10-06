<script lang="ts">
import { onMount } from 'svelte'
import { goto } from '$app/navigation'
import { resolve } from '$app/paths'

onMount(() => {
	const url = new URL(window.location.href)
	const destination = new URL(resolve('/setup/complete'), window.location.origin)
	url.searchParams.forEach((value, key) => {
		destination.searchParams.set(key, value)
	})

	// eslint-disable-next-line svelte/no-navigation-without-resolve
	goto(`${destination.pathname}${destination.search}`, { replaceState: true })
})
</script>
