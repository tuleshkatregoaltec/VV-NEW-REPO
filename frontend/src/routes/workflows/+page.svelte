<script lang="ts">
import {
	BriefcaseBusiness,
	Building2,
	ChartNoAxesCombined,
	FilePenLine,
	GitBranch,
	GripVertical,
	Landmark,
	RotateCcw,
	Scale,
	SearchCheck,
	SlidersHorizontal
} from 'lucide-svelte'
import { browser } from '$app/environment'
import { goto } from '$app/navigation'
import AppFrame from '$lib/components/layout/AppFrame.svelte'
import PageContainer from '$lib/components/layout/PageContainer.svelte'

type WorkflowGroupId = 'institutional' | 'agent'
type WorkflowId =
	| 'feasibility-underwriting'
	| 'market-comparables'
	| 'pipeline'
	| 'acquisition'
	| 'unit-comparables'
	| 'market-research'
	| 'listing-generator'
	| 'sale-proposal'

type WorkflowDefinition = {
	id: WorkflowId
	name: string
	label: string
	groupId: WorkflowGroupId
	icon: typeof Scale
	href?: string
}

type DropTarget = {
	groupId: WorkflowGroupId
	id: WorkflowId | null
	position: 'before' | 'after'
}

const STORAGE_KEY = 'vitevue-workflow-cards'

const GROUPS: Array<{ id: WorkflowGroupId; title: string }> = [
	{ id: 'institutional', title: 'Institutional workflows' },
	{ id: 'agent', title: 'Agent & broker workflows' }
]

const FEASIBILITY_WORKFLOW: WorkflowDefinition = {
	id: 'feasibility-underwriting',
	name: 'Feasibility underwriting',
	label: 'Underwrite',
	groupId: 'institutional',
	icon: Scale,
	href: '/feasibility'
}

const WORKFLOW_CATALOG: WorkflowDefinition[] = [
	FEASIBILITY_WORKFLOW,
	{
		id: 'market-comparables',
		name: 'Market comparables',
		label: 'Compare',
		groupId: 'institutional',
		icon: ChartNoAxesCombined
	},
	{
		id: 'pipeline',
		name: 'Pipeline',
		label: 'Track',
		groupId: 'institutional',
		icon: GitBranch
	},
	{
		id: 'acquisition',
		name: 'Acquisition',
		label: 'Screen',
		groupId: 'institutional',
		icon: BriefcaseBusiness
	},
	{
		id: 'unit-comparables',
		name: 'Unit comparables',
		label: 'Price',
		groupId: 'agent',
		icon: Building2
	},
	{
		id: 'market-research',
		name: 'Market research',
		label: 'Research',
		groupId: 'agent',
		icon: SearchCheck
	},
	{
		id: 'listing-generator',
		name: 'Listing generator',
		label: 'Create',
		groupId: 'agent',
		icon: FilePenLine
	},
	{
		id: 'sale-proposal',
		name: 'Sale proposal',
		label: 'Present',
		groupId: 'agent',
		icon: Landmark
	}
]

const DEFAULT_WORKFLOW_IDS: Record<WorkflowGroupId, WorkflowId[]> = {
	institutional: ['feasibility-underwriting', 'market-comparables', 'pipeline', 'acquisition'],
	agent: ['unit-comparables', 'market-research', 'listing-generator', 'sale-proposal']
}

function defaultWorkflowIds(): Record<WorkflowGroupId, WorkflowId[]> {
	return {
		institutional: [...DEFAULT_WORKFLOW_IDS.institutional],
		agent: [...DEFAULT_WORKFLOW_IDS.agent]
	}
}

function isWorkflowId(value: unknown): value is WorkflowId {
	return WORKFLOW_CATALOG.some((workflow) => workflow.id === value)
}

function normalizeGroupIds(value: unknown, groupId: WorkflowGroupId): WorkflowId[] {
	const defaults = DEFAULT_WORKFLOW_IDS[groupId]
	if (!Array.isArray(value)) return [...defaults]

	const allowed = new Set(defaults)
	const selected = value.filter((id): id is WorkflowId => isWorkflowId(id) && allowed.has(id))
	const unique = Array.from(new Set(selected))
	const missing = defaults.filter((id) => !unique.includes(id))
	return [...unique, ...missing]
}

function normalizeWorkflowIds(value: unknown): Record<WorkflowGroupId, WorkflowId[]> {
	if (!value || typeof value !== 'object') return defaultWorkflowIds()

	const stored = value as Partial<Record<WorkflowGroupId, unknown>>
	return {
		institutional: normalizeGroupIds(stored.institutional, 'institutional'),
		agent: normalizeGroupIds(stored.agent, 'agent')
	}
}

