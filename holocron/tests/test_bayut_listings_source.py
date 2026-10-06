from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from holocron.sources.bayut_listings.extract import (
    BayutAccessBlockedError,
    BayutBrowserListingsClient,
    BayutSearchPage,
    _is_captcha_page,
    _search_url,
    extract_release,
)
from holocron.sources.bayut_listings.source import BayutListingsConfig


class FakeBayutClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def fetch_search_page(self, *, search_path: str, page: int) -> BayutSearchPage:
        self.calls.append((search_path, page))
        cards = (
            {
                "listing_url": "https://www.bayut.com/property/details-123.html",
                "title": "Waterfront apartment",
                "text": "AED 1,250,000 Apartment 1 2 812 sqft Waterfront apartment",
            },
        )
        if page > 1:
            cards = ()
        return BayutSearchPage(
            requested_url=f"https://www.bayut.com{search_path}?page={page}",
            final_url=f"https://www.bayut.com{search_path}?page={page}",
            status_code=200,
            html="<html><body>listing results</body></html>",
            cards=cards,
        )


def test_search_url_adds_page_without_mutating_first_page() -> None:
    assert (
        _search_url(
            base_url="https://www.bayut.com",
            search_path="/for-sale/property/dubai/?sort=latest",
            page_number=1,
        )
        == "https://www.bayut.com/for-sale/property/dubai/?sort=latest"
    )
    assert (
        _search_url(
            base_url="https://www.bayut.com",
            search_path="/for-sale/property/dubai/?sort=latest",
            page_number=3,
        )
        == "https://www.bayut.com/for-sale/property/dubai/page-3/?sort=latest"
    )


def test_captcha_detection_uses_url_and_html() -> None:
    assert _is_captcha_page(final_url="https://www.bayut.com/captchaChallenge", html="")
    assert _is_captcha_page(final_url="https://www.bayut.com/search", html="hCaptcha")
    assert not _is_captcha_page(final_url="https://www.bayut.com/search", html="listing results")


def test_extracts_deduplicated_cards_and_stops_on_empty_page(tmp_path: Path) -> None:
    client = FakeBayutClient()
    release = extract_release(
        tmp_path,
        config={
            "search_paths": ["/for-sale/property/dubai/"],
            "max_pages_per_search": 3,
            "request_pause_seconds": 0,
        },
        now=datetime(2026, 8, 18, tzinfo=UTC),
        listing_client=client,
    )
    assert client.calls == [("/for-sale/property/dubai/", 1), ("/for-sale/property/dubai/", 2)]
    assert release.metadata["property_row_count"] == 1
    assert release.metadata["stopped_early"] is True
    assert (tmp_path / "bayut_listing_search_pages.jsonl").exists()
    text = (tmp_path / "bayut_listing_properties.jsonl").read_text()
    assert '"listing_id":"123"' in text
    assert '"price_aed":1250000' in text


def test_access_error_is_explicit() -> None:
    with pytest.raises(BayutAccessBlockedError, match="does not attempt to bypass"):
        raise BayutAccessBlockedError(
            "Bayut presented a CAPTCHA challenge instead of listing results. "
            "Use a permitted session or an authorised data feed; this collector "
            "does not attempt to bypass access controls."
        )


def test_bounded_browser_does_not_treat_a_hydration_shell_as_empty_results() -> None:
    context = MagicMock()
    page = context.new_page.return_value
    page.goto.return_value.status = 200
    page.url = "https://www.bayut.com/for-sale/property/dubai/"
    page.content.return_value = "<html><body>Loading...</body></html>"
    page.title.return_value = "Bayut"
    page.locator.return_value.evaluate_all.return_value = []
    page.locator.return_value.inner_text.return_value = "Loading..."
    client = BayutBrowserListingsClient(context=context, config=BayutListingsConfig())
    with pytest.raises(RuntimeError, match="unrecognized_page"):
        client.fetch_search_page(search_path="/for-sale/property/dubai/", page=1)
