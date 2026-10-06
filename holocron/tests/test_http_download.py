from __future__ import annotations

from urllib.parse import urlparse

import httpx
import pytest

from holocron.platform.http_download import normalize_external_url, validated_stream_get


def _validate_public_example_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError("URL must use https")
    host = parsed.hostname or ""
    if host in {"127.0.0.1", "localhost"}:
        raise ValueError("URL host is private or local")
    return parsed._replace(fragment="").geturl()


def test_validated_stream_get_validates_redirect_before_following() -> None:
    requested_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        return httpx.Response(302, headers={"location": "https://127.0.0.1/private"})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError, match="private or local"):
            with validated_stream_get(
                client,
                "https://example.com/start",
                validate_url=_validate_public_example_url,
            ):
                pass

    assert requested_urls == ["https://example.com/start"]


def test_validated_stream_get_follows_allowed_relative_redirect() -> None:
    requested_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        if str(request.url) == "https://example.com/start":
            return httpx.Response(302, headers={"location": "/asset.jpg"})
        return httpx.Response(200, content=b"asset-bytes")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with validated_stream_get(
            client,
            "https://example.com/start",
            validate_url=_validate_public_example_url,
        ) as response:
            assert response.read() == b"asset-bytes"

    assert requested_urls == ["https://example.com/start", "https://example.com/asset.jpg"]


def test_normalize_external_url_applies_allowlist_and_strips_fragments() -> None:
    assert (
        normalize_external_url(
            "https://cdn.example.com/asset.jpg#tracking",
            allowed_hosts=("example.com",),
        )
        == "https://cdn.example.com/asset.jpg"
    )


def test_normalize_external_url_rejects_private_ip_hosts() -> None:
    with pytest.raises(ValueError, match="private or local"):
        normalize_external_url("https://127.0.0.1/asset.jpg")
