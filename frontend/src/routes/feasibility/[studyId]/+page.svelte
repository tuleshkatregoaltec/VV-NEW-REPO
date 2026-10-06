<script lang="ts">
import { createQuery } from '@tanstack/svelte-query'
import { page } from '$app/state'
import LoadingState from '$lib/components/feasibility/LoadingState.svelte'
import Workspace from '$lib/components/feasibility/Workspace.svelte'
import AppFrame from '$lib/components/layout/AppFrame.svelte'
import PageContainer from '$lib/components/layout/PageContainer.svelte'
import { feasibilityQueries } from '$lib/queries/feasibility'
import { feasibilityStudy } from '$lib/stores/feasibilityStudy.svelte'

let hydratedId = $state<number | null>(null)
let showLoading = $state(false)
const routeStudyId = $derived(Number(page.params.studyId))
const normalizedStudyId = $derived(
	Number.isFinite(routeStudyId) && routeStudyId > 0 ? routeStudyId : null
)
const studyQuery = createQuery(() => feasibilityQueries.study(normalizedStudyId))
const isCurrentStudyReady = $derived(
	feasibilityStudy.phase === 'ready' &&
		feasibilityStudy.savedStudyId === routeStudyId &&
		Boolean(feasibilityStudy.study)
)
const loadError = $derived.by(() => {
	if (normalizedStudyId === null) return 'Invalid feasibility study ID.'
	if (studyQuery.isError) {
		return studyQuery.error instanceof Error
			? studyQuery.error.message
			: 'Failed to load feasibility study.'
	}
	if (feasibilityStudy.phase === 'error') {
		return feasibilityStudy.error || 'Failed to load feasibility study.'
	}
	return ''
})

$effect(() => {
	const saved = studyQuery.data
	if (!saved || hydratedId === saved.id) return
	hydratedId = saved.id
	feasibilityStudy.hydrateSavedStudy(saved)
})

$effect(() => {
	if (isCurrentStudyReady || loadError) {
		showLoading = false
		return
	}

	showLoading = false
	const timer = setTimeout(() => {
		showLoading = true
	}, 350)
	return () => clearTimeout(timer)
})
</script>

<AppFrame>
	<PageContainer variant="fullBleed" class="h-full overflow-hidden">
		{#if isCurrentStudyReady}
			<Workspace />
		{:else if loadError}
			<div class="grid h-full place-items-center p-6">
				<div class="max-w-md rounded-lg border border-rose-200 bg-card p-5 text-sm text-rose-700 shadow-sm">
					{loadError}
				</div>
			</div>
		{:else if showLoading}
			<LoadingState />
		{:else}
			<div class="h-full bg-app"></div>
		{/if}
	</PageContainer>
</AppFrame>
