# Bayut listings

This is an access-gated active-listings collector. It gathers the listing cards
rendered by Bayut search pages and writes both page-level evidence and
deduplicated listing records. It does not solve CAPTCHAs, rotate identities, or
attempt to bypass access controls.

Start with a single search path and page to verify normal permitted access:

```yaml
source_config:
  search_paths:
    - /for-sale/property/dubai/
  start_page: 1
  max_pages_per_search: 1
  request_pause_seconds: 3
  storage_state_path: /path/to/permitted-browser-state.json
```

The collector raises `BayutAccessBlockedError` if it receives a CAPTCHA page;
that is a deliberate terminal result for the run. A browser state file must be
obtained through an authorised normal session and is not a bypass mechanism.

Raw output:

- `bayut_listing_search_pages.jsonl`: request URL, final URL, status, card
  count, and complete HTML evidence for every fetched page.
- `bayut_listing_properties.jsonl`: deduplicated listing IDs, URLs, title,
  parsed price/size where visible, and complete card text.

`start_page` is a manual resume cursor. A run is not coverage-certified: a
future planner must first enumerate the permitted Dubai community paths and
verify pagination/result limits before claiming a full-site inventory.

## CAPTCHA attribution probe

The probe is separate from the collector. It measures challenge onset under a
small randomized cohort plan and stops each trial on CAPTCHA, 403, 429,
navigation failure, an empty page, or a duplicate-only page. It never attempts
to solve a challenge.

Files:

- `scripts/run_bayut_captcha_probe.py`: bounded Playwright runner.
- `scripts/analyze_bayut_captcha_probe.py`: combines and summarizes JSONL runs.
- `scripts/bayut_captcha_probe.example.json`: initial experiment matrix.

The example plan includes both `/for-sale/property/dubai/` and
`/to-rent/property/dubai/`. Each path is a separate randomized trial task, and
the summary reports them independently as well as in the cohort aggregate.

Copy the example plan and replace `identity_url` with an internal endpoint that
returns JSON containing at least `ip`, and preferably `country`, `asn`, and
`org`. Keep this endpoint independent of Bayut's challenge decision. The
placeholder is rejected, and the default `require_identity_success: true`
aborts a trial before its Bayut navigation if the endpoint fails, omits the IP,
or reports a country other than `expected_country`.

Proxy credentials are read only from the environment and are not written to
the plan or evidence:

```bash
export BAYUT_PROBE_PROXY_SERVER='http://proxy-gateway.example:8000'
export BAYUT_PROBE_PROXY_USERNAME='customer-zone-residential-session-{session}'
export BAYUT_PROBE_PROXY_PASSWORD='from-secret-manager'

uv run python scripts/run_bayut_captcha_probe.py \
  --plan scripts/bayut_captcha_probe.example.json \
  --output-root /tmp/bayut-probes \
  --dry-run

uv run python scripts/run_bayut_captcha_probe.py \
  --plan /path/to/edited-plan.json \
  --output-root /path/to/probe-evidence
```

If Playwright's managed Chromium is not installed, either install it with the
project's Playwright version or set `chrome_path` to an existing Chrome binary.

`{session}` must match the provider's documented sticky-session token syntax.
The runner substitutes a random token per trial or per page. A page-scoped
token creates a new proxy session for the complete browser context; it does not
claim to rotate every HTTP subrequest.

The example cohorts isolate these effects:

| Comparison | Main signal |
| --- | --- |
| direct reuse vs residential sticky reuse | IP/ASN/network path at constant browser lifecycle |
| residential sticky reuse vs sticky fresh context | cookies/cache/context lifetime at a nominally fixed proxy session |
| page rotation with carried state vs sticky reuse | changing proxy identity while preserving cookies/local storage approximately |
| page rotation with carried vs reset state | session state at changing proxy identity |
| fresh context vs fresh browser | browser-process lifetime; add a `fresh_browser` cohort when needed |

`fresh_browser` varies process lifetime, not a complete device fingerprint. A
fingerprint/device cohort should run the same matched plan on separate controlled
machines or browser engines and use server-side request attribution.

