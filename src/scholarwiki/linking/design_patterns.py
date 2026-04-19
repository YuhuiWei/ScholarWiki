from __future__ import annotations
import json
from pathlib import Path

from openai import AsyncOpenAI

from ..config import Config


def write_pattern_page(wiki_dir: Path, slug: str, markdown: str) -> None:
    """Atomically write a design pattern page. Creates wiki/patterns/ if needed."""
    patterns_dir = wiki_dir / "patterns"
    patterns_dir.mkdir(parents=True, exist_ok=True)
    page = patterns_dir / f"{slug}.md"
    tmp = page.with_suffix(".md.tmp")
    tmp.write_text(markdown, encoding="utf-8")
    tmp.replace(page)


async def cluster_patterns(
    papers: list[dict],
    existing_pattern_index: list[tuple[str, str]],
    cfg: Config,
) -> dict[str, dict]:
    """
    One async GPT-5 call to cluster papers by design pattern.

    Returns: {pattern_slug: {"paper_ids": [...], "title": "Human-readable title"}}
    Only clusters with >=2 papers are returned.
    """
    from .synthesis_prompts import PATTERN_CLUSTER_SYSTEM

    if not papers:
        return {}

    existing_text = "\n".join(f"- {slug}: {title}" for title, slug in existing_pattern_index)
    papers_text = "\n".join(
        f"- paper_id={p.get('paper_id', '?')} | title={p.get('title', '?')} | logic_pattern={p.get('logic_pattern', '')}"
        for p in papers
    )
    user_message = (
        f"Existing pattern pages:\n{existing_text or '(none)'}\n\n"
        f"Papers to assign:\n{papers_text}"
    )

    client = AsyncOpenAI()
    resp = await client.chat.completions.create(
        model=cfg.linking.synthesis_model,
        messages=[
            {"role": "system", "content": PATTERN_CLUSTER_SYSTEM},
            {"role": "user", "content": user_message},
        ],
        response_format={"type": "json_object"},
    )
    try:
        data = json.loads(resp.choices[0].message.content)
    except (json.JSONDecodeError, IndexError, AttributeError):
        return {}

    assignments: dict[str, list[str]] = {}
    for slug, paper_ids in data.get("assignments", {}).items():
        assignments[slug] = paper_ids

    new_titles: dict[str, str] = data.get("new_pattern_titles", {})

    # Build existing title lookup
    existing_title_map = {slug: title for title, slug in existing_pattern_index}

    result = {}
    for slug, paper_ids in assignments.items():
        if len(paper_ids) < 2:
            continue  # Spec: patterns require >=2 papers
        title = new_titles.get(slug) or existing_title_map.get(slug) or slug.replace("_", " ").title()
        result[slug] = {"paper_ids": paper_ids, "title": title}

    return result
