<script lang="ts">
import { onMount } from 'svelte'
import { goto } from '$app/navigation'

onMount(() => {
	goto('/admin/organizations')
})
</script>

<p class="text-sm text-fg-4">Redirecting to admin panel...</p>
