from typing import Iterable, List

from .config import (
    CHUNK_OVERLAP_CHARS,
    CHUNK_SIZE_CHARS,
)
from .normalize import normalize_for_search
from .types import Chunk, ExtractedUnit


def _chunk_text(
    text: str,
    max_chars: int,
    overlap_chars: int,
) -> List[str]:
    words = text.split()

    if not words:
        return []

    chunks = []
    current = []
    current_len = 0

    for word in words:
        extra = len(word) + (1 if current else 0)

        if current and current_len + extra > max_chars:
            chunk = " ".join(current).strip()

            if chunk:
                chunks.append(chunk)

            overlap = []
            overlap_len = 0

            for w in reversed(current):
                add = len(w) + (1 if overlap else 0)

                if overlap and overlap_len + add > overlap_chars:
                    break

                overlap.append(w)
                overlap_len += add

            current = list(reversed(overlap))
            current_len = len(" ".join(current))

        if current:
            current_len += 1 + len(word)
        else:
            current_len = len(word)

        current.append(word)

    tail = " ".join(current).strip()

    if tail and (not chunks or tail != chunks[-1]):
        chunks.append(tail)

    return chunks


def chunk_units(
    units: Iterable[ExtractedUnit],
    max_chars: int = CHUNK_SIZE_CHARS,
    overlap_chars: int = CHUNK_OVERLAP_CHARS,
) -> List[Chunk]:
    out = []
    chunk_no = 0

    for unit in units:
        for content in _chunk_text(
            unit.text,
            max_chars=max_chars,
            overlap_chars=overlap_chars,
        ):
            out.append(
                Chunk(
                    content=content,
                    content_norm=normalize_for_search(content),
                    page_no=unit.page_no,
                    chunk_no=chunk_no,
                    extraction_mode=unit.extraction_mode,
                )
            )
            chunk_no += 1

    return out
