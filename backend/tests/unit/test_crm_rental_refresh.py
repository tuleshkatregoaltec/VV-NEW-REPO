from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.crm import import_service
from scripts.crm import refresh_rental_imports


def claim(**overrides):
    values = dict(
        import_id=2,
        property_key="tower|101",
        unit_number="101",
        lead_id=None,
        unit_candidate_key=None,
        lease_end=None,
        annual_rent_aed=None,
        owner_key="original-owner",
        ownership_status="verified_current_owner",
        phone_primary="+971501234567",
        evidence={"sales_match": {"matched_sales": 2}},
        updated_at=datetime(2026, 8, 26, tzinfo=timezone.utc),
    )
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_refresh_adds_hits_clears_stale_links_and_preserves_owner_work(monkeypatch):
    new = claim()
    old = claim(
        property_key="tower|102",
        unit_number="102",
        lead_id="old-event",
        unit_candidate_key="old-key",
        lease_end=date(2025, 1, 1),
        annual_rent_aed=100000,
    )
    untouched = claim(property_key="tower|103", unit_number="103")
    before = [vars(row).copy() for row in (new, old, untouched)]
    db = AsyncMock()
    db.add = MagicMock()
    db.exec.return_value = SimpleNamespace(all=lambda: [new, old, untouched])
    evidence = AsyncMock(
        return_value={
            "tower|101": {
                "event_key": "new-event",
                "unit_candidate_key": "new-key",
                "lease_end": date(2026, 11, 1),
                "annual_rent_aed": 125000,
            }
        }
    )
    summaries = AsyncMock()
    monkeypatch.setattr(import_service, "_rental_evidence_for_units", evidence)
    monkeypatch.setattr(import_service, "_refresh_contact_import_match_summaries", summaries)
    result = await import_service.refresh_property_contact_rentals(db, organization_id="org")
    assert result == {
        "claims": 3,
        "before_hits": 1,
        "after_hits": 1,
        "added_hits": 1,
        "removed_hits": 1,
        "changed_claims": 2,
    }
    assert new.lead_id == "new-event" and new.annual_rent_aed == 125000
    assert (old.lead_id, old.unit_candidate_key, old.lease_end, old.annual_rent_aed) == (None,) * 4
    allowed = {"lead_id", "unit_candidate_key", "lease_end", "annual_rent_aed", "updated_at"}
    for row, original in zip((new, old, untouched), before):
        assert {k: v for k, v in vars(row).items() if k not in allowed} == {
            k: v for k, v in original.items() if k not in allowed
        }
    assert untouched.updated_at == before[2]["updated_at"]
    evidence.assert_awaited_once_with(["101", "102", "103"])
    summaries.assert_awaited_once_with(db, organization_id="org", import_ids={2})
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_repeated_refresh_does_not_rewrite_existing_links(monkeypatch):
    row = claim(
        lead_id="event",
        unit_candidate_key="key",
        lease_end=date(2026, 11, 1),
        annual_rent_aed=125000,
    )
    db = AsyncMock()
    db.add = MagicMock()
    db.exec.return_value = SimpleNamespace(all=lambda: [row])
    monkeypatch.setattr(
        import_service,
        "_rental_evidence_for_units",
        AsyncMock(
            return_value={
                row.property_key: {
                    "event_key": "event",
                    "unit_candidate_key": "key",
                    "lease_end": row.lease_end,
                    "annual_rent_aed": 125000,
                }
            }
        ),
    )
    monkeypatch.setattr(import_service, "_refresh_contact_import_match_summaries", AsyncMock())
    result = await import_service.refresh_property_contact_rentals(
        db, organization_id="org", import_id=2, commit=False
    )
    assert result["changed_claims"] == 0
    assert result["after_hits"] == 1
    db.add.assert_not_called()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_warehouse_read_does_not_clear_saved_links(monkeypatch):
    row = claim(lead_id="old-event")
    db = AsyncMock()
    db.add = MagicMock()
    db.exec.return_value = SimpleNamespace(all=lambda: [row])
    monkeypatch.setattr(
        import_service,
        "_rental_evidence_for_units",
        AsyncMock(side_effect=RuntimeError("Warehouse unavailable")),
    )
    with pytest.raises(RuntimeError, match="Warehouse unavailable"):
        await import_service.refresh_property_contact_rentals(db, organization_id="org")
    assert row.lead_id == "old-event"
    db.add.assert_not_called()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_source_change_aborts_publication_and_leaves_marker_unchanged(monkeypatch, tmp_path):
    db = AsyncMock()
    db.__aenter__.return_value = db
    db.execute.return_value = MagicMock()
    db.execute.return_value.scalars.return_value.all.return_value = ["org"]
    monkeypatch.setattr(refresh_rental_imports, "get_postgres_engine", MagicMock())
    monkeypatch.setattr(refresh_rental_imports, "async_sessionmaker", lambda *a, **k: lambda: db)
    monkeypatch.setattr(
        refresh_rental_imports,
        "rental_snapshot",
        AsyncMock(side_effect=[{"version": 1}, {"version": 2}]),
    )
    monkeypatch.setattr(
        refresh_rental_imports, "claim_snapshot", AsyncMock(return_value={"rows": 1})
    )
    rematch = AsyncMock(return_value={"claims": 1})
    monkeypatch.setattr(import_service, "refresh_property_contact_rentals", rematch)
    with pytest.raises(RuntimeError, match="changed during refresh"):
        await refresh_rental_imports.refresh(tmp_path)
    db.commit.assert_not_awaited()
    assert not (tmp_path / "import-rental-matches.json").exists()


@pytest.mark.asyncio
async def test_dry_run_rolls_back_and_does_not_advance_marker(monkeypatch, tmp_path):
    db = AsyncMock()
    db.__aenter__.return_value = db
    db.execute.return_value = MagicMock()
    db.execute.return_value.scalars.return_value.all.return_value = ["org"]
    monkeypatch.setattr(refresh_rental_imports, "get_postgres_engine", MagicMock())
    monkeypatch.setattr(refresh_rental_imports, "async_sessionmaker", lambda *a, **k: lambda: db)
    monkeypatch.setattr(
        refresh_rental_imports, "rental_snapshot", AsyncMock(return_value={"version": 1})
    )
    monkeypatch.setattr(
        refresh_rental_imports, "claim_snapshot", AsyncMock(return_value={"rows": 1})
    )
    monkeypatch.setattr(
        import_service, "refresh_property_contact_rentals", AsyncMock(return_value={"claims": 1})
    )
    report = await refresh_rental_imports.refresh(tmp_path, dry_run=True)
    assert report["dry_run"]
    db.rollback.assert_awaited_once()
    db.commit.assert_not_awaited()
    assert not (tmp_path / "import-rental-matches.json").exists()
