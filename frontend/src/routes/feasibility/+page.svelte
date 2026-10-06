<script lang="ts">
import { createQuery, useQueryClient } from '@tanstack/svelte-query'
import { CalendarClock, Edit3, FolderOpen, Layers3, MapPinned, Plus, Trash2 } from 'lucide-svelte'
import { goto } from '$app/navigation'
import { feasibility } from '$lib/api/feasibility'
import NewStudySetup from '$lib/components/feasibility/NewStudySetup.svelte'
import AppFrame from '$lib/components/layout/AppFrame.svelte'
import PageContainer from '$lib/components/layout/PageContainer.svelte'
import { feasibilityKeys, feasibilityQueries } from '$lib/queries/feasibility'

type PageMode = 'overview' | 'new'

let mode = $state<PageMode>('overview')
let deletingId = $state<number | null>(null)
let renamingId = $state<number | null>(null)
let renameValue = $state('')
let error = $state('')

const queryClient = useQueryClient()
const studiesQuery = createQuery(() => feasibilityQueries.studies())
const studies = $derived(studiesQuery.data ?? [])
const btrCount = $derived(
	studies.filter((study) => study.development_model === 'build_to_rent_residential').length
)
const latestStudy = $derived(studies[0])

function fmtDate(value: string | Date) {
	return new Intl.DateTimeFormat('en-AE', {
		month: 'short',
		day: 'numeric',
		year: 'numeric',
		hour: '2-digit',
		minute: '2-digit'
	}).format(new Date(value))
}

function modelLabel(model: string) {
	if (model === 'build_to_rent_residential') return 'Build to rent'
	if (model === 'build_to_lease_commercial') return 'Build to lease'
	return 'Build to sell'
}

async function deleteStudy(studyId: number) {
	deletingId = studyId
	error = ''
	try {
		await feasibility.deleteStudy(studyId)
		await queryClient.invalidateQueries({ queryKey: feasibilityKeys.studies() })
	} catch (err) {
		error = err instanceof Error ? err.message : 'Failed to delete study.'
	} finally {
		deletingId = null
	}
}

function startRenameStudy(study: (typeof studies)[number]) {
	renamingId = study.id
	renameValue = study.name
}

function cancelRenameStudy() {
	renamingId = null
	renameValue = ''
}

function focusRenameInput(node: HTMLInputElement) {
	queueMicrotask(() => {
		node.focus()
		node.select()
	})
}

async function renameStudy(study: (typeof studies)[number]) {
	const trimmed = renameValue.trim()
	if (!trimmed || trimmed === study.name) {
		cancelRenameStudy()
		return
	}
	error = ''
	try {
		await feasibility.updateStudy(study.id, { name: trimmed })
		cancelRenameStudy()
		await queryClient.invalidateQueries({ queryKey: feasibilityKeys.studies() })
	} catch (err) {
		error = err instanceof Error ? err.message : 'Failed to rename study.'
	}
}
</script>

