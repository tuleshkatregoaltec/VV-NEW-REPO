<script lang="ts">
import { createQuery } from '@tanstack/svelte-query'
import {
	ArrowLeft,
	Bookmark,
	Check,
	ChevronRight,
	CircleAlert,
	ExternalLink,
	FileSpreadsheet,
	FileUp,
	Inbox,
	Mail,
	MessageCircle,
	MessageSquareText,
	Phone,
	Plus,
	RefreshCw,
	Search,
	ShieldCheck,
	Trash2,
	UserRound,
	UsersRound,
	X
} from 'lucide-svelte'
import type {
	InboundEnquiry,
	InboundImportPreview,
	InboundIntent,
	InboundMatch,
	InboundMatchState,
	InboundStatus,
	InboundWorkspace
} from '$lib/api/inbound'
import { inbound } from '$lib/api/inbound'
import CrmPanelSkeleton from '$lib/components/crm/CrmPanelSkeleton.svelte'
import AppFrame from '$lib/components/layout/AppFrame.svelte'
import PageContainer from '$lib/components/layout/PageContainer.svelte'
import {
	formatCrmStatus as label,
	formatCrmNumber as number,
	formatCrmDate as shortDate
} from '$lib/crm/format'
import { inboundQueries } from '$lib/queries/inbound'

type WorkspaceTab = InboundWorkspace | 'imports'
type MatchLane = 'listings' | 'offplan' | 'owners' | 'units' | 'demand'

const pipeline: InboundStatus[] = [
	'new',
	'assigned',
	'attempted',
	'contacted',
	'qualified',
	'viewing',
	'valuation',
	'signed',
	'won',
	'nurture',
	'closed_lost',
	'disqualified'
]
const mappingFields = [
	['full_name', 'Full name'],
	['first_name', 'First name'],
	['last_name', 'Last name'],
	['phone', 'Phone'],
	['email', 'Email'],
	['whatsapp', 'WhatsApp'],
	['intent', 'Intent'],
	['source', 'Source / channel'],
	['campaign', 'Campaign'],
	['source_lead_id', 'Source lead ID'],
	['notes', 'Message / notes'],
	['locations', 'Location'],
	['property_type', 'Property type'],
	['bedrooms', 'Bedrooms'],
	['budget_min', 'Minimum budget'],
	['budget_max', 'Maximum budget'],
	['timeline', 'Timeline'],
	['financing', 'Financing'],
	['created_at', 'Received date']
] as const

let tab = $state<WorkspaceTab>('inbox')
let search = $state('')
let debouncedSearch = $state('')
let status = $state('')
let selectedId = $state<number | null>(null)
let showCreate = $state(false)
let saving = $state(false)
let errorMessage = $state('')
let noteBody = $state('')
let activityBody = $state('')
let matchLane = $state<MatchLane>('listings')
let importFile = $state<File | null>(null)
let importName = $state('')
let importContext = $state('')
let importPreview = $state<InboundImportPreview | null>(null)
let importBusy = $state(false)
let deletingImportId = $state<number | null>(null)
let lastLoadedDetailId = $state<number | null>(null)
let form = $state({
	full_name: '',
	phone: '',
	email: '',
	source: 'Manual',
	campaign: '',
	notes: ''
})
let qualification = $state({
	intent: 'unknown' as InboundIntent,
	locations: '',
	property_type: '',
	bedrooms: '',
	budget_min: '',
	budget_max: '',
	building: '',
	unit_number: '',
	timeline: ''
})

const listParams = $derived({
	workspace: tab === 'imports' ? undefined : tab,
	status: status || undefined,
	search: debouncedSearch || undefined
})
const listQuery = createQuery(() => inboundQueries.list(listParams, tab !== 'imports'))
const importQuery = createQuery(() => inboundQueries.imports(tab === 'imports'))
const detailQuery = createQuery(() => inboundQueries.detail(selectedId))
const matchesQuery = createQuery(() => inboundQueries.matches(selectedId))
const detail = $derived(detailQuery.data)
const matches = $derived(matchesQuery.data)
const visibleMatches = $derived(matches?.lanes[matchLane] ?? [])
const importMappingReady = $derived(
	Boolean(
		importPreview?.sheets.length &&
			importPreview.sheets.every((sheet) => {
				const fields = new Set(Object.keys(sheet.field_map))
				return (
					(fields.has('full_name') || fields.has('first_name')) &&
					(fields.has('phone') || fields.has('email') || fields.has('whatsapp'))
				)
			})
	)
)

$effect(() => {
	const value = search.trim()
	const timeout = setTimeout(() => (debouncedSearch = value), 250)
	return () => clearTimeout(timeout)
})

$effect(() => {
	if (!detail || detail.id === lastLoadedDetailId) return
	lastLoadedDetailId = detail.id
	const criteria = detail.criteria
	qualification = {
		intent: detail.intent,
		locations: Array.isArray(criteria.locations)
			? criteria.locations.join(', ')
			: String(criteria.locations ?? ''),
		property_type: String(criteria.property_type ?? ''),
		bedrooms: criteria.bedrooms_min === undefined ? '' : String(criteria.bedrooms_min),
		budget_min: String(criteria.budget_min_aed ?? ''),
		budget_max: String(criteria.budget_max_aed ?? criteria.expected_price_aed ?? ''),
		building: String(criteria.building ?? ''),
		unit_number: String(criteria.unit_number ?? ''),
		timeline: String(criteria.timeline ?? '')
	}
})

function intentLabel(intent: InboundIntent) {
	return { unknown: 'Unknown', buy: 'Buyer', rent: 'Tenant', sell: 'Seller', let: 'Landlord' }[
		intent
	]
}

function workspaceTitle() {
	return {
		inbox: 'Lead inbox',
		unqualified: 'Needs qualification',
		qualified: 'Qualified opportunities',
		closed: 'Closed & nurture',
		imports: 'Campaigns & imports'
	}[tab]
}

function criteriaLine(item: InboundEnquiry) {
	if (item.intent === 'unknown') return item.raw_notes || 'Intent has not been established'
	const locations = Array.isArray(item.criteria.locations)
		? item.criteria.locations.join(', ')
		: item.criteria.locations
	const parts = [locations, item.criteria.property_type]
	if (item.criteria.bedrooms_min !== undefined) parts.push(`${item.criteria.bedrooms_min} bed`)
	if (item.criteria.budget_max_aed)
		parts.push(`AED ${Number(item.criteria.budget_max_aed).toLocaleString()}`)
	return parts.filter(Boolean).join(' · ') || 'Brief requires qualification'
}

