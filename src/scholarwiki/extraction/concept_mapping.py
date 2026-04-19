from __future__ import annotations
import json
from pathlib import Path

from ..linking.concept_match import match_concept


def _load_json(path: Path) -> dict:
    """Load JSON from path; return empty dict on missing or corrupt file."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def generate_concept_mapping(
    paper_id: str,
    staging_paper_dir: Path,
    concept_index: list[tuple[str, str]],
) -> dict:
    """
    Read staging module JSONs for one paper and produce concept_mapping.json content.

    Returns a dict matching the concept_mapping.json schema:
    {
      "paper_id": str,
      "concept_contributions": [{"concept_name", "matched_page", "match_type",
                                  "knowledge_items", "roadmap_edges"}, ...],
      "pattern_signals": {"logic_pattern": str},
      "writing_signals": {"venue": str, "topic_area": str},
    }
    """
    knowledge = _load_json(staging_paper_dir / "knowledge.json")
    roadmap = _load_json(staging_paper_dir / "roadmap.json")
    logic = _load_json(staging_paper_dir / "logic.json")
    writing = _load_json(staging_paper_dir / "writing.json")

    # Collect concept → {knowledge_items, roadmap_edges} mapping
    # Use insertion order via dict to deduplicate concept names
    concept_refs: dict[str, dict] = {}

    for item in knowledge.get("knowledge_items", []):
        item_id = item.get("id", "")
        for concept_name in item.get("related_concepts", []):
            if not concept_name:
                continue
            if concept_name not in concept_refs:
                concept_refs[concept_name] = {"knowledge_items": [], "roadmap_edges": []}
            if item_id:
                concept_refs[concept_name]["knowledge_items"].append(item_id)

    for i, edge in enumerate(roadmap.get("relationships", [])):
        concept_name = edge.get("target_entity", "")
        if not concept_name:
            continue
        if concept_name not in concept_refs:
            concept_refs[concept_name] = {"knowledge_items": [], "roadmap_edges": []}
        concept_refs[concept_name]["roadmap_edges"].append(f"r{i}")

    # Fuzzy-match each concept against existing wiki pages
    concept_contributions = []
    for concept_name, refs in concept_refs.items():
        match = match_concept(concept_name, concept_index)
        if match:
            _, matched_slug = match
            contribution = {
                "concept_name": concept_name,
                "matched_page": matched_slug,
                "match_type": "existing",
                "knowledge_items": refs["knowledge_items"],
                "roadmap_edges": refs["roadmap_edges"],
            }
        else:
            contribution = {
                "concept_name": concept_name,
                "matched_page": None,
                "match_type": "new",
                "knowledge_items": refs["knowledge_items"],
                "roadmap_edges": refs["roadmap_edges"],
            }
        concept_contributions.append(contribution)

    topic_area = writing.get("topic_area", "") or ""
    return {
        "paper_id": paper_id,
        "concept_contributions": concept_contributions,
        "pattern_signals": {
            "logic_pattern": logic.get("logic_pattern", ""),
        },
        "writing_signals": {
            "venue": writing.get("venue", "") or "",
            "topic_area": topic_area,
            "topic_tags": [topic_area] if topic_area else [],
        },
    }