<AppFrame stableScrollGutter>
		{#if mode === 'new'}
			<PageContainer variant="standard">
				<NewStudySetup onCancel={() => (mode = 'overview')} />
			</PageContainer>
		{:else}
			<PageContainer variant="standard" class="gap-5">
				<div class="ui-surface overflow-hidden">
					<div class="grid gap-5 bg-navy px-5 py-5 text-bone lg:grid-cols-[minmax(0,1fr)_auto] lg:items-end">
						<div>
							<p class="text-xs font-semibold uppercase tracking-[0.18em] text-on-navy-muted">Feasibility</p>
							<h1 class="mt-2 font-display text-3xl leading-tight tracking-[var(--tracking-display)] text-bone">
								Saved studies workspace
							</h1>
							<p class="mt-2 max-w-3xl text-sm leading-6 text-on-navy-muted">
								Reopen persisted assumptions, create a fresh plot-backed study, or continue model edits from the workbook.
							</p>
						</div>
						<button type="button" class="inline-flex h-10 items-center gap-2 rounded-md bg-bone px-4 text-sm font-semibold text-navy transition hover:bg-bone-muted" onclick={() => (mode = 'new')}>
							<Plus size={16} />
							<span>New study</span>
						</button>
					</div>
					<div class="grid divide-y divide-border bg-card md:grid-cols-3 md:divide-x md:divide-y-0">
						<div class="flex items-center gap-3 p-4">
							<span class="grid h-10 w-10 place-items-center rounded-md bg-info-bg text-info">
								<Layers3 size={18} />
							</span>
							<div>
								<p class="text-2xl font-semibold text-fg-1">{studies.length}</p>
								<p class="text-xs font-medium uppercase tracking-[0.12em] text-fg-4">Saved studies</p>
							</div>
						</div>
						<div class="flex items-center gap-3 p-4">
							<span class="grid h-10 w-10 place-items-center rounded-md bg-panel text-fg-2">
								<MapPinned size={18} />
							</span>
							<div>
								<p class="text-2xl font-semibold text-fg-1">{btrCount}</p>
								<p class="text-xs font-medium uppercase tracking-[0.12em] text-fg-4">BTR models</p>
							</div>
						</div>
						<div class="flex items-center gap-3 p-4">
							<span class="grid h-10 w-10 place-items-center rounded-md bg-panel text-fg-2">
								<CalendarClock size={18} />
							</span>
							<div class="min-w-0">
								<p class="truncate text-sm font-semibold text-fg-1">{latestStudy ? latestStudy.name : 'No recent study'}</p>
								<p class="text-xs font-medium uppercase tracking-[0.12em] text-fg-4">Most recent</p>
							</div>
						</div>
					</div>
				</div>

				{#if error}
					<p class="rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</p>
				{/if}

				<section class="ui-surface">
					{#if studiesQuery.isPending}
						<p class="p-6 text-sm text-fg-4">Loading saved studies...</p>
					{:else if studiesQuery.isError}
						<p class="p-6 text-sm text-rose-600">Failed to load saved studies.</p>
					{:else if studies.length === 0}
						<div class="grid h-full min-h-[360px] place-items-center p-6 text-center">
							<div>
								<FolderOpen class="mx-auto text-fg-5" size={42} strokeWidth={1.5} />
								<p class="mt-4 text-sm font-semibold text-fg-1">No studies yet</p>
								<button type="button" data-variant="primary" class="ui-button mt-4 h-10 px-4 text-sm" onclick={() => (mode = 'new')}>
									<Plus size={16} />
									<span>New study</span>
								</button>
							</div>
						</div>
					{:else}
						<div class="bg-panel p-4">
							<div class="grid gap-3 lg:grid-cols-2 2xl:grid-cols-3">
								{#each studies as study}
									<article class="ui-surface group p-4 transition hover:border-strong hover:shadow-md">
										<div class="flex items-start justify-between gap-3">
											<div class="min-w-0 flex-1">
												{#if renamingId === study.id}
													<input
														bind:value={renameValue}
														use:focusRenameInput
														onblur={() => void renameStudy(study)}
														onkeydown={(event) => {
															if (event.key === 'Enter') event.currentTarget.blur();
															if (event.key === 'Escape') cancelRenameStudy();
														}}
														class="ui-field h-9 w-full min-w-0 px-2 text-sm font-semibold"
													/>
												{:else}
													<button
														type="button"
														class="flex max-w-full items-center gap-1.5 text-left text-base font-semibold text-fg-1 transition hover:text-info"
														onclick={() => startRenameStudy(study)}
														aria-label={`Rename ${study.name}`}
													>
														<span class="truncate">{study.name}</span>
														<Edit3 class="shrink-0 text-fg-4" size={13} />
													</button>
													<p class="mt-1 text-xs text-fg-4">Updated {fmtDate(study.updated_at)}</p>
												{/if}
											</div>
											<span class="ui-badge px-2 py-1 text-[11px] font-semibold uppercase tracking-[0.12em]">
												{modelLabel(study.development_model)}
											</span>
										</div>

										<div class="ui-panel mt-4 p-3">
											<p class="text-xs uppercase tracking-[0.14em] text-fg-4">Plot / project</p>
											<p class="mt-1 truncate text-sm font-semibold text-fg-1">{study.plot_data.project_name}</p>
											<p class="mt-1 text-xs text-fg-4">{study.plot_number} · {study.plot_data.community_name}</p>
										</div>

										<div class="mt-4 grid grid-cols-2 gap-3 text-sm">
											<div>
												<p class="text-xs uppercase tracking-[0.14em] text-fg-4">Plot area</p>
												<p class="mt-1 font-semibold text-fg-1">{study.plot_data.plot_area_sqm.toLocaleString('en-AE', { maximumFractionDigits: 0 })} sqm</p>
											</div>
											<div>
												<p class="text-xs uppercase tracking-[0.14em] text-fg-4">Max GFA</p>
												<p class="mt-1 font-semibold text-fg-1">{study.plot_data.max_gfa_sqm.toLocaleString('en-AE', { maximumFractionDigits: 0 })} sqm</p>
											</div>
										</div>

										<div class="mt-4 flex items-center justify-between gap-2 border-t border-border pt-3">
											<button type="button" data-variant="primary" class="ui-button h-9 px-3 text-xs" onclick={() => goto(`/feasibility/${study.id}`)}>
												<FolderOpen size={14} />
												Open
											</button>
											<div class="flex gap-2">
												<button type="button" data-variant="danger" data-size="icon" class="ui-button h-9 w-9 disabled:cursor-not-allowed disabled:opacity-50" disabled={deletingId === study.id} onclick={() => void deleteStudy(study.id)} aria-label="Delete study">
													<Trash2 size={14} />
												</button>
											</div>
										</div>
									</article>
								{/each}
							</div>
						</div>
					{/if}
				</section>
			</PageContainer>
		{/if}
</AppFrame>
