import { client } from './client'

export type InboundIntent = 'unknown' | 'buy' | 'rent' | 'sell' | 'let'
export type InboundRecordKind = 'unqualified_contact' | 'opportunity'
export type InboundStatus =
	| 'new'
	| 'needs_review'
	| 'assigned'
	| 'attempted'
	| 'contacted'
	| 'qualified'
	| 'viewing'
	| 'valuation'
	| 'signed'
	| 'active'
	| 'won'
	| 'nurture'
	| 'closed_lost'
	| 'disqualified'
export type InboundMatchState = 'suggested' | 'saved' | 'dismissed' | 'contacted' | 'stale'
export type InboundWorkspace = 'inbox' | 'unqualified' | 'qualified' | 'closed'

export interface InboundRegistryProfile {
	owner_key: string
	contact_name: string
	ownership_status: string
	identity_strength: 'exact' | 'possible' | 'weak'
	identity_reason: string
	area_name: string
	project_name: string
	building_name: string
	unit_number: string
	property_type: string
	transaction_date: string | null
	transaction_price_aed: number | null
	latest_sale_date: string | null
	latest_sale_price_aed: number | null
	later_sale_date: string | null
	ltv_pct: number | null
	seller_type: string | null
	lease_start: string | null
	lease_end: string | null
	annual_rent_aed: number | null
	contract_state: string | null
	lead_id: string | null
}

export interface InboundContact {
	id: number
	full_name: string
	phone: string | null
	email: string | null
	whatsapp: string | null
	preferred_language: string | null
	preferred_channel: string | null
	consent_status: string
	do_not_contact: boolean
	registry_profiles: InboundRegistryProfile[]
}

export interface InboundActivity {
	id: number
	activity_type: string
	body: string | null
	user_id: string
	metadata: Record<string, unknown>
	created_at: string
}

export interface InboundOwnershipEnrichment {
	matched: boolean
	match_basis: 'phone' | 'email' | 'name' | 'none'
	verification: 'contact_exact' | 'name_only' | 'none'
	current_owner: boolean
	former_owner: boolean
	rental_owner: boolean
	multiple_property_owner: boolean
	current_property_count: number
	prior_property_count: number
	rental_property_count: number
	known_property_count: number
	observed_portfolio_value_aed: number
	reasons: string[]
}

export interface InboundPriority {
	band: 'high' | 'medium' | 'standard'
	score: number
	opportunity_value_aed: number
	reasons: string[]
}

export interface InboundEnquiry {
	id: number
	contact: InboundContact
	record_kind: InboundRecordKind
	intent: InboundIntent
	status: InboundStatus
	assigned_user_id: string | null
	source: string
	campaign: string | null
	source_import_id: number | null
	enquiry_date: string
	criteria: Record<string, unknown>
	strict_fields: string[]
	raw_notes: string | null
	observed_data: Record<string, unknown>
	inferred_data: Record<string, unknown>
	confirmed_data: Record<string, unknown>
	qualification: Record<string, unknown>
	extraction_confidence: number
	review_reasons: string[]
	next_follow_up: string | null
	first_response_due_at: string | null
	first_contact_at: string | null
	last_contact_at: string | null
	contact_attempt_count: number
	lost_reason: string | null
	sla_state: 'on_time' | 'due_soon' | 'overdue' | 'responded'
	qualification_complete: boolean
	ownership_enrichment: InboundOwnershipEnrichment
	priority: InboundPriority
	tags: string[]
	notes: Array<{ id: number; body: string; user_id: string; created_at: string }>
	activities: InboundActivity[]
	match_count: number
	saved_match_count: number
	created_at: string
	updated_at: string
}

export interface InboundEnquiryList {
	enquiries: InboundEnquiry[]
	total: number
	summary: Record<string, number>
}

export interface InboundEnquiryCreate {
	intent?: InboundIntent
	record_kind?: InboundRecordKind
	full_name: string
	phone?: string
	email?: string
	whatsapp?: string
	source?: string
	campaign?: string
	notes?: string
	criteria?: Record<string, unknown>
	strict_fields?: string[]
	consent_status?: string
}

export interface InboundEnquiryUpdate {
	intent?: InboundIntent
	status?: InboundStatus
	record_kind?: InboundRecordKind
	assigned_user_id?: string | null
	criteria?: Record<string, unknown>
	strict_fields?: string[]
	next_follow_up?: string | null
	tags?: string[]
	notes?: string | null
	confirmed_data?: Record<string, unknown>
	qualification?: Record<string, unknown>
	lost_reason?: string | null
	consent_status?: 'unknown' | 'provided' | 'withdrawn'
	do_not_contact?: boolean
	preferred_channel?: string | null
}

