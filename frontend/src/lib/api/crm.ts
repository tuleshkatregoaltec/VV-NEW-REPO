import { client } from './client'

export type CrmLeadStatus = 'expired' | 'expiring_30' | 'expiring_60' | 'expiring_90'
export type CrmLeadPriority = 'urgent' | 'high' | 'medium'
export type CrmBreakdownLevel = 'area' | 'project' | 'building'
export type CrmMatchConfidence = 'high' | 'medium' | 'low'
export type CrmAssetClass = 'residential' | 'commercial' | 'other'

export interface CrmLead {
	lead_id: string
	unit_candidate_key: string
	building_name: string
	project_name: string
	area_name: string
	registry_building_name: string
	registry_project_name: string
	registry_area_name: string
	canonical_location_id: string | null
	geography_match_status: string
	coordinate_precision: string
	latitude: number | null
	longitude: number | null
	asset_class: CrmAssetClass
	property_type: string
	property_subtype: string
	matched_sales_property_type: string | null
	bedrooms: string
	size_sqft: number | null
	contract_amount_aed: number
	contract_term_days: number
	contract_term_months: number | null
	annual_rent_aed: number
	latest_purchase_price_aed: number | null
	unit_number: string | null
	unit_match_status: string
	matching_units: number
	last_purchase_date: string | null
	matched_sale_price_aed: number | null
	gross_yield_pct: number | null
	identity_sale_date: string | null
	identity_sale_price_aed: number | null
	latest_price_per_sqft_aed: number | null
	latest_capital_gain_pct: number | null
	latest_ltv_pct: number | null
	latest_seller_type: string | null
	latest_seller_transaction_count: number | null
	latest_market_status: string | null
	lease_start: string
	lease_end: string
	days_to_expiry: number
	status: CrmLeadStatus
	priority: CrmLeadPriority
	score: number
	contract_state: string
	match_confidence: CrmMatchConfidence
	property_identity_key: string
	ownership_timing: string
	lease_evidence_state: string
	data_complete_through: string | null
	lead_reason: string
	recommended_action: string
	sale_conversation: boolean
	source: string
}

export interface CrmSummary {
	total_leads: number
	urgent: number
	expired_unlet: number
	expiring_30_days: number
	expiring_31_to_60_days: number
	expiring_61_to_90_days: number
	sale_conversation_candidates: number
	annual_rent_at_risk_aed: number
}

export interface CrmBreakdownItem {
	label: string
	total: number
	urgent: number
	expired: number
	expiring_30: number
	expiring_60: number
	expiring_90: number
	potential_value_aed: number
}

export interface CrmAssetBreakdownItem {
	asset_class: CrmAssetClass
	total: number
	urgent: number
	exact_unit_matches: number
	annual_rent_at_risk_aed: number
	property_types: string[]
}

export interface CrmCoverage {
	rental_source: string
	rental_start_date: string | null
	rental_end_date: string | null
	rental_rows: number
	exact_unit_ids_available: boolean
	exact_unit_matches: number
	data_complete_through: string | null
	matching_method: string
	caveat: string
}

export interface CrmDashboardResponse {
	leads: CrmLead[]
	total: number
	limit: number
	offset: number
	summary: CrmSummary
	asset_breakdown: CrmAssetBreakdownItem[]
	breakdown: CrmBreakdownItem[]
	breakdown_level: string
	filters: { areas: string[]; projects: string[]; buildings: string[]; property_types: string[] }
	coverage: CrmCoverage
	as_of: string
}

export interface CrmTimelineEvent {
	event_id: string
	event_type: 'lease' | 'sale'
	event_date: string
	title: string
	description: string
	amount_aed: number | null
	end_date: string | null
	source: string
	confidence: CrmMatchConfidence
	ltv_pct: number | null
	capital_gain_pct: number | null
}

export interface CrmLeadDetailResponse {
	lead: CrmLead
	timeline: CrmTimelineEvent[]
	next_best_actions: string[]
	agent_signals: string[]
	match_explanation: string
	generated_at: string
}

export interface CrmSavedLead {
	id: number
	lead: CrmLead
	created_at: string
	updated_at: string
}

export type CrmPipelineStatus =
	| 'new'
	| 'researching'
	| 'contact_ready'
	| 'contacted'
	| 'qualified'
	| 'nurture'
	| 'won'
	| 'closed'

export type CrmHighlightColor = 'none' | 'amber' | 'green' | 'blue' | 'red' | 'purple'

export interface CrmLeadNote {
	id: number
	body: string
	created_at: string
	updated_at: string
}

