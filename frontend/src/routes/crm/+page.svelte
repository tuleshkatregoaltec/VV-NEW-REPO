<script lang="ts">
import { createQuery } from '@tanstack/svelte-query'
import {
	ArrowRight,
	AtSign,
	BadgeDollarSign,
	Bookmark,
	BookmarkCheck,
	BriefcaseBusiness,
	Building2,
	CalendarClock,
	CalendarDays,
	CheckCircle2,
	ChevronRight,
	CircleAlert,
	ClipboardList,
	Clock3,
	Database,
	FileText,
	FileUp,
	FolderOpen,
	Highlighter,
	History,
	House,
	KeyRound,
	NotebookPen,
	Pencil,
	Phone,
	RefreshCw,
	Save,
	Search,
	Send,
	ShieldCheck,
	Sparkles,
	Store,
	Trash2,
	TrendingUp,
	UserRound,
	UsersRound,
	X
} from 'lucide-svelte'
import { tick } from 'svelte'
import type {
	CrmAssetClass,
	CrmBreakdownLevel,
	CrmContactImport,
	CrmHighlightColor,
	CrmLead,
	CrmLeadPriority,
	CrmLeadStatus,
	CrmOwnerRegistryScope,
	CrmOwnershipStatus,
	CrmPipelineStatus,
	CrmTimelineEvent
} from '$lib/api/crm'
import { crm } from '$lib/api/crm'
import CrmDashboardSkeleton from '$lib/components/crm/CrmDashboardSkeleton.svelte'
import CrmPanelSkeleton from '$lib/components/crm/CrmPanelSkeleton.svelte'
import AppFrame from '$lib/components/layout/AppFrame.svelte'
import PageContainer from '$lib/components/layout/PageContainer.svelte'
import {
	formatCrmMoney,
	formatCrmNumber as number,
	formatCrmDate as shortDate
} from '$lib/crm/format'
import { crmQueries } from '$lib/queries/crm'

const PAGE_SIZE = 50
const OWNER_PAGE_SIZE = 50
let selectedLeadId = $state<string | null>(null)
let search = $state('')
let debouncedSearch = $state('')
let status = $state<CrmLeadStatus | ''>('')
let priority = $state<CrmLeadPriority | ''>('')
let assetClass = $state<CrmAssetClass | ''>('')
let propertyType = $state('')
let area = $state('')
let project = $state('')
let building = $state('')
let breakdown = $state<CrmBreakdownLevel>('area')
let expiredDays = $state(365)
let offset = $state(0)
let showSaved = $state(false)
let savedFolder = $state<'manual' | 'rental_ready' | 'registry' | 'prior_owners' | 'import'>(
	'manual'
)
let selectedImportId = $state<number | null>(null)
let savingCandidateKey = $state<string | null>(null)
let ownerSearch = $state('')
let debouncedOwnerSearch = $state('')
let ownerStatus = $state<CrmOwnershipStatus | ''>('')
let ownerLeaseWindow = $state<CrmLeadStatus | ''>('')
let ownerPortfolioOnly = $state(false)
let ownerMinRent = $state('')
let ownerMaxRent = $state('')
let ownerMinValue = $state('')
let ownerMaxValue = $state('')
let ownerOffset = $state(0)
let debouncedOwnerMinRent = $state('')
let debouncedOwnerMaxRent = $state('')
let debouncedOwnerMinValue = $state('')
let debouncedOwnerMaxValue = $state('')
let selectedOwnerKeys = $state<string[]>([])
let bulkPipelineStatus = $state<CrmPipelineStatus | ''>('')
let bulkHighlightColor = $state<CrmHighlightColor | ''>('')
let bulkNote = $state('')
let bulkSaving = $state(false)
let renamingImportId = $state<number | null>(null)
let importRenameDraft = $state('')
let pendingDeleteImport = $state<CrmContactImport | null>(null)
let deletingImportId = $state<number | null>(null)
let selectedOwnerKey = $state<string | null>(null)
let showOutreachPreview = $state(false)
let importFile = $state<File | null>(null)
let importListName = $state('')
let importRunning = $state(false)
let importError = $state('')
let latestImport = $state<CrmContactImport | null>(null)
let workspaceVersion = $state('')
let workspaceSaving = $state(false)
let noteSaving = $state(false)
let noteBody = $state('')
let workspaceDraft = $state({
	pipeline_status: 'new' as CrmPipelineStatus,
	highlight_color: 'none' as CrmHighlightColor,
	owner_name: '',
	owner_email: '',
	owner_phone: '',
	next_follow_up: '',
	tags: ''
})

const dashboardParams = $derived({
	search: debouncedSearch || undefined,
	status: status || undefined,
	priority: priority || undefined,
	asset_class: assetClass || undefined,
	property_type: propertyType || undefined,
	area: area || undefined,
	project: project || undefined,
	building: building || undefined,
	breakdown,
	expired_days: expiredDays,
	limit: PAGE_SIZE,
	offset
})
const contactImportsEnabled = $derived(showSaved || showOutreachPreview)
const dashboardQuery = createQuery(() => crmQueries.dashboard(dashboardParams))
const detailQuery = createQuery(() => crmQueries.lead(selectedLeadId))
const workspacesQuery = createQuery(() => crmQueries.workspaces())
const workspaceQuery = createQuery(() => crmQueries.workspace(selectedLeadId))
const savedQuery = createQuery(() => crmQueries.saved())
const leadContactsQuery = createQuery(() => crmQueries.leadContacts(selectedLeadId))
const contactImportsQuery = createQuery(() => crmQueries.contactImports(contactImportsEnabled))
const ownerRegistryScope = $derived<CrmOwnerRegistryScope>(
	savedFolder === 'rental_ready'
		? 'rental_ready'
		: savedFolder === 'registry'
			? 'registry'
			: savedFolder === 'prior_owners'
				? 'prior_owners'
				: 'all'
)
const ownerRegistryEnabled = $derived(
	showSaved &&
		savedFolder !== 'manual' &&
		(savedFolder !== 'import' || selectedImportId !== null) &&
		!selectedLeadId &&
		!selectedOwnerKey
)
const ownerRegistryQuery = createQuery(() =>
	crmQueries.ownerRegistry(
		ownerRegistryScope,
		{
			list_id: savedFolder === 'import' ? (selectedImportId ?? undefined) : undefined,
			status: ownerStatus || undefined,
			search: debouncedOwnerSearch || undefined,
			lease_window: ownerLeaseWindow || undefined,
			portfolio_only: ownerPortfolioOnly || undefined,
			min_rent_aed: Number(debouncedOwnerMinRent) || undefined,
			max_rent_aed: Number(debouncedOwnerMaxRent) || undefined,
			min_value_aed: Number(debouncedOwnerMinValue) || undefined,
			max_value_aed: Number(debouncedOwnerMaxValue) || undefined,
			offset: ownerOffset
		},
		ownerRegistryEnabled
	)
)
const ownerProfileQuery = createQuery(() => crmQueries.ownerProfile(selectedOwnerKey))
const ownerWorkspacesQuery = createQuery(() =>
	crmQueries.ownerWorkspaces(ownerRegistryEnabled || Boolean(selectedOwnerKey))
)
const dashboard = $derived(dashboardQuery.data)
const summary = $derived(dashboard?.summary)
const detail = $derived(detailQuery.data)
const workspaceResult = $derived(workspaceQuery.data)
const workspace = $derived(
	workspaceResult?.lead_id === selectedLeadId ? workspaceResult : undefined
)
const importedLeadContacts = $derived(leadContactsQuery.data ?? [])
const displayedImport = $derived(latestImport ?? contactImportsQuery.data?.[0])
const ownerRegistry = $derived(ownerRegistryQuery.data)
const selectedOwner = $derived(ownerProfileQuery.data)
const selectedImport = $derived(
	contactImportsQuery.data?.find((item) => item.list_id === selectedImportId)
)
const maxBreakdownTotal = $derived(
	Math.max(1, ...(dashboard?.breakdown.map((item) => item.total) ?? [1]))
)
const hasFilters = $derived(
	Boolean(
		search ||
			status ||
			priority ||
			assetClass ||
			propertyType ||
			area ||
			project ||
			building ||
			expiredDays !== 365
	)
)
const savedByCandidate = $derived(
	new Map((savedQuery.data ?? []).map((saved) => [saved.lead.unit_candidate_key, saved]))
)
const workspaceByCandidate = $derived(
	new Map((workspacesQuery.data ?? []).map((item) => [item.unit_candidate_key, item]))
)
const ownerWorkspaceByKey = $derived(
	new Map((ownerWorkspacesQuery.data ?? []).map((item) => [item.owner_key, item]))
)
const filteredSavedLeads = $derived(
	(savedQuery.data ?? [])
		.map((saved) => saved.lead)
		.filter((lead) => {
			if (assetClass && lead.asset_class !== assetClass) return false
			if (propertyType && lead.property_subtype !== propertyType) return false
			if (status && lead.status !== status) return false
			if (priority && lead.priority !== priority) return false
			if (area && lead.area_name !== area) return false
			if (project && lead.project_name !== project) return false
			if (building && lead.building_name !== building) return false
			if (debouncedSearch) {
				const haystack =
					`${lead.building_name} ${lead.project_name} ${lead.area_name} ${lead.unit_number ?? ''} ${lead.property_subtype}`.toLowerCase()
				if (!haystack.includes(debouncedSearch.toLowerCase())) return false
			}
			return true
		})
)
const displayedLeads = $derived(showSaved ? filteredSavedLeads : (dashboard?.leads ?? []))
const displayedTotal = $derived(showSaved ? filteredSavedLeads.length : (dashboard?.total ?? 0))

$effect(() => {
	const value = search.trim()
	const timeout = setTimeout(() => {
		debouncedSearch = value
		offset = 0
	}, 250)
	return () => clearTimeout(timeout)
})

$effect(() => {
	const value = ownerSearch.trim()
	const timeout = setTimeout(() => {
		debouncedOwnerSearch = value
		ownerOffset = 0
	}, 250)
	return () => clearTimeout(timeout)
})

$effect(() => {
	const values = [ownerMinRent, ownerMaxRent, ownerMinValue, ownerMaxValue]
	const timeout = setTimeout(() => {
		debouncedOwnerMinRent = values[0]
		debouncedOwnerMaxRent = values[1]
		debouncedOwnerMinValue = values[2]
		debouncedOwnerMaxValue = values[3]
		ownerOffset = 0
	}, 450)
	return () => clearTimeout(timeout)
})

$effect(() => {
	if (!selectedLeadId || !workspace) return
	const version = `${selectedLeadId}:${workspace.updated_at}`
	if (workspaceVersion === version) return
	workspaceDraft = {
		pipeline_status: workspace.pipeline_status,
		highlight_color: workspace.highlight_color,
		owner_name: workspace.owner_name ?? '',
		owner_email: workspace.owner_email ?? '',
		owner_phone: workspace.owner_phone ?? '',
		next_follow_up: workspace.next_follow_up ?? '',
		tags: workspace.tags.join(', ')
	}
	workspaceVersion = version
	noteBody = ''
})

function lookbackLabel(days: number) {
	if (days === 365) return '1 year'
	if (days === 730) return '2 years'
	if (days === 548) return '18 months'
	return `${days} days`
}

function money(value: number | null | undefined, compact = false) {
	return value ? formatCrmMoney(value, compact) : '—'
}

function propertyTitle(lead: CrmLead) {
	return lead.building_name || lead.project_name || lead.area_name || 'Property unresolved'
}

function propertyPath(lead: CrmLead) {
	const title = propertyTitle(lead)
	return [lead.project_name, lead.area_name]
		.filter((value, index, values) => value && value !== title && values.indexOf(value) === index)
		.join(' · ')
}

function registryPath(lead: CrmLead) {
	return [lead.registry_building_name, lead.registry_project_name, lead.registry_area_name]
		.filter((value, index, values) => value && values.indexOf(value) === index)
		.join(' · ')
}

function hasCanonicalAddressChange(lead: CrmLead) {
	const canonical = [lead.building_name, lead.project_name, lead.area_name].filter(Boolean).join('|')
	const registry = [lead.registry_building_name, lead.registry_project_name, lead.registry_area_name].filter(Boolean).join('|')
	return Boolean(registry && canonical !== registry)
}

function statusLabel(lead: CrmLead) {
	if (lead.ownership_timing === 'sale_during_lease') return 'Ownership changed'
	if (lead.status === 'expired' && lead.lease_evidence_state === 'unit_unresolved') {
		return `${Math.abs(lead.days_to_expiry)}d expired · unit unresolved`
	}
	return lead.status === 'expired'
		? `${Math.abs(lead.days_to_expiry)}d unlet signal`
		: `${lead.days_to_expiry}d remaining`
}

function statusClass(value: CrmLeadStatus) {
	if (value === 'expired') return 'bg-error-bg text-error'
	if (value === 'expiring_30') return 'bg-warning-bg text-warning'
	if (value === 'expiring_60') return 'bg-info-bg text-info'
	return 'bg-panel text-fg-2'
}

function priorityClass(value: CrmLeadPriority) {
	if (value === 'urgent') return 'border-navy bg-navy text-on-navy'
	if (value === 'high') return 'border-warning-border bg-warning-bg text-warning'
	return 'border-border bg-panel text-fg-2'
}

function confidenceClass(value: string) {
	if (value === 'high') return 'text-success'
	if (value === 'medium') return 'text-warning'
	return 'text-fg-4'
}

const PIPELINE_LABELS: Record<CrmPipelineStatus, string> = {
	new: 'New lead',
	researching: 'Researching',
	contact_ready: 'Contact ready',
	contacted: 'Contacted',
	qualified: 'Qualified',
	nurture: 'Nurture',
	won: 'Won',
	closed: 'Closed'
}

function pipelineClass(status: CrmPipelineStatus | undefined) {
	if (status === 'won') return 'border-success-border bg-success-bg text-success'
	if (status === 'qualified') return 'border-info-border bg-info-bg text-info'
	if (status === 'contacted' || status === 'contact_ready')
		return 'border-warning-border bg-warning-bg text-warning'
	if (status === 'closed') return 'border-border bg-panel text-fg-4'
	return 'border-border bg-card text-fg-3'
}

function highlightRowClass(color: CrmHighlightColor | undefined) {
	if (color === 'amber') return 'bg-amber-50/70 border-l-4 border-l-amber-400 dark:bg-amber-950/20'
	if (color === 'green')
		return 'bg-emerald-50/70 border-l-4 border-l-emerald-500 dark:bg-emerald-950/20'
	if (color === 'blue') return 'bg-sky-50/70 border-l-4 border-l-sky-500 dark:bg-sky-950/20'
	if (color === 'red') return 'bg-rose-50/70 border-l-4 border-l-rose-500 dark:bg-rose-950/20'
	if (color === 'purple')
		return 'bg-violet-50/70 border-l-4 border-l-violet-500 dark:bg-violet-950/20'
	return 'border-l-4 border-l-transparent'
}

