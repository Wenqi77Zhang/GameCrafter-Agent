"""Small deterministic HTML metadata parser for official listing pages."""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser

from gamecrafter.application.ports.source_capture import EvidenceDocument, EvidenceImage


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
class HtmlImage:
    """One image reference discovered without downloading its bytes."""

    url: str
    alt_text: str | None


@dataclass(frozen=True, slots=True)
class ParsedHtml:
    """Bounded metadata extracted without running scripts."""

    title: str | None
    document_language: str | None
    links: tuple[HtmlLink, ...]
    alternates: tuple[AlternateLink, ...]
    images: tuple[HtmlImage, ...]
    metadata: dict[str, str]


class _MetadataParser(HTMLParser):
    def __init__(self, *, max_links: int, max_images: int) -> None:
        super().__init__(convert_charrefs=True)
        self.max_links = max_links
        self.max_images = max_images
        self.document_language: str | None = None
        self.links: list[HtmlLink] = []
        self.alternates: list[AlternateLink] = []
        self.images: list[HtmlImage] = []
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
        elif tag == "img" and len(self.images) < self.max_images:
            source = attributes.get("src") or attributes.get("data-src")
            if source:
                alt_text = attributes.get("alt")
                self.images.append(
                    HtmlImage(
                        url=source,
                        alt_text=" ".join(alt_text.split()) if alt_text else None,
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
            images=tuple(self.images),
            metadata=dict(self.metadata),
        )


def parse_html_metadata(
    html: str,
    *,
    max_links: int = 200,
    max_images: int = 20,
) -> ParsedHtml:
    """Extract bounded anchors and metadata from untrusted HTML."""

    parser = _MetadataParser(max_links=max_links, max_images=max_images)
    parser.feed(html)
    parser.close()
    return parser.result()


class _VisibleTextParser(HTMLParser):
    _IGNORED = frozenset({"script", "style", "noscript", "template", "svg"})
    _BLOCKS = frozenset(
        {
            "article",
            "br",
            "div",
            "footer",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "header",
            "li",
            "main",
            "nav",
            "p",
            "section",
            "table",
            "td",
            "th",
            "tr",
        }
    )

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._ignored_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._IGNORED:
            self._ignored_depth += 1
        elif self._ignored_depth == 0 and tag in self._BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._IGNORED and self._ignored_depth > 0:
            self._ignored_depth -= 1
        elif self._ignored_depth == 0 and tag in self._BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._ignored_depth == 0:
            self.parts.append(data)


def extract_evidence_document(html: str) -> EvidenceDocument:
    """Extract stable visible text without executing or trusting page scripts."""

    metadata = parse_html_metadata(html)
    parser = _VisibleTextParser()
    parser.feed(html)
    parser.close()
    lines = []
    for raw_line in "".join(parser.parts).splitlines():
        line = " ".join(raw_line.split())
        if line and (not lines or line != lines[-1]):
            lines.append(line)
    title = (
        metadata.metadata.get("og:title")
        or metadata.metadata.get("twitter:title")
        or metadata.title
        or "Untitled official page"
    )
    images: list[EvidenceImage] = []
    seen_images: set[str] = set()
    social_image = metadata.metadata.get("og:image") or metadata.metadata.get("twitter:image")
    if social_image:
        images.append(EvidenceImage(url=social_image, alt_text="social preview"))
        seen_images.add(social_image)
    for candidate in metadata.images:
        if candidate.url in seen_images or not candidate.alt_text:
            continue
        seen_images.add(candidate.url)
        images.append(EvidenceImage(url=candidate.url, alt_text=candidate.alt_text))
    return EvidenceDocument(
        title=" ".join(title.split())[:500],
        normalized_text="\n".join(lines),
        document_language=metadata.document_language,
        metadata=metadata.metadata,
        images=tuple(images),
    )
