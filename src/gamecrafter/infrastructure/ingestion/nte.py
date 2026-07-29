"""Deterministic adapters and access profiles for official NTE websites."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from urllib.parse import urljoin, urlsplit, urlunsplit

from gamecrafter.application.ports.site_adapter import AdaptedSource, DiscoveredPage
from gamecrafter.domain.knowledge.sources import SourceType
from gamecrafter.infrastructure.ingestion.html import parse_html_metadata
from gamecrafter.security.source_policy import (
    SiteAccessRule,
    SourcePolicyError,
    canonicalize_web_url,
)

NTE_GLOBAL_RULE = SiteAccessRule(
    site_key="nte-global",
    hostname="nte.perfectworld.com",
    page_patterns=(
        r"/(?:en|cn|jp)/main\.html",
        r"/(?:en|cn|jp)/article/news(?:/(?:gamenews|gamebroad|gameevent))?"
        r"/index\d*\.html",
        r"/(?:en|cn|jp)/article/news/(?:gamenews|gamebroad|gameevent)"
        r"/\d{8}/\d+\.html",
    ),
    asset_prefixes=("/",),
    browser_patterns=(r"/(?:en|cn|jp)/main\.html",),
)

NTE_MAINLAND_RULE = SiteAccessRule(
    site_key="nte-mainland-cn",
    hostname="yh.wanmei.com",
    page_patterns=(
        r"/main\.html",
        r"/(?:m/)?news(?:/(?:gamenews|gamebroad|gameevent))?/index\d*\.html",
        r"/(?:m/)?news/(?:gamenews|gamebroad|gameevent)/\d{8}/\d+\.html",
    ),
    asset_prefixes=("/",),
    browser_patterns=(r"/main\.html",),
)

NTE_ACCESS_RULES = (NTE_GLOBAL_RULE, NTE_MAINLAND_RULE)

_GLOBAL_DETAIL_PATTERN = re.compile(
    r"^/(?P<locale>en|cn|jp)/article/news/"
    r"(?P<category>gamenews|gamebroad|gameevent)/"
    r"(?P<date>\d{8})/(?P<article_id>\d+)\.html$"
)
_MAINLAND_DETAIL_PATTERN = re.compile(
    r"^/(?:m/)?news/(?P<category>gamenews|gamebroad|gameevent)/"
    r"(?P<date>\d{8})/(?P<article_id>\d+)\.html$"
)
_ISO_DATE_PATTERN = re.compile(r"\b(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})\b")
_FAQ_KEYWORDS = (
    "faq",
    "frequently asked",
    "setup guide",
    "guide",
    "常见问题",
    "指南",
    "よくある質問",
    "ガイド",
)
_UPDATE_KEYWORDS = (
    "version",
    "update",
    "maintenance",
    "patch",
    "版本",
    "更新",
    "维护",
    "修复",
    "アップデート",
    "メンテナンス",
    "更新",
)


class NteSiteAdapter:
    """Shared implementation for one NTE official-site profile."""

    def __init__(self, *, mainland: bool = False) -> None:
        self._mainland = mainland
        self._access_rule = NTE_MAINLAND_RULE if mainland else NTE_GLOBAL_RULE
        self.site_key = self._access_rule.site_key
        self._hostname = self._access_rule.hostname
        self._detail_pattern = _MAINLAND_DETAIL_PATTERN if mainland else _GLOBAL_DETAIL_PATTERN

    def supports(self, url: str) -> bool:
        try:
            canonical = self.canonicalize(url)
        except SourcePolicyError:
            return False
        path = urlsplit(canonical).path
        return any(re.fullmatch(pattern, path) for pattern in self._access_rule.page_patterns)

    def canonicalize(self, url: str) -> str:
        canonical = canonicalize_web_url(url)
        parsed = urlsplit(canonical)
        if parsed.hostname != self._hostname:
            raise SourcePolicyError("URL belongs to another site adapter")
        path = parsed.path
        if self._mainland and path.startswith("/m/news/"):
            path = path.removeprefix("/m")
        query = "" if path == "/main.html" or path.endswith("/main.html") else parsed.query
        return urlunsplit(("https", self._hostname, path, query, ""))

    def adapt(self, url: str, *, title: str) -> AdaptedSource:
        """Normalize a homepage or article selected for evidence capture."""

        canonical = self.canonicalize(url)
        path = urlsplit(canonical).path
        detail_match = self._detail_pattern.fullmatch(path)
        if detail_match is not None:
            category = detail_match.group("category")
            source_type, basis = _classify(category, title)
            locale = "zh-CN" if self._mainland else detail_match.group("locale")
            return AdaptedSource(
                canonical_url=canonical,
                site_key=self.site_key,
                locale=locale,
                region="CN" if self._mainland else "global",
                source_type=source_type,
                raw_category=category,
                classification_basis=basis,
                family_signal=f"{category}:path-date:{detail_match.group('date')}",
            )

        if self.browser_fallback_allowed(canonical):
            locale = "zh-CN" if self._mainland else path.split("/")[1]
            return AdaptedSource(
                canonical_url=canonical,
                site_key=self.site_key,
                locale=locale,
                region="CN" if self._mainland else "global",
                source_type=SourceType.OVERVIEW,
                raw_category=None,
                classification_basis="official homepage path",
            )

        raise SourcePolicyError("listing pages are discovery inputs, not source evidence")

    def discover(self, html: str, *, page_url: str) -> tuple[DiscoveredPage, ...]:
        canonical_page = self.canonicalize(page_url)
        candidates: list[DiscoveredPage] = []
        seen: set[str] = set()
        for link in parse_html_metadata(html).links:
            if not link.href or not link.text:
                continue
            try:
                candidate_url = self.canonicalize(urljoin(canonical_page, link.href))
            except SourcePolicyError:
                continue
            path_match = self._detail_pattern.fullmatch(urlsplit(candidate_url).path)
            if path_match is None or candidate_url in seen:
                continue
            seen.add(candidate_url)
            adapted = self.adapt(candidate_url, title=link.text)
            published_at = _extract_date(link.text)
            candidates.append(
                DiscoveredPage(
                    canonical_url=adapted.canonical_url,
                    site_key=adapted.site_key,
                    locale=adapted.locale,
                    region=adapted.region,
                    title=_clean_title(link.text),
                    source_type=adapted.source_type,
                    raw_category=adapted.raw_category,
                    classification_basis=adapted.classification_basis,
                    published_at=published_at,
                    family_signal=adapted.family_signal,
                )
            )
        return tuple(candidates)

    def browser_fallback_allowed(self, url: str) -> bool:
        try:
            path = urlsplit(self.canonicalize(url)).path
        except SourcePolicyError:
            return False
        return path == "/main.html" or (
            not self._mainland and re.fullmatch(r"/(?:en|cn|jp)/main\.html", path) is not None
        )


def _extract_date(text: str) -> datetime | None:
    match = _ISO_DATE_PATTERN.search(text)
    if match is not None:
        try:
            return datetime(
                int(match.group(1)),
                int(match.group(2)),
                int(match.group(3)),
                tzinfo=UTC,
            )
        except ValueError:
            return None
    return None


def _classify(category: str, title: str) -> tuple[SourceType, str]:
    normalized_title = title.casefold()
    if category == "gameevent":
        return SourceType.EVENT, "official category: gameevent"
    if any(keyword in normalized_title for keyword in _FAQ_KEYWORDS):
        return SourceType.GUIDE_FAQ, "title rule: guide or FAQ"
    if any(keyword in normalized_title for keyword in _UPDATE_KEYWORDS):
        return SourceType.UPDATE, "title rule: version, maintenance, or update"
    return SourceType.NEWS, f"official category: {category}"


def _clean_title(value: str) -> str:
    without_date = _ISO_DATE_PATTERN.sub("", value)
    return " ".join(without_date.split()).strip(" -|")


NTE_SITE_ADAPTERS = (
    NteSiteAdapter(),
    NteSiteAdapter(mainland=True),
)
