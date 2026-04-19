from __future__ import annotations
import re
from pathlib import Path


_SENTINEL = "<!-- Populated by linking pass -->"


def backfill_source_page(
    page_path: Path,
    knowledge_text: str,
    relationships_text: str,
    experimental_text: str,
    logic_text: str,
    writing_text: str,
) -> None:
    """Replace the five linking-pass sentinel blocks in a source page. Idempotent."""
    if not page_path.exists():
        return
    text = page_path.read_text(encoding="utf-8")
    if _SENTINEL not in text:
        return  # Already backfilled

    replacements = [
        ("## Knowledge Contributions", knowledge_text),
        ("## Research Relationships", relationships_text),
        ("## Experimental Design", experimental_text),
        ("## Research Logic", logic_text),
        ("## Writing Notes", writing_text),
    ]

    for section_header, content in replacements:
        pattern = re.compile(
            rf"({re.escape(section_header)}\n){re.escape(_SENTINEL)}",
            re.MULTILINE,
        )
        text = pattern.sub(
            lambda m, c=content: m.group(1) + c,
            text,
            count=1,
        )

    tmp = page_path.with_suffix(".md.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(page_path)