export interface CrmWorkspaceSummary {
	id: number | null
	lead_id: string
	unit_candidate_key: string
	pipeline_status: CrmPipelineStatus
	highlight_color: CrmHighlightColor
	owner_name: string | null
	owner_email: string | null
	owner_phone: string | null
	next_follow_up: string | null
	tags: string[]
	note_count: number
	updated_at: string
}

export interface CrmWorkspace extends CrmWorkspaceSummary {
	notes: CrmLeadNote[]
}

export interface CrmWorkspaceUpdate {
	pipeline_status?: CrmPipelineStatus
	highlight_color?: CrmHighlightColor
	owner_name?: string | null
	owner_email?: string | null
	owner_phone?: string | null
	next_follow_up?: string | null
	tags?: string[]
}

export type CrmOwnershipStatus =
	| 'verified_current_owner'
	| 'probable_current_owner'
	| 'unit_linked_unverified'
	| 'former_owner'
	| 'conflicting_claim'
	| 'insufficient_property_data'
	| 'registry_not_observed'
	| 'unmatched'

export interface CrmContactImportSummary {
	total_rows: number
	candidate_rows: number
	duplicate_rows_collapsed: number
	valid_contacts: number
	verified_current_owners: number
	probable_current_owners: number
	unit_linked_unverified: number
	former_owners: number
	conflicting_claims: number
	insufficient_property_data: number
	registry_not_observed: number
	unmatched: number
	rental_opportunities: number
	contact_ready: number
}

export interface CrmSheetMapping {
	sheet_name: string
	header_row: number
	meaningful_rows: number
	sheet_family: string
	mapping_source: 'heuristic' | 'llm' | 'heuristic_fallback'
	confidence: number
	field_map: Record<string, string>
	warnings: string[]
}

export interface CrmContactImport {
	id: number
	list_id: number | null
	name: string
	original_filename: string
	status: 'processing' | 'completed' | 'failed'
	summary: CrmContactImportSummary
	mappings: CrmSheetMapping[]
	error_message: string | null
	created_at: string
	completed_at: string | null
}

export interface CrmContactListSummary {
	id: number
	source_import_id: number | null
	name: string
	description: string | null
	total_contacts: number
	contact_ready: number
	needs_review: number
	former_owners: number
	created_at: string
	updated_at: string
}

export interface CrmContactClaim {
	id: number
	source_sheet: string
	source_row_number: number
	contact_name: string
	phone_primary: string | null
	phone_alternate: string | null
	email_primary: string | null
	area_name: string
	project_name: string
	building_name: string
	unit_number: string
	property_type: string
	transaction_date: string | null
	transaction_price_aed: number | null
	ownership_status: CrmOwnershipStatus
	confidence_score: number
	match_reason: string
	lead_id: string | null
	unit_candidate_key: string | null
	latest_sale_date: string | null
	latest_sale_price_aed: number | null
	later_sale_date: string | null
	lease_end: string | null
	annual_rent_aed: number | null
	owner_key: string
	duplicate_count: number
	source_rows: string[]
}

export interface CrmContactListDetail {
	list: CrmContactListSummary
	contacts: CrmContactClaim[]
	total: number
	limit: number
	offset: number
}

export interface CrmLeadImportedContact {
	claim_id: number
	list_id: number
	list_name: string
	contact_name: string
	phone_primary: string | null
	phone_alternate: string | null
	email_primary: string | null
	ownership_status: CrmOwnershipStatus
	confidence_score: number
	match_reason: string
	source_sheet: string
	imported_at: string
	owner_key: string
	duplicate_count: number
	property_count: number
	source_lists: string[]
}

export type CrmOwnerRegistryScope = 'all' | 'rental_ready' | 'registry' | 'prior_owners'

export interface CrmOwnerRegistryParams {
	list_id?: number
	status?: CrmOwnershipStatus
	search?: string
	lease_window?: CrmLeadStatus
	portfolio_only?: boolean
	min_rent_aed?: number
	max_rent_aed?: number
	min_value_aed?: number
	max_value_aed?: number
	limit?: number
	offset?: number
}

