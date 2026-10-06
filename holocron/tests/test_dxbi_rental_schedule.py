from pathlib import Path


def test_rental_schedule_uses_lag_windows_and_a_blocking_shared_lock() -> None:
    root = Path(__file__).parents[1]
    script = (root / "deploy" / "systemd" / "dxbi-report-daily.sh").read_text()

    assert "rentals:daily" in script and "start_offset=14" in script
    assert "rentals:weekly" in script and "start_offset=180" in script
    assert "rentals:monthly" in script and "start_offset=365" in script
    assert "end_offset=15" in script
    assert "end_offset=181" in script
    assert "flock 9" in script
    assert "flock -n 9" not in script
    assert 'touch "${output_dir}/_SUCCESS"' not in script


def test_sync_treats_a_stale_or_missing_daily_run_as_unhealthy() -> None:
    root = Path(__file__).parents[1]
    script = (root / "scripts" / "sync_dxbi_daily_runs.sh").read_text()

    assert "-mmin -2160" in script
    assert "no successful daily run in the last 36 hours" in script
