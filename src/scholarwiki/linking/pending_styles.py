from __future__ import annotations
"""Pending writing styles ledger — defers style groups until validated by ≥N papers."""

import json
from datetime import date
from pathlib import Path


def load_pending_styles(staging_dir: Path) -> dict:
    """Load pending_styles.json; return empty structure if missing or corrupt."""
    path = staging_dir / "pending_styles.json"
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if "papers" in data:
                return data
        except (json.JSONDecodeError, KeyError):
            pass
    return {"papers": {}}


def save_pending_styles(staging_dir: Path, pending: dict) -> None:
    """Atomically write pending_styles.json."""
    path = staging_dir / "pending_styles.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(pending, indent=2), encoding="utf-8")
    tmp.replace(path)


def update_pending_styles(staging_dir: Path, paper_ids: list[str]) -> None:
    """
    After extract --collect, add each paper's writing signals to the ledger.

    Reads writing_signals from each paper's concept_mapping.json.
    Existing paper entries are overwritten (idempotent re-runs).
    """
    pending = load_pending_styles(staging_dir)
    today = str(date.today())

    for paper_id in paper_ids:
        mapping_path = staging_dir / paper_id / "concept_mapping.json"
        if not mapping_path.exists():
            continue
        try:
            mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, KeyError):
            continue

        ws = mapping.get("writing_signals", {})
        venue = ws.get("venue", "") or ""
        topic_tags = ws.get("topic_tags") or [ws.get("topic_area", "general")]

        pending["papers"][paper_id] = {
            "venue": venue,
            "topic_tags": topic_tags,
            "first_seen": today,
        }

    save_pending_styles(staging_dir, pending)


def resolve_styles_for_linking(
    staging_dir: Path,
    min_papers: int = 2,
) -> tuple[dict[str, dict], dict]:
    """
    Before link submit, cluster all pending papers by venue+topic_tags,
    return groups with ≥min_papers and the remaining (not-yet-promoted) papers.

    Returns:
        style_clusters: {slug: {"paper_ids": [...], "title": "..."}}
            Only groups with >=min_papers papers.
        updated_pending: ledger with promoted papers removed (save after linking).
    """
    from .writing_styles import cluster_writing_styles

    pending = load_pending_styles(staging_dir)

    style_input = [
        {
            "paper_id": paper_id,
            "venue": info.get("venue", ""),
            "topic_area": (info.get("topic_tags") or ["general"])[0],
            "topic_tags": info.get("topic_tags", []),
        }
        for paper_id, info in pending["papers"].items()
    ]

    if not style_input:
        return {}, pending

    all_clusters = cluster_writing_styles(style_input)

    promoted_paper_ids: set[str] = set()
    style_clusters: dict[str, dict] = {}

    for slug, cluster in all_clusters.items():
        if len(cluster["paper_ids"]) >= min_papers:
            style_clusters[slug] = cluster
            promoted_paper_ids.update(cluster["paper_ids"])

    remaining_papers = {
        pid: info
        for pid, info in pending["papers"].items()
        if pid not in promoted_paper_ids
    }

    return style_clusters, {"papers": remaining_papers}
