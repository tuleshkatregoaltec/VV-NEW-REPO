import json
import sys
from types import SimpleNamespace

from holocron.platform import sync_market_data


def test_dld_failure_does_not_prevent_dxbi_catchup(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".env.dev").write_text("CLICKHOUSE_HOST=localhost\n")
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=1 if len(calls) == 1 else 0)

    monkeypatch.setattr(sync_market_data.subprocess, "run", run)
    monkeypatch.setattr(sys, "argv", ["sync", "--repo-dir", str(repo), "--data-dir", str(tmp_path)])
    assert sync_market_data.main() == 1
    assert len(calls) == 5
    assert "sync_dxbi_daily_runs.sh" in calls[2][-1]
    report = json.loads((tmp_path / "DLD-Sync/automation-status.json").read_text())
    assert report["stages"] == {
        "dld": 1,
        "dld_projections": 0,
        "dxbi": 0,
        "rental_repairs": 0,
        "import_rentals": 0,
    }
    assert not report["healthy"]


def test_failed_dxbi_publication_keeps_imported_rental_matches(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=1 if "sync_dxbi_daily_runs.sh" in command[-1] else 0)

    monkeypatch.setattr(sync_market_data.subprocess, "run", run)
    monkeypatch.setattr(sys, "argv", ["sync", "--repo-dir", str(repo), "--data-dir", str(tmp_path)])
    assert sync_market_data.main() == 1
    assert len(calls) == 4
    assert not any("scripts.crm.refresh_rental_imports" in c for c in calls)
    report = json.loads((tmp_path / "DLD-Sync/automation-status.json").read_text())
    assert report["stages"]["import_rentals"] == 1
    assert "cache" not in report["stages"]


def test_successful_import_refresh_runs_from_backend_before_cache_clear(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs["cwd"]))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(sync_market_data.subprocess, "run", run)
    monkeypatch.setattr(sys, "argv", ["sync", "--repo-dir", str(repo), "--data-dir", str(tmp_path)])
    assert sync_market_data.main() == 0
    assert "scripts.crm.refresh_rental_imports" in calls[4][0]
    assert calls[4][1] == repo / "backend"
    assert len(calls) == 6