function highlightDotClass(color: CrmHighlightColor) {
	if (color === 'amber') return 'bg-amber-400'
	if (color === 'green') return 'bg-emerald-500'
	if (color === 'blue') return 'bg-sky-500'
	if (color === 'red') return 'bg-rose-500'
	if (color === 'purple') return 'bg-violet-500'
	return 'bg-white border border-border'
}

function dateTime(value: string) {
	return new Intl.DateTimeFormat('en-GB', {
		day: '2-digit',
		month: 'short',
		hour: '2-digit',
		minute: '2-digit'
	}).format(new Date(value))
}

function clearFilters() {
	search = ''
	debouncedSearch = ''
	status = ''
	priority = ''
	assetClass = ''
	propertyType = ''
	area = ''
	project = ''
	building = ''
	expiredDays = 365
	offset = 0
}

function selectAssetClass(value: CrmAssetClass | '') {
	assetClass = value
	propertyType = ''
	offset = 0
}

function assetSummary(value: CrmAssetClass) {
	return dashboard?.asset_breakdown.find((item) => item.asset_class === value)
}

function assetLabel(lead: CrmLead) {
	if (lead.asset_class === 'commercial' && lead.property_subtype !== 'Commercial') {
		return `${lead.property_subtype} · sale-verified`
	}
	return lead.property_subtype
}

function selectBreakdown(label: string) {
	if (label === 'Unresolved hierarchy') return
	if (breakdown === 'area') {
		area = label
		project = ''
		building = ''
		breakdown = 'project'
	} else if (breakdown === 'project') {
		project = label
		building = ''
		breakdown = 'building'
	} else {
		building = label
	}
	offset = 0
}

async function toggleSaved(lead: CrmLead) {
	if (savingCandidateKey) return
	savingCandidateKey = lead.unit_candidate_key
	try {
		const saved = savedByCandidate.get(lead.unit_candidate_key)
		if (saved) await crm.deleteSavedLead(saved.id)
		else await crm.saveLead(lead.lead_id)
		await savedQuery.refetch()
	} finally {
		savingCandidateKey = null
	}
}

async function persistWorkspace(
	payload: Parameters<typeof crm.updateWorkspace>[1],
	showBusy = true
) {
	if (!selectedLeadId || workspaceSaving) return
	if (showBusy) workspaceSaving = true
	try {
		await crm.updateWorkspace(selectedLeadId, payload)
		workspaceVersion = ''
		await Promise.all([workspaceQuery.refetch(), workspacesQuery.refetch()])
	} finally {
		if (showBusy) workspaceSaving = false
	}
}

async function saveWorkspaceDetails() {
	await persistWorkspace({
		owner_name: workspaceDraft.owner_name || null,
		owner_email: workspaceDraft.owner_email || null,
		owner_phone: workspaceDraft.owner_phone || null,
		next_follow_up: workspaceDraft.next_follow_up || null,
		tags: workspaceDraft.tags
			.split(',')
			.map((tag) => tag.trim())
			.filter(Boolean)
	})
}

async function setPipelineStatus(status: CrmPipelineStatus) {
	workspaceDraft.pipeline_status = status
	await persistWorkspace({ pipeline_status: status }, false)
}

async function setHighlight(color: CrmHighlightColor) {
	workspaceDraft.highlight_color = color
	await persistWorkspace({ highlight_color: color }, false)
}

async function addWorkspaceNote() {
	if (!selectedLeadId || !noteBody.trim() || noteSaving) return
	noteSaving = true
	try {
		await crm.addNote(selectedLeadId, noteBody.trim())
		noteBody = ''
		workspaceVersion = ''
		await Promise.all([workspaceQuery.refetch(), workspacesQuery.refetch()])
	} finally {
		noteSaving = false
	}
}

async function deleteWorkspaceNote(noteId: number) {
	if (noteSaving) return
	noteSaving = true
	try {
		await crm.deleteNote(noteId)
		workspaceVersion = ''
		await Promise.all([workspaceQuery.refetch(), workspacesQuery.refetch()])
	} finally {
		noteSaving = false
	}
}

function openReport(leadId: string) {
	window.open(`/crm/report/${encodeURIComponent(leadId)}`, '_blank', 'noopener,noreferrer')
}

function timelineIcon(event: CrmTimelineEvent) {
	return event.event_type === 'sale' ? BadgeDollarSign : KeyRound
}

function chooseImportFile(event: Event) {
	const input = event.currentTarget as HTMLInputElement
	importFile = input.files?.[0] ?? null
	if (importFile && !importListName.trim()) {
		importListName = importFile.name.replace(/\.(xlsx|csv)$/i, '')
	}
	importError = ''
}

function openOwnerDataWorkspace() {
	showOutreachPreview = true
}

async function runContactImport() {
	if (!importFile || importRunning) return
	importRunning = true
	importError = ''
	try {
		const result = await crm.uploadContactImport(importFile, importListName.trim())
		latestImport = result
		const refreshes: Promise<unknown>[] = [contactImportsQuery.refetch(), workspacesQuery.refetch()]
		if (ownerRegistryEnabled) refreshes.push(ownerRegistryQuery.refetch())
		if (selectedLeadId) refreshes.push(leadContactsQuery.refetch())
		await Promise.all(refreshes)
	} catch (error) {
		importError = error instanceof Error ? error.message : 'The owner-data import failed.'
	} finally {
		importRunning = false
	}
}

function ownershipLabel(status: CrmOwnershipStatus) {
	if (status === 'verified_current_owner') return 'Verified owner'
	if (status === 'probable_current_owner') return 'Probable owner'
	if (status === 'unit_linked_unverified') return 'Ownership review'
	if (status === 'former_owner') return 'Former owner'
	if (status === 'conflicting_claim') return 'Conflicting evidence'
	if (status === 'insufficient_property_data') return 'Insufficient property data'
	if (status === 'registry_not_observed') return 'Registry gap'
	return 'Unmatched'
}

function ownershipClass(status: CrmOwnershipStatus) {
	if (status === 'verified_current_owner') return 'border-success-border bg-success-bg text-success'
	if (status === 'probable_current_owner') return 'border-info-border bg-info-bg text-info'
	if (status === 'former_owner') return 'border-error-border bg-error-bg text-error'
	if (
		status === 'unit_linked_unverified' ||
		status === 'conflicting_claim' ||
		status === 'registry_not_observed'
	)
		return 'border-warning-border bg-warning-bg text-warning'
	return 'border-border bg-panel text-fg-4'
}

function openSavedFolder(
	folder: 'manual' | 'rental_ready' | 'registry' | 'prior_owners' | 'import',
	importListId: number | null = null
) {
	savedFolder = folder
	selectedImportId = folder === 'import' ? importListId : null
	showSaved = true
	selectedOwnerKey = null
	selectedOwnerKeys = []
	ownerOffset = 0
	ownerSearch = ''
	ownerStatus = ''
	ownerLeaseWindow = ''
	ownerPortfolioOnly = false
	ownerMinRent = ''
	ownerMaxRent = ''
	ownerMinValue = ''
	ownerMaxValue = ''
	debouncedOwnerMinRent = ''
	debouncedOwnerMaxRent = ''
	debouncedOwnerMinValue = ''
	debouncedOwnerMaxValue = ''
}

