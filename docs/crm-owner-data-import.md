# CRM Owner Data Import and Verification

Status: implementation specification  
Last updated: 26 August 2026
Owning domain: `backend/app/crm` and `frontend/src/routes/crm`

## 1. Purpose

Allow an organization to upload irregular Excel owner and seller datasets, verify the
property and ownership claims against the platform's transaction registry, connect
credible contacts to lease-opportunity units, and publish the results as saved CRM
folders for agent action.

The final CRM shortlist must contain the real imported contact information when it is
available:

- owner or seller name;
- primary and alternate telephone numbers;
- email addresses;
- building, project, area, and unit number;
- acquisition date and price where supplied or verified;
- lease status, rent, and expiry;
- ownership and contact confidence;
- source file, sheet, and source-row provenance;
- later-sale conflicts and review notes;
- assigned agent, pipeline status, tags, notes, and next follow-up.

The LLM is an aid for understanding unfamiliar spreadsheet schemas. It is not the
system of record, it does not decide whether someone currently owns a property, and
it does not need to receive names, phone numbers, or email addresses.

## Published CRM Workspaces

Completed imports are audit records, not the final working location for contacts.
Normalized claims are continuously published into organization-wide Saved
workspaces:

- **Rental owner leads** contains verified and probable current owners linked to an
  exact lease-opportunity unit.
- **Owner registry & review** contains non-rental owners, former owners, conflicting
  claims, and records that still need ownership evidence.
- **My saved prospects** remains the agent's manually curated property shortlist.

An owner profile accumulates properties across every import when both the normalized
name and a strong contact identifier agree. Name-only records remain property-scoped
so two unrelated people with the same name are not combined into a false portfolio.

Duplicate source rows are grouped by canonical owner and property identity. The
strongest supported ownership claim is presented once, while the original sheet,
row numbers, alternate dates, and conflicting claims remain available as provenance.

## 2. User Outcome

An agent or manager should be able to:

1. upload one or more `.xlsx` or `.csv` files;
2. name the destination folder, for example `Downtown owners — July 2026`;
3. review the detected sheets and proposed field mappings;
4. process the import without keeping the page open;
5. see counts for verified, probable, stale, review-required, and unmatched records;
6. inspect why a contact was matched or rejected;
7. publish selected matches into a saved CRM folder;
8. open a property and see the populated owner details alongside its lease and sales
   evidence;
9. bulk assign, tag, highlight, export, or update the status of the resulting leads;
10. retain a complete audit trail back to the uploaded source row.

No outreach is sent automatically as part of an import.

## 3. Existing Platform Capabilities

The current CRM already provides:

- lease-opportunity scoring and filtering;
- property evidence timelines and reports;
- saved leads in `crm_saved_leads`;
- per-agent workspaces in `crm_lead_workspaces`;
- owner name, phone, and email fields;
- pipeline status, highlighting, tags, notes, and next follow-up;
- organization and user isolation on persisted CRM records.

The import feature should extend this domain rather than use the existing
service-key-protected generic upload endpoint as a user-facing API.

The current `crm_lead_workspaces.owner_*` columns can continue to support manually
entered contacts. Imported contacts need normalized records and join tables so the
system can represent co-owners, conflicting historical claims, multiple phone
numbers, and reusable contacts without overwriting evidence.

## 4. Sample Data Assessment

The supplied sample contains approximately 240,700 source rows across these folders:

| Folder | Approximate rows | Observed formats |
| --- | ---: | --- |
| Downtown / Business Bay | 119,721 | Transaction-party exports with buyer/seller role, dates, prices, units, names, and phones |
| Dubai Marina / JBR | 116,810 | Transaction-party exports; one major file does not expose price |
| Tilal Al Ghaf | 4,204 | Transaction exports and simpler owner/contact lists |

Observed schema problems that the importer must handle:

- different names for the same canonical field;
- the same header meaning different things in different workbooks;
- multiple possible unit-number columns;
- buyer, seller, mortgage, grant, and transfer events in one sheet;
- files labelled `2024` whose data ends in December 2023;
- contact lists with no purchase date or price;
- duplicate and co-owner rows;
- missing emails and inconsistent phone formatting;
- Excel sheets whose reported used range includes thousands of empty placeholder
  columns;