export interface CrmOwnerProperty {
	property_key: string
	area_name: string
	project_name: string
	building_name: string
	unit_number: string
	property_type: string
	ownership_status: CrmOwnershipStatus
	confidence_score: number
	match_reason: string
	lead_id: string | null
	unit_candidate_key: string | null
	imported_transaction_date: string | null
	imported_transaction_price_aed: number | null
	imported_property_type: string
	latest_sale_date: string | null
	latest_sale_price_aed: number | null
	registry_sale_date: string | null
	registry_sale_price_aed: number | null
	registry_property_type: string | null
	registry_bedrooms: string | null
	registry_size_sqft: number | null
	registry_built_up_area_sqft: number | null
	registry_price_per_sqft_aed: number | null
	registry_market_status: string | null
	later_sale_date: string | null
	lease_end: string | null
	annual_rent_aed: number | null
	duplicate_count: number
	source_lists: string[]
	source_rows: string[]
}

export interface CrmOwnerProfile {
	owner_key: string
	contact_name: string
	phone_primary: string | null
	phone_alternate: string | null
	email_primary: string | null
	highest_ownership_status: CrmOwnershipStatus
	highest_confidence_score: number
	property_count: number
	rental_linked_count: number
	contact_ready_count: number
	annual_rent_aed: number
	next_lease_end: string | null
	properties: CrmOwnerProperty[]
}

export interface CrmOwnerRegistryResponse {
	scope: CrmOwnerRegistryScope
	owners: CrmOwnerProfile[]
	total: number
	limit: number
	offset: number
	summary: {
		rental_owner_profiles: number
		registry_owner_profiles: number
		prior_owner_profiles: number
		needs_review_profiles: number
		multi_property_owners: number
	}
}

export interface CrmOwnerWorkspaceSummary {
	owner_key: string
	pipeline_status: CrmPipelineStatus
	highlight_color: CrmHighlightColor
	next_follow_up: string | null
	tags: string[]
	note_count: number
	last_note: string | null
	updated_at: string
}

export interface CrmOwnerBulkUpdate {
	owner_keys: string[]
	pipeline_status?: CrmPipelineStatus
	highlight_color?: CrmHighlightColor
	note?: string
}

export interface CrmSaleComparable {
	transaction_date: string
	building_name: string
	unit_number: string
	unit_series: string | null
	property_type: string
	bedrooms: string
	size_sqft: number
	sale_amount_aed: number
	price_per_sqft_aed: number | null
	selection_reason: string
}

export interface CrmRentalComparable {
	lease_start: string
	building_name: string
	unit_number: string | null
	unit_series: string | null
	unit_match_status: string
	property_type: string
	bedrooms: string
	size_sqft: number
	annual_rent_aed: number
	rent_per_sqft_aed: number | null
	selection_reason: string
}

export interface CrmPropertyReport {
	lead: CrmLead
	period_start: string
	period_end: string
	sales_comparables: CrmSaleComparable[]
	rental_comparables: CrmRentalComparable[]
	analysis: {
		estimated_market_value_aed: number | null
		estimated_value_low_aed: number | null
		estimated_value_high_aed: number | null
		estimated_market_rent_aed: number | null
		indicated_capital_change_aed: number | null
		indicated_capital_change_pct: number | null
		indicative_selling_costs_aed: number | null
		indicative_proceeds_before_debt_aed: number | null
		estimated_market_gross_yield_pct: number | null
		current_rent_vs_market_pct: number | null
		target_unit_series: string | null
		sales_selection_basis: string
		rental_selection_basis: string
		sales_comparables_used: number
		rental_comparables_used: number
		confidence: CrmMatchConfidence
	}
	price_index: {
		name: string
		base_period: string
		latest_period: string
		current_index: number
		change_since_base_pct: number
		year_over_year_pct: number | null
		current_median_psf_aed: number | null
		segment_name: string
		segment_current_index: number | null
		segment_year_over_year_pct: number | null
		segment_current_median_psf_aed: number | null
		points: Array<{
			quarter: string
			label: string
			dubai_index: number
			dld_index: number | null
			transaction_index: number | null
			segment_index: number | null
			dubai_median_psf_aed: number | null
			segment_median_psf_aed: number | null
			dld_transactions: number
			transaction_count: number
			segment_transactions: number
		}>
		methodology: string
	}
	agent_signals: string[]
	methodology: string[]
	generated_at: string
}

export interface CrmDashboardParams {
	status?: CrmLeadStatus
	priority?: CrmLeadPriority
	asset_class?: CrmAssetClass
	property_type?: string
	area?: string
	project?: string
	building?: string
	search?: string
	breakdown?: CrmBreakdownLevel
	expired_days?: number
	limit?: number
	offset?: number
}

