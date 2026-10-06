<script lang="ts">
import type { Snippet } from 'svelte'

type PageContainerVariant = 'standard' | 'wide' | 'focused' | 'fullBleed'

let {
	children,
	variant = 'standard',
	class: className = ''
}: {
	children: Snippet
	variant?: PageContainerVariant
	class?: string
} = $props()

const variantClasses: Record<PageContainerVariant, string> = {
	standard: 'mx-auto flex w-full max-w-[1360px] flex-col px-4 py-5 lg:px-6',
	wide: 'mx-auto flex w-full max-w-[1440px] flex-col px-3 py-3 lg:px-5 lg:py-5',
	focused: 'mx-auto flex w-full max-w-5xl flex-col px-4 py-5 lg:px-6',
	fullBleed: 'w-full'
}
</script>

<div class="{variantClasses[variant]} {className}">
	{@render children()}
</div>