function sourceLine(item: InboundEnquiry) {
	return [item.source, item.campaign, shortDate(item.enquiry_date)].filter(Boolean).join(' · ')
}

function slaLabel(item: InboundEnquiry) {
	if (item.sla_state === 'responded')
		return `${item.contact_attempt_count} attempt${item.contact_attempt_count === 1 ? '' : 's'}`
	if (item.sla_state === 'overdue') return 'Response overdue'
	if (item.sla_state === 'due_soon') return 'Due within 2 min'
	return 'Within response SLA'
}

function ownershipSignals(item: InboundEnquiry) {
	const enrichment = item.ownership_enrichment
	if (!enrichment.matched) return []
	const signals: string[] = []
	if (enrichment.current_owner) signals.push('Current owner')
	if (enrichment.former_owner) signals.push('Prior owner')
	if (enrichment.rental_owner) signals.push('Rental owner')
	if (enrichment.multiple_property_owner)
		signals.push(`${number(enrichment.known_property_count)} properties`)
	return signals
}

function priorityTone(item: InboundEnquiry) {
	if (item.priority.band === 'high') return 'border-success-border bg-success-bg text-success'
	if (item.priority.band === 'medium') return 'border-info-border bg-info-bg text-info'
	return 'border-border bg-panel text-fg-4'
}

function verificationLabel(item: InboundEnquiry) {
	const enrichment = item.ownership_enrichment
	if (enrichment.verification === 'contact_exact') return `Exact ${enrichment.match_basis} match`
	return 'Name match — verify'
}

function money(value: unknown) {
	const amount = Number(value || 0)
	return amount > 0 ? `AED ${amount.toLocaleString()}` : 'Not available'
}

function percent(value: unknown) {
	if (value === null || value === undefined || value === '') return 'Not available'
	const amount = Number(value)
	return Number.isFinite(amount) ? `${amount.toFixed(1)}%` : 'Not available'
}

function relationshipStatus(value: string) {
	if (value.includes('current_owner')) return 'Current owner'
	if (value === 'former_owner') return 'Prior owner'
	return label(value)
}

function matchLanes(item: InboundEnquiry) {
	if (item.intent === 'buy')
		return [
			{ id: 'listings', label: 'Secondary listings' },
			{ id: 'offplan', label: 'Off-plan projects' },
			{ id: 'owners', label: 'Owner prospects' },
			{ id: 'units', label: 'Off-market units' }
		] as const
	if (item.intent === 'rent')
		return [
			{ id: 'listings', label: 'Rental listings' },
			{ id: 'units', label: 'Lease signals' },
			{ id: 'owners', label: 'Rental owners' }
		] as const
	return [{ id: 'demand', label: 'Qualified demand' }] as const
}

function matchFacts(item: InboundMatch) {
	const snapshot = item.snapshot
	if (item.target_type === 'listing')
		return [
			snapshot.property_type,
			snapshot.bedrooms ? `${snapshot.bedrooms} bed` : null,
			snapshot.size_value ? `${number(Number(snapshot.size_value))} sqft` : null,
			snapshot.listing_age_days !== null && snapshot.listing_age_days !== undefined
				? `${snapshot.listing_age_days} days listed`
				: null
		].filter(Boolean) as string[]
	if (item.target_type === 'project')
		return [
			snapshot.area_name,
			snapshot.unit_type,
			snapshot.unit_bedrooms,
			snapshot.area_from_sqft ? `from ${number(Number(snapshot.area_from_sqft))} sqft` : null,
			snapshot.completion_date ? `Completion ${snapshot.completion_date}` : null
		].filter(Boolean) as string[]
	return []
}

function matchUrl(item: InboundMatch) {
	if (item.target_type === 'listing') return String(item.snapshot.share_url || '')
	if (item.target_type === 'project') return String(item.snapshot.website_url || '')
	return ''
}

function factRows(value: Record<string, unknown>) {
	return Object.entries(value).filter(
		([, item]) => item !== null && item !== '' && item !== undefined
	)
}

function chooseImport(event: Event) {
	const input = event.currentTarget as HTMLInputElement
	importFile = input.files?.[0] ?? null
	if (importFile) importName = importFile.name.replace(/\.(xlsx|csv)$/i, '')
	importPreview = null
	errorMessage = ''
}

async function previewFile() {
	if (!importFile || importBusy) return
	importBusy = true
	errorMessage = ''
	try {
		importPreview = await inbound.preview(importFile, importContext.trim())
	} catch (error) {
		errorMessage = error instanceof Error ? error.message : 'The file could not be inspected.'
	} finally {
		importBusy = false
	}
}

function updateMapping(sheetIndex: number, field: string, header: string) {
	if (!importPreview) return
	const next = structuredClone(importPreview)
	if (header) next.sheets[sheetIndex].field_map[field] = header
	else delete next.sheets[sheetIndex].field_map[field]
	importPreview = next
}

async function confirmImport() {
	if (!importFile || !importPreview || importBusy) return
	importBusy = true
	errorMessage = ''
	try {
		await inbound.upload(importFile, importName.trim(), importContext.trim(), {
			sheets: importPreview.sheets
		})
		importFile = null
		importPreview = null
		importName = ''
		importContext = ''
		await importQuery.refetch()
	} catch (error) {
		errorMessage = error instanceof Error ? error.message : 'The import failed.'
	} finally {
		importBusy = false
	}
}

async function createContact() {
	if (!form.full_name.trim() || saving) return
	saving = true
	try {
		const created = await inbound.create({
			intent: 'unknown',
			record_kind: 'unqualified_contact',
			full_name: form.full_name.trim(),
			phone: form.phone.trim() || undefined,
			email: form.email.trim() || undefined,
			source: form.source.trim() || 'Manual',
			campaign: form.campaign.trim() || undefined,
			notes: form.notes.trim() || undefined,
			criteria: {}
		})
		showCreate = false
		selectedId = created.id
		tab = 'unqualified'
		form = { full_name: '', phone: '', email: '', source: 'Manual', campaign: '', notes: '' }
		await listQuery.refetch()
	} finally {
		saving = false
	}
}

