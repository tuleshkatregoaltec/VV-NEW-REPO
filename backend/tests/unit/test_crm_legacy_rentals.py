import asyncio

from app.crm import service


def test_existing_lead_does_not_query_legacy_tables(monkeypatch):
    calls = []

    async def query(sql, params):
        calls.append(sql)
        return [{"event_key": "current", "unit_candidate_key": "current-unit"}]

    monkeypatch.setattr(service, "query", query)
    rows = asyncio.run(service._query_with_legacy_rentals("SELECT * FROM dxbi_rental_events", {}))
    assert rows[0]["event_key"] == "current"
    assert len(calls) == 1


def test_saved_legacy_candidate_remains_resolvable_after_v2_cutover(monkeypatch):
    async def query(sql, params):
        if "system.tables" in sql:
            return [{"tables": 1}]
        if "dxbi_rental_unit_candidates_legacy" in sql:
            assert params == {"lead_id": "saved-old-lead"}
            return [{"unit_candidate_key": "saved-old-unit"}]
        return []

    monkeypatch.setattr(service, "query", query)
    assert asyncio.run(service._candidate_key_for_lead("saved-old-lead")) == "saved-old-unit"


def test_mixed_saved_leads_only_fall_back_for_missing_identities(monkeypatch):
    async def query(sql, params):
        if "system.tables" in sql:
            return [{"tables": 1}]
        if "dxbi_rental_events_legacy" in sql:
            assert params["candidate_keys"] == ["old"]
            return [{"saved_candidate_key": "old"}]
        return [{"saved_candidate_key": "new"}]

    monkeypatch.setattr(service, "query", query)
    rows = asyncio.run(
        service._query_with_legacy_rentals(
            "SELECT * FROM dxbi_rental_events",
            {"candidate_keys": ["new", "old"]},
            saved_candidates=True,
        )
    )
    assert [row["saved_candidate_key"] for row in rows] == ["new", "old"]