- project or building aliases that differ from the transaction registry;
- compound unit identifiers that require deterministic splitting or extraction.

Initial transaction-registry matching demonstrates that deterministic verification is
viable:

| Source | Candidate units matched | Matched records with a later sale |
| --- | ---: | ---: |
| Business Bay | 65.0% | 31.8% |
| Downtown | 61.6% | 32.7% |
| Marina/JBR combined | 70.9% | 34.5% |
| JBR-specific | 70.7% | 20.0% |

These percentages are assessment results, not permanent acceptance thresholds.
They show why later-sale detection is mandatory before an imported person is
presented as a current owner.

## 5. Core Design Principle

Use an LLM once per unfamiliar sheet schema, then use deterministic code for every
row.

```text
Authenticated upload
        |
        v
Workbook preflight and safe sampling
        |
        v
LLM proposes a redacted schema mapping
        |
        v
User confirms or corrects the mapping
        |
        v
Deterministic normalization of every row
        |
        v
Transaction-registry ownership verification
        |
        v
Lease-opportunity matching
        |
        v
Review queue and saved CRM folder
```

This keeps processing inexpensive and repeatable while ensuring that names and
contact details can still be stored and used inside the CRM.

## 6. Import Lifecycle

### 6.1 Upload

- Accept `.xlsx` and `.csv` initially.
- Require an active subscription and organization context.
- Stream the original file to object storage; do not load the full file into API
  process memory.
- Calculate a SHA-256 file hash during upload.
- Store objects under an organization-scoped, non-public prefix.
- Reject encrypted workbooks, unsupported formats, macros, unsafe archives, and files
  above the configured size limit.
- Sanitize display filenames separately from storage object keys.
- Detect duplicate uploads by organization and file hash.

Suggested initial limits:

- 10 files per batch;
- 100 MB per file;
- 500,000 meaningful rows per batch;
- 100 meaningful columns per sheet after empty-column pruning.

### 6.2 Preflight

For every workbook and sheet:

- enumerate sheets and hidden sheets;
- identify the real header row;
- calculate the meaningful used range instead of trusting the Excel dimension;
- ignore fully empty and placeholder `Column123` columns;
- infer primitive types and null rates;
- collect unique-count and format statistics;
- detect likely transaction-party and contact-list families;
- generate masked examples for schema analysis;
- show warnings for malformed dates, impossible prices, duplicate rows, and ambiguous
  unit columns.

No records are published to the CRM during preflight.

### 6.3 Schema Mapping

The canonical import fields are:

| Group | Canonical fields |
| --- | --- |
| Property | `area_name`, `project_name`, `building_name`, `unit_number`, `plot_number`, `property_type`, `bedrooms`, `size_sqft` |
| Transaction | `transaction_date`, `transaction_price_aed`, `procedure_type`, `party_role`, `registration_number` |
| Contact | `contact_name`, `phone_primary`, `phone_alternate`, `email_primary`, `email_alternate` |
| Source | `source_row_number`, `source_record_id`, `source_notes` |

The schema assistant receives only:

- headers;
- inferred primitive types;
- null and distinct counts;
- masked or synthetic examples;
- structural patterns such as `NN-NNN` or `+9715*******`;
- a small number of redacted representative rows.

It returns strict JSON containing:

- canonical field mappings;
- deterministic transformations;
- sheet family;
- header-row index;
- ignored columns;
- confidence per mapping;
- warnings and unresolved choices.

Mappings below the configured confidence threshold require user confirmation.
Approved mappings are saved as reusable import profiles keyed by a normalized header
signature. A later workbook with the same signature should not require another LLM
request.

### 6.4 Deterministic Normalization

After mapping approval, application code processes every meaningful row:

- trim and Unicode-normalize text;
- normalize area, project, and building aliases;
- normalize unit numbers without discarding the original value;
- convert dates using an explicit day/month policy;
- parse AED amounts and reject impossible values;
- normalize UAE telephone numbers to E.164 when possible;
- validate email syntax without claiming mailbox ownership;
- distinguish buyer, seller, mortgage, grant, and non-transfer procedures;
- create stable row fingerprints for idempotency;
- preserve the raw source values and all transformations in provenance metadata.

