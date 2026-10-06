# Standalone Bayut collection handoff

This directory is self-contained. It does not need the Holocron repository or
any files outside this directory. The only Python dependency is Playwright.

The collector downloads search-card text and core listing information only. It
blocks image, font, and media requests by default and does not visit listing
detail pages. It detects CAPTCHA pages, discards the complete browser context,
and retries the same checkpoint with a new configured proxy session. It does
not solve a CAPTCHA.

## DataImpulse quick start and bandwidth comparison

The new `bayut_dataimpulse_practice.example.json` runs three sale pages and three
rental pages in `resource_mode: "document"`. This mode downloads the main HTML
document, disables page JavaScript, and blocks scripts, styles, images, media,
frames, and background requests. It retains the normal Playwright proxy setup.
It is suitable only when listing cards are present in the initial HTML.

For DataImpulse, set these environment variables (keep the quotes and replace
only the login/password values):

```bash
export BAYUT_PROXY_SERVER='http://gw.dataimpulse.com:823'
export BAYUT_PROXY_USERNAME='YOUR_LOGIN__cr.ae;sessid.{session}'
export BAYUT_PROXY_PASSWORD='YOUR_PASSWORD'

python run_bayut_collection.py dry-run \
  --config bayut_dataimpulse_practice.example.json \
  --output-dir output-dataimpulse-document

python run_bayut_collection.py practice \
  --config bayut_dataimpulse_practice.example.json \
  --output-dir output-dataimpulse-document
```

