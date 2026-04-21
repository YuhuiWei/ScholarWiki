from __future__ import annotations
import re
from collections import Counter, defaultdict
from pathlib import Path

from .concept_match import slug_from_title

# Canonical names for common venues (lowercase key → canonical display name)
_VENUE_CANONICAL: dict[str, str] = {
    "neurips": "NeurIPS",
    "nips": "NeurIPS",
    "iclr": "ICLR",
    "icml": "ICML",
    "aaai": "AAAI",
    "acl": "ACL",
    "emnlp": "EMNLP",
    "naacl": "NAACL",
    "cvpr": "CVPR",
    "iccv": "ICCV",
    "eccv": "ECCV",
    "biorxiv": "bioRxiv",
    "medrxiv": "medRxiv",
    "arxiv": "arXiv",
    "science": "Science",
    "nature": "Nature",
    "nature methods": "Nature Methods",
    "nature communications": "Nature Communications",
    "cell": "Cell",
    "pnas": "PNAS",
    "plos": "PLOS",
}

# Venue → broad category for pooling across venues in small corpora
_VENUE_CATEGORY: dict[str, str] = {
    "NeurIPS": "CS ML Conference",
    "ICML": "CS ML Conference",
    "ICLR": "CS ML Conference",
    "AAAI": "CS ML Conference",
    "CVPR": "CS ML Conference",
    "ICCV": "CS ML Conference",
    "ECCV": "CS ML Conference",
    "ACL": "CS NLP Conference",
    "EMNLP": "CS NLP Conference",
    "NAACL": "CS NLP Conference",
    "Science": "Biology Journal",
    "Nature": "Biology Journal",
    "Nature Methods": "Biology Journal",
    "Nature Communications": "Biology Journal",
    "Cell": "Biology Journal",
    "PNAS": "Biology Journal",
    "PLOS": "Biology Journal",
    "bioRxiv": "Biology Preprint",
    "medRxiv": "Biology Preprint",
    "arXiv": "CS Preprint",
}


def _normalize_venue(venue: str) -> str:
    """Return a canonical, year-stripped venue name for clustering.

    Examples:
        "NeurIPS 2023"             → "NeurIPS"
        "ICLR 2026 (under review)" → "ICLR"
        "bioRxiv"                  → "bioRxiv"
    """
    if not venue:
        return "unknown"
    # Strip parentheticals: "(under review)", "(workshop)", etc.
    v = re.sub(r"\s*\([^)]*\)", "", venue).strip()
    # Strip trailing 4-digit year
    v = re.sub(r"\s+\d{4}$", "", v).strip()
    return _VENUE_CANONICAL.get(v.lower(), v)


def _venue_category(norm_venue: str) -> str:
    return _VENUE_CATEGORY.get(norm_venue, "Other")


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


def _word_set(tags: list[str]) -> set[str]:
    """Flatten tag list into a set of individual words (lowercase, stripped).

    "multimodal deep learning", "multimodal learning"
    → {"multimodal", "deep", "learning"}   ∩   {"multimodal", "learning"}
    → Jaccard = 2/3 = 0.67

    This tolerates slight phrasing variation between papers better than
    treating each full tag phrase as an atomic token.
    """
    words: set[str] = set()
    stop = {"in", "of", "for", "and", "the", "a", "an", "with", "on", "to"}
    for tag in tags:
        for word in re.split(r"[\s\-_/]+", tag.lower()):
            word = word.strip(".,;:()")
            if word and word not in stop and len(word) > 1:
                words.add(word)
    return words


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


def _jaccard_sub_cluster(papers: list[dict], threshold: float = 0.25) -> list[list[dict]]:
    """Greedy word-level Jaccard sub-clustering within a group.

    Uses word-level comparison so "multimodal deep learning" and "multimodal learning"
    correctly cluster together (Jaccard ≈ 0.67 on words, vs 0.0 on full tag strings).
    """
    assigned = [False] * len(papers)
    clusters: list[list[dict]] = []
    for i, paper in enumerate(papers):
        if assigned[i]:
            continue
        cluster = [paper]
        assigned[i] = True
        words_i = _word_set(paper.get("topic_tags") or [])
        for j in range(i + 1, len(papers)):
            if assigned[j]:
                continue
            words_j = _word_set(papers[j].get("topic_tags") or [])
            if _jaccard(words_i, words_j) >= threshold:
                cluster.append(papers[j])
                assigned[j] = True
        clusters.append(cluster)
    return clusters


def cluster_writing_styles(papers: list[dict]) -> dict[str, dict]:
    """
    Two-level clustering: venue category → Jaccard sub-cluster by topic_tags.

    Level 1: Papers are pooled by venue category (CS ML Conference, Biology Journal,
    Biology Preprint, CS Preprint, etc.) so that NeurIPS/ICML/ICLR papers combine,
    and bio-journal papers combine — important for small corpora where exact-venue
    matching would leave every venue as a singleton.

    Level 2: Within each category group, Jaccard sub-clustering (threshold 0.25)
    separates papers on different topics into distinct style guides.

    Each paper dict: paper_id, venue, topic_area, topic_tags (list).
    Returns: {style_slug: {"paper_ids": [...], "title": "..."}}
    """
    if not papers:
        return {}

    # Step 1: group by venue category
    category_groups: dict[str, list[dict]] = defaultdict(list)
    for p in papers:
        raw_venue = (p.get("venue") or "unknown").strip()
        norm_venue = _normalize_venue(raw_venue)
        category = _venue_category(norm_venue)
        category_groups[category].append(p)

    result: dict[str, dict] = {}

    for category, cat_papers in category_groups.items():
        category_slug = slug_from_title(category)

        # Step 2: Jaccard sub-clustering within category
        sub_clusters = _jaccard_sub_cluster(cat_papers, threshold=0.25)

        for cluster in sub_clusters:
            tags = _common_tags(cluster)
            tag_part = "_".join(slug_from_title(t) for t in tags) if tags else "general"
            slug = f"{category_slug}_{tag_part}"
            slug = _unique_slug(slug, result)
            title = f"{category} — {', '.join(tags)}" if tags else category
            result[slug] = {
                "paper_ids": [p["paper_id"] for p in cluster],
                "title": title,
            }

    return result


def _unique_slug(slug: str, existing: dict) -> str:
    """Append numeric suffix if slug already used."""
    if slug not in existing:
        return slug
    i = 2
    while f"{slug}_{i}" in existing:
        i += 1
    return f"{slug}_{i}"
