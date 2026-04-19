from __future__ import annotations
from pathlib import Path


def write_concept_page(wiki_dir: Path, slug: str, markdown: str) -> None:
    """Atomically write a concept page. Creates wiki/concepts/ if needed."""
    concepts_dir = wiki_dir / "concepts"
    concepts_dir.mkdir(parents=True, exist_ok=True)
    page = concepts_dir / f"{slug}.md"
    tmp = page.with_suffix(".md.tmp")
    tmp.write_text(markdown, encoding="utf-8")
    tmp.replace(page)
