<script lang="ts">
import type { Snippet } from 'svelte'
import { setContext } from 'svelte'
import Navbar from '$lib/components/navigation/Navbar.svelte'

let {
	children,
	stableScrollGutter = false
}: {
	children: Snippet
	stableScrollGutter?: boolean
} = $props()

let openDropdownId = $state<string | null>(null)
setContext('openDropdownId', {
	get value() {
		return openDropdownId
	},
	set value(v: string | null) {
		openDropdownId = v
	}
})
</script>

<div class="theme-app flex h-screen flex-col bg-app text-fg-1">
	<Navbar />

	<main
		class="app-scroll-root min-h-0 flex-1 overflow-auto"
		data-stable-gutter={stableScrollGutter ? 'true' : undefined}
	>
		{@render children()}
	</main>
</div>
