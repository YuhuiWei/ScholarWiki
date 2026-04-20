from __future__ import annotations
"""Pending concepts ledger — defers single-paper concepts until validated by ≥N papers."""

import json
from datetime import date
from pathlib import Path


def load_pending(staging_dir: Path) -> dict:
    """Load pending_concepts.json; return empty structure if missing or corrupt."""
    path = staging_dir / "pending_concepts.json"
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if "concepts" in data:
                return data
        except (json.JSONDecodeError, KeyError):
            pass
    return {"concepts": {}}


def save_pending(staging_dir: Path, pending: dict) -> None:
    """Atomically write pending_concepts.json."""
    path = staging_dir / "pending_concepts.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(pending, indent=2), encoding="utf-8")
    tmp.replace(path)


def update_pending_from_mappings(staging_dir: Path, paper_ids: list[str]) -> None:
    """
    After extract --collect, update the ledger with each paper's concept contributions.

    For each concept in each paper's concept_mapping.json:
    - If concept already in ledger → add this paper to its entry
    - If concept not in ledger → create new entry

    Existing paper entries for a concept are overwritten (idempotent re-runs).
    """
    pending = load_pending(staging_dir)
    today = str(date.today())

    for paper_id in paper_ids:
        mapping_path = staging_dir / paper_id / "concept_mapping.json"
        if not mapping_path.exists():
            continue
        try:
            mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, KeyError):
            continue

        for contrib in mapping.get("concept_contributions", []):
            name = contrib.get("concept_name", "")
            if not name:
                continue
            if name not in pending["concepts"]:
                pending["concepts"][name] = {
                    "papers": {},
                    "first_seen": today,
                }
            pending["concepts"][name]["papers"][paper_id] = {
                "knowledge_items": contrib.get("knowledge_items", []),
                "roadmap_edges": contrib.get("roadmap_edges", []),
            }

    save_pending(staging_dir, pending)


def resolve_concepts_for_linking(
    staging_dir: Path,
    min_papers: int = 2,
) -> tuple[set[str], dict]:
    """
    Before link submit, split concepts into: synthesize now vs stay pending.

    Returns:
        concepts_to_link: concept names with ≥min_papers contributors
        updated_pending: ledger with promoted concepts removed (save after linking)
    """
    pending = load_pending(staging_dir)

    concepts_to_link: set[str] = set()
    remaining: dict[str, dict] = {}

    for name, entry in pending["concepts"].items():
        if len(entry.get("papers", {})) >= min_papers:
            concepts_to_link.add(name)
        else:
            remaining[name] = entry

    return concepts_to_link, {"concepts": remaining}
