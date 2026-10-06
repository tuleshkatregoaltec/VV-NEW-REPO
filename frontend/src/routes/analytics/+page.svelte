<script lang="ts">
import { createQuery } from '@tanstack/svelte-query'
import { Building2, GitCompare } from 'lucide-svelte'
import type { ProjectSearchItem } from '$lib/api/analytics'
import type { SearchSelection } from '$lib/api/projects'
import AnalyticsCompareView from '$lib/components/analytics/AnalyticsCompareView.svelte'
import ProjectPanel from '$lib/components/analytics/ProjectPanel.svelte'
import PageContainer from '$lib/components/layout/PageContainer.svelte'
import ProjectSearchInput from '$lib/components/projects/ProjectSearchInput.svelte'
import { projectQueries } from '$lib/queries/projects'

const DUBAI_MARKET_SELECTION: ProjectSearchItem = { name: 'Dubai', filter_type: 'market' }

let projectA = $state<ProjectSearchItem | null>({ ...DUBAI_MARKET_SELECTION })
let projectB = $state<ProjectSearchItem | null>(null)
let comparing = $state(false)
let isDubaiMarketSelected = $derived(projectA?.filter_type === 'market')

const allProjectsQuery = createQuery(() => projectQueries.list())
const allProjects = $derived(allProjectsQuery.data ?? [])

function toggleCompare() {
	comparing = !comparing
	if (!comparing) projectB = null
}

function toAnalyticsSelection(sel: SearchSelection): ProjectSearchItem | null {
	if (sel.type === 'master') {
		return { name: sel.masterName, filter_type: 'master' }
	}

	const project = allProjects.find((item) => item.project_id === sel.projectId)
	if (!project) return null
	return { name: project.project_name, filter_type: 'project' }
}

function handleSearchSelectA(sel: SearchSelection) {
	projectA = toAnalyticsSelection(sel)
}

function handleSearchSelectB(sel: SearchSelection) {
	projectB = toAnalyticsSelection(sel)
}

function selectDubaiMarket() {
	projectA = { ...DUBAI_MARKET_SELECTION }
}
</script>

<PageContainer variant="standard" class="gap-4">
		<section class="ui-surface relative z-30 overflow-visible">
			<div class="ui-page-header grid px-5 py-4 xl:grid-cols-[minmax(0,1fr)_auto] xl:items-center">
				<div>
					<p class="text-xs font-semibold uppercase tracking-[0.18em] text-on-navy-muted">
						Analytics
					</p>
					<h1 class="mt-1 font-display text-2xl leading-tight tracking-[var(--tracking-display)] text-bone">
						Dubai market analytics
					</h1>
				</div>

				<button
					type="button"
					onclick={toggleCompare}
					data-variant={comparing ? 'primary' : 'secondary'}
					class="ui-button h-10 px-4 text-sm"
				>
					<GitCompare size={16} strokeWidth={1.8} />
					{comparing ? 'Exit compare' : 'Compare'}
				</button>
			</div>
		</section>

		<section class="ui-surface p-4 sm:p-5">
			<div class="mb-4 flex flex-col gap-3 xl:flex-row xl:items-end xl:justify-between">
				<div>
					<p class="text-xs font-semibold uppercase tracking-[0.18em] text-fg-4">
						Project scope
					</p>
					<p class="mt-1 text-sm text-fg-3">
						Dubai is loaded by default. Search a project or master community to narrow the view.
					</p>
				</div>
				<button
					type="button"
					onclick={selectDubaiMarket}
					data-variant={isDubaiMarketSelected ? 'primary' : 'secondary'}
					class="ui-button h-9 px-3 text-sm"
				>
					<Building2 size={15} strokeWidth={1.8} />
					Dubai market
				</button>
			</div>
			<div class="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
				<div class="flex-1">
					<div class="grid gap-3 {comparing ? 'xl:grid-cols-2' : ''}">
						<ProjectSearchInput allProjects={allProjects} onSelect={handleSearchSelectA} />
						{#if comparing}
							<ProjectSearchInput allProjects={allProjects} onSelect={handleSearchSelectB} />
						{/if}
					</div>
				</div>

				<div class="hidden xl:block"></div>
			</div>
		</section>

		{#if comparing}
			{#if projectA && projectB}
				<AnalyticsCompareView {projectA} {projectB} {allProjects} />
			{:else}
				<div class="grid grid-cols-1 gap-6 xl:grid-cols-2">
					{#if projectA}
						<div class="ui-surface p-5">
							<p class="text-xs font-semibold uppercase tracking-[0.18em] text-fg-4">Project A</p>
							<p class="mt-2 text-lg font-semibold text-fg-1">{projectA.name}</p>
							<p class="mt-1 text-sm text-fg-3">Select Project B to start comparison.</p>
						</div>
					{:else}
						{@render EmptyState('Project A')}
					{/if}
					{#if projectB}
						<div class="ui-surface p-5">
							<p class="text-xs font-semibold uppercase tracking-[0.18em] text-fg-4">Project B</p>
							<p class="mt-2 text-lg font-semibold text-fg-1">{projectB.name}</p>
							<p class="mt-1 text-sm text-fg-3">Select Project A to start comparison.</p>
						</div>
					{:else}
						{@render EmptyState('Project B')}
					{/if}
				</div>
			{/if}
		{:else if projectA}
			<ProjectPanel selection={projectA} />
		{:else}
			{@render EmptyState('Analytics')}
		{/if}
</PageContainer>

{#snippet EmptyState(label: string)}
	<div class="rounded-lg border border-dashed border-strong bg-card px-8 py-20 text-center shadow-sm">
		<div class="mx-auto mb-5 flex h-14 w-14 items-center justify-center rounded-md bg-navy-pale text-primary-light">
			<Building2 size={28} strokeWidth={1.5} />
		</div>
		<p class="text-base font-semibold text-fg-1">{label} is waiting for a project.</p>
		<p class="mt-2 text-sm text-fg-4">Search above to load live transaction-backed analytics.</p>
	</div>
{/snippet}
