"""Small deterministic HTML metadata parser for official listing pages."""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser


@dataclass(frozen=True, slots=True)
class HtmlLink:
    """One anchor's URL and visible text."""

    href: str
    text: str


@dataclass(frozen=True, slots=True)
class AlternateLink:
    """Official alternate-language relationship declared by a page."""

    href: str
    language: str | None


@dataclass(frozen=True, slots=True)
class ParsedHtml:
    """Bounded metadata extracted without running scripts."""

    title: str | None
    document_language: str | None
    links: tuple[HtmlLink, ...]
    alternates: tuple[AlternateLink, ...]
    metadata: dict[str, str]


class _MetadataParser(HTMLParser):
    def __init__(self, *, max_links: int) -> None:
        super().__init__(convert_charrefs=True)
        self.max_links = max_links
        self.document_language: str | None = None
        self.links: list[HtmlLink] = []
        self.alternates: list[AlternateLink] = []
        self.metadata: dict[str, str] = {}
        self._in_title = False
        self._title_parts: list[str] = []
        self._anchor_href: str | None = None
        self._anchor_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {key.lower(): value for key, value in attrs}
        if tag == "html" and attributes.get("lang"):
            self.document_language = attributes["lang"]
        elif tag == "title":
            self._in_title = True
        elif tag == "a" and len(self.links) < self.max_links:
            self._anchor_href = attributes.get("href")
            self._anchor_parts = []
        elif tag == "meta":
            key = attributes.get("property") or attributes.get("name")
            content = attributes.get("content")
            if key and content:
                self.metadata.setdefault(key.lower(), content.strip())
        elif tag == "link":
            rel = (attributes.get("rel") or "").lower().split()
            href = attributes.get("href")
            if "alternate" in rel and href and len(self.alternates) < self.max_links:
                self.alternates.append(
                    AlternateLink(
                        href=href,
                        language=attributes.get("hreflang"),
                    )
                )

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        elif tag == "a" and self._anchor_href is not None:
            text = " ".join(" ".join(self._anchor_parts).split())
            self.links.append(HtmlLink(href=self._anchor_href, text=text))
            self._anchor_href = None
            self._anchor_parts = []

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title_parts.append(data)
        if self._anchor_href is not None:
            self._anchor_parts.append(data)

    def result(self) -> ParsedHtml:
        title = " ".join(" ".join(self._title_parts).split()) or None
        return ParsedHtml(
            title=title,
            document_language=self.document_language,
            links=tuple(self.links),
            alternates=tuple(self.alternates),
            metadata=dict(self.metadata),
        )


def parse_html_metadata(html: str, *, max_links: int = 200) -> ParsedHtml:
    """Extract bounded anchors and metadata from untrusted HTML."""

    parser = _MetadataParser(max_links=max_links)
    parser.feed(html)
    parser.close()
    return parser.result()
