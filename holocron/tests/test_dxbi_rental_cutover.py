import importlib.util
from datetime import date
from pathlib import Path


def _load_script():
    path = Path(__file__).parents[1] / "scripts" / "activate_dxbi_rental_v2.py"
    spec = importlib.util.spec_from_file_location("activate_dxbi_rental_v2", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FailingCandidateExchange:
    def __init__(self) -> None:
        self.commands: list[str] = []

    def command(self, sql: str) -> None:
        self.commands.append(sql)
        if "dxbi_rental_unit_candidates" in sql:
            raise RuntimeError("candidate exchange failed")


def test_cutover_rolls_back_event_exchange_if_candidate_exchange_fails(monkeypatch) -> None:
    cutover = _load_script()
    client = FailingCandidateExchange()
    monkeypatch.setattr(cutover, "validate", lambda *args, **kwargs: {"event_rows": 10})

    try:
        cutover.activate(
            client,
            backfill_run_id="rental-backfill",
            cutover_date=date(2026, 9, 4),
        )
    except RuntimeError as exc:
        assert "candidate exchange failed" in str(exc)
    else:
        raise AssertionError("failed candidate exchange did not abort cutover")

    assert client.commands == [
        "EXCHANGE TABLES dxbi_rental_events AND dxbi_rental_events_v2",
        "EXCHANGE TABLES dxbi_rental_unit_candidates AND dxbi_rental_unit_candidates_v2",
        "EXCHANGE TABLES dxbi_rental_events AND dxbi_rental_events_v2",
    ]
