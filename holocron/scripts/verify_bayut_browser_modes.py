#!/usr/bin/env python3
"""Verify both Bayut fetchers against a local site; no Bayut/proxy traffic is used."""

from __future__ import annotations

import argparse
import gzip
import importlib.util
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright

from holocron.sources.bayut_listings import full_collection


HTML = b"""<!doctype html><html><head><title>1 Apartments for Sale</title>
<link rel="stylesheet" href="/style.css"><script src="/script.js"></script>
</head><body><article><h3>AED 12,500.75</h3>
<a href="/property/details-123.html"><h2 aria-label="Title">Apartment</h2></a>
<p>AED 12,500.75</p><p>1,234.50 sqft</p><img src="/image.png"></article>
<article><h3>AED 20,000</h3><a href="/property/details-124.html"
title="Link title fallback">Details</a><p>2,000 sqft</p></article>
<div aria-label="Off-Plan properties rail"><article>
<a href="/property/details-999.html"><h2>Unrelated promoted listing</h2></a>
</article></div>
<iframe src="/frame"></iframe>
<script>window.inlineScriptRan = true; fetch('/inline-fetch');</script>
</body></html>"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chrome-path", default="")
    args = parser.parse_args()
    requested_paths: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            pass

        def do_GET(self) -> None:
            requested_paths.append(self.path)
            if self.path.startswith("/for-sale/"):
                body, content_type = gzip.compress(HTML), "text/html"
            elif self.path == "/style.css":
                body, content_type = b"/* unused styles */" * 10_000, "text/css"
            elif self.path == "/script.js":
                body, content_type = b"/* unused script */" * 10_000, "application/javascript"
            else:
                body, content_type = b"<html><body>auxiliary resource</body></html>", "text/html"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            if self.path.startswith("/for-sale/"):
                self.send_header("Content-Encoding", "gzip")
            self.end_headers()
            self.wfile.write(body)

    standalone_path = (
        Path(__file__).resolve().parents[1] / "handoff/bayut_standalone/bayut_collection.py"
    )
    spec = importlib.util.spec_from_file_location("bayut_standalone_smoke", standalone_path)
    assert spec and spec.loader
    standalone = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = standalone
    spec.loader.exec_module(standalone)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    results = []
    try:
        with sync_playwright() as playwright:
            for module in (full_collection, standalone):
                cards_by_mode = {}
                traffic_by_mode = {}
                for mode in ("browser", "document"):
                    requested_paths.clear()
                    config_values = {
                        "base_url": f"http://127.0.0.1:{server.server_port}",
                        "chrome_path": args.chrome_path,
                        "resource_mode": mode,
                        "request_pause_seconds": 0,
                        "request_jitter_seconds": 0,
                        "settle_milliseconds": 250,
                    }
                    config = (
                        full_collection.BayutFullCollectionConfig.model_validate(config_values)
                        if module is full_collection
                        else standalone.CollectionConfig(**config_values)
                    )
                    with module.BrowserPageFetcher(playwright=playwright, config=config) as fetcher:
                        result = fetcher.fetch(
                            search_path="/for-sale/apartments/dubai/",
                            page_number=1,
                            observation_id=f"local-{mode}",
                        )
                    assert result.outcome == "ok", result
                    assert len(result.cards) == 2, result.cards
                    assert [card["title"] for card in result.cards] == [
                        "Apartment",
                        "Link title fallback",
                    ], result.cards
                    cards_by_mode[mode] = result.cards
                    traffic_by_mode[mode] = result.network["response_bytes"]
                    if mode == "document":
                        assert requested_paths == ["/for-sale/apartments/dubai/"], requested_paths
                        assert result.network["request_count"] >= 1
                    else:
                        assert "/script.js" in requested_paths
                        assert "/inline-fetch" in requested_paths
                        assert "/style.css" in requested_paths
                    results.append(
                        {
                            "collector": "integrated"
                            if module is full_collection
                            else "standalone",
                            "mode": mode,
                            "actual_server_requests": list(requested_paths),
                            "network": result.network,
                        }
                    )
                assert cards_by_mode["browser"] == cards_by_mode["document"]
                assert 0 < traffic_by_mode["document"] < traffic_by_mode["browser"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
    print(json.dumps({"verified": True, "results": results}, indent=2))


if __name__ == "__main__":
    main()
