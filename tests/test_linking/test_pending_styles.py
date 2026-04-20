from __future__ import annotations
import json
from pathlib import Path
import pytest
from scholarwiki.linking.pending_styles import (
    load_pending_styles,
    save_pending_styles,
    update_pending_styles,
    resolve_styles_for_linking,
)


def _write_concept_mapping(staging_dir: Path, paper_id: str, venue: str, topic_tags: list[str]):
    paper_dir = staging_dir / paper_id
    paper_dir.mkdir(parents=True, exist_ok=True)
    mapping = {
        "paper_id": paper_id,
        "concept_contributions": [],
        "pattern_signals": {"logic_pattern": "", "methodological_tags": []},
        "writing_signals": {
            "venue": venue,
            "topic_area": topic_tags[0] if topic_tags else "general",
            "topic_tags": topic_tags,
        },
    }
    (paper_dir / "concept_mapping.json").write_text(json.dumps(mapping))


def test_load_pending_styles_empty(tmp_path):
    result = load_pending_styles(tmp_path)
    assert result == {"papers": {}}


def test_load_pending_styles_missing_file(tmp_path):
    assert load_pending_styles(tmp_path / "nonexistent") == {"papers": {}}


def test_save_and_load_roundtrip(tmp_path):
    data = {"papers": {"paper1": {
        "venue": "NeurIPS",
        "topic_tags": ["deep learning"],
        "first_seen": "2026-04-19",
    }}}
    save_pending_styles(tmp_path, data)
    assert load_pending_styles(tmp_path) == data


def test_update_pending_styles_adds_papers(tmp_path):
    _write_concept_mapping(tmp_path, "paper1", "NeurIPS", ["deep learning"])
    update_pending_styles(tmp_path, ["paper1"])

    pending = load_pending_styles(tmp_path)
    assert "paper1" in pending["papers"]
    assert pending["papers"]["paper1"]["venue"] == "NeurIPS"
    assert "deep learning" in pending["papers"]["paper1"]["topic_tags"]


def test_update_is_idempotent(tmp_path):
    _write_concept_mapping(tmp_path, "paper1", "NeurIPS", ["deep learning"])
    update_pending_styles(tmp_path, ["paper1"])
    update_pending_styles(tmp_path, ["paper1"])  # run twice

    pending = load_pending_styles(tmp_path)
    assert len(pending["papers"]) == 1


def test_update_preserves_existing_papers(tmp_path):
    save_pending_styles(tmp_path, {"papers": {"old_paper": {
        "venue": "Nature", "topic_tags": ["genomics"], "first_seen": "2026-01-01",
    }}})
    _write_concept_mapping(tmp_path, "new_paper", "NeurIPS", ["deep learning"])
    update_pending_styles(tmp_path, ["new_paper"])

    pending = load_pending_styles(tmp_path)
    assert "old_paper" in pending["papers"]
    assert "new_paper" in pending["papers"]


def test_resolve_promotes_multi_paper_group(tmp_path):
    _write_concept_mapping(tmp_path, "paper1", "NeurIPS", ["deep learning", "transformers"])
    _write_concept_mapping(tmp_path, "paper2", "NeurIPS", ["deep learning", "transformers"])
    update_pending_styles(tmp_path, ["paper1", "paper2"])

    clusters, updated = resolve_styles_for_linking(tmp_path, min_papers=2)

    assert len(clusters) >= 1
    all_promoted_ids = {pid for c in clusters.values() for pid in c["paper_ids"]}
    assert "paper1" in all_promoted_ids
    assert "paper2" in all_promoted_ids
    # Promoted papers removed from pending
    assert "paper1" not in updated["papers"]
    assert "paper2" not in updated["papers"]


def test_resolve_single_paper_stays_pending(tmp_path):
    _write_concept_mapping(tmp_path, "paper1", "NeurIPS", ["deep learning"])
    update_pending_styles(tmp_path, ["paper1"])

    clusters, updated = resolve_styles_for_linking(tmp_path, min_papers=2)

    assert len(clusters) == 0
    assert "paper1" in updated["papers"]


def test_resolve_empty_ledger(tmp_path):
    clusters, updated = resolve_styles_for_linking(tmp_path, min_papers=2)
    assert clusters == {}
    assert updated == {"papers": {}}


def test_update_skips_missing_mapping_file(tmp_path):
    (tmp_path / "ghost_paper").mkdir()
    update_pending_styles(tmp_path, ["ghost_paper"])
    assert load_pending_styles(tmp_path) == {"papers": {}}