function loadWorkflowIds(): Record<WorkflowGroupId, WorkflowId[]> {
	if (!browser) return defaultWorkflowIds()

	try {
		const stored = localStorage.getItem(STORAGE_KEY)
		return stored ? normalizeWorkflowIds(JSON.parse(stored)) : defaultWorkflowIds()
	} catch (error) {
		console.warn('Failed to load workflow preferences:', error)
		return defaultWorkflowIds()
	}
}

function saveWorkflowIds(value: Record<WorkflowGroupId, WorkflowId[]>) {
	if (!browser) return

	try {
		localStorage.setItem(STORAGE_KEY, JSON.stringify(value))
	} catch (error) {
		console.warn('Failed to save workflow preferences:', error)
	}
}

function workflowDefinition(id: WorkflowId): WorkflowDefinition {
	return WORKFLOW_CATALOG.find((workflow) => workflow.id === id) ?? FEASIBILITY_WORKFLOW
}

let editMode = $state(false)
let workflowIds = $state<Record<WorkflowGroupId, WorkflowId[]>>(loadWorkflowIds())
let previewWorkflowIds = $state<Record<WorkflowGroupId, WorkflowId[]> | null>(null)
let visibleWorkflowIds = $derived(previewWorkflowIds ?? workflowIds)
let draggedWorkflow = $state<{ groupId: WorkflowGroupId; id: WorkflowId } | null>(null)
let dropTarget = $state<DropTarget | null>(null)

$effect(() => {
	saveWorkflowIds(workflowIds)
})

function previewOrder(
	groupId: WorkflowGroupId,
	workflowId: WorkflowId,
	target: DropTarget | null = null
): Record<WorkflowGroupId, WorkflowId[]> {
	const nextIds = workflowIds[groupId].filter((id) => id !== workflowId)
	if (!target?.id || target.groupId !== groupId) {
		return { ...workflowIds, [groupId]: [...nextIds, workflowId] }
	}

	const targetIndex = nextIds.indexOf(target.id)
	const insertIndex =
		targetIndex === -1 ? nextIds.length : targetIndex + (target.position === 'after' ? 1 : 0)
	return {
		...workflowIds,
		[groupId]: [...nextIds.slice(0, insertIndex), workflowId, ...nextIds.slice(insertIndex)]
	}
}

function startDrag(event: DragEvent, groupId: WorkflowGroupId, id: WorkflowId) {
	if (!editMode) return
	draggedWorkflow = { groupId, id }
	dropTarget = null
	previewWorkflowIds = { ...workflowIds, [groupId]: [...workflowIds[groupId]] }
	event.dataTransfer?.setData('text/plain', id)
	if (event.dataTransfer) event.dataTransfer.effectAllowed = 'move'
}

function dragPosition(event: DragEvent): DropTarget['position'] {
	const target = event.currentTarget
	if (!(target instanceof HTMLElement)) return 'after'
	const bounds = target.getBoundingClientRect()
	return event.clientX < bounds.left + bounds.width / 2 ? 'before' : 'after'
}

function handleWorkflowDragOver(event: DragEvent, groupId: WorkflowGroupId, id: WorkflowId) {
	if (!draggedWorkflow || draggedWorkflow.groupId !== groupId) return
	event.preventDefault()
	event.stopPropagation()
	if (id === draggedWorkflow.id) return

	const target = { groupId, id, position: dragPosition(event) }
	dropTarget = target
	previewWorkflowIds = previewOrder(groupId, draggedWorkflow.id, target)
	if (event.dataTransfer) event.dataTransfer.dropEffect = 'move'
}

function handleGroupDragOver(event: DragEvent, groupId: WorkflowGroupId) {
	if (!draggedWorkflow || draggedWorkflow.groupId !== groupId) return
	event.preventDefault()
	dropTarget = { groupId, id: null, position: 'after' }
	previewWorkflowIds = previewOrder(groupId, draggedWorkflow.id, dropTarget)
	if (event.dataTransfer) event.dataTransfer.dropEffect = 'move'
}

function handleDrop(event: DragEvent, groupId: WorkflowGroupId, target: DropTarget | null = null) {
	event.preventDefault()
	event.stopPropagation()
	if (!draggedWorkflow || draggedWorkflow.groupId !== groupId) {
		clearDragState()
		return
	}

	workflowIds = previewWorkflowIds ?? previewOrder(groupId, draggedWorkflow.id, target)
	clearDragState()
}

function clearDragState() {
	draggedWorkflow = null
	dropTarget = null
	previewWorkflowIds = null
}

function workflowDragClass(groupId: WorkflowGroupId, id: WorkflowId) {
	if (!editMode) return ''
	if (draggedWorkflow?.groupId === groupId && draggedWorkflow.id === id) {
		return 'border-dashed border-strong bg-elevated opacity-55 shadow-none'
	}
	if (dropTarget?.groupId !== groupId || dropTarget.id !== id) return ''
	return 'shadow-[inset_0_0_0_1px_var(--color-border-strong)]'
}

function resetWorkflows() {
	workflowIds = defaultWorkflowIds()
	clearDragState()
}

