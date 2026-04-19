from __future__ import annotations
import re
from pathlib import Path

from rapidfuzz import fuzz


def slug_from_title(title: str) -> str:
    """Convert a concept title to a filesystem-safe slug."""
    return re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")


def list_concept_index(concepts_dir: Path) -> list[tuple[str, str]]:
    """Return [(title, slug)] for all existing concept pages."""
    if not concepts_dir.exists():
        return []
    index: list[tuple[str, str]] = []
    for page in sorted(concepts_dir.glob("*.md")):
        text = page.read_text(encoding="utf-8")
        m = re.search(r'^title:\s*["\']?(.+?)["\']?\s*$', text, re.MULTILINE)
        title = m.group(1) if m else page.stem.replace("_", " ")
        index.append((title, page.stem))
    return index


def match_concept(
    concept: str,
    index: list[tuple[str, str]],
    threshold: int = 85,
) -> tuple[str, str] | None:
    """Fuzzy-match a concept string against the index.

    Returns (title, slug) of best match if score >= threshold, else None.
    """
    best_ratio = 0
    best_match: tuple[str, str] | None = None
    for title, slug in index:
        ratio = fuzz.token_sort_ratio(concept.lower(), title.lower())
        if ratio > best_ratio:
            best_ratio = ratio
            best_match = (title, slug)
    if best_match and best_ratio >= threshold:
        return best_match
    return None