function qualificationCriteria() {
	const bed = qualification.bedrooms === '' ? undefined : Number(qualification.bedrooms)
	return Object.fromEntries(
		Object.entries({
			locations: qualification.locations
				.split(',')
				.map((item) => item.trim())
				.filter(Boolean),
			property_type: qualification.property_type || undefined,
			bedrooms_min: Number.isFinite(bed) ? bed : undefined,
			bedrooms_max: Number.isFinite(bed) ? bed : undefined,
			budget_min_aed: Number(qualification.budget_min) || undefined,
			budget_max_aed: Number(qualification.budget_max) || undefined,
			expected_price_aed: ['sell', 'let'].includes(qualification.intent)
				? Number(qualification.budget_max) || undefined
				: undefined,
			building: qualification.building.trim() || undefined,
			unit_number: qualification.unit_number.trim() || undefined,
			timeline: qualification.timeline.trim() || undefined
		}).filter(([, value]) => value !== undefined && (!Array.isArray(value) || value.length))
	)
}

async function saveQualification(markQualified = false) {
	if (!selectedId || qualification.intent === 'unknown' || saving) return
	saving = true
	try {
		await inbound.update(selectedId, {
			intent: qualification.intent,
			record_kind: 'opportunity',
			criteria: qualificationCriteria(),
			confirmed_data: { intent: qualification.intent, criteria: qualificationCriteria() },
			status: markQualified ? 'qualified' : detail?.status
		})
		await Promise.all([detailQuery.refetch(), matchesQuery.refetch(), listQuery.refetch()])
	} finally {
		saving = false
	}
}

async function updateStatus(value: InboundStatus) {
	if (!selectedId) return
	await inbound.update(selectedId, { status: value })
	await Promise.all([detailQuery.refetch(), listQuery.refetch()])
}

async function logActivity(type: 'contact_attempt' | 'call' | 'email' | 'whatsapp' | 'meeting') {
	if (!selectedId) return
	await inbound.addActivity(selectedId, type, activityBody.trim() || undefined)
	activityBody = ''
	await Promise.all([detailQuery.refetch(), listQuery.refetch()])
}

async function addNote() {
	if (!selectedId || !noteBody.trim()) return
	await inbound.addNote(selectedId, noteBody.trim())
	noteBody = ''
	await detailQuery.refetch()
}

async function refreshMatches() {
	if (!selectedId || !detail?.qualification_complete) return
	await inbound.refreshMatches(selectedId)
	await matchesQuery.refetch()
}

async function setMatchState(item: InboundMatch, state: InboundMatchState) {
	await inbound.updateMatch(item.id, state)
	await Promise.all([matchesQuery.refetch(), detailQuery.refetch()])
}

async function deleteImport(id: number) {
	if (deletingImportId || !confirm('Delete this import and its enquiries?')) return
	deletingImportId = id
	try {
		await inbound.deleteImport(id)
		await importQuery.refetch()
	} finally {
		deletingImportId = null
	}
}

async function updateContactability(payload: {
	consent_status?: 'unknown' | 'provided' | 'withdrawn'
	do_not_contact?: boolean
	preferred_channel?: string | null
}) {
	if (!selectedId) return
	await inbound.update(selectedId, payload)
	await detailQuery.refetch()
}
</script>

<svelte:head><title>Lead inbox · Vitevue CRM</title></svelte:head>

