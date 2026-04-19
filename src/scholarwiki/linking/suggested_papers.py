from __future__ import annotations
import json
from collections import defaultdict
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from ..models import Registry

_PROJECT_ROOT = Path(__file__).parent.parent.parent.parent


def rebuild_suggested_papers(
    wiki_dir: Path,
    registry: Registry,
    staging_dir: Path,
    today: str,
    templates_dir: Path | None = None,
) -> None:
    """Rebuild wiki/suggested_papers.md from roadmap refs not in registry."""
    tdir = templates_dir or (_PROJECT_ROOT / "templates")

    # Collect known DOIs and titles from registry
    known_dois: set[str] = {
        p.doi.lower() for p in registry.papers.values() if p.doi
    }
    known_titles_lower: set[str] = {
        p.title.lower() for p in registry.papers.values()
    }

    # Collect references from all roadmap.json files in staging
    ref_counts: dict[str, dict] = defaultdict(lambda: {
        "title": "", "doi": None, "referenced_by": set(),
        "relationship_types": set(), "significance": "low",
    })

    for paper_dir in staging_dir.iterdir():
        if not paper_dir.is_dir():
            continue
        roadmap_file = paper_dir / "roadmap.json"
        if not roadmap_file.exists():
            continue
        paper_id = paper_dir.name
        entry = registry.papers.get(paper_id)
        paper_slug = paper_id
        if entry and entry.wiki_source_page:
            from pathlib import PurePath
            paper_slug = PurePath(entry.wiki_source_page).stem

        try:
            data = json.loads(roadmap_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        for rel in data.get("relationships") or []:
            target_doi = (rel.get("target_doi") or "").lower().strip()
            target_entity = rel.get("target_entity") or ""
            significance = rel.get("significance") or "low"
            rel_type = rel.get("relationship_type") or "relates_to"

            # Skip if already in registry
            if target_doi and target_doi in known_dois:
                continue
            if target_entity.lower() in known_titles_lower:
                continue

            key = target_doi or target_entity.lower()
            if not key:
                continue

            ref = ref_counts[key]
            ref["title"] = target_entity or ref["title"]
            ref["doi"] = rel.get("target_doi") or ref["doi"]
            ref["referenced_by"].add(paper_slug)
            ref["relationship_types"].add(rel_type)
            if significance == "high":
                ref["significance"] = "high"
            elif significance == "medium" and ref["significance"] != "high":
                ref["significance"] = "medium"

    # Build priority buckets
    def _make_entry(ref: dict) -> dict:
        title = ref["title"]
        words = title.split()
        # Use at most 6 words but stop before the last word so the search
        # query is always a distinct prefix — avoids duplicating the exact
        # title string when the title is short.
        n = min(6, max(1, len(words) - 1))
        search_query = " ".join(words[:n])
        return {
            "title": title,
            "doi": ref["doi"],
            "referenced_by": sorted(ref["referenced_by"]),
            "relationship_types": sorted(ref["relationship_types"]),
            "search_query": search_query,
        }

    high: list[dict] = []
    medium: list[dict] = []
    low: list[dict] = []

    for ref in ref_counts.values():
        count = len(ref["referenced_by"])
        entry = _make_entry(ref)
        if count >= 3:
            high.append(entry)
        elif count == 2:
            medium.append(entry)
        else:
            low.append(entry)

    high.sort(key=lambda x: x["title"])
    medium.sort(key=lambda x: x["title"])
    low.sort(key=lambda x: x["title"])

    env = Environment(loader=FileSystemLoader(str(tdir)), keep_trailing_newline=True)
    tmpl = env.get_template("suggested_papers.md.j2")
    content = tmpl.render(
        last_updated=today,
        high_priority=high,
        medium_priority=medium,
        low_priority=low,
    )

    wiki_dir.mkdir(parents=True, exist_ok=True)
    page_path = wiki_dir / "suggested_papers.md"
    tmp = page_path.with_suffix(".md.tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(page_path)
