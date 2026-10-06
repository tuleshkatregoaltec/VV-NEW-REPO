<script lang="ts">
interface Props {
	title: string
	description: string
	icon: string
}

let { title, description, icon }: Props = $props()
</script>

<div
	class="group h-full rounded-lg border border-bone-border bg-card-warm p-6 transition-colors duration-200 hover:border-[var(--color-bone-300)]"
>
	<div class="mb-5 inline-block text-5xl transition-transform duration-200 group-hover:scale-105">
		{icon}
	</div>
	<h3 class="mb-3 font-display text-2xl font-normal leading-tight tracking-[-0.02em] text-fg-1">
		{title}
	</h3>
	<p class="text-sm leading-relaxed text-fg-3">{description}</p>

	<div
		class="mt-4 border-t border-bone-border pt-4 opacity-0 transition-opacity duration-200 group-hover:opacity-100"
	>
		<span class="flex items-center gap-1 text-sm font-medium text-primary">
			Learn more
			<svg
				class="w-4 h-4 group-hover:translate-x-1 transition-transform"
				fill="none"
				stroke="currentColor"
				viewBox="0 0 24 24"
			>
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
			</svg>
		</span>
	</div>
</div>
