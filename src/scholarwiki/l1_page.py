from __future__ import annotations
import re
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from .models import PaperEntry

_PROJECT_ROOT = Path(__file__).parent.parent.parent  # src/scholarwiki/ -> project root


def l1_page_slug(entry: PaperEntry) -> str:
    """Generate filename slug: {firstauthor_lastname}{year}_{first_title_word}."""
    if entry.authors:
        last = entry.authors[0].split(",")[0].strip().lower()
        last = re.sub(r"[^a-z0-9]", "", last)
    else:
        last = "unknown"
    year = str(entry.year) if entry.year else ""
    words = re.sub(r"[^a-z0-9 ]", "", entry.title.lower()).split()
    stopwords = {"a", "an", "the", "is", "are", "of", "for", "in", "on", "and", "or"}
    keyword = next((w for w in words if w not in stopwords), words[0] if words else "paper")
    return f"{last}{year}_{keyword}"


def render_l1_page(entry: PaperEntry, templates_dir: Path | None = None) -> str:
    tdir = templates_dir or (_PROJECT_ROOT / "templates")
    env = Environment(loader=FileSystemLoader(str(tdir)), keep_trailing_newline=True)
    tmpl = env.get_template("l1_source.md.jinja2")
    return tmpl.render(entry=entry)


def write_l1_page(entry: PaperEntry, wiki_dir: Path, templates_dir: Path | None = None) -> Path:
    """Render and write L1 page; return the path written."""
    sources_dir = wiki_dir / "sources"
    sources_dir.mkdir(parents=True, exist_ok=True)
    slug = l1_page_slug(entry)
    page_path = sources_dir / f"{slug}.md"
    page_path.write_text(render_l1_page(entry, templates_dir), encoding="utf-8")
    return page_path


def update_l1_zotero_key(page_path: Path, zotero_key: str) -> None:
    """Regex-replace zotero_key: \"\" in L1 page frontmatter with the real key."""
    if not page_path.exists():
        return
    text = page_path.read_text(encoding="utf-8")
    updated = re.sub(r'zotero_key: ""', f'zotero_key: "{zotero_key}"', text, count=1)
    if updated != text:
        page_path.write_text(updated, encoding="utf-8")
