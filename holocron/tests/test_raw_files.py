import hashlib
import json

from holocron.platform.raw_files import read_jsonl_file, write_jsonl_raw_file


def test_read_jsonl_file_preserves_unicode_line_separators_inside_strings(tmp_path) -> None:
    path = tmp_path / "rows.jsonl"
    rows = [
        {"id": 1, "description": "line one\u2028line two"},
        {"id": 2, "description": "plain"},
    ]
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )

    assert read_jsonl_file(path=path, source_label="test") == rows


def test_write_jsonl_raw_file_returns_raw_file_metadata(tmp_path) -> None:
    path = tmp_path / "nested" / "rows.jsonl"
    rows = [{"id": 1, "name": "Dubai"}, {"id": 2, "name": "Abu Dhabi"}]

    raw_file = write_jsonl_raw_file(path, rows)

    content = path.read_bytes()
    assert content == b'{"id":1,"name":"Dubai"}\n{"id":2,"name":"Abu Dhabi"}\n'
    assert raw_file.path == str(path)
    assert raw_file.row_count == 2
    assert raw_file.content_type == "application/x-ndjson"
    assert raw_file.size_bytes == len(content)
    assert raw_file.sha256 == hashlib.sha256(content).hexdigest()
