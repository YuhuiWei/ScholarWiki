from __future__ import annotations
from pathlib import Path

from ..models import Registry


def generate_stats(wiki_dir: Path, registry: Registry) -> str:
    """Return a formatted summary of knowledge base statistics."""
    papers = list(registry.papers.values())
    total = len(papers)
    by_status: dict[str, int] = {}
    for p in papers:
        by_status[p.extraction_status] = by_status.get(p.extraction_status, 0) + 1

    def count_pages(subdir: str) -> int:
        d = wiki_dir / subdir
        return len(list(d.glob("*.md"))) if d.exists() else 0

    concept_count = count_pages("concepts")
    pattern_count = count_pages("patterns")
    style_count = count_pages("writing")

    suggested_count = 0
    sf = wiki_dir / "suggested_papers.md"
    if sf.exists():
        suggested_count = sf.read_text(encoding="utf-8").count("\n### ")

    lines = [
        "ScholarWiki Knowledge Base",
        "=" * 40,
        f"Papers:     {total} total",
    ]
    for status in ["linked", "extracted", "submitted", "queued", "pending"]:
        if status in by_status:
            lines.append(f"  {status}: {by_status[status]}")

    lines.extend([
        f"Concepts:   {concept_count} pages",
        f"Patterns:   {pattern_count} design patterns",
        f"Styles:     {style_count} writing style guides",
        f"Suggested:  {suggested_count} papers recommended",
    ])

    return "\n".join(lines)
