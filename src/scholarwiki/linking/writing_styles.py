from __future__ import annotations
from collections import Counter, defaultdict
from pathlib import Path

from .concept_match import slug_from_title


def write_style_page(wiki_dir: Path, slug: str, markdown: str) -> None:
    """Atomically write a writing style page. Creates wiki/writing/ if needed."""
    writing_dir = wiki_dir / "writing"
    writing_dir.mkdir(parents=True, exist_ok=True)
    page = writing_dir / f"{slug}.md"
    tmp = page.with_suffix(".md.tmp")
    tmp.write_text(markdown, encoding="utf-8")
    tmp.replace(page)


def _jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 0.0
    union = len(a | b)
    return len(a & b) / union if union else 0.0


def _common_tags(papers: list[dict]) -> list[str]:
    """Return tags common to all papers; fall back to most-frequent tags."""
    tag_sets = [set(p.get("topic_tags") or []) for p in papers]
    if not tag_sets:
        return []
    common = tag_sets[0].copy()
    for t in tag_sets[1:]:
        common &= t
    if common:
        return sorted(common)[:2]
    # No common tags — use most frequent
    all_tags: list[str] = []
    for s in tag_sets:
        all_tags.extend(s)
    return [t for t, _ in Counter(all_tags).most_common(2)]


def cluster_writing_styles(papers: list[dict]) -> dict[str, dict]:
    """
    Cluster papers by venue (exact match) then topic_tags (Jaccard >= 0.3).

    Each paper dict: paper_id, venue, topic_area, topic_tags (list).
    Returns: {style_slug: {"paper_ids": [...], "title": "..."}}
    All groups with >=1 paper are included.
    """
    if not papers:
        return {}

    # Step 1: group by exact venue string
    venue_groups: dict[str, list[dict]] = defaultdict(list)
    for p in papers:
        venue = (p.get("venue") or "unknown").strip()
        venue_groups[venue].append(p)

    result: dict[str, dict] = {}

    for venue, venue_papers in venue_groups.items():
        venue_slug = slug_from_title(venue)

        if len(venue_papers) < 2:
            # Small group — single cluster
            tags = _common_tags(venue_papers)
            tag_part = "_".join(slug_from_title(t) for t in tags) if tags else "general"
            slug = f"{venue_slug}_{tag_part}"
            slug = _unique_slug(slug, result)
            title = f"{venue} — {', '.join(tags)}" if tags else venue
            result[slug] = {"paper_ids": [p["paper_id"] for p in venue_papers], "title": title}
            continue

        # Step 2: Jaccard sub-clustering within venue
        assigned = [False] * len(venue_papers)
        for i, paper in enumerate(venue_papers):
            if assigned[i]:
                continue
            cluster = [paper]
            assigned[i] = True
            tags_i = set(paper.get("topic_tags") or [])
            for j in range(i + 1, len(venue_papers)):
                if assigned[j]:
                    continue
                tags_j = set(venue_papers[j].get("topic_tags") or [])
                if _jaccard(tags_i, tags_j) >= 0.3:
                    cluster.append(venue_papers[j])
                    assigned[j] = True

            tags = _common_tags(cluster)
            tag_part = "_".join(slug_from_title(t) for t in tags) if tags else "general"
            slug = f"{venue_slug}_{tag_part}"
            slug = _unique_slug(slug, result)
            title = f"{venue} — {', '.join(tags)}" if tags else venue
            result[slug] = {"paper_ids": [p["paper_id"] for p in cluster], "title": title}

    return result


def _unique_slug(slug: str, existing: dict) -> str:
    """Append numeric suffix if slug already used."""
    if slug not in existing:
        return slug
    i = 2
    while f"{slug}_{i}" in existing:
        i += 1
    return f"{slug}_{i}"