export const crm = {
	dashboard: (params: CrmDashboardParams = {}, signal?: AbortSignal) =>
		client.get<CrmDashboardResponse>(
			client.withQuery('/api/v1/crm/dashboard', {
				status: params.status,
				priority: params.priority,
				asset_class: params.asset_class,
				property_type: params.property_type,
				area: params.area,
				project: params.project,
				building: params.building,
				search: params.search,
				breakdown: params.breakdown,
				expired_days: params.expired_days,
				limit: params.limit,
				offset: params.offset
			}),
			{ signal }
		),
	lead: (leadId: string, signal?: AbortSignal) =>
		client.get<CrmLeadDetailResponse>(`/api/v1/crm/leads/${encodeURIComponent(leadId)}`, {
			signal
		}),
	leadContacts: (leadId: string, signal?: AbortSignal) =>
		client.get<CrmLeadImportedContact[]>(
			`/api/v1/crm/leads/${encodeURIComponent(leadId)}/contacts`,
			{ signal }
		),
	report: (leadId: string, signal?: AbortSignal) =>
		client.get<CrmPropertyReport>(`/api/v1/crm/leads/${encodeURIComponent(leadId)}/report`, {
			signal
		}),
	workspaces: () => client.get<CrmWorkspaceSummary[]>('/api/v1/crm/workspaces'),
	workspace: (leadId: string, signal?: AbortSignal) =>
		client.get<CrmWorkspace>(`/api/v1/crm/workspaces/${encodeURIComponent(leadId)}`, {
			signal
		}),
	updateWorkspace: (leadId: string, payload: CrmWorkspaceUpdate) =>
		client.patch<CrmWorkspace, CrmWorkspaceUpdate>(
			`/api/v1/crm/workspaces/${encodeURIComponent(leadId)}`,
			payload
		),
	addNote: (leadId: string, body: string) =>
		client.post<CrmWorkspace, { body: string }>(
			`/api/v1/crm/workspaces/${encodeURIComponent(leadId)}/notes`,
			{ body }
		),
	deleteNote: (noteId: number) => client.delete<void>(`/api/v1/crm/notes/${noteId}`),
	savedLeads: () => client.get<CrmSavedLead[]>('/api/v1/crm/saved-leads'),
	saveLead: (leadId: string) =>
		client.post<CrmSavedLead>(`/api/v1/crm/saved-leads/${encodeURIComponent(leadId)}`),
	deleteSavedLead: (savedId: number) => client.delete<void>(`/api/v1/crm/saved-leads/${savedId}`),
	contactImports: (signal?: AbortSignal) =>
		client.get<CrmContactImport[]>('/api/v1/crm/contact-imports', { signal }),
	renameContactImport: (importId: number, name: string) =>
		client.patch<CrmContactImport, { name: string }>(`/api/v1/crm/contact-imports/${importId}`, {
			name
		}),
	deleteContactImport: (importId: number) =>
		client.delete<void>(`/api/v1/crm/contact-imports/${importId}`),
	contactLists: () => client.get<CrmContactListSummary[]>('/api/v1/crm/contact-lists'),
	contactList: (
		listId: number,
		params: { status?: CrmOwnershipStatus; search?: string; limit?: number; offset?: number } = {}
	) =>
		client.get<CrmContactListDetail>(
			client.withQuery(`/api/v1/crm/contact-lists/${listId}`, params)
		),
	ownerRegistry: (
		scope: CrmOwnerRegistryScope,
		params: CrmOwnerRegistryParams = {},
		signal?: AbortSignal
	) =>
		client.get<CrmOwnerRegistryResponse>(
			client.withQuery('/api/v1/crm/owner-registry', {
				scope,
				...params
			}),
			{ signal }
		),
	ownerProfile: (ownerKey: string, signal?: AbortSignal) =>
		client.get<CrmOwnerProfile>(`/api/v1/crm/owners/${encodeURIComponent(ownerKey)}`, {
			signal
		}),
	ownerWorkspaces: (signal?: AbortSignal) =>
		client.get<CrmOwnerWorkspaceSummary[]>('/api/v1/crm/owner-workspaces', { signal }),
	bulkUpdateOwnerWorkspaces: (payload: CrmOwnerBulkUpdate) =>
		client.patch<CrmOwnerWorkspaceSummary[], CrmOwnerBulkUpdate>(
			'/api/v1/crm/owner-workspaces/bulk',
			payload
		),
	uploadContactImport: (file: File, name: string) => {
		const form = new FormData()
		form.set('file', file)
		form.set('name', name)
		return client.post<CrmContactImport, FormData>('/api/v1/crm/contact-imports', form)
	}
}