export interface InboundImport {
	id: number
	name: string
	original_filename: string
	status: 'processing' | 'completed' | 'failed'
	summary: {
		total_rows: number
		imported: number
		duplicates: number
		needs_review: number
		buyers: number
		tenants: number
		sellers: number
		landlords: number
		unqualified_contacts: number
		rejected: number
		owner_matches: number
		current_owners: number
		former_owners: number
		rental_owners: number
		portfolio_owners: number
		high_priority: number
	}
	mapping: Record<string, unknown>
	error_message: string | null
	created_at: string
	completed_at: string | null
}

export interface InboundImportPreviewSheet {
	sheet: string
	header_row: number
	headers: string[]
	field_map: Record<string, string>
	sample_rows: Array<Record<string, string>>
	row_count: number
	mapping_source: 'deterministic' | 'ai_assisted'
}

export interface InboundImportPreview {
	original_filename: string
	size_bytes: number
	total_rows: number
	sheets: InboundImportPreviewSheet[]
	warnings: string[]
}

export interface InboundMatch {
	id: number
	target_type: 'owner' | 'unit' | 'listing' | 'project' | 'demand'
	target_key: string
	state: InboundMatchState
	fit: 'exact' | 'near' | 'review' | 'outside'
	title: string
	subtitle: string
	reasons: string[]
	missing_fields: string[]
	snapshot: Record<string, unknown>
	generated_at: string
}

export interface InboundMatches {
	enquiry_id: number
	listing_fresh: boolean
	listing_last_refresh: string | null
	offplan_catalog_available: boolean
	offplan_last_refresh: string | null
	lanes: Record<'owners' | 'units' | 'listings' | 'offplan' | 'demand', InboundMatch[]>
}

export interface InboundListParams {
	workspace?: InboundWorkspace
	intent_group?: 'demand' | 'instructions'
	status?: string
	search?: string
}

export const inbound = {
	list: (params: InboundListParams = {}, signal?: AbortSignal) =>
		client.get<InboundEnquiryList>(
			client.withQuery('/api/v1/crm/inbound/enquiries', { ...params }),
			{ signal }
		),
	get: (id: number, signal?: AbortSignal) =>
		client.get<InboundEnquiry>(`/api/v1/crm/inbound/enquiries/${id}`, { signal }),
	create: (payload: InboundEnquiryCreate) =>
		client.post<InboundEnquiry, InboundEnquiryCreate>('/api/v1/crm/inbound/enquiries', payload),
	update: (id: number, payload: InboundEnquiryUpdate) =>
		client.patch<InboundEnquiry, InboundEnquiryUpdate>(
			`/api/v1/crm/inbound/enquiries/${id}`,
			payload
		),
	addNote: (id: number, body: string) =>
		client.post<InboundEnquiry, { body: string }>(`/api/v1/crm/inbound/enquiries/${id}/notes`, {
			body
		}),
	addActivity: (
		id: number,
		activity_type: 'contact_attempt' | 'call' | 'email' | 'whatsapp' | 'meeting',
		body?: string
	) =>
		client.post<InboundEnquiry, { activity_type: string; body?: string }>(
			`/api/v1/crm/inbound/enquiries/${id}/activities`,
			{ activity_type, body }
		),
	matches: (id: number, signal?: AbortSignal) =>
		client.get<InboundMatches>(`/api/v1/crm/inbound/enquiries/${id}/matches`, { signal }),
	refreshMatches: (id: number, expandUnits = false) =>
		client.post<InboundMatches>(
			`/api/v1/crm/inbound/enquiries/${id}/matches/refresh?expand_units=${expandUnits}`
		),
	updateMatch: (id: number, state: InboundMatchState) =>
		client.patch<InboundMatch, { state: InboundMatchState }>(`/api/v1/crm/inbound/matches/${id}`, {
			state
		}),
	imports: (signal?: AbortSignal) =>
		client.get<InboundImport[]>('/api/v1/crm/inbound/imports', { signal }),
	preview: (file: File, campaignContext = '') => {
		const form = new FormData()
		form.set('file', file)
		form.set('campaign_context', campaignContext)
		return client.post<InboundImportPreview, FormData>('/api/v1/crm/inbound/imports/preview', form)
	},
	upload: (
		file: File,
		name: string,
		campaignContext = '',
		mapping?: Pick<InboundImportPreview, 'sheets'>
	) => {
		const form = new FormData()
		form.set('file', file)
		form.set('name', name)
		form.set('campaign_context', campaignContext)
		if (mapping) form.set('mapping_json', JSON.stringify(mapping))
		return client.post<InboundImport, FormData>('/api/v1/crm/inbound/imports', form)
	},
	deleteImport: (id: number) => client.delete<void>(`/api/v1/crm/inbound/imports/${id}`)
}