Normalization failures are recorded per row and do not abort the full batch unless
the approved mapping itself is invalid.

## 7. Ownership Reconstruction and Verification

### 7.1 Property Identity

Use the strongest available identity in this order:

1. exact normalized building and exact unit;
2. exact project, building alias, and exact unit;
3. exact project and compound unit transformation approved in the import profile;
4. building/project, date, price, size, and layout evidence requiring review;
5. fuzzy text similarity only as a candidate generator, never as automatic proof.

Area-only, project-only, or building-only matches must not populate an owner onto a
unit-level CRM lead.

### 7.2 Transaction Claims

For transaction-party sheets:

- group people belonging to the same unit and transfer event;
- preserve co-buyers as separate contacts on one ownership claim;
- ignore mortgage registration as a change of ownership;
- do not treat a seller row as the current owner;
- choose the latest valid buyer/acquisition event within the uploaded history;
- compare its date and price with the platform's latest transfer event;
- search for a later platform sale after the uploaded acquisition event.

### 7.3 Contact-Only Claims

A contact-only sheet lacking acquisition evidence can establish that a contact was
associated with a unit, but not that the person currently owns it.

Such a record starts as `unit_linked_unverified`. It can be promoted only when:

- another source file supplies matching acquisition evidence;
- the transaction registry corroborates the supplied ownership details; or
- an authorized user manually verifies it and records the evidence.

### 7.4 Verification Status

Recommended canonical statuses:

| Status | Meaning | CRM treatment |
| --- | --- | --- |
| `verified_current_owner` | Exact property plus latest transfer date/price evidence, with no later sale | Contact-ready if the unit is a lease opportunity |
| `probable_current_owner` | Exact property and plausible acquisition, with no contradictory later sale | Visible with verification warning |
| `unit_linked_unverified` | Exact unit association but no sufficient ownership evidence | Review before outreach |
| `former_owner` | A later sale exists after the contact's acquisition evidence | Never presented as current owner |
| `conflicting_claim` | Multiple incompatible current-owner claims or registry mismatch | Manual review |
| `unmatched` | No defensible unit match | Remains in import results only |

Suggested high-confidence evidence:

- exact canonical building and unit;
- supplied acquisition date equal to the latest transfer date within an explicit
  tolerance;
- supplied price within 2% of the registry transfer price;
- no later ownership transfer;
- consistent project, property type, layout, or size where available.

The score and all component reasons must be stored. The UI must show evidence, not
just a percentage.

## 8. Lease-Opportunity Matching

After ownership verification:

- join the canonical property identity to the existing CRM
  `unit_candidate_key`;
- require an exact unit-level relationship for automatic lead enrichment;
- preserve the configurable expired-lease trailing window;
- distinguish residential, commercial, and other asset classes;
- attach current rent, lease dates, expiry state, and opportunity score;
- retain verified contacts that do not currently qualify as lease opportunities in
  the import folder under `No current lease opportunity`;
- reevaluate folder membership when lease data or the user's expiry window changes.

An import match must never replace the property evidence used to generate the lease
opportunity. It enriches the lead with contact and ownership evidence.

## 9. Proposed Persistence Model

All tables are organization-scoped. User-scoped fields are added only for assignment
or personal views.

### `crm_contact_import_batches`

- `id`
- `organization_id`
- `created_by_user_id`
- `name`
- `status`
- `file_count`
- `source_row_count`
- `processed_row_count`
- `published_match_count`
- `error_count`
- `created_at`, `started_at`, `completed_at`

### `crm_contact_import_files`

- `id`, `batch_id`
- `original_filename`, `object_key`, `sha256`
- `size_bytes`
- `sheet_count`
- `status`
- `error_summary`
- timestamps

### `crm_contact_import_sheets`

- `id`, `file_id`
- `sheet_name`, `header_row`
- `meaningful_row_count`, `meaningful_column_count`
- `sheet_family`
- `header_signature`
- `mapping_json`, `mapping_confidence`
- `mapping_status`
- `profile_id`

### `crm_import_mapping_profiles`

- `id`, `organization_id`
- `name`, `header_signature`
- `mapping_json`
- `created_by_user_id`
- timestamps

### `crm_contacts`