The country/session syntax follows DataImpulse's
[country](https://docs.dataimpulse.com/proxies/parameters/country) and
[session ID](https://docs.dataimpulse.com/proxies/parameters/session-id) docs.
Session IDs request continuity; an offline residential peer can still be replaced.
The example uses ipify for IP connectivity checks. It requests UAE egress through
the proxy username but **does not independently verify its country**. To verify
country, use a geolocation endpoint returning the supported fields below and set
`expected_country: "AE"`.

`dry-run` requires neither credentials nor a running browser. If Chrome is
installed but Playwright's bundled browser is unavailable, set `chrome_path`.

To compare browser mode, copy the config, change `resource_mode` to `"browser"`,
and use a different output directory. Browser mode retains JavaScript and CSS
while blocking images, fonts, and media. Compare listing IDs/fields, errors, and
the provider dashboard's traffic delta across the two six-page runs. Do not
select document mode for the full run until it returns the expected cards.
An empty hydration shell is an `unrecognized_page` error, never a successful
empty inventory; a redirect to a different search is an `unexpected_redirect`.

The summary includes measured bytes per unique listing and a projection for
250,000 listings. `page_attempts.jsonl` includes `network_json` with request and
response bytes plus blocked, failed, and unfinished request counts. These browser
measurements exclude identity checks and unmeasured partial transfers; the
provider dashboard determines billed traffic. Saved JSONL/SQLite size is separate.

## Reliability and coverage

Listings and the next-page checkpoint are committed in the same transaction.
`--max-pages N` now bounds attempted collection pages, including failed pages;
each page may make up to `max_attempts_per_page` attempts. The runner stops after
`max_consecutive_failed_pages` exhausted pages (default three), leaving remaining
partitions untouched. Inspect the error, fix it, and use `--retry-errors` to resume.
Request pauses apply to every attempt, including planner leaves and failures.
Commands export progress automatically; collection/planning errors return exit
code 2. `status` and `export` work without proxy credentials and require an
existing checkpoint.

New configs require 100% of reported child counts and observed listing counts.
If an operator explicitly allows a lower threshold, a shortfall is reported as
`complete_with_tolerance` for that partition, not `complete`. `root_coverage` reconciles unique IDs
against each original root's count, exposing overlap between leaf partitions.
Any root shortfall keeps overall `coverage_status` at `not_complete`.
Missing parent counts are unresolved; a partial child list cannot certify itself.
Counts are captured during planning and listings can change while collection runs;
`complete` means count reconciliation, not proof of a simultaneous site snapshot.
Large locations without usable child partitions still require a reviewed plan.

Keep each run's original config. Existing checkpoints migrate the new metric
column and accept the new options at their backward-compatible defaults. Changing
coverage thresholds or resource mode requires a new output directory. Old runs
whose omitted defaults were 0.98/0.9 must specify those original values to resume.

## 1. Install

Use Python 3.11 or newer:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m playwright install chromium
```

On Windows PowerShell, activate with:

```powershell
.venv\Scripts\Activate.ps1
```

If Playwright cannot install its browser but Chrome is already installed, set
`chrome_path` in the config to the absolute Chrome executable path.

## 2. Configure the identity check

Copy the practice config and replace its `identity_url`. The endpoint must be
reachable through the proxy and return a JSON object containing at least an IP:

```json
{
  "ip": "203.0.113.10",
  "country": "AE",
  "asn": "AS64500",
  "org": "Example Residential ISP"
}
```

Common alternatives such as `query`, `countryCode`, and a nested `asn` object
are also accepted. With `require_identity_success` enabled, a failed check,
missing IP, or country mismatch prevents the Bayut request.

## 3. Configure the residential proxy

Credentials are read only from environment variables and are never written to
the config, SQLite database, evidence, or exports:

```bash
export BAYUT_PROXY_SERVER='http://provider-gateway.example:8000'
export BAYUT_PROXY_USERNAME='customer-zone-residential-session-{session}'
export BAYUT_PROXY_PASSWORD='secret-from-provider'
```

For Windows PowerShell:

```powershell
$env:BAYUT_PROXY_SERVER='http://provider-gateway.example:8000'
$env:BAYUT_PROXY_USERNAME='customer-zone-residential-session-{session}'
$env:BAYUT_PROXY_PASSWORD='secret-from-provider'
```

`{session}` must appear in the server, username, or password exactly where the
provider documents its sticky-session identifier. With
`proxy_rotation: "context"`, the runner generates a new value for every browser
context. With `pages_per_context: 1`, this means one proxy session per complete
top-level page; its document and subrequests are not rotated independently.

If the provider rotates automatically and has no session-token syntax, set
`proxy_rotation` to `provider_default` and remove `{session}` from the
credentials. Confirm the real behaviour using the identity samples and provider
logs rather than assuming the advertised pool size equals unique egress.

## 4. Run the practice collection

Edit `bayut_practice.example.json`, then validate it without opening a browser:

```bash
python run_bayut_collection.py dry-run \
  --config bayut_practice.example.json \
  --output-dir output-practice
```

Run three sale pages and three rental pages:

```bash
python run_bayut_collection.py practice \
  --config bayut_practice.example.json \
  --output-dir output-practice
```

The practice command automatically exports its results. Inspect
`output-practice/summary.json` for outcomes, unique observed IPs, countries,
latency, bandwidth, cards, and duplication. Reuse the same output directory to
resume. Use `--retry-errors` to requeue a failed practice path.

## 5. Run the full sale and rental collection

Edit `bayut_full.example.json`. The full config uses sixteen built-in,
property-type-specific residential roots: nine sale and seven rental.

Plan geography shards first:

```bash
python run_bayut_collection.py plan \
  --config bayut_full.example.json \
  --output-dir output-full

python run_bayut_collection.py status \
  --config bayut_full.example.json \
  --output-dir output-full
```

Planning recursively splits large property-type roots by Bayut location links.
Do not start collection while the status contains `plan_pending`, `plan_error`,
or `unresolved`. Export at this point if you need to inspect `shards.jsonl`:

```bash
python run_bayut_collection.py export \
  --config bayut_full.example.json \
  --output-dir output-full
```

Once the plan is complete, collect and then export:

```bash
python run_bayut_collection.py collect \
  --config bayut_full.example.json \
  --output-dir output-full

python run_bayut_collection.py export \
  --config bayut_full.example.json \
  --output-dir output-full
```

`--max-nodes N` limits planning work in one invocation. `--max-pages N` limits
scheduled collection pages (each with bounded retries) in one invocation. Both commands resume from the
SQLite checkpoint. `--retry-errors` requeues transport failures but does not
waive an unresolved coverage partition, page cap, or listing-count mismatch.

## Outputs

- `collection.sqlite3`: authoritative, page-level resume checkpoint and global
  listing-ID deduplication.
- `listings.jsonl`: text/core listing export.
- `shards.jsonl`: planner and coverage state.
- `page_attempts.jsonl`: request, challenge, latency, bandwidth, and identity
  observations.
- `summary.json`: sale/rental totals and operational summary.
- `evidence/`: compressed HTML only for challenges/errors under the default
  `evidence: "challenge"` setting.

The historical estimate of 650 MB to 1 GB for roughly 245,000 cards refers to
SQLite and JSONL storage, not proxy traffic. Measure both during practice.
Do not set `evidence` to `all` unless retaining every search-page HTML response
is intentional.

## Bounded request test (macOS/Linux)

`run_bayut_request_test.py` adds a cumulative page-attempt budget, a measured
response-byte budget, a single-process lock, per-page progress and staged resume.
It is not a full-coverage crawl. A page attempt can cause many browser resource
requests; blocked resources also appear in the request-event count.

Use two roots (Dubai sale and rental), `practice_pages_per_root: 500`,
`max_attempts_per_page: 1`, and session reuse such as `pages_per_context: 50`.
Test resource settings on a few pages before continuing. The saved-page audit
fixed price headings being used as titles and excludes the embedded off-plan
carousel from search results.

```bash
python run_bayut_request_test.py --config request-test.json \
  --output-dir request-test --max-attempts 1000 --max-response-mb 2000 --stop-after 6

# Resume the same checkpoint; those six attempts count toward the 1,000 total.
python run_bayut_request_test.py --config request-test.json \
  --output-dir request-test --max-attempts 1000 --max-response-mb 2000
```

The runner interleaves roots by page number and stops a root on empty,
duplicate-only or failed pages. It stops the test on HTTP rate limiting,
configured consecutive failures, or a failure rate above 10% after at least ten
attempts. Limits include attempts already saved in that output directory.
The byte limit is checked between pages, can overshoot by one page and excludes
identity checks and partial transfers; it is **not** a provider-billed usage cap.

`test_summary.json` records why a stage/run stopped and whether the attempt target
was reached. While running, read the per-page log or use the existing `status`
command against the same config and checkpoint. SIGTERM/Ctrl-C exports the
finished-page checkpoint. A request interrupted before its attempt was recorded
may be fetched again after resume. Do not change configs or automatically
requeue failed roots to force the counter to 1,000.
