from holocron.platform.rental_repair_queue import accepted_run
from holocron.platform.sync_rental_repairs import verified_run


def test_false_success_with_zero_rows_is_rejected():
    report = {
        "status": "success",
        "expected_partitions": 1,
        "completed_partitions": 1,
        "raw_rows": 0,
    }
    assert not accepted_run(report, 0)


def test_partial_and_suspiciously_thin_days_are_not_published():
    report = {
        "status": "success",
        "expected_partitions": 1,
        "completed_partitions": 1,
        "raw_rows": 900,
    }
    assert accepted_run(report, 800)
    assert not accepted_run(report, 1000)
    assert not accepted_run({**report, "failed_partitions": 1}, 800)
    assert not accepted_run({**report, "status": "failed"}, 800)


def test_unverified_success_is_not_imported(tmp_path):
    import json

    (tmp_path / "_SUCCESS").touch()
    (tmp_path / "reconciliation.json").write_text(
        json.dumps(
            {
                "status": "success",
                "expected_partitions": 1,
                "completed_partitions": 1,
                "raw_rows": 100,
            }
        )
    )
    assert not verified_run(tmp_path)
    (tmp_path / "_VERIFIED").touch()
    assert verified_run(tmp_path)
