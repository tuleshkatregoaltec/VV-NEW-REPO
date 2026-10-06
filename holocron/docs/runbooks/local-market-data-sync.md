# Local market data updates

The macOS LaunchAgent `com.vitevue.dxbi-sync` runs
`holocron.platform.sync_market_data`. It runs daily at 09:00 in the Mac's
timezone, with no hourly or login trigger. This machine uses Asia/Dubai. The Mac needs to
be awake, online, and running the local ClickHouse container. Missed data is
checked again on the next run. The server's overnight scrapers run independently.

The coordinator uses `.env.dev` for local database settings. DLD server
credentials stay inside the existing remote Dagster container; SSH reads the
published warehouse data. Each DLD Open Data table is compared using row counts
and checksums, downloaded to staging when changed, and checked again before an
atomic exchange. Separate historical imports are preserved. The previous local
table remains available as `<table>_local_sync_previous` until the next successful
replacement. An empty source cannot erase a populated local table.

The next stage refreshes `silver_transactions` and `silver_rent_contracts` using
the existing DLD transformations. It compares the entire local source checksum
and transformation hash against the last successful publication, so an unchanged
bronze sync still catches up stale projections. Rebuilds use staging tables,
bounded memory, date-coverage validation, and another source checksum before
atomic exchange. The previous projections remain in `<table>_local_sync_previous`.
Per-table publication markers in `DLD-Sync/` advance only after success; unchanged
inputs and published summaries skip the rebuild. A failure makes the daily
coordinator unhealthy and retries on its next run.

DXBI raw runs are downloaded with rsync. Both deployed `run=YYYY-MM-DD` folders
and newer `run=YYYY-MM-DD-daily` folders are recognized by the 36-hour health
check. Completed runs without load markers are loaded; old runs remain available
for catch-up. Rental imports explicitly target the active schema. Before v2
cutover they retain v1 event/candidate identities; a daily refresh never activates
an incomplete v2 backfill. Failed imports do not advance their load markers.

DLD, daily DXBI, and verified rental repairs are attempted independently. Updated source data triggers
the geography refresh. After successful imports, the coordinator clears the
affected transaction and analytics API caches. File locks prevent overlapping
jobs and are released by the OS when a process exits.

After successful daily DXBI and repair publication, `import_rentals` refreshes
the saved owner-import rental links and import-card counts. It uses explicit v2
rental unit numbers with the imported building/project identity; hidden units
still require a unique sales inference. The existing lease window (365 days
back through 90 days ahead) remains in force. Contacts, owner/property keys,
ownership assessments, sales evidence, notes and workspaces are preserved.
Missing eligible evidence clears an old rental link. This does not revalidate
an owner's acquisition or current ownership status.

`DLD-Sync/import-rental-matches.json` records the completed refresh. Unchanged
warehouse table versions/counts/timestamps, claim timestamps, matching code and
calendar date skip the work. A date change re-evaluates lease-window eligibility.
Empty projections or a warehouse change during the run abort publication, and
upstream DXBI failures defer this stage. Claim updates and all import summaries
commit in one PostgreSQL transaction before the completion marker advances.

Operational files under `/Users/eier/VV`:

- `DLD-Sync/automation-status.json`: latest coordinator result and stage exit codes.
- `DLD-Sync/latest.json`: DLD checksums, publication results, and errors.
- `DXBI-Daily/.loaded/`: completed DXBI load markers and rental reconciliation.
- `DXBI-Daily/sync.log` and `sync-error.log`: LaunchAgent output.
- `DXBI-Repair/runs/`: downloaded historical repair attempts and validation markers.
- `DXBI-Repair/.loaded/`: successfully published repair attempts.
- `DLD-Sync/backups/`: the previous LaunchAgent configuration.

The checked-in LaunchAgent is at `deploy/launchd/com.vitevue.dxbi-sync.plist`.
Inspect the installed job with `launchctl print gui/$(id -u)/com.vitevue.dxbi-sync`.
Start a catch-up with `launchctl kickstart gui/$(id -u)/com.vitevue.dxbi-sync`.

Fresh imports establish recency, not complete source coverage. Historical DXBI
rental coverage gaps still require separate backfill and validation. This local
sync reflects published server data; upstream failed or disabled DLD jobs must
be investigated in Dagster.

## Historical rental repairs

The VPS runs `dxbi-rentals-repair.timer` and the matching oneshot service. The
initial 396-date plan covers all of 2025 and March 2026, prioritizing the March 6
through September 2025 v2 gap and low November, December, October, early-2025,
and March-2026 coverage. Its plan, status, and per-attempt raw output live under
`/root/data/dxbi-rental-repair-20260915/`. The service uses a separate scraper copy
so the pagination correction can be verified without replacing the nightly job.

One date runs at a time under the nightly rental scraper's shared lock. Repair
work pauses from 23:00 to 03:00 UTC. A date has a 40-minute deadline and a
2,000-request budget; the systemd timer resumes the queue after each invocation.
Failed attempts retain diagnostics and retry after 24 hours. A changed scraper
hash allows an earlier retry using the corrected parser. Failed or suspiciously
thin output never receives the `_VERIFIED` marker. The density threshold is a
sanity check (half the prior CRM count), not proof of complete source coverage.

The local daily coordinator downloads repairs, accepts only `_SUCCESS` plus
`_VERIFIED` with a complete reconciliation, merges into the active v2 history,
then rebuilds candidates, sale matches, and geography. Load markers advance only
after all these steps succeed. The Mac must be awake for local publication; the
server continues scraping while it is asleep.

The v2 history retains unmatched older observations. Some older snapshots hide
unit numbers that newer snapshots expose. An exact lease cohort (location,
property type, bedrooms, size, dates, amount, state, and source contract ID)
retains distinct visible units and enough unidentified occurrences to preserve
the largest observed snapshot count. `source_cohort_size` persists that count
so repeated partial imports remain idempotent. This is conservative snapshot
reconciliation, not government contract-ID verification; changed source fields
can still leave observations that cannot safely be matched.

An active import stages the affected dates, retains the rest of the history,
and exchanges the completed table only after validation. Candidate and sale
match projections are also rebuilt into staging tables before exchange. Sale
matches respect a visible rental unit number. Existing saved CRM references
that use older candidate identities resolve against the retained `_legacy`
tables and are labelled as historical snapshots; they are not assigned to a
guessed v2 unit. Preserve these backups while old saved references exist.

The local retained-history publication audit is under
`/Users/eier/VV/DXBI-Backfill/crm-v2-upgrade-20260915/`. This publication brings
available higher-coverage data into the CRM without certifying the unfinished
historical repair queue as complete. One legacy row with a backwards lease date
is quarantined and retained in the backup instead of being given invented dates.