For a provider that advertises automatic per-request rotation, add a residential
cohort with `proxy_session_scope: "provider_default"`,
`isolation: "reuse_context"`, and `identity_check_scope: "page"`. The identity
endpoint still samples only its own request. To determine whether the document
and its subrequests used one or many egress IPs, correlate Bayut edge logs by
timestamp and URL. Optionally set `correlation_header_name` to an internal test
header; the runner will attach the observation ID only to requests whose host
matches `base_url`. Confirm that the header is logged and excluded from scoring
before using it for attribution.

Each page event records its sales/rental search path, challenge outcome, status, latency, cards, new and
duplicate listing IDs, current card-field presence, request counts by resource
type, transfer bytes, sampled egress identity, and HTML hash. Challenge evidence
includes HTML and a screenshot for every terminal anomaly, including an
unrecognized status-200 empty page. `summary.json` reports challenge onset, censored
trials, error rate, IP uniqueness, country consistency, card duplication, field
availability, latency, and bandwidth.

Interpret results in this order:

1. Reject runs with identity-check failures, unexpected countries/ASNs, high
   proxy reuse, or materially different error rates.
2. Compare challenge onset only at matched cadence and media-blocking settings.
3. Treat trials that reached the page cap without a challenge as right-censored,
   not as proof of unlimited allowance.
4. Use `card_field_availability` to decide hydration. If listing ID, title,
   price, and size meet the required completeness, detail requests are not
   needed for those fields; any larger target schema needs its own card-field
   audit.

Start with the example's 10-page-per-path limit. The plan validator caps a trial
at 500 top-level pages and the whole plan across cohorts and both paths at 2,000;
search coverage planning is a separate phase after the attribution experiment.

The handoff operator must provide only external inputs: the three proxy
environment values, the internal identity endpoint, the correct Chrome/Playwright
browser setup, and Bayut edge-log access for observation correlation. Provider
credentials and production edge-log validation cannot be embedded in this
repository.

## Full Dubai residential collection

The full-scale runner is a third, separate entry point. It covers sale and
rental listing cards across the current residential property-type roots without
changing the bounded source collector or the probe:

- `holocron/sources/bayut_listings/full_collection.py`: planner, Playwright
  fetcher, SQLite checkpoints, deduplication, and export.
- `scripts/run_bayut_full_collection.py`: `dry-run`, `plan`, `collect`, `all`,
  `status`, and `export` commands.
- `scripts/bayut_full_collection.example.json`: handoff configuration.

The plan begins with nine sale roots and seven rental roots. It reads Bayut's
page-one count and direct child-location counts, recursively splitting a root
until each leaf is below `max_results_per_shard`. A split is accepted only when
the sum of its child counts reconciles with the parent count inside the
configured bounds. A large leaf with no usable children is `unresolved`; the
collector refuses to start while any plan shard is pending, errored, or
unresolved. This prevents a 500-page cursor from being mistaken for full
coverage.

Page 2 and later use Bayut's canonical `/page-N/` path. Collection ends a shard
on a natural empty or duplicate-only page, then reconciles observed unique IDs
with the planner count. Premature endings become `count_mismatch`, and reaching
`max_pages_per_shard` becomes `capped`; either keeps `coverage_status` from
becoming `complete`.

Copy the example, replace its internal identity URL, and provide credentials
only through the full-runner environment names:

```bash
export BAYUT_FULL_PROXY_SERVER='http://proxy-gateway.example:8000'
export BAYUT_FULL_PROXY_USERNAME='customer-zone-residential-session-{session}'
export BAYUT_FULL_PROXY_PASSWORD='from-secret-manager'

uv run python scripts/run_bayut_full_collection.py dry-run \
  --config /path/to/bayut-full.json \
  --output-dir /path/to/bayut-full-output

uv run python scripts/run_bayut_full_collection.py plan \
  --config /path/to/bayut-full.json \
  --output-dir /path/to/bayut-full-output

uv run python scripts/run_bayut_full_collection.py collect \
  --config /path/to/bayut-full.json \
  --output-dir /path/to/bayut-full-output

uv run python scripts/run_bayut_full_collection.py export \
  --config /path/to/bayut-full.json \
  --output-dir /path/to/bayut-full-output
```

