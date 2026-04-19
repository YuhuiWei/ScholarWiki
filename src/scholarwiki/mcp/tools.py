from __future__ import annotations
"""Tool implementations — pure functions that read from wiki_dir."""
import re
from pathlib import Path

from rapidfuzz import fuzz

WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
_SKIP_FILES = {"index.md", "log.md"}


def search_wiki(query: str, wiki_dir: Path, max_results: int = 5) -> list[dict]:
    """Keyword + fuzzy search across all wiki markdown files."""
    query_terms = query.lower().split()
    results = []

    for md_file in wiki_dir.rglob("*.md"):
        if md_file.name in _SKIP_FILES:
            continue

        content = md_file.read_text(encoding="utf-8")
        content_lower = content.lower()

        # Score: number of query terms present
        term_hits = sum(1 for t in query_terms if t in content_lower)
        if term_hits == 0:
            continue

        # Extract title from frontmatter or derive from filename
        title = md_file.stem.replace("_", " ")
        title_match = re.search(r'^title:\s*"?(.+?)"?\s*$', content, re.MULTILINE)
        if title_match:
            title = title_match.group(1)

        # Bonus for title relevance
        title_score = fuzz.token_sort_ratio(query.lower(), title.lower()) / 100
        score = term_hits + title_score

        # Excerpt: first 300 chars of body (after frontmatter)
        body = content.split("---", 2)[-1].strip() if content.startswith("---") else content
        excerpt = (body[:300].rsplit(" ", 1)[0] + "...") if len(body) > 300 else body

        results.append({
            "path": str(md_file.relative_to(wiki_dir)),
            "title": title,
            "score": round(score, 2),
            "excerpt": excerpt,
        })

    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:max_results]


def read_page(wiki_dir: Path, subdir: str, name: str) -> str | None:
    """Read a wiki page by subdirectory and name/slug. Falls back to fuzzy match."""
    page = wiki_dir / subdir / f"{name}.md"
    if page.exists():
        return page.read_text(encoding="utf-8")

    target_dir = wiki_dir / subdir
    if not target_dir.exists():
        return None

    best_match = None
    best_score = 0
    for f in target_dir.glob("*.md"):
        score = fuzz.token_sort_ratio(name.lower(), f.stem.replace("_", " ").lower())
        if score > best_score and score >= 70:
            best_score = score
            best_match = f

    if best_match:
        return best_match.read_text(encoding="utf-8")
    return None


def read_style_page(wiki_dir: Path, venue: str, topic: str = "") -> str | None:
    """Find a writing style page matching venue and optional topic."""
    style_dir = wiki_dir / "writing"
    if not style_dir.exists():
        return None

    venue_lower = venue.lower().replace(" ", "_")
    topic_lower = topic.lower().replace(" ", "_") if topic else ""

    best_match = None
    best_score = 0
    for f in style_dir.glob("*.md"):
        stem = f.stem.lower()
        content = f.read_text(encoding="utf-8").lower()
        score = 0
        if venue_lower in stem:
            score += 2
        elif venue_lower in content:
            score += 1
        if topic_lower and topic_lower in stem:
            score += 2
        elif topic_lower and topic_lower in content:
            score += 1

        if score > best_score:
            best_score = score
            best_match = f

    if best_match and best_score >= 1:
        return best_match.read_text(encoding="utf-8")
    return None