- `id`, `organization_id`
- `display_name`
- normalized and display phone/email collections;
- contact-validity flags;
- optional manual notes;
- `created_at`, `updated_at`

Contact details should be encrypted at rest at the field or database/storage layer
appropriate to the production environment. Searchable normalized values may require
separate keyed hashes.

### `crm_contact_source_records`

- `id`, `contact_id`, `batch_id`, `file_id`, `sheet_id`
- `source_row_number`, `row_fingerprint`
- source property and transaction values;
- normalized property and transaction values;
- encrypted raw contact payload or object-storage pointer;
- validation warnings;
- timestamps

### `crm_property_contact_claims`

- `id`, `organization_id`, `contact_id`
- canonical property identity and optional `unit_candidate_key`;
- `claim_role`;
- `ownership_status`, `confidence_score`;
- acquisition date and price;
- later-sale date and price;
- evidence components and match explanation;
- `reviewed_by_user_id`, `reviewed_at`;
- timestamps

### `crm_contact_lists`

- `id`, `organization_id`
- `name`, `description`
- `source_import_batch_id`
- `created_by_user_id`
- visibility and timestamps

### `crm_contact_list_members`

- `id`, `list_id`
- `property_contact_claim_id`
- optional assigned user;
- pipeline status, highlight, tags, next follow-up;
- timestamps

The existing `crm_saved_leads` can remain the user's lightweight property bookmark
mechanism. A contact list is organization-level, supports multiple contacts per
property, and has import provenance.

## 10. API Surface

Suggested authenticated CRM endpoints:

```text
POST   /api/v1/crm/contact-imports
GET    /api/v1/crm/contact-imports
GET    /api/v1/crm/contact-imports/{batch_id}
POST   /api/v1/crm/contact-imports/{batch_id}/files
GET    /api/v1/crm/contact-imports/{batch_id}/sheets
PATCH  /api/v1/crm/contact-imports/{batch_id}/sheets/{sheet_id}/mapping
POST   /api/v1/crm/contact-imports/{batch_id}/process
GET    /api/v1/crm/contact-imports/{batch_id}/results
PATCH  /api/v1/crm/contact-imports/{batch_id}/claims/{claim_id}
POST   /api/v1/crm/contact-imports/{batch_id}/publish

GET    /api/v1/crm/contact-lists
POST   /api/v1/crm/contact-lists
GET    /api/v1/crm/contact-lists/{list_id}
PATCH  /api/v1/crm/contact-lists/{list_id}
DELETE /api/v1/crm/contact-lists/{list_id}
```

File upload and processing authorization must use the signed-in organization context,
not a client-supplied organization ID.

Large imports must run as durable jobs. The API should persist job state and return
`202 Accepted`; it should not hold an HTTP request open while parsing 90,000 rows.
The first implementation may execute the same service synchronously in tests, but
production processing must survive API restarts.

## 11. CRM User Experience

### Import entry point

Add an `Import owner data` action to the CRM toolbar.

Wizard stages:

1. **Upload** — files, folder name, optional area label.
2. **Recognize** — sheets, row counts, detected formats, warnings.
3. **Map fields** — proposed mappings with confidence and editable selectors.
4. **Process** — durable progress, safe navigation away, error counts.
5. **Review** — result categories, evidence drawer, conflict resolution.
6. **Publish** — create or add to an organization CRM folder.

### Result summary

Show:

- total meaningful source rows;
- distinct properties and contacts;
- verified current owners;
- probable owners;
- unit-linked unverified contacts;
- former owners with later sales;
- conflicts;
- rental-opportunity matches;
- no-current-opportunity contacts;
- unmatched and invalid rows.

### Saved folders

CRM folders appear alongside the existing owner pursuit queue. Each folder supports:

- search and filters;
- bulk selection;
- assigned agent;
- pipeline status;
- highlight and tags;
- next follow-up;
- export;
- archive;
- provenance and verification filters.

### Property drawer

When an imported contact is connected to a lead, show:

- all associated contacts and co-owners;
- verified name, telephone, and email fields;
- preferred contact selection;
- contact and ownership status badges;
- source file, sheet, and imported date;
- acquisition evidence;
- later-sale warnings;
- lease opportunity and property timeline;
- notes and activity history.