<AppFrame stableScrollGutter>
	<PageContainer variant="wide" class="pb-14">
		<header class="flex flex-col gap-5 border-b border-border pb-6 pt-5 lg:flex-row lg:items-end lg:justify-between">
			<div>
				<a href="/crm" class="mb-3 inline-flex items-center gap-1.5 text-xs font-semibold text-fg-4 hover:text-info"><ArrowLeft size={13} /> Lease opportunity CRM</a>
				<div class="flex items-center gap-3"><span class="flex h-10 w-10 items-center justify-center rounded-lg bg-navy text-on-navy"><Inbox size={19} /></span><div><h1 class="text-2xl font-semibold tracking-tight">Lead inbox</h1><p class="mt-1 text-sm text-fg-3">Respond, qualify, and connect real enquiries to evidence-backed opportunities.</p></div></div>
			</div>
			<div class="flex gap-2"><button class="ui-button" data-variant="secondary" data-size="sm" onclick={() => { tab = 'imports'; selectedId = null }}><FileUp size={14} /> Import</button><button class="ui-button" data-variant="primary" data-size="sm" onclick={() => (showCreate = true)}><Plus size={14} /> Add contact</button></div>
		</header>

		<section class="mt-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
			<div class="ui-surface p-4"><p class="font-mono text-[10px] uppercase text-success">High priority</p><p class="mt-2 text-2xl font-semibold text-success">{number(listQuery.data?.summary.high_priority)}</p><p class="mt-1 text-xs text-fg-4">Strong ownership evidence</p></div>
			<div class="ui-surface p-4"><p class="font-mono text-[10px] uppercase text-error">Response overdue</p><p class="mt-2 text-2xl font-semibold text-error">{number(listQuery.data?.summary.overdue)}</p><p class="mt-1 text-xs text-fg-4">No first attempt recorded</p></div>
			<div class="ui-surface p-4"><p class="font-mono text-[10px] uppercase text-warning">Needs qualification</p><p class="mt-2 text-2xl font-semibold">{number(listQuery.data?.summary.unqualified)}</p><p class="mt-1 text-xs text-fg-4">Intent remains unknown</p></div>
			<div class="ui-surface p-4"><p class="font-mono text-[10px] uppercase text-info">Owner matched</p><p class="mt-2 text-2xl font-semibold">{number(listQuery.data?.summary.owner_matched)}</p><p class="mt-1 text-xs text-fg-4">Current, prior, rental, or portfolio</p></div>
		</section>

		<nav class="mt-4 flex gap-1 overflow-x-auto border-b border-border pb-3">
			{#each [
				{ id: 'inbox', label: 'Inbox', icon: Inbox }, { id: 'unqualified', label: 'Needs qualification', icon: CircleAlert },
				{ id: 'qualified', label: 'Qualified', icon: ShieldCheck }, { id: 'imports', label: 'Campaigns & imports', icon: FileSpreadsheet },
				{ id: 'closed', label: 'Closed & nurture', icon: Check }
			] as item}
				<button class="ui-button shrink-0" data-variant={tab === item.id ? 'primary' : 'ghost'} data-size="sm" onclick={() => { tab = item.id as WorkspaceTab; selectedId = null }}><item.icon size={14} /> {item.label}</button>
			{/each}
		</nav>

		{#if tab === 'imports'}
			<div class="mt-4 grid gap-4 xl:grid-cols-[380px_minmax(0,1fr)]">
				<section class="ui-surface p-5"><h2 class="text-sm font-semibold">Import a real lead source</h2><p class="mt-1 text-xs leading-5 text-fg-4">Preview first. The file is not stored and no contacts are created until you approve the mapping.</p><label class="mt-4 block cursor-pointer rounded-lg border border-dashed border-border bg-panel p-6 text-center"><input class="sr-only" type="file" accept=".csv,.xlsx" onchange={chooseImport} /><FileUp class="mx-auto text-info" size={22} /><p class="mt-2 text-xs font-semibold">{importFile?.name ?? 'Choose CSV or XLSX'}</p></label><input bind:value={importName} class="mt-3 h-10 w-full rounded-md border border-border bg-card px-3 text-sm" placeholder="Campaign / import name" /><textarea bind:value={importContext} class="mt-3 min-h-24 w-full rounded-md border border-border bg-card p-3 text-xs leading-5" placeholder="Optional source context: channel, advert, audience, form questions. This is provenance—not assumed personal intent."></textarea><button class="mt-3 w-full ui-button" data-variant="primary" data-size="sm" disabled={!importFile || importBusy} onclick={previewFile}>{#if importBusy}<RefreshCw class="animate-spin" size={13} /> Inspecting{:else}<Search size={13} /> Preview and map{/if}</button>{#if errorMessage}<p class="mt-3 rounded-md border border-error-border bg-error-bg p-3 text-xs text-error">{errorMessage}</p>{/if}</section>

				<section class="ui-surface overflow-hidden">
					{#if importPreview}<div class="border-b border-border p-5"><div class="flex items-center justify-between"><div><h2 class="text-sm font-semibold">Review mapping</h2><p class="mt-1 text-xs text-fg-4">{number(importPreview.total_rows)} rows · contact details are masked in samples</p></div><button class="ui-button" data-variant="primary" data-size="sm" disabled={importBusy || !importMappingReady} onclick={confirmImport}><Check size={13} /> Approve import</button></div>{#if !importMappingReady}<p class="mt-3 rounded-md border border-error-border bg-error-bg p-3 text-xs text-error">Map a name column and at least one phone, email, or WhatsApp column before approving.</p>{/if}{#each importPreview.warnings as warning}<p class="mt-3 rounded-md border border-warning-border bg-warning-bg p-3 text-xs text-warning">{warning}</p>{/each}</div><div class="max-h-[680px] overflow-y-auto p-5">{#each importPreview.sheets as sheet, sheetIndex}<article class="mb-5 rounded-lg border border-border p-4"><div class="flex items-center justify-between"><h3 class="text-sm font-semibold">{sheet.sheet}</h3><span class="text-xs text-fg-4">{number(sheet.row_count)} rows · header {sheet.header_row} · {sheet.mapping_source === 'ai_assisted' ? 'AI-assisted mapping' : 'deterministic mapping'}</span></div><div class="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">{#each mappingFields as field}<label class="grid gap-1"><span class="text-[9px] font-semibold uppercase text-fg-4">{field[1]}</span><select value={sheet.field_map[field[0]] ?? ''} onchange={(event) => updateMapping(sheetIndex, field[0], (event.currentTarget as HTMLSelectElement).value)} class="h-9 rounded-md border border-border bg-card px-2 text-xs"><option value="">Not mapped</option>{#each sheet.headers as header}<option value={header}>{header}</option>{/each}</select></label>{/each}</div>{#if sheet.sample_rows.length}<div class="mt-4 overflow-x-auto"><table class="w-full text-left text-[10px]"><thead><tr class="border-b border-border text-fg-4">{#each Object.keys(sheet.sample_rows[0]).slice(0, 6) as key}<th class="px-2 py-2 font-semibold uppercase">{label(key)}</th>{/each}</tr></thead><tbody>{#each sheet.sample_rows.slice(0, 3) as row}<tr class="border-b border-border/60">{#each Object.keys(sheet.sample_rows[0]).slice(0, 6) as key}<td class="max-w-36 truncate px-2 py-2">{row[key]}</td>{/each}</tr>{/each}</tbody></table></div>{/if}</article>{/each}</div>
					{:else}<div class="border-b border-border px-5 py-4"><h2 class="text-sm font-semibold">Import history</h2><p class="mt-1 text-xs text-fg-4">Auditable sources. Unqualified rows remain separate from opportunities.</p></div>{#if importQuery.isLoading}<CrmPanelSkeleton rows={5} compact />{:else if importQuery.data?.length}<div class="divide-y divide-border">{#each importQuery.data as item}<article class="flex items-start justify-between gap-4 p-5"><div><p class="text-sm font-semibold">{item.name}</p><p class="mt-1 text-xs text-fg-4">{item.original_filename} · {shortDate(item.completed_at)}</p><div class="mt-3 flex flex-wrap gap-2 text-[10px]"><span class="rounded border border-border px-2 py-1">{number(item.summary.imported)} rows</span><span class="rounded border border-success-border bg-success-bg px-2 py-1 text-success">{number(item.summary.high_priority)} high priority</span><span class="rounded border border-info-border bg-info-bg px-2 py-1 text-info">{number(item.summary.owner_matches)} owner matches</span><span class="rounded border border-border px-2 py-1">{number(item.summary.portfolio_owners)} portfolio owners</span><span class="rounded border border-warning-border bg-warning-bg px-2 py-1 text-warning">{number(item.summary.unqualified_contacts)} unqualified</span><span class="rounded border border-border px-2 py-1">{number(item.summary.duplicates)} duplicates</span></div></div><button class="ui-button text-error" data-variant="ghost" data-size="icon" disabled={deletingImportId === item.id} onclick={() => deleteImport(item.id)}><Trash2 size={14} /></button></article>{/each}</div>{:else}<div class="p-12 text-center text-sm text-fg-4">No genuine lead sources imported yet.</div>{/if}{/if}
				</section>
			</div>
		{:else}
			<section class="mt-4 ui-surface p-4"><div class="grid gap-3 md:grid-cols-[minmax(0,1fr)_220px]"><label class="relative"><Search class="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-fg-4" size={14} /><input bind:value={search} class="h-10 w-full rounded-md border border-border bg-card pl-9 pr-3 text-sm" placeholder="Search name, campaign, message, area…" /></label><select bind:value={status} class="h-10 rounded-md border border-border bg-card px-3 text-sm"><option value="">All stages</option>{#each pipeline as value}<option value={value}>{label(value)}</option>{/each}</select></div></section>

			<div class="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1fr)_500px]">
				<section class="ui-surface overflow-hidden"><header class="flex items-center justify-between border-b border-border px-5 py-4"><div><h2 class="text-sm font-semibold">{workspaceTitle()}</h2><p class="mt-1 text-xs text-fg-4">{number(listQuery.data?.total)} records · ownership-enriched priority order</p></div><button class="ui-button" data-variant="ghost" data-size="icon" onclick={() => listQuery.refetch()}><RefreshCw size={14} class={listQuery.isFetching ? 'animate-spin' : ''} /></button></header>{#if listQuery.isLoading}<CrmPanelSkeleton rows={7} compact />{:else if listQuery.data?.enquiries.length}<div class="divide-y divide-border">{#each listQuery.data.enquiries as item}<button class="grid w-full gap-3 p-4 text-left hover:bg-panel md:grid-cols-[minmax(0,1fr)_150px_145px] {selectedId === item.id ? 'bg-info-bg' : ''}" onclick={() => { selectedId = item.id; matchLane = item.intent === 'sell' || item.intent === 'let' ? 'demand' : 'listings' }}><div class="min-w-0"><div class="flex flex-wrap items-center gap-2"><p class="truncate text-sm font-semibold">{item.contact.full_name}</p><span class="rounded-full border border-border px-2 py-0.5 text-[9px] font-semibold">{intentLabel(item.intent)}</span><span class="rounded-full border px-2 py-0.5 text-[9px] font-semibold {priorityTone(item)}">{label(item.priority.band)} · {item.priority.score}</span></div><p class="mt-1 line-clamp-1 text-xs text-fg-3">{criteriaLine(item)}</p>{#if item.ownership_enrichment.matched}<div class="mt-2 flex flex-wrap items-center gap-1.5">{#each ownershipSignals(item) as signal}<span class="rounded border border-info-border bg-info-bg px-1.5 py-0.5 text-[9px] font-semibold text-info">{signal}</span>{/each}<span class="text-[9px] text-fg-4">{verificationLabel(item)}</span></div>{/if}<p class="mt-1 text-[10px] text-fg-4">{sourceLine(item)}</p></div><div><p class="text-[9px] uppercase text-fg-4">Next action</p><p class="mt-1 text-xs font-semibold">{item.record_kind === 'unqualified_contact' ? 'Qualify intent' : label(item.status)}</p><p class="mt-1 text-[10px] text-fg-4">{item.assigned_user_id ? 'Assigned' : 'Unassigned'}</p></div><div class="md:text-right"><p class="text-xs font-semibold {item.sla_state === 'overdue' ? 'text-error' : item.sla_state === 'due_soon' ? 'text-warning' : 'text-fg-2'}">{slaLabel(item)}</p><p class="mt-1 text-[10px] text-fg-4">{item.next_follow_up ? `Follow up ${shortDate(item.next_follow_up)}` : 'No follow-up set'}</p></div></button>{/each}</div>{:else}<div class="p-12 text-center"><UserRound class="mx-auto text-fg-4" size={24} /><p class="mt-3 text-sm font-semibold">Nothing in {workspaceTitle().toLowerCase()}</p><p class="mt-1 text-xs text-fg-4">New records will appear here when they meet this workspace definition.</p></div>{/if}</section>

				<aside class="ui-surface overflow-hidden xl:sticky xl:top-20 xl:max-h-[calc(100vh-7rem)] xl:overflow-y-auto">{#if !selectedId}<div class="grid min-h-[560px] place-items-center p-8 text-center"><div><Inbox class="mx-auto text-info" size={25} /><p class="mt-3 text-sm font-semibold">Select a contact</p><p class="mt-1 text-xs leading-5 text-fg-4">Source evidence, qualification, next actions, and matching will appear here.</p></div></div>{:else if detailQuery.isLoading}<CrmPanelSkeleton rows={7} />{:else if detail}
					<header class="border-b border-border p-5"><div class="flex items-start justify-between gap-3"><div><div class="flex flex-wrap gap-2"><span class="rounded-full border px-2 py-1 text-[9px] font-semibold {priorityTone(detail)}">{label(detail.priority.band)} · {detail.priority.score}</span><span class="rounded-full border border-border px-2 py-1 text-[9px] font-semibold">{intentLabel(detail.intent)}</span><span class="rounded-full border border-border px-2 py-1 text-[9px]">{label(detail.status)}</span><span class="rounded-full border px-2 py-1 text-[9px] {detail.sla_state === 'overdue' ? 'border-error-border bg-error-bg text-error' : 'border-success-border bg-success-bg text-success'}">{slaLabel(detail)}</span>{#if detail.contact.do_not_contact}<span class="rounded-full border border-error-border bg-error-bg px-2 py-1 text-[9px] font-semibold text-error">Do not contact</span>{/if}</div><h2 class="mt-3 text-xl font-semibold">{detail.contact.full_name}</h2><p class="mt-1 text-xs text-fg-4">{sourceLine(detail)}</p></div><button class="ui-button" data-variant="ghost" data-size="icon" onclick={() => (selectedId = null)}><X size={15} /></button></div><div class="mt-4 flex flex-wrap gap-2">{#if detail.contact.phone}<a class="ui-button" data-variant="secondary" data-size="sm" href={`tel:${detail.contact.phone}`}><Phone size={13} /> Call</a><button class="ui-button" data-variant="secondary" data-size="sm" onclick={() => logActivity('call')}><Check size={13} /> Log call</button>{/if}{#if detail.contact.email}<a class="ui-button" data-variant="secondary" data-size="sm" href={`mailto:${detail.contact.email}`}><Mail size={13} /> Email</a>{/if}{#if detail.contact.whatsapp || detail.contact.phone}<button class="ui-button" data-variant="secondary" data-size="sm" onclick={() => logActivity('whatsapp')}><MessageCircle size={13} /> Log WhatsApp</button>{/if}</div><input bind:value={activityBody} class="mt-3 h-9 w-full rounded-md border border-border bg-card px-3 text-xs" placeholder="Optional outcome before logging contact…" /><div class="mt-3 grid gap-2 sm:grid-cols-2"><label class="grid gap-1"><span class="text-[9px] font-semibold uppercase text-fg-4">Pipeline stage</span><select value={detail.status} onchange={(event) => updateStatus((event.currentTarget as HTMLSelectElement).value as InboundStatus)} class="h-9 rounded-md border border-border bg-card px-3 text-xs">{#each pipeline as value}<option value={value}>{label(value)}</option>{/each}</select></label><label class="grid gap-1"><span class="text-[9px] font-semibold uppercase text-fg-4">Preferred channel</span><select value={detail.contact.preferred_channel ?? ''} onchange={(event) => updateContactability({ preferred_channel: (event.currentTarget as HTMLSelectElement).value || null })} class="h-9 rounded-md border border-border bg-card px-3 text-xs"><option value="">Not confirmed</option><option value="phone">Phone</option><option value="whatsapp">WhatsApp</option><option value="email">Email</option></select></label><label class="grid gap-1"><span class="text-[9px] font-semibold uppercase text-fg-4">Contact consent</span><select value={detail.contact.consent_status} onchange={(event) => updateContactability({ consent_status: (event.currentTarget as HTMLSelectElement).value as 'unknown' | 'provided' | 'withdrawn' })} class="h-9 rounded-md border border-border bg-card px-3 text-xs"><option value="unknown">Unknown</option><option value="provided">Provided</option><option value="withdrawn">Withdrawn</option></select></label><label class="flex items-center gap-2 self-end rounded-md border border-border bg-panel px-3 py-2 text-xs font-semibold"><input type="checkbox" checked={detail.contact.do_not_contact} onchange={(event) => updateContactability({ do_not_contact: (event.currentTarget as HTMLInputElement).checked })} /> Do not contact</label></div></header>

					<section class="border-b border-border p-5"><div class="flex items-center gap-2"><ShieldCheck size={15} class="text-info" /><div><h3 class="text-sm font-semibold">Qualification</h3><p class="mt-0.5 text-[10px] text-fg-4">Agent-confirmed facts control matching. Unknown remains valid.</p></div></div><div class="mt-4 grid gap-3 sm:grid-cols-2"><label class="grid gap-1"><span class="text-[9px] uppercase text-fg-4">Confirmed intent</span><select bind:value={qualification.intent} class="h-9 rounded-md border border-border bg-card px-2 text-xs">{#each ['unknown','buy','rent','sell','let'] as value}<option value={value}>{intentLabel(value as InboundIntent)}</option>{/each}</select></label><label class="grid gap-1"><span class="text-[9px] uppercase text-fg-4">Locations</span><input bind:value={qualification.locations} class="h-9 rounded-md border border-border px-2 text-xs" placeholder="Dubai Marina, JBR" /></label><label class="grid gap-1"><span class="text-[9px] uppercase text-fg-4">Property type</span><input bind:value={qualification.property_type} class="h-9 rounded-md border border-border px-2 text-xs" placeholder="Apartment" /></label><label class="grid gap-1"><span class="text-[9px] uppercase text-fg-4">Bedrooms</span><input type="number" bind:value={qualification.bedrooms} class="h-9 rounded-md border border-border px-2 text-xs" /></label><label class="grid gap-1"><span class="text-[9px] uppercase text-fg-4">Minimum budget</span><input type="number" bind:value={qualification.budget_min} class="h-9 rounded-md border border-border px-2 text-xs" /></label><label class="grid gap-1"><span class="text-[9px] uppercase text-fg-4">Maximum budget / expected price</span><input type="number" bind:value={qualification.budget_max} class="h-9 rounded-md border border-border px-2 text-xs" /></label>{#if ['sell','let'].includes(qualification.intent)}<label class="grid gap-1"><span class="text-[9px] uppercase text-fg-4">Building</span><input bind:value={qualification.building} class="h-9 rounded-md border border-border px-2 text-xs" /></label><label class="grid gap-1"><span class="text-[9px] uppercase text-fg-4">Unit</span><input bind:value={qualification.unit_number} class="h-9 rounded-md border border-border px-2 text-xs" /></label>{/if}<label class="grid gap-1 sm:col-span-2"><span class="text-[9px] uppercase text-fg-4">Timeline</span><input bind:value={qualification.timeline} class="h-9 rounded-md border border-border px-2 text-xs" placeholder="Within 3 months" /></label></div><div class="mt-4 flex gap-2"><button class="ui-button" data-variant="secondary" data-size="sm" disabled={qualification.intent === 'unknown' || saving} onclick={() => saveQualification(false)}>Save confirmed brief</button><button class="ui-button" data-variant="primary" data-size="sm" disabled={qualification.intent === 'unknown' || saving} onclick={() => saveQualification(true)}><ShieldCheck size={13} /> Mark qualified</button></div>{#if detail.status === 'qualified' && !detail.qualification_complete}<p class="mt-3 rounded-md border border-warning-border bg-warning-bg p-3 text-xs text-warning">Add a location plus budget, layout, or property type. Seller and landlord briefs require an exact building and unit.</p>{/if}</section>

					<section class="border-b border-border p-5"><h3 class="text-sm font-semibold">What we know</h3><div class="mt-3 grid gap-3"><article class="rounded-lg border border-border bg-panel p-3"><p class="font-mono text-[9px] uppercase text-fg-4">Observed from source</p>{#if detail.raw_notes}<p class="mt-2 whitespace-pre-wrap text-xs leading-5">{detail.raw_notes}</p>{/if}{#each factRows(detail.observed_data).filter(([key]) => key !== 'message') as fact}<p class="mt-2 text-[10px] text-fg-3"><span class="font-semibold">{label(fact[0])}:</span> {typeof fact[1] === 'object' ? JSON.stringify(fact[1]) : String(fact[1])}</p>{/each}</article>{#if factRows(detail.inferred_data).length}<article class="rounded-lg border border-warning-border bg-warning-bg p-3"><p class="font-mono text-[9px] uppercase text-warning">Suggested — not confirmed</p>{#each factRows(detail.inferred_data) as fact}<p class="mt-2 text-[10px]"><span class="font-semibold">{label(fact[0])}:</span> {typeof fact[1] === 'object' ? JSON.stringify(fact[1]) : String(fact[1])}</p>{/each}</article>{/if}<article class="rounded-lg border border-success-border bg-success-bg p-3"><p class="font-mono text-[9px] uppercase text-success">Agent confirmed</p><p class="mt-2 text-xs">{factRows(detail.confirmed_data).length ? `${intentLabel(detail.intent)} brief saved` : 'No facts have been confirmed yet.'}</p></article></div></section>

					{#if detail.ownership_enrichment.matched}<section class="border-b border-border p-5"><div class="flex items-start justify-between gap-3"><div class="flex items-center gap-2"><UsersRound size={15} class="text-info" /><div><h3 class="text-sm font-semibold">Ownership intelligence</h3><p class="mt-0.5 text-[10px] text-fg-4">{verificationLabel(detail)} against the agency owner registry.</p></div></div><span class="rounded-full border px-2 py-1 text-[9px] font-semibold {priorityTone(detail)}">{label(detail.priority.band)} · {detail.priority.score}</span></div><div class="mt-3 flex flex-wrap gap-2">{#each ownershipSignals(detail) as signal}<span class="rounded border border-info-border bg-info-bg px-2 py-1 text-[10px] font-semibold text-info">{signal}</span>{/each}</div><div class="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4"><div class="rounded-lg border border-border bg-panel p-3"><p class="font-mono text-[9px] uppercase text-fg-4">Current</p><p class="mt-1 text-lg font-semibold">{number(detail.ownership_enrichment.current_property_count)}</p></div><div class="rounded-lg border border-border bg-panel p-3"><p class="font-mono text-[9px] uppercase text-fg-4">Prior</p><p class="mt-1 text-lg font-semibold">{number(detail.ownership_enrichment.prior_property_count)}</p></div><div class="rounded-lg border border-border bg-panel p-3"><p class="font-mono text-[9px] uppercase text-fg-4">Rental</p><p class="mt-1 text-lg font-semibold">{number(detail.ownership_enrichment.rental_property_count)}</p></div><div class="rounded-lg border border-border bg-panel p-3"><p class="font-mono text-[9px] uppercase text-fg-4">Observed value</p><p class="mt-1 text-sm font-semibold">{detail.ownership_enrichment.observed_portfolio_value_aed ? money(detail.ownership_enrichment.observed_portfolio_value_aed) : 'Not available'}</p></div></div><div class="mt-3 space-y-1">{#each detail.priority.reasons as reason}<p class="text-[10px] leading-4 text-fg-3">• {reason}</p>{/each}</div><p class="mt-3 rounded-md border border-border bg-panel p-3 text-[10px] leading-4 text-fg-4">This evidence raises follow-up priority. It does not establish or change the person’s stated intent.</p></section>{/if}

					{#if detail.contact.registry_profiles.length}<section class="border-b border-border p-5"><h3 class="text-sm font-semibold">Matched property relationships</h3><p class="mt-1 text-[10px] text-fg-4">Property-level transaction and lease evidence. Financing is recorded at purchase and is not a current mortgage balance.</p><div class="mt-3 space-y-3">{#each detail.contact.registry_profiles.slice(0, 8) as profile}<article class="rounded-lg border border-border bg-panel p-4"><div class="flex justify-between gap-3"><div><div class="flex flex-wrap items-center gap-2"><p class="text-xs font-semibold">{profile.building_name || profile.project_name || 'Property'} · Unit {profile.unit_number || 'unresolved'}</p><span class="rounded-full border border-border px-2 py-0.5 text-[9px] font-semibold">{relationshipStatus(profile.ownership_status)}</span></div><p class="mt-1 text-[10px] text-fg-4">{profile.identity_reason}</p></div><span class="h-fit rounded-full border border-border px-2 py-1 text-[9px] font-semibold">{label(profile.identity_strength)}</span></div><div class="mt-3 grid gap-2 sm:grid-cols-3"><div class="rounded-md border border-border bg-card p-3"><p class="font-mono text-[9px] uppercase text-fg-4">Owner-record transaction</p><p class="mt-1 text-xs font-semibold">{money(profile.transaction_price_aed)}</p><p class="mt-1 text-[9px] text-fg-4">{profile.transaction_date ? shortDate(profile.transaction_date) : 'Date unavailable'}</p></div><div class="rounded-md border border-border bg-card p-3"><p class="font-mono text-[9px] uppercase text-fg-4">Latest recorded sale</p><p class="mt-1 text-xs font-semibold">{money(profile.latest_sale_price_aed)}</p><p class="mt-1 text-[9px] text-fg-4">{profile.latest_sale_date ? shortDate(profile.latest_sale_date) : 'Date unavailable'} · LTV {percent(profile.ltv_pct)}</p></div><div class="rounded-md border border-border bg-card p-3"><p class="font-mono text-[9px] uppercase text-fg-4">Lease evidence</p><p class="mt-1 text-xs font-semibold">{money(profile.annual_rent_aed)}{profile.annual_rent_aed ? ' / year' : ''}</p><p class="mt-1 text-[9px] text-fg-4">{profile.lease_start ? shortDate(profile.lease_start) : 'Start unavailable'} → {profile.lease_end ? shortDate(profile.lease_end) : 'No linked lease'}{profile.contract_state ? ` · ${label(profile.contract_state)}` : ''}</p></div></div></article>{/each}</div></section>{/if}

					<section class="border-b border-border p-5"><div class="flex items-center justify-between"><div><h3 class="text-sm font-semibold">Opportunity matching</h3><p class="mt-1 text-[10px] text-fg-4">Secondary listings, developer supply, qualified demand, and off-market signals remain separate.</p></div>{#if detail.qualification_complete}<button class="ui-button" data-variant="ghost" data-size="sm" onclick={refreshMatches}><RefreshCw size={13} /> Refresh</button>{/if}</div>{#if !detail.qualification_complete}<div class="mt-3 rounded-lg border border-border bg-panel p-4 text-xs leading-5 text-fg-3">Matching unlocks after an agent confirms intent and the minimum property brief. No inferred owner profile or campaign label can unlock it.</div>{:else}<div class="mt-3 flex gap-1 overflow-x-auto">{#each matchLanes(detail) as lane}<button class="ui-button shrink-0" data-variant={matchLane === lane.id ? 'primary' : 'ghost'} data-size="sm" onclick={() => (matchLane = lane.id as MatchLane)}>{lane.label}</button>{/each}</div>{#if matchLane === 'offplan' && matches?.offplan_last_refresh}<p class="mt-2 text-[9px] text-fg-4">Developer catalog captured {shortDate(matches.offplan_last_refresh)}. Confirm price and availability before presenting.</p>{:else if matchLane === 'listings' && matches?.listing_last_refresh}<p class="mt-2 text-[9px] text-fg-4">{matches.listing_fresh ? 'Active inventory refreshed' : 'Listing catalog captured'} {shortDate(matches.listing_last_refresh)}.{matches.listing_fresh ? '' : ' Confirm availability before presenting.'}</p>{/if}{#if visibleMatches.length}<div class="mt-3 space-y-2">{#each visibleMatches.slice(0, 20) as item}<article class="rounded-lg border border-border bg-panel p-4"><div class="flex justify-between gap-3"><div><p class="text-xs font-semibold">{item.title}</p><p class="mt-1 text-[10px] text-fg-4">{item.subtitle}</p></div><span class="h-fit rounded-full border border-border px-2 py-1 text-[9px] font-semibold">{label(item.fit)} fit</span></div>{#if matchFacts(item).length}<div class="mt-2 flex flex-wrap gap-1.5">{#each matchFacts(item) as fact}<span class="rounded border border-border bg-card px-2 py-1 text-[9px] text-fg-3">{fact}</span>{/each}</div>{/if}<p class="mt-2 text-[10px] leading-4 text-fg-3">{item.reasons.slice(0,4).join(' · ')}</p><div class="mt-3 flex justify-end gap-1">{#if matchUrl(item)}<a class="ui-button" data-variant="ghost" data-size="sm" href={matchUrl(item)} target="_blank" rel="noreferrer"><ExternalLink size={12} /> Open source</a>{/if}<button class="ui-button" data-variant="ghost" data-size="sm" onclick={() => setMatchState(item, item.state === 'saved' ? 'suggested' : 'saved')}><Bookmark size={12} /> {item.state === 'saved' ? 'Saved' : 'Save'}</button><button class="ui-button" data-variant="ghost" data-size="sm" onclick={() => setMatchState(item, 'dismissed')}><X size={12} /> Dismiss</button></div></article>{/each}</div>{:else}<p class="mt-4 text-center text-xs text-fg-4">No evidence-backed matches in this lane.</p>{/if}{/if}</section>

					<section class="p-5"><div class="flex items-center gap-2"><MessageSquareText size={14} class="text-info" /><h3 class="text-sm font-semibold">Shared activity</h3></div><textarea bind:value={noteBody} class="mt-3 min-h-20 w-full rounded-md border border-border p-3 text-xs" placeholder="Add a qualification or follow-up note…"></textarea><button class="mt-2 ui-button" data-variant="secondary" data-size="sm" disabled={!noteBody.trim()} onclick={addNote}><Plus size={12} /> Add note</button>{#if detail.activities.length}<div class="mt-4 space-y-3">{#each detail.activities as activity}<div class="flex gap-3"><span class="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-border bg-panel"><ChevronRight size={12} /></span><div><p class="text-xs font-semibold">{label(activity.activity_type)}</p>{#if activity.body}<p class="mt-1 whitespace-pre-wrap text-xs leading-5 text-fg-3">{activity.body}</p>{/if}<p class="mt-1 text-[9px] text-fg-4">{shortDate(activity.created_at)}</p></div></div>{/each}</div>{/if}</section>
				{:else if detailQuery.isError}<div class="p-8 text-center"><CircleAlert class="mx-auto text-error" size={24} /><p class="mt-3 text-sm font-semibold">Lead evidence unavailable</p><button class="mt-3 ui-button" data-variant="secondary" data-size="sm" onclick={() => detailQuery.refetch()}><RefreshCw size={13} /> Retry</button></div>{/if}</aside>
			</div>
		{/if}
	</PageContainer>
</AppFrame>

{#if showCreate}
	<button class="fixed inset-0 z-[90] bg-overlay" aria-label="Close" onclick={() => (showCreate = false)}></button>
	<div class="fixed left-1/2 top-1/2 z-[100] w-[calc(100%-2rem)] max-w-lg -translate-x-1/2 -translate-y-1/2 rounded-xl border border-border bg-card shadow-2xl" role="dialog" aria-modal="true"><header class="flex items-center justify-between border-b border-border px-6 py-4"><div><h2 class="text-lg font-semibold">Add an unqualified contact</h2><p class="mt-1 text-xs text-fg-4">Record only what was actually received.</p></div><button class="ui-button" data-variant="ghost" data-size="icon" onclick={() => (showCreate = false)}><X size={16} /></button></header><form class="grid gap-3 p-6" onsubmit={(event) => { event.preventDefault(); createContact() }}><label class="grid gap-1"><span class="text-xs font-semibold">Full name</span><input required bind:value={form.full_name} class="h-10 rounded-md border border-border px-3 text-sm" /></label><div class="grid gap-3 sm:grid-cols-2"><label class="grid gap-1"><span class="text-xs font-semibold">Phone</span><input bind:value={form.phone} class="h-10 rounded-md border border-border px-3 text-sm" /></label><label class="grid gap-1"><span class="text-xs font-semibold">Email</span><input type="email" bind:value={form.email} class="h-10 rounded-md border border-border px-3 text-sm" /></label><label class="grid gap-1"><span class="text-xs font-semibold">Source</span><input bind:value={form.source} class="h-10 rounded-md border border-border px-3 text-sm" /></label><label class="grid gap-1"><span class="text-xs font-semibold">Campaign</span><input bind:value={form.campaign} class="h-10 rounded-md border border-border px-3 text-sm" /></label></div><label class="grid gap-1"><span class="text-xs font-semibold">Original message / notes</span><textarea bind:value={form.notes} class="min-h-24 rounded-md border border-border p-3 text-sm"></textarea></label><div class="flex justify-end gap-2 pt-2"><button type="button" class="ui-button" data-variant="secondary" onclick={() => (showCreate = false)}>Cancel</button><button type="submit" class="ui-button" data-variant="primary" disabled={saving}><Plus size={13} /> Add to qualification queue</button></div></form></div>
{/if}