function handleWorkflowClick(workflow: WorkflowDefinition) {
	if (editMode || !workflow.href) return
	goto(workflow.href)
}
</script>

<AppFrame>
	<PageContainer variant="fullBleed" class="min-h-full">
		<div class="min-h-full bg-app">
			<section
				class="mx-auto flex min-h-full w-full max-w-[1540px] flex-col justify-center px-4 pb-8 pt-12 sm:px-6 lg:px-8 lg:pt-14"
			>
				<section class="ui-surface relative z-30 mb-9 overflow-visible">
					<div class="ui-page-header grid gap-4 px-5 py-4 xl:grid-cols-[minmax(0,1fr)_auto] xl:items-center">
						<div>
							<p class="text-xs font-semibold uppercase tracking-[0.18em] text-on-navy-muted">
								Workflows
							</p>
							<h1 class="mt-1 font-display text-2xl leading-tight tracking-[var(--tracking-display)] text-bone">
								Agentic workflows
							</h1>
						</div>

						<div class="mt-4 flex flex-wrap items-center gap-2 xl:mt-0 xl:justify-end">
							<button
								type="button"
								class="ui-button h-10 px-4 text-xs"
								data-variant={editMode ? 'primary' : 'secondary'}
								onclick={() => (editMode = !editMode)}
							>
								<SlidersHorizontal size={15} strokeWidth={1.8} />
								{editMode ? 'Done' : 'Edit cards'}
							</button>
							{#if editMode}
								<button
									type="button"
									class="ui-button h-10 px-4 text-xs"
									data-variant="secondary"
									onclick={resetWorkflows}
								>
									<RotateCcw size={15} strokeWidth={1.8} />
									Reset defaults
								</button>
							{/if}
						</div>
					</div>
				</section>

				<div class="mt-4 grid gap-7 lg:mt-6">
					{#each GROUPS as group (group.id)}
						<section class="ui-panel w-full p-4 lg:p-5">
							<div class="mb-4">
								<h2 class="text-base font-semibold text-fg-1">{group.title}</h2>
								<div class="mt-3 h-px w-full bg-border"></div>
							</div>

							<div
								role="list"
								class="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4"
								ondragover={(event) => handleGroupDragOver(event, group.id)}
								ondrop={(event) => handleDrop(event, group.id, { groupId: group.id, id: null, position: 'after' })}
							>
								{#each visibleWorkflowIds[group.id].map(workflowDefinition) as workflow (workflow.id)}
									{@const Icon = workflow.icon}
									<div role="listitem" class="h-full">
										<button
											type="button"
											draggable={editMode}
											aria-label={workflow.href ? `Open ${workflow.name}` : `${workflow.name} workflow`}
											ondragstart={(event) => startDrag(event, group.id, workflow.id)}
											ondragover={(event) => handleWorkflowDragOver(event, group.id, workflow.id)}
											ondrop={(event) =>
												handleDrop(event, group.id, {
													groupId: group.id,
													id: workflow.id,
													position: dragPosition(event)
												})}
											ondragend={clearDragState}
											onclick={() => handleWorkflowClick(workflow)}
											class="ui-surface group relative flex h-full min-h-[178px] w-full p-6 text-left transition-[background-color,border-color,box-shadow,opacity,transform] duration-200 hover:-translate-y-0.5 hover:border-strong hover:bg-elevated hover:shadow-md active:translate-y-0 lg:min-h-[198px] 2xl:min-h-[214px] {editMode
												? 'cursor-grab active:cursor-grabbing'
												: 'cursor-pointer'} {workflowDragClass(group.id, workflow.id)}"
										>
											<span class="relative flex h-full w-full flex-col justify-between gap-7">
												<span class="relative h-[70px] w-[70px]">
													<span
														class="absolute left-2 top-2 h-14 w-14 rounded-lg border border-border bg-panel transition-transform duration-200 group-hover:translate-x-0.5 group-hover:translate-y-0.5"
													></span>
													<span
														class="relative grid h-14 w-14 place-items-center rounded-lg border border-border bg-card text-fg-2 shadow-xs transition-colors group-hover:bg-info-bg group-hover:text-info"
													>
														<Icon size={29} strokeWidth={1.8} />
													</span>
												</span>
												<span class="grid gap-2">
													<span
														class="font-mono text-[11px] font-semibold uppercase tracking-[0.08em] text-fg-4"
													>
														{workflow.label}
													</span>
													<span
														class="max-w-[14rem] text-xl font-semibold leading-tight text-fg-1 lg:text-2xl"
													>
														{workflow.name}
													</span>
												</span>
											</span>
											{#if editMode}
												<span class="absolute right-4 top-4 text-fg-4">
													<GripVertical size={17} strokeWidth={1.8} />
												</span>
											{/if}
										</button>
									</div>
								{/each}
							</div>
						</section>
					{/each}
				</div>
			</section>
		</div>
	</PageContainer>
</AppFrame>