Use customer-facing labels such as `Transaction registry`, `Sales evidence`, and
`Rental evidence`. Do not print internal source or scraper names in CRM UI or
generated reports. Existing property-information hyperlinks may remain.

## 12. LLM Integration

Reuse the backend OpenRouter integration. Keep the key server-side in
`OPENROUTER_API_KEY`; never expose it through SvelteKit public environment variables,
API responses, logs, source control, or browser requests.

The schema-mapping call must:

- request structured JSON;
- use a low temperature;
- set a strict input and output token ceiling;
- enforce Zero Data Retention routing;
- disable application prompt logging;
- include no raw PII;
- record model name, token usage, latency, mapping version, and request correlation
  ID without recording the prompt payload;
- fail closed to manual mapping if no compliant model endpoint is available.

LLM output is untrusted input. Validate it with Pydantic, restrict transformations to
an allowlist, and never execute returned formulas, code, SQL, or regular expressions
without independent validation.

Suggested allowed transformations:

- trim and case normalization;
- date format selection;
- numeric and currency parsing;
- exact delimiter split and token selection;
- prefix/suffix removal;
- approved lookup-table alias mapping;
- selection of one source column from explicit alternatives.

## 13. OpenRouter Local Configuration

The repository already loads local backend configuration from root `.env.dev`.

Required values:

```dotenv
OPENROUTER_API_KEY=<new-revocable-api-key>
DEFAULT_CHAT_MODEL=google/gemini-3.1-flash-lite
```

Use `google/gemini-3.1-flash-lite` as the initial schema-recognition model. It is a
current GA model optimized for inexpensive data extraction. A stronger model such as
`google/gemini-3.5-flash` may be used only as an explicit second pass when the first
mapping fails validation or remains below the confidence threshold. Do not configure
automatic cross-model routing.

The key shown in any screenshot, ticket, message, shell history, or committed file
must be revoked and replaced. Prefer a dedicated key named for the local CRM importer
with a small monthly spending limit. Production uses a separate key from the local
environment and stores it in the platform's secret manager.

Set local `.env.dev` permissions to owner-readable and owner-writable only:

```sh
chmod 600 .env.dev
```

Before enabling imports:

1. validate the key with OpenRouter's current-key endpoint;
2. make one minimal structured-output request;
3. confirm that ZDR-compatible routing succeeds for the chosen model;
4. confirm that prompts and contact fields are absent from logs;
5. verify that the backend is restarted after changing `.env.dev`;
6. verify that no key value appears in the frontend bundle or browser network traffic.

## 14. Privacy and Security

Owner names, telephone numbers, emails, and property associations are personal data.

Required controls:

- role-based access and organization isolation;
- private object storage with short-lived signed access only where required;
- encryption in transit and at rest;
- audit events for upload, review, publish, export, and deletion;
- configurable retention and deletion of original files;
- separate retention for normalized CRM records;
- do-not-contact and suppression flags before outbound tooling is enabled;
- export authorization and rate limiting;
- no PII in LLM requests by default;
- no contact data in analytics, exception messages, or ordinary logs;
- explicit legal-basis and data-governance review before production outreach;
- human approval before any future email or WhatsApp send.

## 15. Idempotency, Conflicts, and Reprocessing

- File hash prevents accidental duplicate upload.
- Row fingerprint prevents duplicate source records.
- Import profile versions make schema decisions reproducible.
- Matching-engine version is stored on every claim.
- Reprocessing creates a new result version without erasing the prior audit trail.
- Publishing an already-published claim updates evidence instead of duplicating a
  contact-list member.
- A later registry sale automatically downgrades a current-owner claim to
  `former_owner` and removes it from contact-ready views.
- Manual overrides require a reason, author, and timestamp and must remain visible.

## 16. Observability

Record per batch:

- upload and processing duration;
- row throughput;
- meaningful versus skipped rows;
- schema-mapping token use and cost;
- deterministic exact-match rate;
- review and conflict rate;
- later-sale rejection rate;
- rental-opportunity match rate;
- parser and validation errors;
- publishing and deduplication counts.

Operational logs contain identifiers and counts, not contact values.

## 17. Testing

### Unit tests

