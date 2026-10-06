#!/usr/bin/env python3
"""Select one dated Property Finder snapshot from an all-manifests CSV export."""

from __future__ import annotations

import argparse
import csv
import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--start-date", required=True, help="Inclusive YYYY-MM-DD scrape date")
    args = parser.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(".csv.tmp")
    rows = 0
    modes: Counter[str] = Counter()
    with args.input.open(encoding="utf-8", newline="") as source, temporary.open(
        "w", encoding="utf-8", newline=""
    ) as destination:
        reader = csv.DictReader(source)
        if not reader.fieldnames:
            raise ValueError("Input CSV has no header")
        writer = csv.DictWriter(destination, fieldnames=reader.fieldnames)
        writer.writeheader()
        for row in reader:
            if str(row.get("scraped_at") or "")[:10] < args.start_date:
                continue
            writer.writerow(row)
            rows += 1
            modes[str(row.get("listing_mode") or "unknown")] += 1
    os.replace(temporary, args.output)
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "file": args.output.name,
        "total_rows": rows,
        "rows_by_mode": dict(modes),
        "selection": {"scraped_at_on_or_after": args.start_date},
        "source_file": args.input.name,
        "deduplication_key": "listing_id",
    }
    args.output.with_suffix(".manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
