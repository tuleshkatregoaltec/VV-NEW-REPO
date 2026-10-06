from types import SimpleNamespace

import pytest

from holocron.platform import sync_dld

SCHEMA = [("row_key", "String"), ("source_system", "String")]


class Client:
    def __init__(self):
        self.commands = []

    def query(self, sql, **kwargs):
        return SimpleNamespace(result_rows=SCHEMA)

    def command(self, sql):
        self.commands.append(sql)

    def raw_insert(self, *args, **kwargs):
        pass


def setup_sync(monkeypatch, tmp_path, *, local=(10, 100), source=(10, 200)):
    client = Client()
    monkeypatch.setattr(sync_dld, "fingerprint", lambda *args: local)

    def remote(remote, request, output=None):
        if output is not None:
            output.write(b"test download")
            return None
        return {"schema": SCHEMA, "fingerprint": source}

    monkeypatch.setattr(sync_dld, "remote_call", remote)
    kwargs = dict(
        remote="test",
        table="dld_od_rents_bronze",
        scratch=tmp_path,
        pending=tmp_path / "geography-pending",
    )
    return client, kwargs


def test_equal_row_counts_still_detect_corrected_records(monkeypatch, tmp_path):
    client, kwargs = setup_sync(monkeypatch, tmp_path)
    result = sync_dld.sync_table(client, **kwargs, dry_run=True)
    assert result["changed"]
    assert not client.commands


def test_repeat_sync_does_not_rewrite_identical_data(monkeypatch, tmp_path):
    client, kwargs = setup_sync(monkeypatch, tmp_path, local=(10, 100), source=(10, 100))
    result = sync_dld.sync_table(client, **kwargs)
    assert not result["changed"]
    assert not client.commands
    assert not kwargs["pending"].exists()


def test_empty_source_cannot_erase_populated_local_data(monkeypatch, tmp_path):
    client, kwargs = setup_sync(monkeypatch, tmp_path, source=(0, 0))
    with pytest.raises(RuntimeError, match="empty source"):
        sync_dld.sync_table(client, **kwargs)
    assert not client.commands


def test_corrupted_download_is_not_published(monkeypatch, tmp_path):
    client, kwargs = setup_sync(monkeypatch, tmp_path)
    with pytest.raises(RuntimeError, match="checksum mismatch"):
        sync_dld.sync_table(client, **kwargs)
    assert not any("EXCHANGE" in command for command in client.commands)
    assert not any("previous" in command for command in client.commands)
    assert not kwargs["pending"].exists()


def test_changing_source_is_retried_without_touching_local_tables(monkeypatch, tmp_path):
    client, kwargs = setup_sync(monkeypatch, tmp_path)
    calls = 0

    def remote(remote, request, output=None):
        nonlocal calls
        if output is not None:
            output.write(b"test download")
            return None
        calls += 1
        return {"schema": SCHEMA, "fingerprint": (10, 200) if calls == 1 else (11, 300)}

    monkeypatch.setattr(sync_dld, "remote_call", remote)
    with pytest.raises(RuntimeError, match="changed during export"):
        sync_dld.sync_table(client, **kwargs)
    assert not client.commands