- meaningful used-range detection;
- placeholder-column pruning;
- each known sample schema mapping;
- date, currency, unit, phone, and email normalization;
- buyer/seller and transfer/mortgage classification;
- co-owner grouping;
- later-sale invalidation;
- confidence scoring;
- idempotent row and file fingerprints;
- PII redaction before LLM calls;
- strict rejection of unsafe LLM transformations.

### Backend integration tests

- organization isolation;
- upload type and size enforcement;
- import lifecycle and durable status;
- manual mapping fallback when OpenRouter is unavailable;
- contact creation and deduplication;
- exact property and lease-lead linking;
- publication to a contact list;
- reprocessing and later-sale downgrade;
- deletion and retention behavior.

### Frontend tests

- wizard navigation and mapping correction;
- resumable processing status;
- result filters and evidence drawer;
- folder creation and bulk selection;
- owner contact visibility;
- stale-owner warnings;
- no secret or internal source name rendered.

### End-to-end fixtures

Create small, de-identified fixtures representing:

- Business Bay transaction-party schema;
- Downtown transaction-party schema;
- Marina role-in-`Procedure` schema;
- malformed JBR used range;
- Tilal contact-list schema;
- ELAN compound unit-number schema;
- co-owner and later-sale scenarios.

Do not check the real owner workbooks into source control.

## 18. Delivery Plan

### Phase 1 — Deterministic vertical slice

- import batch/file persistence;
- authenticated Excel upload;
- preflight and manual field mapping;
- deterministic parsing;
- exact building/unit transaction matching;
- later-sale detection;
- exact rental-lead matching;
- saved folder with populated contact details;
- source provenance and result review.

This phase is useful without an LLM key.

### Phase 2 — LLM-assisted schema recognition

- redacted sampling;
- structured mapping output;
- reusable import profiles;
- ZDR enforcement;
- token accounting and manual fallback.

### Phase 3 — Production workflow

- durable worker deployment;
- assignment and bulk actions;
- exports, suppression, and retention controls;
- ongoing revalidation when new sales arrive;
- performance tuning for large organization datasets.

### Phase 4 — Outreach preview

- contact-list hygiene and consent state;
- email and WhatsApp template previews;
- personalization from verified evidence;
- approval gates and audit history.

No live outbound integration is part of Phases 1–3.

## 19. Acceptance Criteria for the First Release

- A user can upload all supplied sample workbooks without the UI blocking.
- The importer ignores the malformed JBR placeholder columns.
- Known sample schemas can be mapped, saved, and reused.
- Real owner names, phones, and emails populate matched CRM folder records.
- A later sale prevents a historical contact from appearing as a verified current
  owner.
- A contact-only unit match is clearly labelled unverified.
- Exact lease-opportunity matches open the existing property CRM drawer and show
  contact provenance.
- Co-owners are retained as separate contacts.
- Re-uploading the same file does not duplicate contacts or folder members.
- OpenRouter failure falls back to manual schema mapping.
- No raw PII is sent to OpenRouter.
- No API key reaches the browser, repository, application logs, or generated report.
- All imported data is isolated by organization.

## 20. Decisions Required Before Production

- retention period for original workbooks;
- whether contact lists are organization-wide or team-scoped;
- roles allowed to upload, review, publish, export, and delete;
- exact legal basis and suppression policy for future outreach;
- field-level encryption and searchable-hash strategy;
- production worker/runtime choice;
- whether manual ownership verification expires after a defined period;
- model and provider allowlist for ZDR-compliant schema recognition.

## 21. External References

