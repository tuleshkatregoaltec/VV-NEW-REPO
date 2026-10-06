#!/usr/bin/env python3
"""Summarize one or more Bayut probe event files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from holocron.sources.bayut_listings.probe import load_probe_events, summarize_probe_events


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize Bayut CAPTCHA probe JSONL evidence.")
    parser.add_argument(
        "inputs",
        type=Path,
        nargs="+",
        help="Run directories or events.jsonl files to combine",
    )
    parser.add_argument("--output", type=Path, help="Optional summary JSON path")
    args = parser.parse_args()

    events = [event for path in args.inputs for event in load_probe_events(path)]
    summary = summarize_probe_events(events)
    rendered = json.dumps(summary, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
