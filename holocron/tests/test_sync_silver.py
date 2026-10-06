import json
from unittest.mock import Mock

import pytest

from holocron.platform import sync_silver


@pytest.fixture
def refresh(monkeypatch, tmp_path):
    client = Mock()
    fingerprint = Mock(return_value=[100, 12345])
    before = {"count": 90, "first_date": "2020-01-01", "last_date": "2026-09-08"}
    after = {"count": 100, "first_date": "2020-01-01", "last_date": "2026-09-16"}
    summary = Mock(side_effect=[before, after])
    monkeypatch.setattr(sync_silver, "source_fingerprint", fingerprint)
    monkeypatch.setattr(sync_silver, "table_summary", summary)
    kwargs = dict(
        table="silver_transactions",
        source="bronze",
        date_column="transaction_date",
        sql="INSERT INTO `silver_transactions_staging` SELECT * FROM bronze",
        state_dir=tmp_path,
    )
    return client, fingerprint, summary, before, after, kwargs


def test_missing_marker_catches_up_stale_projection_and_keeps_backup(refresh):
    client, _, _, before, after, kwargs = refresh
    report = sync_silver.refresh_projection(client, **kwargs)
    assert report["before"] == before
    assert report["published"] == after
    commands = [call.args[0] for call in client.command.call_args_list]
    assert (
        "EXCHANGE TABLES `silver_transactions` AND `silver_transactions_local_sync_staging`"
        in commands
    )
    assert commands[-1] == (
        "RENAME TABLE `silver_transactions_local_sync_staging` "
        "TO `silver_transactions_local_sync_previous`"
    )
    assert json.loads((kwargs["state_dir"] / "silver_transactions.json").read_text()) == report


def test_unchanged_source_skips_rebuild_but_new_source_content_rebuilds(refresh):
    client, fingerprint, summary, _, after, kwargs = refresh
    sync_silver.refresh_projection(client, **kwargs)
    client.reset_mock()
    summary.side_effect = None
    summary.return_value = after
    assert not sync_silver.refresh_projection(client, **kwargs)["changed"]
    client.command.assert_not_called()
    fingerprint.return_value = [100, 54321]  # A correction without a row-count change.
    assert sync_silver.refresh_projection(client, **kwargs)["changed"]
    assert client.command.called


@pytest.mark.parametrize(
    "bad_after",
    [
        {"count": 0, "first_date": None, "last_date": None},
        {"count": 100, "first_date": "2021-01-01", "last_date": "2026-09-16"},
        {"count": 100, "first_date": "2020-01-01", "last_date": "2026-09-07"},
    ],
)
def test_empty_or_truncated_history_does_not_replace_current_table(refresh, bad_after):
    client, _, summary, before, _, kwargs = refresh
    summary.side_effect = [before, bad_after]
    with pytest.raises(RuntimeError):
        sync_silver.refresh_projection(client, **kwargs)
    assert not any("EXCHANGE" in c.args[0] for c in client.command.call_args_list)
    assert not (kwargs["state_dir"] / "silver_transactions.json").exists()


def test_source_change_during_rebuild_prevents_publication(refresh):
    client, fingerprint, _, _, _, kwargs = refresh
    fingerprint.side_effect = [[100, 12345], [101, 98765]]
    with pytest.raises(RuntimeError, match="Source changed"):
        sync_silver.refresh_projection(client, **kwargs)
    assert not any("EXCHANGE" in c.args[0] for c in client.command.call_args_list)
    assert not (kwargs["state_dir"] / "silver_transactions.json").exists()


def test_failed_insert_does_not_publish_or_mark_complete(refresh):
    client, _, _, _, _, kwargs = refresh

    def command(sql):
        if sql.startswith("INSERT"):
            raise RuntimeError("Insert failed")

    client.command.side_effect = command
    with pytest.raises(RuntimeError, match="Insert failed"):
        sync_silver.refresh_projection(client, **kwargs)
    assert not any("EXCHANGE" in c.args[0] for c in client.command.call_args_list)
    assert not (kwargs["state_dir"] / "silver_transactions.json").exists()


def test_failed_backup_rename_keeps_previous_table_in_staging(refresh):
    client, _, _, _, _, kwargs = refresh

    def command(sql):
        if sql.startswith("RENAME"):
            raise RuntimeError("Rename failed")

    client.command.side_effect = command
    with pytest.raises(RuntimeError, match="Rename failed"):
        sync_silver.refresh_projection(client, **kwargs)
    assert client.command.call_args.args[0].startswith("RENAME")
    assert not (kwargs["state_dir"] / "silver_transactions.json").exists()
