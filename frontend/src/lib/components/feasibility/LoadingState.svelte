<script lang="ts">
import { onMount } from 'svelte'

import { feasibilityWorkspace, loadingSteps } from '$lib/stores/feasibilityWorkspace.svelte'

onMount(() => {
	feasibilityWorkspace.resetLoading()
	const timer = setInterval(() => feasibilityWorkspace.advanceLoadingStep(), 1100)
	return () => clearInterval(timer)
})
</script>

<div class="flex h-full min-h-0 items-center justify-center overflow-hidden bg-app px-6 py-6">
	<div class="w-full max-w-2xl overflow-hidden rounded-lg border border-border bg-card shadow-sm">
		<div class="bg-navy px-6 py-5 text-bone">
			<p class="text-xs font-semibold uppercase tracking-[0.18em] text-on-navy-muted">Generating study</p>
			<h2 class="mt-2 font-display text-3xl leading-tight tracking-[var(--tracking-display)] text-bone">
				Building the seeded workbook
			</h2>
		</div>
		<div class="p-6">
			<p class="mt-3 text-sm text-fg-3">
				The backend is researching evidence, setting assumptions, and returning a ready-to-edit first-pass
				study.
			</p>

			<div class="mt-8 space-y-3">
				{#each loadingSteps as step, index}
					<div
						class="flex items-center gap-3 rounded-lg border px-4 py-3 {index <=
						feasibilityWorkspace.loadingStepIndex
							? 'border-border bg-info-bg text-info'
							: 'border-border bg-panel text-fg-4'}"
					>
						<div
							class="h-2.5 w-2.5 rounded-full {index <= feasibilityWorkspace.loadingStepIndex
								? 'bg-info'
								: 'bg-panel'}"
						></div>
						<span class="text-sm font-medium">{step}</span>
					</div>
				{/each}
			</div>
		</div>
	</div>
</div>
