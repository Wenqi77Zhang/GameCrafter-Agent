"""Deterministic, evidence-offset-preserving text chunking."""

from __future__ import annotations

import re
from dataclasses import dataclass
from hashlib import sha256

DEFAULT_MAX_CHARS = 4000
DEFAULT_OVERLAP_CHARS = 400
CHUNKER_VERSION = "unicode-boundary-v1"
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?。！？])\s+")


@dataclass(frozen=True, slots=True)
class TextChunk:
    """One exact slice of normalized source text."""

    index: int
    start_offset: int
    end_offset: int
    text: str
    chunk_id: str

    def __post_init__(self) -> None:
        if self.index < 0:
            raise ValueError("chunk index must be nonnegative")
        if self.start_offset < 0 or self.end_offset <= self.start_offset:
            raise ValueError("chunk offsets must describe a non-empty range")
        if self.end_offset - self.start_offset != len(self.text):
            raise ValueError("chunk offsets must match its Unicode text length")
        if len(self.chunk_id) != 64 or any(
            character not in "0123456789abcdef" for character in self.chunk_id
        ):
            raise ValueError("chunk_id must be a SHA-256 digest")


class DeterministicTextChunker:
    """Prefer natural boundaries while preserving exact Python code-point offsets."""

    def __init__(
        self,
        *,
        max_chars: int = DEFAULT_MAX_CHARS,
        overlap_chars: int = DEFAULT_OVERLAP_CHARS,
    ) -> None:
        if isinstance(max_chars, bool) or not isinstance(max_chars, int) or max_chars <= 0:
            raise ValueError("max_chars must be a positive integer")
        if (
            isinstance(overlap_chars, bool)
            or not isinstance(overlap_chars, int)
            or overlap_chars < 0
        ):
            raise ValueError("overlap_chars must be a nonnegative integer")
        if overlap_chars >= max_chars:
            raise ValueError("overlap_chars must be smaller than max_chars")
        self.max_chars = max_chars
        self.overlap_chars = overlap_chars

    def split(self, text: str) -> tuple[TextChunk, ...]:
        """Return stable exact slices without normalizing or trimming the source."""

        if not isinstance(text, str) or not text.strip():
            raise ValueError("normalized source text must not be blank")
        chunks: list[TextChunk] = []
        start = 0
        while start < len(text):
            hard_end = min(start + self.max_chars, len(text))
            end = (
                hard_end
                if hard_end == len(text)
                else _preferred_end(text, start=start, hard_end=hard_end)
            )
            chunk_text = text[start:end]
            chunks.append(
                TextChunk(
                    index=len(chunks),
                    start_offset=start,
                    end_offset=end,
                    text=chunk_text,
                    chunk_id=_chunk_id(
                        index=len(chunks),
                        start=start,
                        end=end,
                        text=chunk_text,
                        max_chars=self.max_chars,
                        overlap_chars=self.overlap_chars,
                    ),
                )
            )
            if end == len(text):
                break
            start = end - self.overlap_chars
        return tuple(chunks)


def _preferred_end(text: str, *, start: int, hard_end: int) -> int:
    lower_bound = start + (hard_end - start) // 2

    paragraph = text.rfind("\n\n", lower_bound, hard_end)
    if paragraph >= 0:
        return paragraph + 2

    newline = text.rfind("\n", lower_bound, hard_end)
    if newline >= 0:
        return newline + 1

    sentence_ends = [
        start + match.end()
        for match in _SENTENCE_BOUNDARY.finditer(text[start:hard_end])
        if start + match.end() >= lower_bound
    ]
    return sentence_ends[-1] if sentence_ends else hard_end


def _chunk_id(
    *,
    index: int,
    start: int,
    end: int,
    text: str,
    max_chars: int,
    overlap_chars: int,
) -> str:
    canonical = f"{CHUNKER_VERSION}\0{max_chars}\0{overlap_chars}\0{index}\0{start}\0{end}\0{text}"
    return sha256(canonical.encode("utf-8")).hexdigest()
