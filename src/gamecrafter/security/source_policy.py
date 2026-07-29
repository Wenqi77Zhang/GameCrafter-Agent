"""Official-source URL, network, and per-run access policy."""

from __future__ import annotations

import ipaddress
import posixpath
import re
import socket
from dataclasses import dataclass, field
from enum import StrEnum
from threading import Lock
from typing import Protocol
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit

_TRACKING_PARAMETERS = frozenset(
    {
        "fbclid",
        "gclid",
        "mc_cid",
        "mc_eid",
        "request_id",
    }
)


class SourcePolicyError(ValueError):
    """Base error for a source URL rejected before network access."""


class UnsupportedSourceError(SourcePolicyError):
    """Raised when a URL is outside the configured official-source profiles."""


class UnsafeNetworkTargetError(SourcePolicyError):
    """Raised when DNS resolves to a non-public address."""


class AccessBudgetExceededError(SourcePolicyError):
    """Raised before one run exceeds its explicit request budget."""


class AccessPurpose(StrEnum):
    """Policy context for an outbound request."""

    PAGE = "page"
    ASSET = "asset"
    ROBOTS = "robots"


class HostResolver(Protocol):
    """DNS boundary that can be replaced in deterministic tests."""

    def resolve(self, hostname: str) -> tuple[str, ...]:
        """Return every address currently associated with a hostname."""


class SocketHostResolver:
    """Resolve both IPv4 and IPv6 addresses with the operating system."""

    def resolve(self, hostname: str) -> tuple[str, ...]:
        addresses = {
            result[4][0] for result in socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
        }
        return tuple(sorted(addresses))


@dataclass(frozen=True, slots=True)
class SiteAccessRule:
    """One exact official hostname and its allowed path boundaries."""

    site_key: str
    hostname: str
    page_patterns: tuple[str, ...]
    asset_prefixes: tuple[str, ...]
    browser_patterns: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AuthorizedUrl:
    """Canonical URL plus the official profile that authorized it."""

    url: str
    rule: SiteAccessRule


def canonicalize_web_url(
    value: str,
    *,
    drop_parameters: frozenset[str] = frozenset(),
) -> str:
    """Normalize an HTTPS URL without merging semantically distinct pages."""

    if any(ord(character) < 32 for character in value) or "\\" in value:
        raise SourcePolicyError("URL contains forbidden control or backslash characters")
    parsed = urlsplit(value)
    if parsed.scheme.lower() != "https":
        raise SourcePolicyError("only HTTPS official sources are allowed")
    if parsed.username is not None or parsed.password is not None:
        raise SourcePolicyError("credentials are not allowed inside source URLs")
    if not parsed.hostname:
        raise SourcePolicyError("source URL must include a hostname")
    try:
        hostname = parsed.hostname.encode("idna").decode("ascii").lower()
        port = parsed.port
    except (UnicodeError, ValueError) as error:
        raise SourcePolicyError("source URL has an invalid hostname or port") from error
    if port not in {None, 443}:
        raise SourcePolicyError("official sources may use only the default HTTPS port")

    path = parsed.path or "/"
    decoded_path = unquote(path)
    if any(segment in {".", ".."} for segment in decoded_path.split("/")):
        raise SourcePolicyError("source URL path may not contain dot segments")
    normalized_path = posixpath.normpath(path)
    if path.endswith("/") and not normalized_path.endswith("/"):
        normalized_path += "/"
    if not normalized_path.startswith("/"):
        normalized_path = f"/{normalized_path}"

    explicitly_dropped = {parameter.lower() for parameter in drop_parameters}
    query_items = []
    for key, item_value in parse_qsl(parsed.query, keep_blank_values=True):
        lowered = key.lower()
        if (
            lowered.startswith("utm_")
            or lowered in _TRACKING_PARAMETERS
            or lowered in explicitly_dropped
        ):
            continue
        query_items.append((key, item_value))
    query = urlencode(sorted(query_items), doseq=True)
    return urlunsplit(("https", hostname, normalized_path, query, ""))


class OfficialSourcePolicy:
    """Authorize exact official hosts and reject SSRF-capable resolutions."""

    def __init__(
        self,
        rules: tuple[SiteAccessRule, ...],
        *,
        resolver: HostResolver | None = None,
    ) -> None:
        self._rules = {rule.hostname: rule for rule in rules}
        self._resolver = resolver or SocketHostResolver()

    def authorize(
        self,
        value: str,
        *,
        purpose: AccessPurpose = AccessPurpose.PAGE,
        resolve_dns: bool = True,
    ) -> AuthorizedUrl:
        """Validate scheme, exact host, path, and every resolved address."""

        canonical = canonicalize_web_url(value)
        parsed = urlsplit(canonical)
        hostname = parsed.hostname
        if hostname is None or hostname not in self._rules:
            raise UnsupportedSourceError("URL is not on an approved official hostname")
        rule = self._rules[hostname]
        prefixes = {
            AccessPurpose.ASSET: rule.asset_prefixes,
            AccessPurpose.ROBOTS: ("/robots.txt",),
        }
        allowed = (
            any(re.fullmatch(pattern, parsed.path) for pattern in rule.page_patterns)
            if purpose is AccessPurpose.PAGE
            else any(parsed.path.startswith(prefix) for prefix in prefixes[purpose])
        )
        if not allowed:
            raise UnsupportedSourceError(
                f"URL path is outside the approved {purpose.value} boundary"
            )
        if resolve_dns:
            self._validate_public_resolution(hostname)
        return AuthorizedUrl(url=canonical, rule=rule)

    def browser_fallback_allowed(self, value: str) -> bool:
        """Require both page authorization and an explicit browser path prefix."""

        authorized = self.authorize(value, resolve_dns=False)
        path = urlsplit(authorized.url).path
        return any(re.fullmatch(pattern, path) for pattern in authorized.rule.browser_patterns)

    def _validate_public_resolution(self, hostname: str) -> None:
        try:
            addresses = self._resolver.resolve(hostname)
        except OSError as error:
            raise UnsafeNetworkTargetError("official hostname could not be resolved") from error
        if not addresses:
            raise UnsafeNetworkTargetError("official hostname resolved to no addresses")
        for address in addresses:
            try:
                parsed = ipaddress.ip_address(address)
            except ValueError as error:
                raise UnsafeNetworkTargetError("DNS returned an invalid address") from error
            if not parsed.is_global:
                raise UnsafeNetworkTargetError(
                    "official hostname resolved to a non-public network address"
                )


@dataclass(slots=True)
class AccessBudget:
    """Thread-safe counter enforcing one run's bounded discovery plan."""

    max_requests: int
    max_redirects_per_request: int = 3
    max_concurrency_per_host: int = 1
    min_interval_seconds: float = 1.0
    _used_requests: int = field(default=0, init=False, repr=False)
    _lock: Lock = field(default_factory=Lock, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.max_requests <= 0:
            raise ValueError("max_requests must be positive")
        if self.max_redirects_per_request < 0:
            raise ValueError("max_redirects_per_request cannot be negative")
        if self.max_concurrency_per_host <= 0:
            raise ValueError("max_concurrency_per_host must be positive")
        if self.min_interval_seconds < 0:
            raise ValueError("min_interval_seconds cannot be negative")

    @property
    def used_requests(self) -> int:
        with self._lock:
            return self._used_requests

    def consume(self) -> int:
        """Reserve one request before I/O and return the new used count."""

        with self._lock:
            if self._used_requests >= self.max_requests:
                raise AccessBudgetExceededError("source request budget is exhausted")
            self._used_requests += 1
            return self._used_requests
