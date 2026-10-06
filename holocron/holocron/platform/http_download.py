"""HTTP download helpers for externally supplied media/document URLs."""

from __future__ import annotations

import ipaddress
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from urllib.parse import urljoin, urlparse

import httpx

UrlValidator = Callable[[str], str]
_REDIRECT_STATUS_MIN = 300
_REDIRECT_STATUS_MAX = 400


def normalize_external_url(
    url: str,
    *,
    allowed_schemes: tuple[str, ...] = ("https",),
    allowed_hosts: tuple[str, ...] | list[str] | None = None,
    allow_subdomains: bool = True,
    allow_leading_dot_hosts: bool = True,
    allow_protocol_relative: bool = False,
    reject_private_hosts: bool = True,
    strip_fragment: bool = True,
    label: str = "URL",
    host_not_allowed_message: str | None = None,
    unsafe_host_message: str | None = None,
) -> str:
    """Normalize an externally supplied URL after scheme, host, and SSRF checks."""

    normalized = url.strip()
    if allow_protocol_relative and normalized.startswith("//"):
        normalized = f"https:{normalized}"

    parsed = urlparse(normalized)
    schemes = {scheme.lower() for scheme in allowed_schemes}
    if parsed.scheme.lower() not in schemes:
        allowed = " or ".join(sorted(schemes))
        raise ValueError(f"{label} must use {allowed}")
    if parsed.username or parsed.password:
        raise ValueError(f"{label} must not include credentials")

    host = (parsed.hostname or "").lower()
    if not host:
        raise ValueError(f"{label} must include a host")
    if reject_private_hosts and _is_private_or_local_host(host):
        message = unsafe_host_message or f"{label} host is private or local: {host}"
        raise ValueError(message)

    if allowed_hosts is not None and not _host_is_allowed(
        host,
        allowed_hosts,
        allow_subdomains=allow_subdomains,
        allow_leading_dot_hosts=allow_leading_dot_hosts,
    ):
        message = host_not_allowed_message or f"{label} host is not allowlisted: {host}"
        raise ValueError(message)

    if strip_fragment:
        parsed = parsed._replace(fragment="")
    return parsed.geturl()


def _host_is_allowed(
    host: str,
    allowed_hosts: tuple[str, ...] | list[str],
    *,
    allow_subdomains: bool,
    allow_leading_dot_hosts: bool,
) -> bool:
    normalized_hosts = tuple(item.strip().lower() for item in allowed_hosts if item.strip())
    if not normalized_hosts:
        return False
    for allowed_host in normalized_hosts:
        if allow_leading_dot_hosts and allowed_host.startswith("."):
            if host.endswith(allowed_host):
                return True
            continue
        if host == allowed_host:
            return True
        if allow_subdomains and host.endswith(f".{allowed_host}"):
            return True
    return False


def _is_private_or_local_host(host: str) -> bool:
    if host in {"localhost", "localhost.localdomain"}:
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return _is_unsafe_ip_address(address)


def _is_unsafe_ip_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )


@contextmanager
def validated_stream_get(
    client: httpx.Client,
    url: str,
    *,
    validate_url: UrlValidator,
    headers: Mapping[str, str] | None = None,
    max_redirects: int = 5,
) -> Iterator[httpx.Response]:
    """Open a streaming GET while validating every redirect target before fetching it."""

    current_url = validate_url(url)
    last_request: httpx.Request | None = None
    for _ in range(max_redirects + 1):
        request = client.build_request("GET", current_url, headers=headers)
        last_request = request
        response = client.send(request, stream=True, follow_redirects=False)
        if _REDIRECT_STATUS_MIN <= response.status_code < _REDIRECT_STATUS_MAX:
            location = response.headers.get("location")
            response.close()
            if not location:
                raise httpx.HTTPStatusError(
                    "Redirect response did not include a Location header",
                    request=request,
                    response=response,
                )
            current_url = validate_url(urljoin(str(response.url), location))
            continue

        try:
            yield response
        finally:
            response.close()
        return

    raise httpx.TooManyRedirects(
        f"Exceeded maximum redirect count of {max_redirects}",
        request=last_request,
    )