async function toggleSavedWorkspace() {
	if (showSaved) {
		showSaved = false
		return
	}
	showSaved = true
	selectedLeadId = null
	await tick()
	document
		.getElementById('crm-saved-workspace')
		?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function openOwnerProfile(ownerKey: string) {
	selectedOwnerKey = ownerKey
}

function ownerFolderTitle() {
	if (savedFolder === 'rental_ready') return 'Rental owner leads'
	if (savedFolder === 'registry') return 'Current owner registry & review'
	if (savedFolder === 'prior_owners') return 'Prior owners registry'
	if (savedFolder === 'import') return selectedImport?.name ?? 'Imported owner folder'
	return 'Owner profiles'
}

function toggleOwnerSelection(ownerKey: string) {
	selectedOwnerKeys = selectedOwnerKeys.includes(ownerKey)
		? selectedOwnerKeys.filter((key) => key !== ownerKey)
		: [...selectedOwnerKeys, ownerKey]
}

function toggleVisibleOwners() {
	const visible = ownerRegistry?.owners.map((owner) => owner.owner_key) ?? []
	const allSelected = visible.length > 0 && visible.every((key) => selectedOwnerKeys.includes(key))
	selectedOwnerKeys = allSelected
		? selectedOwnerKeys.filter((key) => !visible.includes(key))
		: Array.from(new Set([...selectedOwnerKeys, ...visible]))
}

async function applyOwnerBulkUpdate() {
	if (!selectedOwnerKeys.length || bulkSaving) return
	if (!bulkPipelineStatus && !bulkHighlightColor && !bulkNote.trim()) return
	bulkSaving = true
	try {
		await crm.bulkUpdateOwnerWorkspaces({
			owner_keys: selectedOwnerKeys,
			pipeline_status: bulkPipelineStatus || undefined,
			highlight_color: bulkHighlightColor || undefined,
			note: bulkNote.trim() || undefined
		})
		bulkNote = ''
		bulkPipelineStatus = ''
		bulkHighlightColor = ''
		selectedOwnerKeys = []
		await ownerWorkspacesQuery.refetch()
	} finally {
		bulkSaving = false
	}
}

async function renameImport(item: CrmContactImport) {
	const name = importRenameDraft.trim()
	if (!name || renamingImportId !== item.id) return
	const updated = await crm.renameContactImport(item.id, name)
	if (latestImport?.id === item.id) latestImport = updated
	renamingImportId = null
	importRenameDraft = ''
	await contactImportsQuery.refetch()
}

async function deleteImport(item: CrmContactImport) {
	if (deletingImportId !== null) return
	deletingImportId = item.id
	importError = ''
	try {
		await crm.deleteContactImport(item.id)
		if (latestImport?.id === item.id) latestImport = null
		if (renamingImportId === item.id) {
			renamingImportId = null
			importRenameDraft = ''
		}
		if (selectedImportId === item.list_id) {
			selectedImportId = null
			savedFolder = 'manual'
		}
		pendingDeleteImport = null
		const refreshes: Promise<unknown>[] = [contactImportsQuery.refetch()]
		if (ownerRegistryEnabled) refreshes.push(ownerRegistryQuery.refetch())
		await Promise.all(refreshes)
	} catch (error) {
		importError = error instanceof Error ? error.message : 'The import could not be deleted.'
	} finally {
		deletingImportId = null
	}
}
</script>

<svelte:head>
	<title>Lease opportunity CRM · Vitevue</title>
</svelte:head>

<AppFrame stableScrollGutter>
	<PageContainer variant="wide" class="pb-14">
		<header class="flex flex-col gap-5 border-b border-border px-1 pb-6 pt-5 lg:flex-row lg:items-end lg:justify-between">
			<div>
				<p class="mb-2 font-mono text-[11px] uppercase tracking-[0.08em] text-fg-4">
					Growth workspace / <span class="text-fg-1">Lease opportunities</span>
				</p>
				<div class="flex items-center gap-3">
					<div class="flex h-10 w-10 items-center justify-center rounded-lg bg-navy text-on-navy">
						<KeyRound size={19} strokeWidth={1.8} />
					</div>
					<div>
						<h1 class="text-2xl font-semibold tracking-tight text-fg-1">Lease opportunity CRM</h1>
						<p class="mt-1 text-sm text-fg-3">
							Find owners who may need renewal, re-letting, or an exit conversation.
						</p>
					</div>
				</div>
			</div>
			<div class="flex flex-wrap items-center gap-2">
				<a href="/crm/inbound" class="ui-button" data-variant="primary" data-size="sm"><Sparkles size={14} /> Inbound intelligence</a>
				<button type="button" class="ui-button" data-variant="secondary" data-size="sm" onclick={openOwnerDataWorkspace}>
					<FileUp size={14} /> Import owner data
				</button>
				<button
					type="button"
					class="ui-button"
					data-variant={showSaved ? 'primary' : 'secondary'}
					data-size="sm"
					onclick={toggleSavedWorkspace}
				>
					{#if showSaved}<BookmarkCheck size={14} />{:else}<Bookmark size={14} />{/if}
					Saved {savedQuery.data?.length ? `(${savedQuery.data.length})` : ''}
				</button>
				{#if dashboardQuery.isError}
					<span class="rounded-full border border-error-border bg-error-bg px-3 py-1.5 text-xs font-semibold text-error">
						<span class="mr-1.5 inline-block h-1.5 w-1.5 rounded-full bg-error"></span>Data pipeline unavailable
					</span>
				{:else if dashboardQuery.isFetching}
					<span class="rounded-full border border-border bg-panel px-3 py-1.5 text-xs font-semibold text-fg-3">
						<span class="mr-1.5 inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-warning"></span>Checking data pipeline
					</span>
				{:else}
					<span class="rounded-full border border-success-border bg-success-bg px-3 py-1.5 text-xs font-semibold text-success">
						<span class="mr-1.5 inline-block h-1.5 w-1.5 rounded-full bg-success"></span>Live data pipeline
					</span>
				{/if}
				<button type="button" class="ui-button" data-variant="secondary" data-size="sm" onclick={() => dashboardQuery.refetch()} disabled={dashboardQuery.isFetching}>
					<RefreshCw size={14} class={dashboardQuery.isFetching ? 'animate-spin' : ''} /> Refresh
				</button>
			</div>
		</header>

		{#if dashboardQuery.isLoading}
			<CrmDashboardSkeleton />
		{:else if dashboardQuery.isError}
			<div class="mt-6 rounded-lg border border-error-border bg-error-bg p-5">
				<div class="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between"><div class="flex items-start gap-3"><CircleAlert class="mt-0.5 text-error" size={18} /><div><p class="font-semibold text-error">CRM data could not be loaded</p><p class="mt-1 text-sm text-fg-2">{dashboardQuery.error.message}</p></div></div><button type="button" class="ui-button shrink-0" data-variant="secondary" data-size="sm" onclick={() => dashboardQuery.refetch()} disabled={dashboardQuery.isFetching}><RefreshCw size={14} class={dashboardQuery.isFetching ? 'animate-spin' : ''} /> Try again</button></div>
			</div>
		{:else}
			<section class="mt-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
				<div class="ui-surface p-4">
					<div class="flex items-center justify-between"><span class="font-mono text-[10px] uppercase tracking-[0.08em] text-fg-4">Action now</span><CircleAlert size={16} class="text-error" /></div>
					<p class="mt-3 text-2xl font-semibold tabular-nums text-fg-1">{number(summary?.urgent)}</p><p class="mt-1 text-xs text-fg-3">Urgent owner pursuits</p>
				</div>
				<div class="ui-surface p-4">
					<div class="flex items-center justify-between"><span class="font-mono text-[10px] uppercase tracking-[0.08em] text-fg-4">Expired</span><Clock3 size={16} class="text-warning" /></div>
					<p class="mt-3 text-2xl font-semibold tabular-nums text-fg-1">{number(summary?.expired_unlet)}</p><p class="mt-1 text-xs text-fg-3">Exact units with no later registered lease · trailing {lookbackLabel(expiredDays)}</p>
				</div>
				<div class="ui-surface p-4">
					<div class="flex items-center justify-between"><span class="font-mono text-[10px] uppercase tracking-[0.08em] text-fg-4">90-day pipeline</span><CalendarClock size={16} class="text-info" /></div>
					<p class="mt-3 text-2xl font-semibold tabular-nums text-fg-1">{number((summary?.expiring_30_days ?? 0) + (summary?.expiring_31_to_60_days ?? 0) + (summary?.expiring_61_to_90_days ?? 0))}</p><p class="mt-1 text-xs text-fg-3">Upcoming expiries</p>
				</div>
				<div class="ui-surface p-4">
					<div class="flex items-center justify-between"><span class="font-mono text-[10px] uppercase tracking-[0.08em] text-fg-4">Rent at risk</span><TrendingUp size={16} class="text-success" /></div>
					<p class="mt-3 text-2xl font-semibold tabular-nums text-fg-1">{money(summary?.annual_rent_at_risk_aed, true)}</p><p class="mt-1 text-xs text-fg-3">{number(summary?.sale_conversation_candidates)} possible sale conversations</p>
				</div>
			</section>

			<section class="mt-3 ui-surface p-3">
				<div class="mb-2 flex items-center justify-between gap-3 px-1">
					<div>
						<p class="text-sm font-semibold text-fg-1">Portfolio mode</p>
						<p class="mt-0.5 text-xs text-fg-4">Separate homes from offices, shops, and other commercial premises.</p>
					</div>
					{#if assetClass}<span class="rounded-full border border-info-border bg-info-bg px-2.5 py-1 text-[10px] font-semibold capitalize text-info">{assetClass} view</span>{/if}
				</div>
				<div class="grid gap-2 md:grid-cols-3">
					<button type="button" class="rounded-lg border p-3 text-left transition {assetClass === '' ? 'border-navy bg-panel ring-1 ring-navy/10' : 'border-border hover:bg-panel'}" onclick={() => selectAssetClass('')}>
						<div class="flex items-center gap-2"><Building2 size={16} class="text-info" /><span class="text-xs font-semibold text-fg-2">All assets</span></div>
						<p class="mt-2 text-xl font-semibold tabular-nums text-fg-1">{number(dashboard?.asset_breakdown.reduce((total, item) => total + item.total, 0))}</p>
						<p class="mt-0.5 text-[10px] text-fg-4">Residential + commercial pursuit queue</p>
					</button>
					<button type="button" class="rounded-lg border p-3 text-left transition {assetClass === 'residential' ? 'border-success-border bg-success-bg ring-1 ring-success/10' : 'border-border hover:bg-panel'}" onclick={() => selectAssetClass('residential')}>
						<div class="flex items-center gap-2"><House size={16} class="text-success" /><span class="text-xs font-semibold text-fg-2">Residential</span><span class="ml-auto text-[10px] text-fg-4">Apartment · Villa</span></div>
						<p class="mt-2 text-xl font-semibold tabular-nums text-fg-1">{number(assetSummary('residential')?.total)}</p>
						<p class="mt-0.5 text-[10px] text-fg-4">{number(assetSummary('residential')?.exact_unit_matches)} exact units · {money(assetSummary('residential')?.annual_rent_at_risk_aed, true)} rent</p>
					</button>
					<button type="button" class="rounded-lg border p-3 text-left transition {assetClass === 'commercial' ? 'border-info-border bg-info-bg ring-1 ring-info/10' : 'border-border hover:bg-panel'}" onclick={() => selectAssetClass('commercial')}>
						<div class="flex items-center gap-2"><BriefcaseBusiness size={16} class="text-info" /><span class="text-xs font-semibold text-fg-2">Commercial</span><span class="ml-auto text-[10px] text-fg-4">Office · Shop · More</span></div>
						<p class="mt-2 text-xl font-semibold tabular-nums text-fg-1">{number(assetSummary('commercial')?.total)}</p>
						<p class="mt-0.5 text-[10px] text-fg-4">{number(assetSummary('commercial')?.exact_unit_matches)} exact units · {money(assetSummary('commercial')?.annual_rent_at_risk_aed, true)} rent</p>
					</button>
				</div>
			</section>

			<section class="mt-3 overflow-hidden rounded-lg border border-info-border bg-info-bg">
				<div class="flex flex-col gap-3 px-4 py-3.5 lg:flex-row lg:items-center lg:justify-between">
					<div class="flex items-start gap-3"><ShieldCheck class="mt-0.5 flex-none text-info" size={18} /><div><p class="text-sm font-semibold text-fg-1">Evidence-scored property candidates</p><p class="mt-0.5 text-xs leading-5 text-fg-2">{dashboard?.coverage.matching_method}. {dashboard?.coverage.caveat}</p></div></div>
					<div class="flex flex-none items-center gap-2 font-mono text-[10px] uppercase tracking-[0.06em] text-fg-3"><Database size={13} /><span>{number(dashboard?.coverage.exact_unit_matches)} exact units</span><span>·</span><span>{number(dashboard?.coverage.rental_rows)} leases</span><span>·</span><span>complete through {shortDate(dashboard?.coverage.data_complete_through)}</span></div>
				</div>
			</section>

			{#if showSaved}
				<section id="crm-saved-workspace" class="mt-3 scroll-mt-20 ui-surface p-4">
					<div class="flex flex-col justify-between gap-3 sm:flex-row sm:items-end">
						<div>
							<p class="font-mono text-[10px] uppercase tracking-[0.08em] text-fg-4">Saved workspace</p>
							<h2 class="mt-1 text-lg font-semibold text-fg-1">Lead and owner folders</h2>
							<p class="mt-1 text-xs text-fg-4">Work across the combined registries or open one source import without mixing areas.</p>
						</div>
						{#if ownerRegistry?.summary.multi_property_owners}
							<span class="rounded-full border border-info-border bg-info-bg px-3 py-1.5 text-[10px] font-semibold text-info">{number(ownerRegistry.summary.multi_property_owners)} multi-property owners identified</span>
						{/if}
					</div>
					<div class="mt-4 grid gap-2 md:grid-cols-2 xl:grid-cols-4">
						<button type="button" class={`rounded-xl border p-4 text-left transition ${savedFolder === 'manual' ? 'border-navy bg-panel ring-1 ring-navy/10' : 'border-border hover:bg-panel'}`} onclick={() => openSavedFolder('manual')}>
							<div class="flex items-center justify-between"><span class="flex h-8 w-8 items-center justify-center rounded-lg bg-card text-fg-2"><BookmarkCheck size={15} /></span><span class="font-mono text-sm font-semibold text-fg-1">{number(savedQuery.data?.length)}</span></div>
							<p class="mt-3 text-sm font-semibold text-fg-1">My saved prospects</p>
							<p class="mt-1 text-[10px] leading-4 text-fg-4">Properties manually shortlisted by the agent.</p>
						</button>
						<button type="button" class={`rounded-xl border p-4 text-left transition ${savedFolder === 'rental_ready' ? 'border-success-border bg-success-bg ring-1 ring-success/10' : 'border-border hover:bg-panel'}`} onclick={() => openSavedFolder('rental_ready')}>
							<div class="flex items-center justify-between"><span class="flex h-8 w-8 items-center justify-center rounded-lg bg-success-bg text-success"><KeyRound size={15} /></span><span class="font-mono text-sm font-semibold text-success">{number(contactImportsQuery.data?.reduce((total, item) => total + item.summary.contact_ready, 0))}</span></div>
							<p class="mt-3 text-sm font-semibold text-fg-1">Rental owner leads</p>
							<p class="mt-1 text-[10px] leading-4 text-fg-4">Verified or probable owners linked to the lease pursuit system.</p>
						</button>
						<button type="button" class={`rounded-xl border p-4 text-left transition ${savedFolder === 'registry' ? 'border-info-border bg-info-bg ring-1 ring-info/10' : 'border-border hover:bg-panel'}`} onclick={() => openSavedFolder('registry')}>
							<div class="flex items-center justify-between"><span class="flex h-8 w-8 items-center justify-center rounded-lg bg-info-bg text-info"><UsersRound size={15} /></span><span class="font-mono text-[9px] font-semibold uppercase text-info">Combined</span></div>
							<p class="mt-3 text-sm font-semibold text-fg-1">Current owners & review</p>
							<p class="mt-1 text-[10px] leading-4 text-fg-4">Non-rental current owners and claims requiring verification.</p>
						</button>
						<button type="button" class={`rounded-xl border p-4 text-left transition ${savedFolder === 'prior_owners' ? 'border-error-border bg-error-bg ring-1 ring-error/10' : 'border-border hover:bg-panel'}`} onclick={() => openSavedFolder('prior_owners')}>
							<div class="flex items-center justify-between"><span class="flex h-8 w-8 items-center justify-center rounded-lg bg-error-bg text-error"><History size={15} /></span><span class="font-mono text-sm font-semibold text-error">{number(contactImportsQuery.data?.reduce((total, item) => total + item.summary.former_owners, 0))}</span></div>
							<p class="mt-3 text-sm font-semibold text-fg-1">Prior owners registry</p>
							<p class="mt-1 text-[10px] leading-4 text-fg-4">Seller records and contacts superseded by a later transfer.</p>
						</button>
					</div>
					<div class="mt-5 flex items-center justify-between gap-3 border-t border-border pt-4">
						<div><p class="text-xs font-semibold text-fg-2">Import folders</p><p class="mt-0.5 text-[10px] text-fg-4">Open one upload to keep its area and source context isolated.</p></div>
						<button type="button" class="ui-button" data-variant="ghost" data-size="sm" onclick={openOwnerDataWorkspace}><FileUp size={13} /> Manage imports</button>
					</div>
					<div class="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
						{#each contactImportsQuery.data ?? [] as item (item.id)}
							<button type="button" disabled={!item.list_id} class={`rounded-lg border p-3 text-left transition disabled:opacity-50 ${savedFolder === 'import' && selectedImportId === item.list_id ? 'border-navy bg-panel ring-1 ring-navy/10' : 'border-border bg-card hover:border-info-border hover:bg-panel/50'}`} onclick={() => openSavedFolder('import', item.list_id)}>
								<div class="flex items-start justify-between gap-3"><span class="flex h-8 w-8 flex-none items-center justify-center rounded-lg bg-panel text-fg-3"><FolderOpen size={15} /></span><span class="rounded-full border border-border px-2 py-0.5 font-mono text-[8px] uppercase text-fg-4">{shortDate(item.completed_at)}</span></div>
								<p class="mt-3 truncate text-xs font-semibold text-fg-2">{item.name}</p>
								<p class="mt-1 text-[9px] text-fg-4">{number(item.summary.candidate_rows)} owners · <span class="text-success">{number(item.summary.contact_ready)} rental leads</span> · <span class="text-error">{number(item.summary.former_owners)} prior</span></p>
							</button>
						{/each}
					</div>
				</section>
			{/if}

			{#if !showSaved || savedFolder === 'manual'}
				<section class="mt-3 ui-surface p-4">
				<div class="mb-3 flex items-center justify-between gap-3">
					<div>
						<p class="text-sm font-semibold text-fg-1">Filter pursuit queue</p>
						<p class="mt-0.5 text-xs text-fg-4">Click the opportunity map to drill from area to project to building.</p>
					</div>
					{#if hasFilters}<button type="button" class="ui-button" data-variant="ghost" data-size="sm" onclick={clearFilters}><X size={14} /> Clear filters</button>{/if}
				</div>
				<div class="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
					<label class="grid gap-1.5">
						<span class="text-xs font-semibold text-fg-3">Search leads</span>
						<span class="relative"><Search class="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-fg-4" size={14} /><input bind:value={search} placeholder="Building, project, area or unit…" class="h-10 w-full rounded-md border border-border bg-card pl-9 pr-3 text-sm text-fg-1 outline-none transition focus:border-focus" /></span>
					</label>
					<label class="grid gap-1.5">
						<span class="text-xs font-semibold text-fg-3">Lease window</span>
						<select bind:value={status} onchange={() => (offset = 0)} class="h-10 rounded-md border border-border bg-card px-3 text-sm text-fg-2 outline-none focus:border-focus">
							<option value="">All lease windows</option><option value="expired">Expired · selected lookback</option><option value="expiring_30">Expiring in 30 days</option><option value="expiring_60">Expiring in 31–60 days</option><option value="expiring_90">Expiring in 61–90 days</option>
						</select>
					</label>
					<label class="grid gap-1.5">
						<span class="text-xs font-semibold text-fg-3">Expired lookback</span>
						<select bind:value={expiredDays} onchange={() => (offset = 0)} class="h-10 rounded-md border border-border bg-card px-3 text-sm text-fg-2 outline-none focus:border-focus">
							<option value={30}>Last 30 days</option>
							<option value={60}>Last 60 days</option>
							<option value={90}>Last 90 days</option>
							<option value={120}>Last 120 days</option>
							<option value={180}>Last 6 months</option>
							<option value={365}>Last 1 year</option>
							<option value={548}>Last 18 months</option>
							<option value={730}>Last 2 years</option>
							<option value={1825}>All available history</option>
						</select>
					</label>
					<label class="grid gap-1.5">
						<span class="text-xs font-semibold text-fg-3">Priority</span>
						<select bind:value={priority} onchange={() => (offset = 0)} class="h-10 rounded-md border border-border bg-card px-3 text-sm text-fg-2 outline-none focus:border-focus">
							<option value="">All priorities</option><option value="urgent">Urgent</option><option value="high">High</option><option value="medium">Medium</option>
						</select>
					</label>
					<label class="grid gap-1.5">
						<span class="text-xs font-semibold text-fg-3">{assetClass === 'commercial' ? 'Commercial subtype' : assetClass === 'residential' ? 'Residential subtype' : 'Property type'}</span>
						<select bind:value={propertyType} onchange={() => (offset = 0)} class="h-10 rounded-md border border-border bg-card px-3 text-sm text-fg-2 outline-none focus:border-focus">
							<option value="">{assetClass === 'commercial' ? 'All commercial premises' : assetClass === 'residential' ? 'All homes' : 'All property types'}</option>
							{#each dashboard?.filters.property_types ?? [] as option}<option value={option}>{option}{assetClass === 'commercial' && option !== 'Commercial' ? ' · exact sale match' : ''}</option>{/each}
						</select>
					</label>
					<label class="grid gap-1.5">
						<span class="text-xs font-semibold text-fg-3">Area</span>
						<select bind:value={area} onchange={() => { project = ''; building = ''; breakdown = area ? 'project' : 'area'; offset = 0 }} class="h-10 rounded-md border border-border bg-card px-3 text-sm text-fg-2 outline-none focus:border-focus">
							<option value="">All areas</option>{#each dashboard?.filters.areas ?? [] as option}<option value={option}>{option}</option>{/each}
						</select>
					</label>
					<label class="grid gap-1.5">
						<span class="text-xs font-semibold text-fg-3">Project / community</span>
						<select bind:value={project} disabled={!area} onchange={() => { building = ''; breakdown = project ? 'building' : 'project'; offset = 0 }} class="h-10 rounded-md border border-border bg-card px-3 text-sm text-fg-2 outline-none focus:border-focus disabled:cursor-not-allowed disabled:opacity-55">
							<option value="">{area ? 'All projects / communities' : 'Select an area first'}</option>{#each dashboard?.filters.projects ?? [] as option}<option value={option}>{option}</option>{/each}
						</select>
					</label>
					<label class="grid gap-1.5">
						<span class="text-xs font-semibold text-fg-3">Building</span>
						<select bind:value={building} disabled={!project} onchange={() => (offset = 0)} class="h-10 rounded-md border border-border bg-card px-3 text-sm text-fg-2 outline-none focus:border-focus disabled:cursor-not-allowed disabled:opacity-55">
							<option value="">{project ? 'All buildings' : 'Select a project first'}</option>{#each dashboard?.filters.buildings ?? [] as option}<option value={option}>{option}</option>{/each}
						</select>
					</label>
				</div>
				</section>
			{/if}

			{#if showSaved && savedFolder !== 'manual'}
				<section class="mt-3 grid gap-3 xl:grid-cols-[minmax(0,1fr)_340px]">
					<div class="ui-surface min-w-0 overflow-hidden">
						<header class="border-b border-border px-4 py-4">
							<div class="flex flex-col justify-between gap-3 lg:flex-row lg:items-end">
								<div>
									<p class="font-semibold text-fg-1">{ownerFolderTitle()}</p>
									<p class="mt-0.5 text-xs text-fg-4">{number(ownerRegistry?.total)} deduplicated owner profiles · {savedFolder === 'import' ? 'this import only' : 'accumulated across all imports'}</p>
								</div>
								<button type="button" class="ui-button self-start" data-variant="ghost" data-size="sm" onclick={toggleVisibleOwners}>
									<CheckCircle2 size={13} /> {ownerRegistry?.owners.length && ownerRegistry.owners.every((owner) => selectedOwnerKeys.includes(owner.owner_key)) ? 'Clear page' : 'Select page'}
								</button>
							</div>
							{#if savedFolder === 'rental_ready'}
								<div class="mt-4 flex flex-wrap gap-1.5">
									{#each [['', 'All leases'], ['expired', 'Expired'], ['expiring_30', 'Next 30 days'], ['expiring_60', '31–60 days'], ['expiring_90', '61–90 days']] as option}
										<button type="button" class={`rounded-full border px-3 py-1.5 text-[10px] font-semibold transition ${ownerLeaseWindow === option[0] ? 'border-navy bg-navy text-on-navy' : 'border-border bg-card text-fg-3 hover:border-strong hover:text-fg-1'}`} onclick={() => { ownerLeaseWindow = option[0] as CrmLeadStatus | ''; ownerOffset = 0 }}>{option[1]}</button>
									{/each}
								</div>
							{/if}
							<div class="mt-4 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
								<label class="relative">
									<Search class="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-fg-4" size={13} />
									<input bind:value={ownerSearch} placeholder="Owner, phone or property" class="h-9 w-full rounded-md border border-border bg-card pl-9 pr-3 text-xs text-fg-2 outline-none focus:border-focus" />
								</label>
								<select bind:value={ownerStatus} onchange={() => (ownerOffset = 0)} class="h-9 rounded-md border border-border bg-card px-3 text-xs text-fg-2 outline-none focus:border-focus">
									<option value="">All verification states</option>
									<option value="verified_current_owner">Verified owners</option>
									<option value="probable_current_owner">Probable owners</option>
									<option value="unit_linked_unverified">Ownership review</option>
									<option value="former_owner">Former owners</option>
									<option value="conflicting_claim">Conflicting evidence</option>
									<option value="registry_not_observed">Registry gaps</option>
									<option value="insufficient_property_data">Insufficient property data</option>
									<option value="unmatched">Unmatched</option>
								</select>
								<select bind:value={ownerLeaseWindow} onchange={() => (ownerOffset = 0)} class="h-9 rounded-md border border-border bg-card px-3 text-xs text-fg-2 outline-none focus:border-focus">
									<option value="">All lease windows</option>
									<option value="expired">Expired leases</option>
									<option value="expiring_30">Expiring in 30 days</option>
									<option value="expiring_60">Expiring in 31–60 days</option>
									<option value="expiring_90">Expiring in 61–90 days</option>
								</select>
								<label class="flex h-9 items-center gap-2 rounded-md border border-border bg-card px-3 text-xs text-fg-2"><input type="checkbox" bind:checked={ownerPortfolioOnly} onchange={() => (ownerOffset = 0)} class="h-3.5 w-3.5 accent-navy" /> Multiple properties only</label>
							</div>
							<div class="mt-2 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
								<input bind:value={ownerMinRent} inputmode="numeric" placeholder="Minimum annual rent" class="h-9 rounded-md border border-border bg-card px-3 text-xs text-fg-2 outline-none focus:border-focus" />
								<input bind:value={ownerMaxRent} inputmode="numeric" placeholder="Maximum annual rent" class="h-9 rounded-md border border-border bg-card px-3 text-xs text-fg-2 outline-none focus:border-focus" />
								<input bind:value={ownerMinValue} inputmode="numeric" placeholder="Minimum property value" class="h-9 rounded-md border border-border bg-card px-3 text-xs text-fg-2 outline-none focus:border-focus" />
								<input bind:value={ownerMaxValue} inputmode="numeric" placeholder="Maximum property value" class="h-9 rounded-md border border-border bg-card px-3 text-xs text-fg-2 outline-none focus:border-focus" />
							</div>
						</header>
						{#if selectedOwnerKeys.length}
							<div class="border-b border-info-border bg-info-bg px-4 py-3">
								<div class="flex flex-wrap items-center gap-2">
									<span class="mr-1 text-xs font-semibold text-info">{selectedOwnerKeys.length} selected</span>
									<select bind:value={bulkPipelineStatus} class="h-8 rounded-md border border-info-border bg-card px-2 text-[11px] text-fg-2">
										<option value="">Update status…</option>
										{#each Object.entries(PIPELINE_LABELS) as [value, label]}<option value={value}>{label}</option>{/each}
									</select>
									<div class="flex h-8 items-center gap-1 rounded-md border border-info-border bg-card px-2" title="Highlight selected owners">
										<Highlighter size={12} class="text-fg-4" />
										{#each ['none', 'amber', 'green', 'blue', 'red', 'purple'] as color}
											<button type="button" aria-label={`Use ${color} highlight`} class={`h-4 w-4 rounded-full ${highlightDotClass(color as CrmHighlightColor)} ${bulkHighlightColor === color ? 'ring-2 ring-navy ring-offset-1' : ''}`} onclick={() => (bulkHighlightColor = color as CrmHighlightColor)}></button>
										{/each}
									</div>
									<div class="flex min-w-[260px] flex-1">
										<input bind:value={bulkNote} maxlength="4000" placeholder="Add a note to every selected owner…" class="h-8 min-w-0 flex-1 rounded-l-md border border-info-border bg-card px-3 text-[11px] text-fg-2 outline-none" />
										<button type="button" class="ui-button rounded-l-none" data-variant="primary" data-size="sm" disabled={bulkSaving || (!bulkPipelineStatus && !bulkHighlightColor && !bulkNote.trim())} onclick={applyOwnerBulkUpdate}>{#if bulkSaving}<RefreshCw size={12} class="animate-spin" />{:else}<Save size={12} />{/if} Apply</button>
									</div>
									<button type="button" class="ui-button" data-variant="secondary" data-size="sm" disabled title="WhatsApp automation will be connected in a later phase"><Send size={12} /> WhatsApp sequence · soon</button>
									<button type="button" class="ui-button" data-variant="ghost" data-size="sm" onclick={() => (selectedOwnerKeys = [])}>Clear</button>
								</div>
							</div>
						{/if}
						{#if ownerRegistryQuery.isLoading}
							<CrmPanelSkeleton rows={5} compact />
						{:else if ownerRegistryQuery.isError}
							<div class="grid min-h-80 place-items-center p-8 text-center"><div><CircleAlert class="mx-auto text-error" size={25} /><p class="mt-3 text-sm font-semibold text-fg-1">Owner folder could not be loaded</p><p class="mt-1 max-w-sm text-xs leading-5 text-fg-4">{ownerRegistryQuery.error.message}</p><button type="button" class="ui-button mt-4" data-variant="secondary" data-size="sm" onclick={() => ownerRegistryQuery.refetch()}><RefreshCw size={12} /> Try again</button></div></div>
						{:else if ownerRegistry?.owners.length}
							<div class="divide-y divide-border">
								{#each ownerRegistry.owners as owner (owner.owner_key)}
									{@const primaryProperty = owner.properties[0]}
									{@const ownerWorkspace = ownerWorkspaceByKey.get(owner.owner_key)}
									{@const linkedLeadWorkspace = primaryProperty?.unit_candidate_key ? workspaceByCandidate.get(primaryProperty.unit_candidate_key) : undefined}
									{@const ownerCrmState = ownerWorkspace ?? linkedLeadWorkspace}
									<article class={`grid gap-4 px-4 py-4 transition hover:bg-panel/50 lg:grid-cols-[28px_minmax(190px,1fr)_minmax(220px,1.25fr)_160px] lg:items-center ${highlightRowClass(ownerCrmState?.highlight_color)}`}>
										<div class="flex items-start lg:items-center"><input type="checkbox" checked={selectedOwnerKeys.includes(owner.owner_key)} onchange={() => toggleOwnerSelection(owner.owner_key)} aria-label={`Select ${owner.contact_name}`} class="h-4 w-4 accent-navy" /></div>
										<div class="min-w-0">
											<div class="flex items-center gap-2"><p class="truncate text-sm font-semibold text-fg-1">{owner.contact_name}</p>{#if owner.property_count > 1}<span class="flex-none rounded-full border border-info-border bg-info-bg px-2 py-0.5 text-[9px] font-semibold text-info">{owner.property_count} properties</span>{/if}</div>
											<div class="mt-2 flex flex-wrap gap-x-2 gap-y-1 text-[10px] text-fg-3">
												{#if owner.phone_primary}<a class="hover:text-info hover:underline" href={`tel:${owner.phone_primary}`}>{owner.phone_primary}</a>{/if}
												{#if owner.email_primary}<a class="max-w-full truncate hover:text-info hover:underline" href={`mailto:${owner.email_primary}`}>{owner.email_primary}</a>{/if}
												{#if !owner.phone_primary && !owner.email_primary}<span class="text-warning">Contact details missing</span>{/if}
											</div>
										</div>
										<div class="min-w-0">
											<div class="flex flex-wrap items-center gap-2">
												<span class={`rounded-full border px-2 py-1 text-[9px] font-semibold ${ownershipClass(owner.highest_ownership_status)}`}>{ownershipLabel(owner.highest_ownership_status)} · {owner.highest_confidence_score}</span>
												{#if owner.rental_linked_count}<span class="rounded-full border border-success-border bg-success-bg px-2 py-1 text-[9px] font-semibold text-success">{owner.rental_linked_count} {savedFolder === 'prior_owners' ? 'historic lease records' : 'rental-linked'}</span>{/if}
												{#if ownerCrmState}<span class={`rounded-full border px-2 py-1 text-[9px] font-semibold ${pipelineClass(ownerCrmState.pipeline_status)}`}>{PIPELINE_LABELS[ownerCrmState.pipeline_status]}</span>{/if}
												{#if ownerCrmState?.note_count}<span class="inline-flex items-center gap-1 rounded-full border border-border bg-card px-2 py-1 text-[9px] text-fg-3"><NotebookPen size={10} /> {ownerCrmState.note_count}</span>{/if}
											</div>
											<p class="mt-2 truncate text-xs font-semibold text-fg-2">{primaryProperty?.building_name || primaryProperty?.project_name || 'Property unresolved'}{primaryProperty?.unit_number ? ` · Unit ${primaryProperty.unit_number}` : ''}</p>
											<p class="mt-1 text-[10px] text-fg-4">{primaryProperty?.area_name}{owner.next_lease_end ? ` · next lease ${shortDate(owner.next_lease_end)}` : ''}{primaryProperty?.duplicate_count > 1 ? ` · ${primaryProperty.duplicate_count} rows consolidated` : ''}</p>
											{#if ownerWorkspace?.last_note}<p class="mt-1.5 line-clamp-1 text-[10px] italic text-fg-3">“{ownerWorkspace.last_note}”</p>{/if}
										</div>
										<div class="flex flex-col gap-2">
											{#if owner.annual_rent_aed}<p class="text-right text-xs font-semibold tabular-nums text-fg-2">{money(owner.annual_rent_aed)} <span class="font-normal text-fg-4">rent</span></p>{/if}
											<button type="button" class="ui-button w-full" data-variant="secondary" data-size="sm" onclick={() => openOwnerProfile(owner.owner_key)}>View owner profile <ArrowRight size={12} /></button>
											{#if primaryProperty?.lead_id}<button type="button" class="ui-button w-full" data-variant="ghost" data-size="sm" onclick={() => (selectedLeadId = primaryProperty.lead_id)}>Open lease lead</button>{/if}
										</div>
									</article>
								{/each}
							</div>
							{#if ownerRegistry.total > OWNER_PAGE_SIZE}
								<div class="flex items-center justify-between border-t border-border px-4 py-3">
									<p class="text-[10px] text-fg-4">{number(ownerOffset + 1)}–{number(Math.min(ownerOffset + ownerRegistry.owners.length, ownerRegistry.total))} of {number(ownerRegistry.total)} profiles</p>
									<div class="flex gap-2">
										<button type="button" class="ui-button" data-variant="secondary" data-size="sm" disabled={ownerOffset === 0 || ownerRegistryQuery.isFetching} onclick={() => { ownerOffset = Math.max(0, ownerOffset - OWNER_PAGE_SIZE); selectedOwnerKeys = [] }}>Previous</button>
										<button type="button" class="ui-button" data-variant="secondary" data-size="sm" disabled={ownerOffset + OWNER_PAGE_SIZE >= ownerRegistry.total || ownerRegistryQuery.isFetching} onclick={() => { ownerOffset += OWNER_PAGE_SIZE; selectedOwnerKeys = [] }}>Next</button>
									</div>
								</div>
							{/if}
						{:else}
							<div class="grid min-h-80 place-items-center p-8 text-center"><div><UsersRound class="mx-auto text-fg-4" size={25} /><p class="mt-3 text-sm font-semibold text-fg-1">No owner profiles in this folder</p><p class="mt-1 max-w-sm text-xs leading-5 text-fg-4">Import owner data or broaden the verification filter.</p></div></div>
						{/if}
					</div>
					<aside class="ui-surface h-fit overflow-hidden">
						<div class="border-b border-border px-4 py-4"><div class="flex items-center gap-2"><ShieldCheck size={16} class="text-info" /><p class="font-semibold text-fg-1">Owner intelligence</p></div><p class="mt-1 text-xs leading-5 text-fg-4">One profile per person, with properties accumulated across source files.</p></div>
						<div class="grid grid-cols-2 gap-2 p-4">
							<div class="rounded-lg border border-border bg-panel p-3"><p class="font-mono text-[9px] uppercase text-fg-4">Rental leads</p><p class="mt-1 text-lg font-semibold text-success">{number(ownerRegistry?.summary.rental_owner_profiles)}</p></div>
							<div class="rounded-lg border border-border bg-panel p-3"><p class="font-mono text-[9px] uppercase text-fg-4">Registry</p><p class="mt-1 text-lg font-semibold text-info">{number(ownerRegistry?.summary.registry_owner_profiles)}</p></div>
							<div class="rounded-lg border border-border bg-panel p-3"><p class="font-mono text-[9px] uppercase text-fg-4">Prior owners</p><p class="mt-1 text-lg font-semibold text-error">{number(ownerRegistry?.summary.prior_owner_profiles)}</p></div>
							<div class="rounded-lg border border-border bg-panel p-3"><p class="font-mono text-[9px] uppercase text-fg-4">Needs review</p><p class="mt-1 text-lg font-semibold text-warning">{number(ownerRegistry?.summary.needs_review_profiles)}</p></div>
							<div class="rounded-lg border border-border bg-panel p-3"><p class="font-mono text-[9px] uppercase text-fg-4">Portfolios</p><p class="mt-1 text-lg font-semibold text-fg-1">{number(ownerRegistry?.summary.multi_property_owners)}</p></div>
						</div>
						<div class="border-t border-border bg-panel px-4 py-3"><p class="text-[10px] leading-5 text-fg-3"><strong class="text-fg-2">Identity rule:</strong> multiple properties are joined only when normalized owner and contact identifiers agree. Name-only records remain property-scoped to avoid false portfolios.</p></div>
					</aside>
				</section>
			{:else}
				<section class="mt-3 grid gap-3 xl:grid-cols-[minmax(0,1fr)_380px]">
				<div class="ui-surface min-w-0 overflow-hidden">
					<div class="flex flex-col gap-3 border-b border-border px-4 py-3.5 sm:flex-row sm:items-center sm:justify-between">
						<div><p class="font-semibold text-fg-1">{showSaved ? 'Saved pursuit list' : 'Owner pursuit queue'}</p><p class="mt-0.5 text-xs text-fg-4">{number(displayedTotal)} {showSaved ? 'saved prospects' : 'candidates · ranked by timing and evidence'}</p></div>
						<div class="flex rounded-md bg-panel p-1">
							{#each [['area', 'Area'], ['project', 'Project'], ['building', 'Building']] as item}
								<button type="button" class="rounded px-3 py-1.5 text-xs font-semibold transition-colors {breakdown === item[0] ? 'bg-card text-fg-1 shadow-xs' : 'text-fg-3 hover:text-fg-1'}" onclick={() => { breakdown = item[0] as CrmBreakdownLevel; offset = 0 }}>{item[1]}</button>
							{/each}
						</div>
					</div>

					{#if displayedLeads.length}
						<div class="hidden overflow-x-auto lg:block">
							<table class="w-full min-w-[840px] border-collapse text-left">
								<thead><tr class="border-b border-border bg-panel font-mono text-[10px] uppercase tracking-[0.06em] text-fg-4"><th class="px-4 py-2.5 font-medium">Priority</th><th class="px-3 py-2.5 font-medium">Property candidate</th><th class="px-3 py-2.5 font-medium">Lease signal</th><th class="px-3 py-2.5 text-right font-medium">Rent</th><th class="px-3 py-2.5 font-medium">Agent angle</th><th class="w-10 px-3 py-2.5"><span class="sr-only">Open</span></th></tr></thead>
								<tbody>
									{#each displayedLeads as lead (lead.lead_id)}
										{@const leadWorkspace = workspaceByCandidate.get(lead.unit_candidate_key)}
										<tr class="cursor-pointer border-b border-border transition-colors last:border-0 hover:bg-panel/70 {highlightRowClass(leadWorkspace?.highlight_color)}" onclick={() => (selectedLeadId = lead.lead_id)}>
											<td class="px-4 py-3.5 align-top"><div class="flex items-center gap-2"><span class="inline-flex min-w-8 justify-center rounded-md border px-2 py-1 font-mono text-[11px] font-bold {priorityClass(lead.priority)}">{lead.score}</span><span class="text-xs font-semibold capitalize text-fg-2">{lead.priority}</span></div></td>
											<td class="px-3 py-3.5 align-top"><div class="flex max-w-[280px] items-center gap-2"><p class="min-w-0 flex-1 truncate text-sm font-semibold text-fg-1">{propertyTitle(lead)}</p><span class="flex-none rounded-full border px-2 py-0.5 text-[9px] font-semibold {lead.asset_class === 'commercial' ? 'border-info-border bg-info-bg text-info' : 'border-success-border bg-success-bg text-success'}">{assetLabel(lead)}</span></div>{#if propertyPath(lead)}<p class="mt-0.5 max-w-[280px] truncate text-xs text-fg-3">{propertyPath(lead)}</p>{/if}<p class="mt-1 font-mono text-[10px] text-fg-4"><span class={lead.unit_number ? 'font-bold text-success' : 'text-warning'}>{lead.unit_number ? `Unit ${lead.unit_number}` : 'Unit unresolved'}</span> · {lead.bedrooms} · {lead.size_sqft ? `${number(lead.size_sqft)} sqft` : 'size hidden'} · <span class={confidenceClass(lead.match_confidence)}>{lead.match_confidence} evidence</span></p></td>
											<td class="px-3 py-3.5 align-top"><span class="inline-flex rounded-full px-2 py-1 text-[11px] font-semibold {statusClass(lead.status)}">{statusLabel(lead)}</span><p class="mt-1.5 text-xs text-fg-3">Ends {shortDate(lead.lease_end)}</p></td>
											<td class="px-3 py-3.5 text-right align-top"><p class="text-sm font-semibold tabular-nums text-fg-1">{money(lead.annual_rent_aed)}</p><p class="mt-0.5 text-xs text-fg-4">per year</p></td>
											<td class="px-3 py-3.5 align-top"><div class="flex flex-wrap gap-1.5">{#if lead.ownership_timing === 'sale_during_lease'}<span class="rounded bg-warning-bg px-2 py-1 text-[10px] font-semibold text-warning">Ownership review</span>{:else}<span class="rounded bg-success-bg px-2 py-1 text-[10px] font-semibold text-success">{lead.asset_class === 'commercial' ? 'Lease / occupy' : 'Renew / re-let'}</span>{/if}{#if lead.sale_conversation}<span class="rounded bg-info-bg px-2 py-1 text-[10px] font-semibold text-info">{lead.asset_class === 'commercial' ? 'Investment sale' : 'Possible sale'}</span>{/if}{#if leadWorkspace}<span class="rounded border px-2 py-1 text-[10px] font-semibold {pipelineClass(leadWorkspace.pipeline_status)}">{PIPELINE_LABELS[leadWorkspace.pipeline_status]}{leadWorkspace.note_count ? ` · ${leadWorkspace.note_count} note${leadWorkspace.note_count === 1 ? '' : 's'}` : ''}</span>{/if}</div></td>
										<td class="px-3 py-3.5 align-middle text-fg-4">
											<button
												type="button"
												class="rounded p-1.5 transition hover:bg-card hover:text-success"
												aria-label={savedByCandidate.has(lead.unit_candidate_key) ? 'Remove from saved list' : 'Save prospect'}
												title={savedByCandidate.has(lead.unit_candidate_key) ? 'Remove from saved list' : 'Save prospect'}
												disabled={savingCandidateKey === lead.unit_candidate_key}
												onclick={(event) => { event.stopPropagation(); toggleSaved(lead) }}
											>
												{#if savedByCandidate.has(lead.unit_candidate_key)}<BookmarkCheck size={16} class="text-success" />{:else}<Bookmark size={16} />{/if}
											</button>
										</td>
										</tr>
									{/each}
								</tbody>
							</table>
						</div>
						<div class="divide-y divide-border lg:hidden">
							{#each displayedLeads as lead (lead.lead_id)}
								{@const leadWorkspace = workspaceByCandidate.get(lead.unit_candidate_key)}
								<button type="button" class="block w-full p-4 text-left transition-colors hover:bg-panel {highlightRowClass(leadWorkspace?.highlight_color)}" onclick={() => (selectedLeadId = lead.lead_id)}>
								<div class="flex items-start justify-between gap-3"><div class="min-w-0"><div class="flex items-center gap-2"><p class="truncate text-sm font-semibold text-fg-1">{propertyTitle(lead)}</p><span class="flex-none rounded-full border border-border bg-panel px-2 py-0.5 text-[9px] font-semibold text-fg-3">{assetLabel(lead)}</span></div>{#if propertyPath(lead)}<p class="mt-0.5 truncate text-xs text-fg-3">{propertyPath(lead)}</p>{/if}<p class="mt-1 font-mono text-[10px] {lead.unit_number ? 'text-success' : 'text-warning'}">{lead.unit_number ? `Unit ${lead.unit_number}` : 'Unit unresolved'}</p></div><div class="flex items-center gap-1"><span class="rounded-md border px-2 py-1 font-mono text-[11px] font-bold {priorityClass(lead.priority)}">{lead.score}</span><span class="p-1 text-success">{#if savedByCandidate.has(lead.unit_candidate_key)}<BookmarkCheck size={15} />{/if}</span></div></div>
									<div class="mt-3 flex items-center justify-between"><div class="flex items-center gap-1.5"><span class="rounded-full px-2 py-1 text-[11px] font-semibold {statusClass(lead.status)}">{statusLabel(lead)}</span>{#if leadWorkspace}<span class="rounded border px-2 py-1 text-[10px] font-semibold {pipelineClass(leadWorkspace.pipeline_status)}">{PIPELINE_LABELS[leadWorkspace.pipeline_status]}</span>{/if}</div><span class="text-sm font-semibold text-fg-1">{money(lead.annual_rent_aed)}</span></div>
								</button>
							{/each}
						</div>
						{#if !showSaved}<div class="flex items-center justify-between border-t border-border px-4 py-3"><p class="text-xs text-fg-4">{number(offset + 1)}–{number(Math.min(offset + PAGE_SIZE, displayedTotal))} of {number(displayedTotal)}</p><div class="flex gap-2"><button type="button" class="ui-button" data-variant="secondary" data-size="sm" disabled={offset === 0} onclick={() => (offset = Math.max(0, offset - PAGE_SIZE))}>Previous</button><button type="button" class="ui-button" data-variant="secondary" data-size="sm" disabled={offset + PAGE_SIZE >= displayedTotal} onclick={() => (offset += PAGE_SIZE)}>Next</button></div></div>{/if}
					{:else}
						<div class="grid min-h-72 place-items-center p-8 text-center"><div><House class="mx-auto text-fg-4" size={26} /><p class="mt-3 text-sm font-semibold text-fg-1">No opportunities in this view</p><p class="mt-1 max-w-sm text-xs leading-5 text-fg-3">{dashboard?.coverage.rental_rows ? 'Broaden the filters or lease window to see more owner pursuits.' : 'The CRM is ready; load the normalized rental snapshot to populate its pursuit queue.'}</p></div></div>
					{/if}
				</div>

				<aside class="ui-surface h-fit overflow-hidden">
					<div class="border-b border-border px-4 py-3.5"><div class="flex items-center gap-2"><Building2 size={16} class="text-info" /><p class="font-semibold capitalize text-fg-1">{breakdown} opportunity map</p></div><p class="mt-1 text-xs text-fg-4">Where agents should prospect first</p></div>
					<div class="divide-y divide-border">
						{#each dashboard?.breakdown ?? [] as item}
							<button type="button" class="group block w-full px-4 py-3 text-left transition-colors hover:bg-panel disabled:cursor-default" disabled={item.label === 'Unresolved hierarchy'} onclick={() => selectBreakdown(item.label)}>
								<div class="flex items-center justify-between gap-3"><p class="truncate text-sm font-medium text-fg-1 group-hover:text-info" title={item.label}>{item.label}</p><div class="flex flex-none items-center gap-1.5"><p class="font-mono text-xs font-semibold text-fg-2">{number(item.total)}</p>{#if item.label !== 'Unresolved hierarchy'}<ChevronRight size={14} class="text-fg-4 transition-transform group-hover:translate-x-0.5" />{/if}</div></div><div class="mt-2 h-1.5 overflow-hidden rounded-full bg-panel"><div class="h-full rounded-full bg-info" style={`width: ${Math.max(3, (item.total / maxBreakdownTotal) * 100)}%`}></div></div><div class="mt-2 flex items-center justify-between text-[10px] text-fg-4"><span><strong class="text-error">{item.urgent}</strong> urgent · {item.expired} expired</span><span>{money(item.potential_value_aed, true)} rent</span></div>
							</button>
						{/each}
					</div>
					<div class="border-t border-border bg-panel px-4 py-3"><div class="flex items-start gap-2"><Sparkles class="mt-0.5 flex-none text-info" size={14} /><p class="text-xs leading-5 text-fg-3">Work expired leases first, then the 30-day window before competing agents reach the owner.</p></div></div>
				</aside>
			</section>
			{/if}
		{/if}
	</PageContainer>
</AppFrame>

{#if selectedLeadId}
	<button type="button" class="fixed inset-0 z-[70] cursor-default bg-overlay backdrop-blur-[1px]" onclick={() => (selectedLeadId = null)} aria-label="Close lead"></button>
	<div class="fixed inset-y-0 right-0 z-[80] isolate flex w-full max-w-2xl flex-col border-l border-border bg-card shadow-xl ring-1 ring-black/5" aria-label="Lead evidence" role="dialog" aria-modal="true">
		{#if detailQuery.isLoading}
			<CrmPanelSkeleton rows={5} />
		{:else if detailQuery.isError}
			<div class="p-6"><button type="button" class="float-right ui-button" data-variant="ghost" data-size="icon" onclick={() => (selectedLeadId = null)} aria-label="Close"><X size={16} /></button><p class="font-semibold text-error">Lead evidence unavailable</p><p class="mt-2 text-sm text-fg-3">{detailQuery.error.message}</p></div>
		{:else if detail}
			<header class="border-b border-border px-5 py-4">
					<div class="flex items-start justify-between gap-4">
						<div class="min-w-0"><div class="mb-2 flex flex-wrap items-center gap-2"><span class="rounded-md border px-2 py-1 font-mono text-[11px] font-bold {priorityClass(detail.lead.priority)}">Score {detail.lead.score}</span><span class="rounded-full px-2 py-1 text-[11px] font-semibold {statusClass(detail.lead.status)}">{statusLabel(detail.lead)}</span><span class="inline-flex items-center gap-1 rounded-full border px-2 py-1 text-[11px] font-semibold {detail.lead.asset_class === 'commercial' ? 'border-info-border bg-info-bg text-info' : 'border-success-border bg-success-bg text-success'}">{#if detail.lead.asset_class === 'commercial'}<Store size={11} />{:else}<House size={11} />{/if}{assetLabel(detail.lead)}</span>{#if detail.lead.unit_number}<span class="rounded-full border border-success-border bg-success-bg px-2 py-1 font-mono text-[11px] font-bold text-success">Unit {detail.lead.unit_number}</span>{/if}{#if workspace}<span class="rounded-full border px-2 py-1 text-[11px] font-semibold {pipelineClass(workspace.pipeline_status)}">{PIPELINE_LABELS[workspace.pipeline_status]}</span>{/if}</div><h2 class="truncate text-xl font-semibold text-fg-1">{propertyTitle(detail.lead)}</h2>{#if propertyPath(detail.lead)}<p class="mt-1 text-sm text-fg-3">{propertyPath(detail.lead)}</p>{/if}</div>
						<button type="button" class="ui-button flex-none" data-variant="ghost" data-size="icon" onclick={() => (selectedLeadId = null)} aria-label="Close lead"><X size={17} /></button>
					</div>
					<div class="mt-4 flex flex-wrap gap-2">
						<button type="button" class="ui-button" data-variant="secondary" data-size="sm" disabled={savingCandidateKey === detail.lead.unit_candidate_key} onclick={() => toggleSaved(detail.lead)}>
							{#if savedByCandidate.has(detail.lead.unit_candidate_key)}<BookmarkCheck size={14} class="text-success" /> Saved{:else}<Bookmark size={14} /> Save prospect{/if}
						</button>
						<button type="button" class="ui-button" data-variant="secondary" data-size="sm" onclick={() => openReport(detail.lead.lead_id)}>
							<FileText size={14} /> Generate property report
						</button>
					</div>
			</header>
			<div class="min-h-0 flex-1 overflow-y-auto">
				<section class="border-b border-border p-5">
					<div class="rounded-lg border border-success-border bg-success-bg p-4"><div class="flex items-center gap-2 text-success"><Sparkles size={16} /><p class="text-xs font-bold uppercase tracking-[0.06em]">Next best action</p></div><p class="mt-2 text-sm font-semibold leading-6 text-fg-1">{detail.lead.recommended_action}</p><p class="mt-2 text-xs leading-5 text-fg-2">{detail.lead.lead_reason}</p><button type="button" class="mt-3 inline-flex items-center gap-1.5 text-xs font-semibold text-success" onclick={() => openReport(detail.lead.lead_id)}>Prepare owner brief <ArrowRight size={13} /></button></div>
					<div class="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3">
						<div class="rounded-lg border border-border bg-panel p-3"><p class="font-mono text-[10px] uppercase text-fg-4">Unit number</p><p class="mt-1.5 text-base font-semibold {detail.lead.unit_number ? 'text-success' : 'text-warning'}">{detail.lead.unit_number ?? 'Unresolved'}</p><p class="mt-0.5 text-[11px] text-fg-4">{detail.lead.unit_number ? 'unique sale match' : detail.lead.unit_match_status}</p></div>
						<div class="rounded-lg border border-border bg-panel p-3"><p class="font-mono text-[10px] uppercase text-fg-4">Annualized rent</p><p class="mt-1.5 text-base font-semibold text-fg-1">{money(detail.lead.annual_rent_aed)}</p><p class="mt-0.5 text-[11px] text-fg-4">from {money(detail.lead.contract_amount_aed)} · {detail.lead.contract_term_days} days</p></div>
						<div class="rounded-lg border border-border bg-panel p-3"><p class="font-mono text-[10px] uppercase text-fg-4">Gross yield</p><p class="mt-1.5 text-base font-semibold text-fg-1">{detail.lead.gross_yield_pct ? `${detail.lead.gross_yield_pct.toFixed(2)}%` : '—'}</p><p class="mt-0.5 text-[11px] text-fg-4">rent ÷ matched purchase</p></div>
						<div class="rounded-lg border border-border bg-panel p-3"><p class="font-mono text-[10px] uppercase text-fg-4">Latest purchase</p><p class="mt-1.5 text-base font-semibold text-fg-1">{money(detail.lead.matched_sale_price_aed ?? detail.lead.latest_purchase_price_aed)}</p><p class="mt-0.5 text-[11px] text-fg-4">{shortDate(detail.lead.last_purchase_date)}</p></div>
						<div class="rounded-lg border border-border bg-panel p-3"><p class="font-mono text-[10px] uppercase text-fg-4">Lease term</p><p class="mt-1.5 text-sm font-semibold text-fg-1">{shortDate(detail.lead.lease_start)}</p><p class="mt-0.5 text-[11px] text-fg-4">to {shortDate(detail.lead.lease_end)}</p></div>
						<div class="rounded-lg border border-border bg-panel p-3"><p class="font-mono text-[10px] uppercase text-fg-4">Asset evidence</p><p class="mt-1.5 text-sm font-semibold text-fg-1">{assetLabel(detail.lead)} · {number(detail.lead.size_sqft)} sqft</p><p class="mt-0.5 capitalize text-[11px] {confidenceClass(detail.lead.match_confidence)}">{detail.lead.match_confidence} confidence{detail.lead.matched_sales_property_type ? ` · Matched sale: ${detail.lead.matched_sales_property_type}` : ''}</p></div>
					</div>
					{#if hasCanonicalAddressChange(detail.lead)}
						<div class="mt-3 rounded-lg border border-info-border bg-info-bg p-3.5">
							<div class="flex items-start justify-between gap-3">
								<div><p class="text-xs font-semibold text-fg-1">Standardized property hierarchy</p><p class="mt-1 text-[11px] leading-5 text-fg-3">Registry label: {registryPath(detail.lead)}</p></div>
								<span class="rounded-full border border-info-border bg-card px-2 py-1 font-mono text-[9px] uppercase text-info">{detail.lead.geography_match_status.replaceAll('_', ' ')}</span>
							</div>
						</div>
					{/if}
					{#if detail.agent_signals.length}
						<div class="mt-3 rounded-lg border border-info-border bg-info-bg p-4">
							<p class="font-mono text-[10px] font-bold uppercase tracking-[0.06em] text-info">Verified agent signals</p>
							<ul class="mt-2 space-y-1.5">{#each detail.agent_signals as signal}<li class="flex gap-2 text-xs leading-5 text-fg-2"><span class="mt-2 h-1 w-1 flex-none rounded-full bg-info"></span><span>{signal}</span></li>{/each}</ul>
						</div>
					{/if}
				</section>
				{#if leadContactsQuery.isLoading || importedLeadContacts.length}
					<section class="border-b border-border p-5">
						<div class="flex items-start justify-between gap-3">
							<div class="flex items-center gap-2">
								<UsersRound size={16} class="text-success" />
								<div>
									<h3 class="text-sm font-semibold text-fg-1">Imported owner contacts</h3>
									<p class="mt-0.5 text-xs text-fg-4">Organization data matched to this exact property.</p>
								</div>
							</div>
							{#if leadContactsQuery.isLoading}<RefreshCw size={14} class="animate-spin text-info" />{/if}
						</div>
						<div class="mt-3 space-y-2">
							{#each importedLeadContacts as contact (contact.owner_key)}
								<div class="rounded-lg border border-border bg-panel p-3.5">
									<div class="flex flex-wrap items-start justify-between gap-2">
										<div>
											<p class="text-sm font-semibold text-fg-1">{contact.contact_name}</p>
											<p class="mt-0.5 text-[10px] text-fg-4">{contact.source_lists.join(' · ')} · {contact.source_sheet}{contact.duplicate_count > 1 ? ` · ${contact.duplicate_count} source rows consolidated` : ''}</p>
										</div>
										<span class="rounded-full border px-2 py-1 text-[10px] font-semibold {ownershipClass(contact.ownership_status)}">{ownershipLabel(contact.ownership_status)} · {contact.confidence_score}</span>
									</div>
									<div class="mt-3 flex flex-wrap gap-2">
										{#if contact.phone_primary}<a href={`tel:${contact.phone_primary}`} class="ui-button" data-variant="secondary" data-size="sm"><Phone size={12} /> {contact.phone_primary}</a>{/if}
										{#if contact.email_primary}<a href={`mailto:${contact.email_primary}`} class="ui-button" data-variant="secondary" data-size="sm"><AtSign size={12} /> {contact.email_primary}</a>{/if}
										<button type="button" class="ui-button" data-variant="secondary" data-size="sm" onclick={() => openOwnerProfile(contact.owner_key)}><Building2 size={12} /> {contact.property_count} {contact.property_count === 1 ? 'property' : 'properties'}</button>
									</div>
									<p class="mt-2 text-[11px] leading-5 text-fg-3">{contact.match_reason}</p>
								</div>
							{/each}
						</div>
					</section>
				{/if}
				<section class="border-b border-border p-5">
					<div class="flex items-start justify-between gap-3">
						<div class="flex items-center gap-2"><ClipboardList size={16} class="text-info" /><div><h3 class="text-sm font-semibold text-fg-1">Agent lead workspace</h3><p class="mt-0.5 text-xs text-fg-4">Track enrichment, pursuit status, follow-up, and private notes.</p></div></div>
						{#if workspaceSaving}<RefreshCw size={15} class="animate-spin text-info" />{/if}
					</div>
					{#if workspaceQuery.isLoading}
						<div class="mt-4 overflow-hidden rounded-lg border border-border"><CrmPanelSkeleton rows={1} compact /></div>
					{:else if workspace}
						<div class="mt-4 grid gap-3 sm:grid-cols-2">
							<label class="grid gap-1.5">
								<span class="text-[11px] font-semibold text-fg-3">Pipeline status</span>
								<select bind:value={workspaceDraft.pipeline_status} onchange={() => setPipelineStatus(workspaceDraft.pipeline_status)} class="h-9 rounded-md border border-border bg-card px-3 text-xs text-fg-2 outline-none focus:border-focus">
									<option value="new">New lead</option>
									<option value="researching">Researching owner</option>
									<option value="contact_ready">Contact ready</option>
									<option value="contacted">Contacted</option>
									<option value="qualified">Qualified opportunity</option>
									<option value="nurture">Nurture</option>
									<option value="won">Won / instructed</option>
									<option value="closed">Closed / no action</option>
								</select>
							</label>
							<label class="grid gap-1.5">
								<span class="text-[11px] font-semibold text-fg-3">Next follow-up</span>
								<span class="relative"><CalendarDays class="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-fg-4" size={13} /><input type="date" bind:value={workspaceDraft.next_follow_up} class="h-9 w-full rounded-md border border-border bg-card pl-9 pr-3 text-xs text-fg-2 outline-none focus:border-focus" /></span>
							</label>
						</div>
						<div class="mt-3">
							<div class="flex items-center gap-1.5 text-[11px] font-semibold text-fg-3"><Highlighter size={13} /> Queue highlight</div>
							<div class="mt-2 flex flex-wrap gap-2">
								{#each [['none', 'None'], ['amber', 'Warm'], ['green', 'Priority'], ['blue', 'Research'], ['red', 'Urgent'], ['purple', 'Nurture']] as option}
									<button type="button" class="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1.5 text-[10px] font-semibold transition {workspaceDraft.highlight_color === option[0] ? 'border-navy bg-panel text-fg-1 ring-1 ring-navy/10' : 'border-border text-fg-3 hover:bg-panel'}" onclick={() => setHighlight(option[0] as CrmHighlightColor)}>
										<span class="h-2.5 w-2.5 rounded-full {highlightDotClass(option[0] as CrmHighlightColor)}"></span>{option[1]}
									</button>
								{/each}
							</div>
						</div>
						<div class="mt-4 rounded-lg border border-border bg-panel p-3.5">
							<div class="flex items-center gap-2"><UserRound size={14} class="text-fg-3" /><p class="text-xs font-semibold text-fg-2">Owner/contact enrichment</p><span class="ml-auto rounded-full border border-warning-border bg-warning-bg px-2 py-0.5 text-[9px] font-semibold text-warning">Agent supplied</span></div>
							<div class="mt-3 grid gap-2 sm:grid-cols-2">
								<label class="grid gap-1"><span class="text-[10px] text-fg-4">Owner / contact name</span><input bind:value={workspaceDraft.owner_name} placeholder="Add a verified name" class="h-9 rounded-md border border-border bg-card px-3 text-xs text-fg-2 outline-none focus:border-focus" /></label>
								<label class="grid gap-1"><span class="text-[10px] text-fg-4">Email</span><span class="relative"><AtSign class="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-fg-4" size={12} /><input type="email" bind:value={workspaceDraft.owner_email} placeholder="owner@example.com" class="h-9 w-full rounded-md border border-border bg-card pl-8 pr-3 text-xs text-fg-2 outline-none focus:border-focus" /></span></label>
								<label class="grid gap-1"><span class="text-[10px] text-fg-4">Phone / WhatsApp</span><span class="relative"><Phone class="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-fg-4" size={12} /><input bind:value={workspaceDraft.owner_phone} placeholder="+971…" class="h-9 w-full rounded-md border border-border bg-card pl-8 pr-3 text-xs text-fg-2 outline-none focus:border-focus" /></span></label>
								<label class="grid gap-1"><span class="text-[10px] text-fg-4">Tags</span><input bind:value={workspaceDraft.tags} placeholder="VIP, investor, mortgage" class="h-9 rounded-md border border-border bg-card px-3 text-xs text-fg-2 outline-none focus:border-focus" /></label>
							</div>
							<div class="mt-3 flex justify-end"><button type="button" class="ui-button" data-variant="secondary" data-size="sm" disabled={workspaceSaving} onclick={saveWorkspaceDetails}><Save size={13} /> Save lead details</button></div>
						</div>
						<div class="mt-4">
							<div class="flex items-center justify-between gap-3"><div class="flex items-center gap-2"><NotebookPen size={14} class="text-info" /><p class="text-xs font-semibold text-fg-2">Agent notes</p></div><span class="text-[10px] text-fg-4">{workspace.note_count} note{workspace.note_count === 1 ? '' : 's'}</span></div>
							<div class="mt-2 rounded-lg border border-border bg-card p-2">
								<textarea bind:value={noteBody} rows="3" maxlength="4000" placeholder="Add context from a call, ownership research, valuation conversation, or next action…" class="w-full resize-none bg-transparent px-1 py-1 text-xs leading-5 text-fg-2 outline-none placeholder:text-fg-4"></textarea>
								<div class="flex items-center justify-between border-t border-border px-1 pt-2"><span class="text-[9px] text-fg-4">Private to your organization</span><button type="button" class="ui-button" data-variant="primary" data-size="sm" disabled={!noteBody.trim() || noteSaving} onclick={addWorkspaceNote}>{#if noteSaving}<RefreshCw size={12} class="animate-spin" />{:else}<Send size={12} />{/if} Add note</button></div>
							</div>
							<div class="mt-3 space-y-2">
								{#each workspace.notes as note (note.id)}
									<div class="group rounded-lg border border-border bg-panel px-3 py-2.5"><div class="flex items-start justify-between gap-3"><p class="whitespace-pre-wrap text-xs leading-5 text-fg-2">{note.body}</p><button type="button" class="flex-none rounded p-1 text-fg-4 opacity-0 transition hover:bg-error-bg hover:text-error group-hover:opacity-100" aria-label="Delete note" onclick={() => deleteWorkspaceNote(note.id)}><Trash2 size={12} /></button></div><p class="mt-1.5 font-mono text-[9px] uppercase tracking-[0.04em] text-fg-4">You · {dateTime(note.created_at)}</p></div>
								{:else}
									<p class="rounded-lg border border-dashed border-border px-3 py-4 text-center text-[11px] text-fg-4">No notes yet. Add the first piece of agent context above.</p>
								{/each}
							</div>
						</div>
					{/if}
				</section>
				<section class="border-b border-border p-5"><div class="flex items-center gap-2"><CheckCircle2 size={16} class="text-success" /><h3 class="text-sm font-semibold text-fg-1">Agent pursuit plan</h3></div><ol class="mt-3 space-y-2.5">{#each detail.next_best_actions as action, index}<li class="flex items-start gap-3 text-sm leading-5 text-fg-2"><span class="flex h-5 w-5 flex-none items-center justify-center rounded-full bg-navy font-mono text-[10px] text-on-navy">{index + 1}</span><span>{action}</span></li>{/each}</ol></section>
				<section class="p-5">
					<div class="flex items-center gap-2"><History size={16} class="text-info" /><h3 class="text-sm font-semibold text-fg-1">Property evidence timeline</h3></div><p class="mt-1 text-xs leading-5 text-fg-4">{detail.match_explanation}</p>
					<div class="relative mt-5"><div class="absolute bottom-3 left-[15px] top-3 w-px bg-border"></div><div class="space-y-5">
						{#each detail.timeline as event (event.event_type + event.event_id)}
							{@const Icon = timelineIcon(event)}
							<div class="relative flex gap-3"><div class="z-10 flex h-8 w-8 flex-none items-center justify-center rounded-full border border-border bg-card text-fg-2"><Icon size={14} /></div><div class="min-w-0 flex-1 pt-0.5"><div class="flex items-start justify-between gap-3"><div><p class="text-sm font-semibold text-fg-1">{event.title}</p><p class="mt-0.5 text-xs text-fg-3">{event.description}</p>{#if event.ltv_pct !== null || event.capital_gain_pct !== null}<p class="mt-1 text-[11px] text-info">{event.ltv_pct !== null ? `${event.ltv_pct}% LTV at purchase` : ''}{event.ltv_pct !== null && event.capital_gain_pct !== null ? ' · ' : ''}{event.capital_gain_pct !== null ? `${event.capital_gain_pct > 0 ? '+' : ''}${event.capital_gain_pct}% vs prior sale` : ''}</p>{/if}</div>{#if event.amount_aed}<p class="flex-none text-xs font-semibold tabular-nums text-fg-2">{money(event.amount_aed)}</p>{/if}</div><div class="mt-1.5 flex flex-wrap items-center gap-2 font-mono text-[10px] uppercase tracking-[0.04em] text-fg-4"><span>{shortDate(event.event_date)}</span>{#if event.end_date}<span>→ {shortDate(event.end_date)}</span>{/if}<span>·</span><span>{event.source}</span><span class={confidenceClass(event.confidence)}>· {event.confidence}</span></div></div></div>
						{/each}
					</div></div>
				</section>
			</div>
		{/if}
	</div>
{/if}

{#if selectedOwnerKey}
	<button type="button" class="fixed inset-0 z-[110] cursor-default bg-overlay backdrop-blur-[2px]" onclick={() => (selectedOwnerKey = null)} aria-label="Close owner profile"></button>
	<div class="fixed inset-y-0 right-0 z-[120] isolate flex w-full max-w-2xl flex-col border-l border-border bg-card shadow-2xl" aria-label="Owner portfolio" role="dialog" aria-modal="true">
		{#if ownerProfileQuery.isLoading}
			<CrmPanelSkeleton rows={5} />
		{:else if ownerProfileQuery.isError}
			<div class="p-6"><button type="button" class="float-right ui-button" data-variant="ghost" data-size="icon" onclick={() => (selectedOwnerKey = null)} aria-label="Close"><X size={16} /></button><p class="font-semibold text-error">Owner profile unavailable</p><p class="mt-2 text-sm text-fg-3">{ownerProfileQuery.error.message}</p></div>
		{:else if selectedOwner}
			<header class="border-b border-border px-5 py-5">
				<div class="flex items-start justify-between gap-4">
					<div class="min-w-0">
						<div class="mb-2 flex flex-wrap items-center gap-2"><span class={`rounded-full border px-2.5 py-1 text-[10px] font-semibold ${ownershipClass(selectedOwner.highest_ownership_status)}`}>{ownershipLabel(selectedOwner.highest_ownership_status)} · {selectedOwner.highest_confidence_score}</span>{#if selectedOwner.property_count > 1}<span class="rounded-full border border-info-border bg-info-bg px-2.5 py-1 text-[10px] font-semibold text-info">Portfolio owner</span>{/if}</div>
						<h2 class="truncate text-xl font-semibold text-fg-1">{selectedOwner.contact_name}</h2>
						<p class="mt-1 text-sm text-fg-3">{selectedOwner.property_count} {selectedOwner.property_count === 1 ? 'property' : 'properties'} · {selectedOwner.rental_linked_count} rental-linked</p>
					</div>
					<button type="button" class="ui-button flex-none" data-variant="ghost" data-size="icon" onclick={() => (selectedOwnerKey = null)} aria-label="Close owner profile"><X size={17} /></button>
				</div>
				<div class="mt-4 flex flex-wrap gap-2">
					{#if selectedOwner.phone_primary}<a href={`tel:${selectedOwner.phone_primary}`} class="ui-button" data-variant="secondary" data-size="sm"><Phone size={13} /> {selectedOwner.phone_primary}</a>{/if}
					{#if selectedOwner.email_primary}<a href={`mailto:${selectedOwner.email_primary}`} class="ui-button" data-variant="secondary" data-size="sm"><AtSign size={13} /> {selectedOwner.email_primary}</a>{/if}
				</div>
			</header>
			<div class="min-h-0 flex-1 overflow-y-auto">
				<section class="grid grid-cols-2 gap-2 border-b border-border p-5 sm:grid-cols-4">
					<div class="rounded-lg border border-border bg-panel p-3"><p class="font-mono text-[9px] uppercase text-fg-4">Properties</p><p class="mt-1 text-lg font-semibold text-fg-1">{selectedOwner.property_count}</p></div>
					<div class="rounded-lg border border-border bg-panel p-3"><p class="font-mono text-[9px] uppercase text-fg-4">Rental leads</p><p class="mt-1 text-lg font-semibold text-success">{selectedOwner.contact_ready_count}</p></div>
					<div class="rounded-lg border border-border bg-panel p-3"><p class="font-mono text-[9px] uppercase text-fg-4">Portfolio rent</p><p class="mt-1 text-lg font-semibold text-fg-1">{money(selectedOwner.annual_rent_aed, true)}</p></div>
					<div class="rounded-lg border border-border bg-panel p-3"><p class="font-mono text-[9px] uppercase text-fg-4">Next lease</p><p class="mt-1 text-sm font-semibold text-fg-1">{shortDate(selectedOwner.next_lease_end)}</p></div>
				</section>
				<section class="p-5">
					<div class="flex items-center gap-2"><Building2 size={16} class="text-info" /><h3 class="text-sm font-semibold text-fg-1">Known property portfolio</h3></div>
					<p class="mt-1 text-xs leading-5 text-fg-4">Properties are accumulated across every organization upload sharing the same normalized owner and contact identity.</p>
					<div class="mt-4 space-y-3">
						{#each selectedOwner.properties as property (property.property_key)}
							<article class="rounded-xl border border-border bg-panel p-4">
								<div class="flex flex-wrap items-start justify-between gap-3">
									<div class="min-w-0"><p class="truncate text-sm font-semibold text-fg-1">{property.building_name || property.project_name || 'Property unresolved'}</p><p class="mt-1 text-xs text-fg-3">{property.unit_number ? `Unit ${property.unit_number}` : 'Unit not supplied'}{property.area_name ? ` · ${property.area_name}` : ''}</p></div>
									<span class={`rounded-full border px-2 py-1 text-[9px] font-semibold ${ownershipClass(property.ownership_status)}`}>{ownershipLabel(property.ownership_status)} · {property.confidence_score}</span>
								</div>
								<div class="mt-3 grid gap-2 sm:grid-cols-2">
									<div class="rounded-lg border border-border bg-card p-3">
										<div class="flex items-center gap-1.5"><FileText size={12} class="text-fg-4" /><p class="font-mono text-[9px] uppercase tracking-wide text-fg-4">Imported owner record</p></div>
										<div class="mt-2 grid grid-cols-2 gap-x-3 gap-y-2 text-[10px]">
											<div><p class="text-fg-4">Transaction date</p><p class="mt-0.5 font-semibold text-fg-2">{shortDate(property.imported_transaction_date)}</p></div>
											<div><p class="text-fg-4">Sale price</p><p class="mt-0.5 font-semibold text-fg-2">{money(property.imported_transaction_price_aed)}</p></div>
											<div><p class="text-fg-4">Property type</p><p class="mt-0.5 font-semibold text-fg-2">{property.imported_property_type || 'Not supplied'}</p></div>
											<div><p class="text-fg-4">Unit</p><p class="mt-0.5 font-semibold text-fg-2">{property.unit_number || 'Not supplied'}</p></div>
										</div>
									</div>
									<div class="rounded-lg border border-info-border bg-info-bg/40 p-3">
										<div class="flex items-center justify-between gap-2"><div class="flex items-center gap-1.5"><Database size={12} class="text-info" /><p class="font-mono text-[9px] uppercase tracking-wide text-info">DLD record</p></div>{#if property.registry_market_status}<span class="rounded-full border border-info-border bg-card px-1.5 py-0.5 text-[8px] font-semibold text-info">{property.registry_market_status}</span>{/if}</div>
										<div class="mt-2 grid grid-cols-2 gap-x-3 gap-y-2 text-[10px]">
											<div><p class="text-fg-4">Latest recorded sale</p><p class="mt-0.5 font-semibold text-fg-2">{shortDate(property.registry_sale_date)}</p></div>
											<div><p class="text-fg-4">Recorded price</p><p class="mt-0.5 font-semibold text-fg-2">{money(property.registry_sale_price_aed)}</p></div>
											<div><p class="text-fg-4">Type / bedrooms</p><p class="mt-0.5 font-semibold text-fg-2">{property.registry_property_type || '—'}{property.registry_bedrooms ? ` · ${property.registry_bedrooms}` : ''}</p></div>
											<div><p class="text-fg-4">Recorded size</p><p class="mt-0.5 font-semibold text-fg-2">{property.registry_size_sqft ? `${number(property.registry_size_sqft)} sqft` : '—'}</p></div>
											<div><p class="text-fg-4">Built-up area</p><p class="mt-0.5 font-semibold text-fg-2">{property.registry_built_up_area_sqft ? `${number(property.registry_built_up_area_sqft)} sqft` : '—'}</p></div>
											<div><p class="text-fg-4">Recorded price / sqft</p><p class="mt-0.5 font-semibold text-fg-2">{property.registry_price_per_sqft_aed ? `${money(property.registry_price_per_sqft_aed)} / sqft` : '—'}</p></div>
										</div>
									</div>
								</div>
								<div class="mt-2 grid grid-cols-2 gap-2 text-[10px]"><div><p class="text-fg-4">Lease expiry</p><p class="mt-0.5 font-semibold text-fg-2">{shortDate(property.lease_end)}</p></div><div><p class="text-fg-4">Annual rent</p><p class="mt-0.5 font-semibold text-fg-2">{money(property.annual_rent_aed)}</p></div></div>
								<p class="mt-3 text-[11px] leading-5 text-fg-3">{property.match_reason}</p>
								<div class="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-border pt-3"><p class="text-[9px] text-fg-4">{property.source_lists.join(' · ')}{property.duplicate_count > 1 ? ` · ${property.duplicate_count} source rows consolidated` : ''}</p>{#if property.lead_id}<button type="button" class="ui-button" data-variant="secondary" data-size="sm" onclick={() => { selectedOwnerKey = null; selectedLeadId = property.lead_id }}>Open lease lead <ArrowRight size={12} /></button>{/if}</div>
							</article>
						{/each}
					</div>
				</section>
			</div>
		{/if}
	</div>
{/if}

{#if showOutreachPreview}
	<button type="button" class="fixed inset-0 z-[90] cursor-default bg-overlay backdrop-blur-[2px]" onclick={() => (showOutreachPreview = false)} aria-label="Close owner data workspace"></button>
	<div class="fixed inset-x-3 top-1/2 z-[100] mx-auto max-h-[92vh] max-w-7xl -translate-y-1/2 overflow-y-auto rounded-xl border border-border bg-card shadow-2xl" role="dialog" aria-modal="true" aria-label="Owner data workspace">
		<header class="sticky top-0 z-10 flex items-start justify-between gap-4 border-b border-border bg-card/95 px-6 py-5 backdrop-blur">
			<div>
				<div class="flex items-center gap-2">
					<UsersRound size={18} class="text-info" />
					<h2 class="text-lg font-semibold text-fg-1">Owner data workspace</h2>
					<span class="rounded-full border border-success-border bg-success-bg px-2 py-0.5 text-[10px] font-semibold text-success">Live</span>
				</div>
				<p class="mt-1.5 max-w-3xl text-xs leading-5 text-fg-3">
					Upload an owner database, verify each property against transaction evidence, and turn current rental owners into an actionable contact list.
				</p>
			</div>
			<button type="button" class="ui-button flex-none" data-variant="ghost" data-size="icon" onclick={() => (showOutreachPreview = false)} aria-label="Close"><X size={17} /></button>
		</header>
		<div class="grid min-h-[640px] lg:grid-cols-[310px_minmax(0,1fr)]">
			<aside class="border-b border-border bg-panel/60 p-5 lg:border-b-0 lg:border-r">
				<section>
					<div class="flex items-center gap-2">
						<div class="flex h-8 w-8 items-center justify-center rounded-lg bg-info-bg text-info"><FileUp size={15} /></div>
						<div>
							<p class="text-sm font-semibold text-fg-1">Import owner records</p>
							<p class="text-[10px] text-fg-4">CSV or XLSX · up to 50 MB</p>
						</div>
					</div>
					<label class="mt-4 block cursor-pointer rounded-lg border border-dashed border-border bg-card px-4 py-5 text-center transition hover:border-info">
						<input class="sr-only" type="file" accept=".csv,.xlsx" onchange={chooseImportFile} />
						<FileUp class="mx-auto text-fg-4" size={20} />
						<p class="mt-2 truncate text-xs font-semibold text-fg-2">{importFile?.name ?? 'Choose owner database'}</p>
						<p class="mt-1 text-[10px] text-fg-4">The original columns remain auditable</p>
					</label>
					<label class="mt-3 grid gap-1">
						<span class="text-[10px] font-medium text-fg-4">List name</span>
						<input bind:value={importListName} placeholder="e.g. Downtown owners · July" class="h-9 rounded-md border border-border bg-card px-3 text-xs text-fg-2 outline-none focus:border-focus" />
					</label>
					<button type="button" class="mt-3 w-full ui-button" data-variant="primary" data-size="sm" disabled={!importFile || importRunning} onclick={runContactImport}>
						{#if importRunning}<RefreshCw size={13} class="animate-spin" /> Verifying records{:else}<ShieldCheck size={13} /> Import and verify{/if}
					</button>
					{#if importRunning}
						<p class="mt-2 text-[10px] leading-4 text-fg-4">Large workbooks can take a few minutes. Contact details remain on this platform; only column labels are used to recognize the schema.</p>
					{/if}
					{#if importError}
						<p class="mt-2 rounded-md border border-error-border bg-error-bg px-3 py-2 text-[10px] leading-4 text-error">{importError}</p>
					{/if}
				</section>

				<section class="mt-6 border-t border-border pt-5">
					<div class="mb-3 flex items-center justify-between">
						<div class="flex items-center gap-2"><History size={14} class="text-fg-3" /><p class="text-xs font-semibold text-fg-2">Import history</p></div>
						<span class="font-mono text-[9px] text-fg-4">{number(contactImportsQuery.data?.length)}</span>
					</div>
					<div class="space-y-1.5">
						{#if contactImportsQuery.isLoading}
							<div class="overflow-hidden rounded-lg border border-border bg-card"><CrmPanelSkeleton rows={3} compact /></div>
						{:else if contactImportsQuery.data?.length}
							{#each contactImportsQuery.data as item (item.id)}
								<div class={`rounded-lg border p-3 transition ${displayedImport?.id === item.id ? 'border-info-border bg-info-bg' : 'border-border bg-card hover:border-info-border'}`}>
									{#if renamingImportId === item.id}
										<form class="flex gap-1.5" onsubmit={(event) => { event.preventDefault(); renameImport(item) }}>
											<input bind:value={importRenameDraft} maxlength="200" aria-label="Import folder name" class="h-8 min-w-0 flex-1 rounded-md border border-info-border bg-card px-2 text-xs text-fg-2 outline-none" />
											<button type="submit" class="ui-button" data-variant="primary" data-size="icon" aria-label="Save import name"><Save size={12} /></button>
											<button type="button" class="ui-button" data-variant="ghost" data-size="icon" aria-label="Cancel rename" onclick={() => { renamingImportId = null; importRenameDraft = '' }}><X size={12} /></button>
										</form>
									{:else}
										<div class="flex items-start gap-2">
											<button type="button" class="min-w-0 flex-1 text-left" onclick={() => (latestImport = item)}>
												<div class="flex items-start justify-between gap-2">
													<p class="line-clamp-2 text-xs font-semibold text-fg-2">{item.name}</p>
													<span class="flex-none rounded-full border border-success-border bg-success-bg px-1.5 py-0.5 font-mono text-[8px] uppercase text-success">{item.status}</span>
												</div>
												<div class="mt-2 flex items-center gap-2 text-[9px]">
													<span class="text-fg-4">{number(item.summary.candidate_rows)} unique claims</span>
													<span class="text-success">{number(item.summary.contact_ready)} rental leads</span>
												</div>
											</button>
											<button type="button" class="ui-button flex-none" data-variant="ghost" data-size="icon" aria-label={`Rename ${item.name}`} onclick={() => { renamingImportId = item.id; importRenameDraft = item.name }}><Pencil size={12} /></button>
											<button type="button" class="ui-button flex-none text-error" data-variant="ghost" data-size="icon" aria-label={`Delete ${item.name}`} onclick={() => (pendingDeleteImport = item)}><Trash2 size={12} /></button>
										</div>
									{/if}
								</div>
							{/each}
						{:else}
							<div class="rounded-lg border border-dashed border-border bg-card p-4 text-center text-[10px] leading-4 text-fg-4">Completed uploads will remain here as an audit trail.</div>
						{/if}
					</div>
				</section>
			</aside>

			<main class="min-w-0 p-5">
				{#if displayedImport}
					<section class="mb-5 rounded-xl border border-success-border bg-success-bg p-4">
						<div class="flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
							<div>
								<div class="flex items-center gap-2"><CheckCircle2 size={15} class="text-success" /><p class="text-sm font-semibold text-fg-1">{displayedImport.name} imported</p></div>
								<p class="mt-1 text-[10px] text-fg-3">{number(displayedImport.mappings.length)} sheets mapped · {displayedImport.mappings[0]?.mapping_source === 'llm' ? 'AI-confirmed schema' : 'deterministic schema mapping'}</p>
							</div>
							<span class="rounded-full border border-success-border bg-card px-2.5 py-1 text-[9px] font-semibold uppercase tracking-wide text-success">{displayedImport.status}</span>
						</div>
						<div class="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-5">
							<div class="rounded-lg border border-success-border bg-card p-3"><p class="font-mono text-[9px] uppercase text-fg-4">Unique claims</p><p class="mt-1 text-lg font-semibold tabular-nums text-fg-1">{number(displayedImport.summary.candidate_rows)}</p></div>
							<div class="rounded-lg border border-success-border bg-card p-3"><p class="font-mono text-[9px] uppercase text-fg-4">Duplicates</p><p class="mt-1 text-lg font-semibold tabular-nums text-info">{number(displayedImport.summary.duplicate_rows_collapsed)}</p></div>
							<div class="rounded-lg border border-success-border bg-card p-3"><p class="font-mono text-[9px] uppercase text-fg-4">Current owners</p><p class="mt-1 text-lg font-semibold tabular-nums text-success">{number(displayedImport.summary.verified_current_owners + displayedImport.summary.probable_current_owners)}</p></div>
							<div class="rounded-lg border border-success-border bg-card p-3"><p class="font-mono text-[9px] uppercase text-fg-4">Rental matches</p><p class="mt-1 text-lg font-semibold tabular-nums text-info">{number(displayedImport.summary.rental_opportunities)}</p></div>
							<div class="rounded-lg border border-success-border bg-card p-3"><p class="font-mono text-[9px] uppercase text-fg-4">Contact ready</p><p class="mt-1 text-lg font-semibold tabular-nums text-fg-1">{number(displayedImport.summary.contact_ready)}</p></div>
						</div>
						{#if displayedImport.status === 'completed' && displayedImport.summary.total_rows > 0 && displayedImport.summary.candidate_rows === 0}
							<div class="mt-3 flex items-start gap-2 rounded-lg border border-warning-border bg-warning-bg px-3 py-2.5 text-[10px] leading-4 text-warning">
								<CircleAlert size={14} class="mt-0.5 flex-none" />
								<p>No owner records were published from this workbook. Delete this import and upload the file again to retry it with the latest column-mapping rules.</p>
							</div>
						{/if}
					</section>
				{/if}

				{#if displayedImport}
					<section class="rounded-xl border border-border bg-panel p-5">
						<div class="flex items-start gap-3"><FolderOpen class="mt-0.5 text-info" size={18} /><div><h3 class="text-sm font-semibold text-fg-1">Published to Saved workspaces</h3><p class="mt-1 max-w-2xl text-xs leading-5 text-fg-3">The upload is retained here only as an audit record. Deduplicated owners are published into the actionable folders under <strong>Saved</strong>.</p></div></div>
						<div class="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
							<button type="button" disabled={!displayedImport.list_id} class="rounded-xl border border-navy bg-card p-4 text-left transition hover:bg-panel disabled:opacity-50" onclick={() => { showOutreachPreview = false; openSavedFolder('import', displayedImport.list_id) }}>
								<div class="flex items-center justify-between"><span class="flex h-9 w-9 items-center justify-center rounded-lg bg-panel text-navy"><FolderOpen size={16} /></span><ArrowRight size={15} class="text-navy" /></div>
								<p class="mt-3 text-sm font-semibold text-fg-1">{displayedImport.name}</p>
								<p class="mt-1 text-xs leading-5 text-fg-3">Open this import alone, with its rental, current-owner, review, and prior-owner records intact.</p>
							</button>
							<button type="button" class="rounded-xl border border-success-border bg-success-bg p-4 text-left transition hover:ring-1 hover:ring-success/20" onclick={() => { showOutreachPreview = false; openSavedFolder('rental_ready') }}>
								<div class="flex items-center justify-between"><span class="flex h-9 w-9 items-center justify-center rounded-lg bg-card text-success"><KeyRound size={16} /></span><ArrowRight size={15} class="text-success" /></div>
								<p class="mt-3 text-sm font-semibold text-fg-1">Rental owner leads</p>
								<p class="mt-1 text-xs leading-5 text-fg-3">{number(displayedImport.summary.contact_ready)} verified or probable contacts from this import were linked to lease opportunities.</p>
							</button>
							<button type="button" class="rounded-xl border border-info-border bg-info-bg p-4 text-left transition hover:ring-1 hover:ring-info/20" onclick={() => { showOutreachPreview = false; openSavedFolder('registry') }}>
								<div class="flex items-center justify-between"><span class="flex h-9 w-9 items-center justify-center rounded-lg bg-card text-info"><UsersRound size={16} /></span><ArrowRight size={15} class="text-info" /></div>
								<p class="mt-3 text-sm font-semibold text-fg-1">Combined owner registry</p>
								<p class="mt-1 text-xs leading-5 text-fg-3">Current non-rental owners and unresolved claims across every import.</p>
							</button>
							<button type="button" class="rounded-xl border border-error-border bg-error-bg p-4 text-left transition hover:ring-1 hover:ring-error/20" onclick={() => { showOutreachPreview = false; openSavedFolder('prior_owners') }}>
								<div class="flex items-center justify-between"><span class="flex h-9 w-9 items-center justify-center rounded-lg bg-card text-error"><History size={16} /></span><ArrowRight size={15} class="text-error" /></div>
								<p class="mt-3 text-sm font-semibold text-fg-1">Prior owners registry</p>
								<p class="mt-1 text-xs leading-5 text-fg-3">{number(displayedImport.summary.former_owners)} seller or superseded-owner records were retained as historical relationship intelligence.</p>
							</button>
						</div>
						<div class="mt-4 rounded-lg border border-border bg-card p-4">
							<div class="flex items-center justify-between"><p class="text-xs font-semibold text-fg-2">Processing safeguards</p><span class="font-mono text-[9px] uppercase text-success">Complete</span></div>
							<ul class="mt-3 grid gap-2 text-[10px] leading-4 text-fg-3 sm:grid-cols-2">
								<li>• {number(displayedImport.summary.duplicate_rows_collapsed)} duplicate source rows consolidated.</li>
								<li>• Exact owner-property evidence retained as provenance.</li>
								<li>• Name-only owners remain property-scoped.</li>
								<li>• Contact details remain organization-private.</li>
							</ul>
						</div>
					</section>
				{:else if contactImportsQuery.isLoading}
					<CrmPanelSkeleton rows={5} />
				{:else}
					<div class="flex min-h-[480px] items-center justify-center"><div class="max-w-sm text-center"><FileUp class="mx-auto text-fg-4" size={23} /><p class="mt-3 text-sm font-semibold text-fg-1">Import your first owner database</p><p class="mt-1 text-xs leading-5 text-fg-4">Results will be verified, deduplicated, and published into the Saved workspaces.</p></div></div>
				{/if}
			</main>
		</div>
	</div>
{/if}

{#if pendingDeleteImport}
	<button type="button" class="fixed inset-0 z-[130] cursor-default bg-overlay backdrop-blur-[2px]" aria-label="Cancel import deletion" onclick={() => (pendingDeleteImport = null)}></button>
	<div class="fixed left-1/2 top-1/2 z-[140] w-[calc(100%-2rem)] max-w-md -translate-x-1/2 -translate-y-1/2 rounded-xl border border-error-border bg-card p-5 shadow-2xl" role="alertdialog" aria-modal="true" aria-labelledby="delete-import-title">
		<div class="flex items-start gap-3">
			<span class="flex h-9 w-9 flex-none items-center justify-center rounded-lg bg-error-bg text-error"><Trash2 size={17} /></span>
			<div class="min-w-0">
				<h2 id="delete-import-title" class="text-base font-semibold text-fg-1">Delete “{pendingDeleteImport.name}”?</h2>
				<p class="mt-2 text-xs leading-5 text-fg-3">
					This removes the source import, its Saved folder, and {number(pendingDeleteImport.summary.candidate_rows)} imported owner claims. Agent notes, CRM statuses, and manually saved properties are retained.
				</p>
			</div>
		</div>
		<div class="mt-5 flex justify-end gap-2">
			<button type="button" class="ui-button" data-variant="secondary" data-size="sm" disabled={deletingImportId !== null} onclick={() => (pendingDeleteImport = null)}>Cancel</button>
			<button type="button" class="ui-button" data-variant="danger" data-size="sm" disabled={deletingImportId !== null} onclick={() => deleteImport(pendingDeleteImport!)}>
				{#if deletingImportId !== null}<RefreshCw size={13} class="animate-spin" /> Deleting{:else}<Trash2 size={13} /> Delete import{/if}
			</button>
		</div>
	</div>
{/if}
