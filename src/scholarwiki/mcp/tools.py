from __future__ import annotations
"""Tool implementations — pure functions that read from wiki_dir."""
import re
from pathlib import Path
from typing import TYPE_CHECKING

from rapidfuzz import fuzz

if TYPE_CHECKING:
    from ..models import Registry

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


_SECTION_KEYWORDS: dict[str, list[str]] = {
    "abstract": ["abstract"],
    "introduction": ["introduction", "background"],
    "methods": ["methods", "materials and methods", "methodology", "experimental procedures"],
    "results": ["results", "findings"],
    "discussion": ["discussion", "conclusion", "conclusions"],
}


def read_source_pdf_section(
    paper_slug: str,
    section: str,
    raw_dir: Path,
    registry: "Registry",
    max_chars: int = 8000,
) -> str:
    """Extract text from a section of a paper's source PDF using pymupdf.

    Args:
        paper_slug: Slug of the paper (e.g., "lopez2018_scvi") or paper_id.
        section:    Section name ("abstract", "introduction", "methods", "results",
                    "discussion", "full") or a 1-based page number as a string.
        raw_dir:    Path to the raw/ directory containing papers/.
        registry:   Registry object for slug → paper_id resolution.
        max_chars:  Maximum characters to return (default 8000).

    Returns:
        Extracted text, or an error message string.
    """
    try:
        import fitz  # pymupdf
    except ImportError:
        return "Error: pymupdf not installed. Run: pip install pymupdf"

    # Resolve paper_slug to a PDF path
    papers_dir = raw_dir / "papers"
    pdf_path: Path | None = None

    # Try direct paper_id lookup first, then slug-based search
    for entry in registry.papers.values():
        slug = Path(entry.wiki_source_page).stem if entry.wiki_source_page else entry.paper_id
        if slug == paper_slug or entry.paper_id == paper_slug:
            candidate = papers_dir / f"{entry.paper_id}.pdf"
            if candidate.exists():
                pdf_path = candidate
                break

    if pdf_path is None:
        return f"Error: No PDF found for '{paper_slug}'."

    try:
        doc = fitz.open(str(pdf_path))
    except Exception as exc:
        return f"Error opening PDF: {exc}"

    # Page number shortcut
    if section.isdigit():
        page_num = int(section) - 1
        if page_num < 0 or page_num >= len(doc):
            return f"Error: Page {section} out of range (document has {len(doc)} pages)."
        text = doc[page_num].get_text()
        doc.close()
        return text[:max_chars]

    if section == "full":
        text = "\n".join(page.get_text() for page in doc)
        doc.close()
        return text[:max_chars]

    # Section-based extraction: find the section by scanning page headers
    keywords = _SECTION_KEYWORDS.get(section.lower())
    if keywords is None:
        doc.close()
        return (
            f"Error: Unknown section '{section}'. "
            "Use: abstract, introduction, methods, results, discussion, full, or a page number."
        )

    # Extract full text with page boundaries
    pages_text = [page.get_text() for page in doc]
    doc.close()

    # Find start page of requested section
    start_idx: int | None = None
    for i, page_text in enumerate(pages_text):
        first_200 = page_text[:200].lower()
        if any(kw in first_200 for kw in keywords):
            start_idx = i
            break

    if start_idx is None:
        # Fall back: search anywhere on page if header not found
        for i, page_text in enumerate(pages_text):
            if any(kw in page_text.lower() for kw in keywords):
                start_idx = i
                break

    if start_idx is None:
        return f"Section '{section}' not found in PDF. Try section='full' or a page number."

    # Collect text from start_idx until next known section or max_chars
    collected = pages_text[start_idx]
    next_sections = [kw for s, kws in _SECTION_KEYWORDS.items() if s != section.lower() for kw in kws]
    for page_text in pages_text[start_idx + 1:]:
        first_200 = page_text[:200].lower()
        if any(kw in first_200 for kw in next_sections):
            break
        collected += page_text
        if len(collected) >= max_chars:
            break

    return collected[:max_chars]


def get_bibliography(
    slugs: list[str], wiki_dir: Path, registry: "Registry",
) -> str:
    """Build a formatted bibliography from a list of paper slugs or wiki-link keys.

    Looks up each slug in source pages to find the citation field, falling back
    to reconstructing a citation from frontmatter metadata.
    """
    import yaml

    entries: list[str] = []
    seen: set[str] = set()

    for slug in slugs:
        slug = slug.strip().strip("[]")  # handle [[slug]] format
        if slug in seen:
            continue
        seen.add(slug)

        content = read_page(wiki_dir, "sources", slug)
        if not content:
            entries.append(f"- [{slug}] — *not found in wiki*")
            continue

        # Parse frontmatter
        parts = content.split("---", 2)
        if len(parts) < 3:
            entries.append(f"- [{slug}] — *could not parse frontmatter*")
            continue

        try:
            fm = yaml.safe_load(parts[1])
        except Exception:
            fm = {}

        citation = fm.get("citation")
        if citation:
            entries.append(f"- {citation}")
        else:
            # Reconstruct from metadata
            authors = fm.get("authors", [])
            year = fm.get("year", "n.d.")
            title = fm.get("title", slug)
            venue = fm.get("venue", "")
            doi = fm.get("doi", "")

            if authors:
                # APA-style: Last, F. I., Last2, F. I. (Year). Title. Venue.
                author_str = "; ".join(str(a) for a in authors[:3])
                if len(authors) > 3:
                    author_str += " et al."
            else:
                author_str = "Unknown"

            cite = f"{author_str} ({year}). {title}."
            if venue:
                cite += f" *{venue}*."
            if doi:
                cite += f" https://doi.org/{doi}"
            entries.append(f"- {cite}")

    if not entries:
        return "No papers specified."

    return "## Bibliography\n\n" + "\n".join(entries)


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