Use `status` at any time. Re-run the same command and output directory to
resume. `--max-nodes` and `--max-pages` bound one invocation for a staged
handoff. `--retry-errors` requeues planner or collection transport failures;
it does not waive unresolved coverage or count reconciliation.

### Audit and bandwidth controls (September 2026)

The full runner and standalone bundle now support `resource_mode: "document"`:
only the main HTML document is downloaded and page JavaScript is disabled.
This must be checked against `resource_mode: "browser"` on live sale and rental
pages before using it for a full run. Empty hydration shells and unexpected
redirects fail explicitly. No compact Bayut JSON endpoint has been validated.

New configs use 1.0 for `minimum_child_count_coverage` and
`minimum_observed_count_coverage`. Explicitly relaxed thresholds report
`complete_with_tolerance` when listings are missing. `root_coverage` compares
deduplicated IDs across each entire root with its planning-time count; any root
shortfall keeps the overall status at `not_complete`. Missing
parent counts cannot be inferred from potentially incomplete child links.
Counts can change during a run; these checks do not prove a simultaneous snapshot.

`--max-pages` bounds attempted pages, each with bounded retries. Collection stops
after `max_consecutive_failed_pages` exhausted pages (default three); remaining
shards are preserved. Cadence applies to all attempts. Runs export their progress
automatically and return exit code 2 for planning/collection errors. `dry-run`
does not require credentials; `status` and `export` require an existing checkpoint
but do not require proxy credentials.

`page_attempts.jsonl` now retains `network_json` (including request/response bytes,
blocked and unfinished requests). The summary reports measured response bytes per
unique listing and a projection for 250,000 listings. These exclude identity
checks and unmeasured partial transfers; use the provider dashboard for billing.
Original checkpoint hashes are accepted with new options at their default values;
changing resource mode or count thresholds requires a new output directory.
For old configs that omitted the old count defaults, explicitly set 0.98/0.9 to
resume their original checkpoint.

The standalone bundle includes `bayut_dataimpulse_practice.example.json` and its
README contains DataImpulse setup and comparison instructions. Local browser
verification (uses only a temporary local HTTP server):

```bash
uv run python scripts/verify_bayut_browser_modes.py --chrome-path /path/to/chrome
```

The September 7 audit verified equal card extraction in both modes against a
local fixture, with only the main document reaching the server in document mode.
One direct, non-proxied Bayut request returned HTTP 503 and a 603,805-byte security
check instead of listings. Live document-mode compatibility, provider traffic,
current card selectors, and full geographic partition coverage still require the
DataImpulse trial. The local fixture's bandwidth savings are not a Bayut forecast.

With `proxy_rotation: "context"`, `{session}` is replaced once per complete
browser context. `pages_per_context: 1` therefore requests a new sticky proxy
session for each top-level result page while all of that page's subrequests stay
inside the same context. The configured identity endpoint is checked before the
Bayut request; a failed or geographically inconsistent identity check fails the
attempt before navigation. A CAPTCHA discards the context and retries the same
checkpoint up to `max_attempts_per_page`. No challenge solver is used.

The stable output directory contains:

- `collection.sqlite3`: authoritative WAL-backed checkpoint and deduplicated
  listing store.
- `evidence/`: compressed challenge/error HTML, or all HTML when configured.
- `listings.jsonl`, `shards.jsonl`, `page_attempts.jsonl`, and `summary.json`:
  atomic exports created by the `export` command.

This is a search-card inventory, not detail-page hydration. Its expected scale
is the current live count reported by the planned roots, not a hard-coded
245,000 rows. Use the probe's field-availability measurements to decide whether
any detail-page phase is actually required; if it is, it should consume the
deduplicated `listing_url` export as a separate checkpointed job.
