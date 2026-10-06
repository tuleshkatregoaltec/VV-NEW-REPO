# New Mac developer setup

This is the handoff for a primary development Mac. It sets up the Vitevue
platform, secure access to the scrape environment, and the data workflow
without copying secrets, Docker volumes, or large datasets into Git.

## What Git contains and what it does not

Git contains application code, Holocron source connectors, loaders, tests,
runbooks, and small configuration examples. It does **not** contain:

- `.env*` files, credentials, SSH private keys, or Tailscale state;
- Docker volumes, local Postgres/ClickHouse state, or browser profiles;
- `data/` exports, including Property Finder snapshots and DXB Interact CSVs.

The authoritative Property Finder raw archive is in object storage. DXB
Interact raw and normalized exports are operational data, not source code.
Use the loaders below to reproduce local CRM state instead of committing data.

## 1. Mac prerequisites

Install Xcode command-line tools, Homebrew, Docker Desktop, and Tailscale.

```sh
xcode-select --install
# Install Homebrew from https://brew.sh if it is not already installed.
brew install git just uv oven-sh/bun/bun tailscale
```

Install and start Docker Desktop before running the platform setup. Docker
Desktop provides Docker Compose on macOS.

For GitHub SSH access, create or copy an approved development key and register
its public half with the GitHub account:

```sh
ssh-keygen -t ed25519 -C "<your-github-email>"
ssh -T git@github.com
```

Never copy another machine's private key through Git, chat, or a repository.

## 2. Tailscale and scrape-server access

Tailscale is the private network path to the scrape VPS and its services.

```sh
sudo tailscale up
tailscale status
tailscale ping <scrape-vps-tailnet-name-or-ip>
```

Sign in to the approved tailnet when prompted. Obtain the current scrape VPS
tailnet hostname/IP from the owner or `tailscale status`; do not rely on a
public IP or put one in this document. Once approved, test read-only access:

```sh
ssh -i ~/.ssh/id_ed25519 -o IdentitiesOnly=yes -o BatchMode=yes \
  root@<scrape-vps-tailnet-name-or-ip> 'hostname; docker ps --format "{{.Names}}"'
```

Use the restricted key and private Tailscale address. Do not expose the VPS,
R2, ClickHouse, or Dagster ports publicly.

## 3. Clone and start the platform

```sh
git clone git@github.com:Kian-Sham/VV.git
cd VV
git switch VV
just setup
uv tool install prek
prek install
```

`just setup` installs dependencies, starts the local service stack, applies
migrations, and creates a local bootstrap user. Use a new `.env.dev` generated
from the examples and approved secret manager values; do not copy an old Mac's
environment files verbatim.

Normal development:

```sh
just up
just dev-backend
just dev-frontend
# Or: just dev
```

Local endpoints:

| Service | Address |
| --- | --- |
| Frontend | `http://localhost:5173` |
| Backend API | `http://localhost:8000` |
| Auth | `http://localhost:9999` |
| Mail UI | `http://localhost:9000` |
| MinIO console | `http://localhost:9003` |
| ClickHouse HTTP | `http://localhost:8123` |

Read [development.md](../development.md) before changing local services or
running broad checks. Use `just --list` as the canonical command index.

## 4. Secrets and production connector configuration

The local platform uses MinIO and local ClickHouse by default. Production
Holocron uses external R2-compatible object storage, external ClickHouse, and
Dagster metadata Postgres.

- Platform host processes read `.env.dev`.
- Holocron local Compose uses `holocron/.env.local` when needed.
- Production Holocron environment files are obtained through the approved
  Bitwarden Secrets Manager workflow (`holocron/justfile`: `just env prod`).

Populate new-machine secrets only from the approved password/secret manager.
The full variable contract is in [docs/env-audit.md](env-audit.md) and example
files; examples intentionally contain no live values.

## 5. Data and scrape runbook

### Property Finder listings

- Raw releases and manifests live in object storage under
  `raw/source=pf_listings/`.
- The application-facing current table is `pf_listings_bronze` in ClickHouse.
- The full scrape is a snapshot; select one scrape cohort by `scraped_at` when
  exporting. Do not combine historical manifest runs into a current inventory.
- Clean CSVs are generated operationally and remain ignored under
  `data/exports/propertyfinder/`.
- Routine listing refreshes retain listing facts and textual details, but no
  longer hydrate/download listing media files. Existing raw/media archives are
  intentionally retained until an explicit cleanup decision.

Useful scripts:

```sh
# Run from the repository root. These write ignored data outputs.
cd holocron && uv run python scripts/export_pf_listing_snapshot_csv.py <output.csv>
cd .. && uv run --directory backend python scripts/listings/select_pf_listing_snapshot.py \
  <all-runs.csv> <latest-snapshot.csv> --start-date YYYY-MM-DD
```

Use the production Holocron container (through Tailscale) for R2-backed export
or bronze refresh jobs. A local MinIO setup does not contain production raw
releases.

### DXB Interact sales and rentals

- Local CRM tables are `dxbi_rental_events`,
  `dxbi_rental_unit_candidates`, `dxbi_sales_unit_events`, and
  `dxbi_rental_sale_matches`.
- Raw incremental shards are gzip JSONL. Derived partitions are ignored under
  `data/exports/dxbi-transactions/` and are grouped by contract start date
  (rentals) or transaction date (sales).
- Keep raw shards and derived CSVs out of Git. Copy approved recent increments
  from the scrape server only when an update is needed.

To refresh a local CRM warehouse after staging approved source files:

```sh
# Rentals accept raw .jsonl.gz shards.
cd holocron && uv run python scripts/load_dxbi_rental_events.py <rental-shard-dir> \
  --host 127.0.0.1 --port 8123 --database vitevue \
  --username vitevue --password <local-clickhouse-password>

# Sales accept the normalized date-partition CSV directory.
uv run python scripts/load_dxbi_normalized_sales_csv.py <sales-csv-dir> \
  --host 127.0.0.1 --port 8123 --database vitevue \
  --username vitevue --password <local-clickhouse-password>
```

Both loaders refresh the downstream candidate/match tables. Verify dates and
counts before relying on CRM results:

```sql
SELECT count(), max(lease_start) FROM dxbi_rental_events;
SELECT count(), max(transaction_date) FROM dxbi_sales_unit_events;
SELECT count(), max(last_purchase_date) FROM dxbi_rental_sale_matches;
```

### Scrape safety

- Prefer stored/raw releases and resumable checkpoints over rerunning a full
  scraper.
- Inspect service state, checkpoint dates, failed shards, restarts, and recent
  logs before changing a running scrape.
- Never delete a raw archive, browser profile, checkpoint, or object-storage
  prefix without explicit confirmation and a backup/recovery plan.
- Keep traffic inside the source's allowed operating model; do not treat proxy
  rotation or CAPTCHA workarounds as a substitute for authorization.

## 6. Daily operating checks

```sh
git status
just ps
just test-backend
just test-frontend
```

Before a push, inspect `git status`, confirm `data/` and `.env*` remain ignored,
run focused checks, and push the `VV` branch to the `backup` remote:

```sh
git push backup VV
```

For production scrape checks, use the Tailscale SSH command above and start
with read-only checks. Record what changed, the source date range, row counts,
and any unresolved gaps in a committed runbook or issue.
