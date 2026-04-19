from __future__ import annotations
import json
from pathlib import Path
import pytest
from scholarwiki.extraction.concept_mapping import generate_concept_mapping


def _write_staging(d: Path, knowledge=None, roadmap=None, logic=None, writing=None):
    d.mkdir(parents=True, exist_ok=True)
    (d / "knowledge.json").write_text(json.dumps(knowledge or {"knowledge_items": []}))
    (d / "roadmap.json").write_text(json.dumps(roadmap or {"relationships": []}))
    (d / "logic.json").write_text(json.dumps(logic or {"logic_pattern": "", "reasoning_chain": []}))
    (d / "writing.json").write_text(json.dumps(writing or {"venue": "", "topic_area": ""}))


def test_new_concept_no_existing_pages(tmp_path):
    _write_staging(tmp_path, knowledge={
        "knowledge_items": [
            {"id": "k1", "claim": "X", "related_concepts": ["batch correction"]}
        ]
    })
    result = generate_concept_mapping("paper_abc", tmp_path, concept_index=[])
    assert result["paper_id"] == "paper_abc"
    contribs = result["concept_contributions"]
    assert len(contribs) == 1
    assert contribs[0]["concept_name"] == "batch correction"
    assert contribs[0]["match_type"] == "new"
    assert contribs[0]["matched_page"] is None
    assert "k1" in contribs[0]["knowledge_items"]


def test_existing_concept_fuzzy_matched(tmp_path):
    _write_staging(tmp_path, knowledge={
        "knowledge_items": [
            {"id": "k1", "claim": "X", "related_concepts": ["Batch Correction in scRNA-seq"]}
        ]
    })
    index = [("Batch correction in scRNA-seq", "batch_correction_in_scrna_seq")]
    result = generate_concept_mapping("paper_abc", tmp_path, concept_index=index)
    c = result["concept_contributions"][0]
    assert c["match_type"] == "existing"
    assert c["matched_page"] == "batch_correction_in_scrna_seq"


def test_roadmap_edges_captured(tmp_path):
    _write_staging(tmp_path, roadmap={
        "relationships": [
            {"target_entity": "scVI (Lopez et al., 2018)", "relationship_type": "extends",
             "description": "builds on", "significance": "high"}
        ]
    })
    result = generate_concept_mapping("paper_abc", tmp_path, concept_index=[])
    contribs = result["concept_contributions"]
    # roadmap target entity should appear as a concept contribution
    names = [c["concept_name"] for c in contribs]
    assert "scVI (Lopez et al., 2018)" in names
    scvi = next(c for c in contribs if c["concept_name"] == "scVI (Lopez et al., 2018)")
    assert "r0" in scvi["roadmap_edges"]


def test_pattern_signals_captured(tmp_path):
    _write_staging(tmp_path, logic={
        "logic_pattern": "premise → innovation → validation",
        "reasoning_chain": [{"step": 1, "type": "premise", "content": "X", "evidence_basis": None}]
    })
    result = generate_concept_mapping("paper_abc", tmp_path, concept_index=[])
    assert result["pattern_signals"]["logic_pattern"] == "premise → innovation → validation"


def test_writing_signals_captured(tmp_path):
    _write_staging(tmp_path, writing={
        "venue": "Nature Methods",
        "topic_area": "scRNA-seq",
    })
    result = generate_concept_mapping("paper_abc", tmp_path, concept_index=[])
    assert result["writing_signals"]["venue"] == "Nature Methods"
    assert result["writing_signals"]["topic_area"] == "scRNA-seq"


def test_missing_files_handled_gracefully(tmp_path):
    # Only write knowledge.json, leave others missing
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "knowledge.json").write_text(json.dumps({"knowledge_items": []}))
    # Should not raise
    result = generate_concept_mapping("paper_abc", tmp_path, concept_index=[])
    assert result["paper_id"] == "paper_abc"
    assert result["pattern_signals"]["logic_pattern"] == ""


def test_concept_deduplication(tmp_path):
    """Same concept appearing in multiple knowledge items → single contribution entry."""
    _write_staging(tmp_path, knowledge={
        "knowledge_items": [
            {"id": "k1", "claim": "A", "related_concepts": ["batch correction"]},
            {"id": "k2", "claim": "B", "related_concepts": ["batch correction"]},
        ]
    })
    result = generate_concept_mapping("paper_abc", tmp_path, concept_index=[])
    names = [c["concept_name"] for c in result["concept_contributions"]]
    assert names.count("batch correction") == 1
    bc = next(c for c in result["concept_contributions"] if c["concept_name"] == "batch correction")
    assert "k1" in bc["knowledge_items"]
    assert "k2" in bc["knowledge_items"]