- [OpenRouter quickstart](https://openrouter.ai/docs/quickstart)
- [OpenRouter current-key validation endpoint](https://openrouter.ai/docs/api/api-reference/api-keys/get-current-key)
- [OpenRouter Zero Data Retention](https://openrouter.ai/docs/guides/features/zdr)
- [OpenRouter guardrails and spending controls](https://openrouter.ai/docs/guides/features/guardrails/overview)

## 22. Saved Owner Workspace Implementation

The current CRM publishes owner imports into both combined intelligence views and
source-specific Saved folders:

- **Rental owner leads** contains verified or probable current owners linked to a
  lease opportunity.
- **Current owners & review** contains non-rental current-owner candidates and
  claims that still need verification.
- **Prior owners registry** retains seller rows and uploaded buyers superseded by a
  later observed transfer.
- **Import folders** preserve one isolated view per uploaded workbook so areas and
  source contexts do not have to be mixed.

Import names can be edited after processing; the audit record and Saved folder are
renamed together. Owner folders support server-side lease-window, annual-rent,
property-value, verification, search, and multi-property filters.

Agent state is stored per normalized owner identity. Users can select a page or an
arbitrary subset and apply pipeline state, colour highlighting, or an organization-
private note in bulk. Existing lease-lead notes and highlights remain visible on
rental-owner rows. WhatsApp and email sequence controls are presentation-only until
consent, provider, suppression, and approval workflows are implemented.

## 23. Implemented Property Resolver and August 2026 Backfill

The local CRM now resolves imported property identities with deterministic evidence;
it does not call an LLM per owner row. The resolver applies these stages:

1. normalize literal placeholders such as `NULL`, unit whitespace, spelling variants,
   Roman numerals, token order, and leading zeroes;
2. recover complete villa or numeric unit identifiers embedded in a building column;
3. apply vetted project/building aliases and project-specific address rules, including
   The Edge tower inference from explicit `A`/`B` unit prefixes;
4. resolve exact sale-date and price signatures only when the source location agrees,
   or when one collision candidate wins by a conservative location margin;
5. check exact price within a 14-day date window when DLD export and DXBI display
   dates differ, again requiring location agreement;
6. match the normalized unit within the area, project, and building hierarchy and
   reject tied or weak location candidates;
7. apply the full sales history to distinguish current, probable, conflicting, and
   former owners.

Every canonical-address change is recorded in claim evidence with the source and
resolved identity. Previously accepted globally unique date/price matches can be
replayed from their original source identity using the audit mode. This prevents an
unrelated but globally unique transaction from silently overriding a contradictory
project name.

Two non-match conditions are deliberately separated from `unmatched`:

- `insufficient_property_data` means the imported row has no recoverable unit or
  property identifier;
- `registry_not_observed` means the import has a usable unit, but that unit is absent
  from current DXBI sales coverage;
- `unmatched` is reserved for rows where registry candidates exist but the location
  cannot be selected safely.

After the 26 August 2026 backfill and historical-signature audit, the four loaded
imports contain 80,732 claims with 1,734 true unmatched rows (2.15%):

| Import | Claims | True unmatched |
| --- | ---: | ---: |
| Tilal Al Ghaf — Elan | 922 | 40 |
| Business Bay 2024 SVR | 26,197 | 581 |
| JBR, June 2024 | 12,860 | 390 |
| Dubai Hills Elite | 40,753 | 723 |

An additional 2,235 rows are explicitly marked as insufficient source property data,
and 193 contain usable units not observed in current registry coverage. They remain
visible for source enrichment or future DXBI reprocessing and are not represented as
successful matches. Import-card summaries are refreshed from live claims after every
rematch so the UI cannot continue showing the original stale import counts.

Operational commands are provided by
`backend/scripts/crm/rematch_owner_claims.py`:

```sh
# Re-evaluate unresolved claims for one import.
uv run python scripts/crm/rematch_owner_claims.py \
  --organization-id <organization-id> --import-id <import-id>

# Re-audit historical date/price-only resolutions from original source addresses.
uv run python scripts/crm/rematch_owner_claims.py \
  --organization-id <organization-id> --import-id <import-id> \
  --audit-unique-transactions

# Refresh import-card counts without running ClickHouse matching.
uv run python scripts/crm/rematch_owner_claims.py \
  --organization-id <organization-id> --summary-only

# Refresh rental links for every claim while retaining sales/ownership assessments.
uv run python scripts/crm/rematch_owner_claims.py \
  --organization-id <organization-id> --rentals-only
```

The local market-data coordinator also runs `scripts.crm.refresh_rental_imports`
after successful DXBI publication. Rental matching now uses explicit v2 source
unit numbers where available, matched to the saved building/project-and-unit
identity. Hidden-unit rows still require an unambiguous sales-registry inference.
The existing lease-end window is unchanged. This rental refresh updates links,
lease/rent fields, and import summaries; it does not redo sales-based ownership
verification or modify contact data and agent workspaces. Original source files
do not need to be uploaded again. The August 26 figures above are a historical
audit, not current rental-match totals.
