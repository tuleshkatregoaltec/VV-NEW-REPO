<script lang="ts">
import type { Snippet } from 'svelte'
import { page } from '$app/state'
import AppFrame from '$lib/components/layout/AppFrame.svelte'
import PageContainer from '$lib/components/layout/PageContainer.svelte'

let { children }: { children: Snippet } = $props()

const navItems = [{ href: '/admin/organizations', label: 'Organizations' }]
</script>

<AppFrame stableScrollGutter>
	<PageContainer variant="standard" class="gap-5">
		<div>
			<div class="mb-2 flex items-center gap-2">
				<span class="text-xs font-semibold uppercase tracking-[0.18em] text-fg-4">Admin</span>
			</div>
			<nav class="flex gap-1 border-b border-border">
				{#each navItems as item (item.href)}
					<a
						href={item.href}
						class="rounded-t-md px-4 py-2 text-sm font-medium transition-colors
                        {page.url.pathname.startsWith(item.href)
							? 'border-b-2 border-navy text-navy'
							: 'text-fg-4 hover:text-fg-1'}"
					>
						{item.label}
					</a>
				{/each}
			</nav>
		</div>
		{@render children()}
	</PageContainer>
</AppFrame>
