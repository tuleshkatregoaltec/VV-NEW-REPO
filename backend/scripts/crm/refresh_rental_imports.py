"""Catch up imported owner lists after a published rental candidate/match refresh."""

import argparse
import asyncio
import fcntl
import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from app.clickhouse.client import close_clickhouse, query
from app.crm import import_service
from app.postgres.client import close_postgres, get_postgres_engine


async def rental_snapshot() -> dict:
    snapshots = {}
    for table in ("dxbi_rental_unit_candidates", "dxbi_rental_sale_matches"):
        rows = await query(
            f"SELECT count() AS rows, toString(max(loaded_at)) AS loaded_at "
            f"FROM {table} FINAL SETTINGS max_threads=2, max_memory_usage=2000000000"
        )
        snapshots[table] = rows[0]
    versions = await query(
        "SELECT name,toString(uuid) AS uuid FROM system.tables "
        "WHERE database=currentDatabase() "
        "AND name IN ('dxbi_rental_unit_candidates','dxbi_rental_sale_matches') ORDER BY name"
    )
    snapshots["versions"] = versions
    if len(versions) != 2 or any(
        not snapshots[t]["rows"]
        for t in ("dxbi_rental_unit_candidates", "dxbi_rental_sale_matches")
    ):
        raise RuntimeError("Rental projections are missing or empty; retaining imported matches")
    return snapshots


async def claim_snapshot(db: AsyncSession) -> dict:
    row = (
        (
            await db.execute(
                text(
                    "SELECT count(*) AS rows,coalesce(max(id),0) AS last_id, "
                    "coalesce(max(updated_at)::text,'') AS updated_at FROM crm_property_contact_claims"
                )
            )
        )
        .mappings()
        .one()
    )
    return dict(row)


async def refresh(state_dir: Path, *, dry_run: bool = False) -> dict:
    marker = state_dir / "import-rental-matches.json"
    previous = json.loads(marker.read_text()) if marker.exists() else {}
    snapshot = await rental_snapshot()
    rules = hashlib.sha256(Path(import_service.__file__).read_bytes()).hexdigest()
    today = date.today().isoformat()
    factory = async_sessionmaker(get_postgres_engine(), class_=AsyncSession, expire_on_commit=False)
    async with factory() as db:
        before = await claim_snapshot(db)
        if (
            previous.get("rental_snapshot") == snapshot
            and previous.get("claims") == before
            and previous.get("rules") == rules
            and previous.get("as_of") == today
        ):
            return {"changed": False, "claims": before["rows"], "as_of": today}
        organizations = (
            (
                await db.execute(
                    text(
                        "SELECT DISTINCT organization_id FROM crm_property_contact_claims ORDER BY 1"
                    )
                )
            )
            .scalars()
            .all()
        )
        results = []
        for organization in organizations:
            result = await import_service.refresh_property_contact_rentals(
                db,
                organization_id=organization,
                commit=False,
            )
            results.append(result)
        if snapshot != await rental_snapshot():
            raise RuntimeError("Rental projections changed during refresh; no matches published")
        after = await claim_snapshot(db)
        if dry_run:
            await db.rollback()
            return {"dry_run": True, "as_of": today, "results": results}
        await db.commit()
    report = {
        "changed": True,
        "as_of": today,
        "rules": rules,
        "rental_snapshot": snapshot,
        "claims": after,
        "results": results,
        "finished_at": datetime.now(timezone.utc).isoformat(),
    }
    temporary = marker.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(report, indent=2) + "\n")
    temporary.replace(marker)
    return report


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    args.state_dir.mkdir(parents=True, exist_ok=True)
    with (args.state_dir / "import-rental-matches.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            print(json.dumps(await refresh(args.state_dir, dry_run=args.dry_run)), flush=True)
        finally:
            await close_clickhouse()
            await close_postgres()


if __name__ == "__main__":
    asyncio.run(main())
