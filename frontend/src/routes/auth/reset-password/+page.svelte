<script lang="ts">
import { onMount } from 'svelte'

onMount(() => {
	const destination = `/reset${window.location.search}${window.location.hash}`
	window.location.replace(destination)
})
</script>
