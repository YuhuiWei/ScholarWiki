from __future__ import annotations
import json
from pathlib import Path
import pytest
from scholarwiki.linking.pending_concepts import (
    load_pending,
    save_pending,
    update_pending_from_mappings,
    resolve_concepts_for_linking,
)


def _write_concept_mapping(staging_dir: Path, paper_id: str, concepts: list[str]):
    paper_dir = staging_dir / paper_id
    paper_dir.mkdir(parents=True, exist_ok=True)
    mapping = {
        "paper_id": paper_id,
        "concept_contributions": [
            {"concept_name": c, "knowledge_items": ["k1"], "roadmap_edges": [],
             "matched_page": None, "match_type": "new"}
            for c in concepts
        ],
        "pattern_signals": {"logic_pattern": "", "methodological_tags": []},
        "writing_signals": {"venue": "", "topic_tags": []},
    }
    (paper_dir / "concept_mapping.json").write_text(json.dumps(mapping))


def test_load_pending_empty(tmp_path):
    result = load_pending(tmp_path)
    assert result == {"concepts": {}}


def test_load_pending_missing_file(tmp_path):
    assert load_pending(tmp_path / "nonexistent") == {"concepts": {}}


def test_save_and_load_roundtrip(tmp_path):
    data = {"concepts": {"batch correction": {
        "papers": {"p1": {"knowledge_items": ["k1"], "roadmap_edges": []}},
        "first_seen": "2026-04-19",
    }}}
    save_pending(tmp_path, data)
    assert load_pending(tmp_path) == data


def test_update_pending_new_concepts(tmp_path):
    _write_concept_mapping(tmp_path, "paper1", ["batch correction", "scRNA-seq"])
    update_pending_from_mappings(tmp_path, ["paper1"])

    pending = load_pending(tmp_path)
    assert "batch correction" in pending["concepts"]
    assert "scRNA-seq" in pending["concepts"]
    assert "paper1" in pending["concepts"]["batch correction"]["papers"]


def test_update_pending_second_paper_accumulates(tmp_path):
    _write_concept_mapping(tmp_path, "paper1", ["batch correction"])
    update_pending_from_mappings(tmp_path, ["paper1"])

    _write_concept_mapping(tmp_path, "paper2", ["batch correction"])
    update_pending_from_mappings(tmp_path, ["paper2"])

    pending = load_pending(tmp_path)
    assert len(pending["concepts"]["batch correction"]["papers"]) == 2
    assert "paper1" in pending["concepts"]["batch correction"]["papers"]
    assert "paper2" in pending["concepts"]["batch correction"]["papers"]


def test_update_preserves_existing_pending(tmp_path):
    save_pending(tmp_path, {"concepts": {
        "old concept": {"papers": {"old_paper": {"knowledge_items": [], "roadmap_edges": []}},
                        "first_seen": "2026-04-01"},
    }})
    _write_concept_mapping(tmp_path, "new_paper", ["new concept"])
    update_pending_from_mappings(tmp_path, ["new_paper"])

    pending = load_pending(tmp_path)
    assert "old concept" in pending["concepts"]
    assert "new concept" in pending["concepts"]


def test_update_is_idempotent(tmp_path):
    _write_concept_mapping(tmp_path, "paper1", ["batch correction"])
    update_pending_from_mappings(tmp_path, ["paper1"])
    update_pending_from_mappings(tmp_path, ["paper1"])  # run twice

    pending = load_pending(tmp_path)
    assert len(pending["concepts"]["batch correction"]["papers"]) == 1


def test_resolve_promotes_multi_paper_concepts(tmp_path):
    _write_concept_mapping(tmp_path, "paper1", ["batch correction", "rare concept"])
    _write_concept_mapping(tmp_path, "paper2", ["batch correction"])
    update_pending_from_mappings(tmp_path, ["paper1", "paper2"])

    to_link, updated = resolve_concepts_for_linking(tmp_path, min_papers=2)

    assert "batch correction" in to_link
    assert "rare concept" not in to_link
    assert "rare concept" in updated["concepts"]
    assert "batch correction" not in updated["concepts"]


def test_resolve_single_paper_stays_pending(tmp_path):
    _write_concept_mapping(tmp_path, "paper1", ["unique finding"])
    update_pending_from_mappings(tmp_path, ["paper1"])

    to_link, updated = resolve_concepts_for_linking(tmp_path, min_papers=2)

    assert "unique finding" not in to_link
    assert "unique finding" in updated["concepts"]


def test_resolve_with_min_papers_3(tmp_path):
    for i in range(2):
        _write_concept_mapping(tmp_path, f"paper{i}", ["popular concept"])
    update_pending_from_mappings(tmp_path, ["paper0", "paper1"])

    to_link, _ = resolve_concepts_for_linking(tmp_path, min_papers=3)
    assert "popular concept" not in to_link


def test_resolve_empty_ledger(tmp_path):
    to_link, updated = resolve_concepts_for_linking(tmp_path, min_papers=2)
    assert to_link == set()
    assert updated == {"concepts": {}}


def test_update_skips_missing_mapping_file(tmp_path):
    # paper_id with no concept_mapping.json — should not crash
    (tmp_path / "ghost_paper").mkdir()
    update_pending_from_mappings(tmp_path, ["ghost_paper"])
    assert load_pending(tmp_path) == {"concepts": {}}
