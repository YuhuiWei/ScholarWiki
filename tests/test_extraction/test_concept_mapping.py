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


def test_roadmap_citation_not_a_concept(tmp_path):
    """Roadmap target entities that look like citations should not become concept pages."""
    _write_staging(tmp_path, roadmap={
        "relationships": [
            {"target_entity": "scVI (Lopez et al., 2018)", "relationship_type": "extends",
             "description": "builds on", "significance": "high"}
        ]
    })
    result = generate_concept_mapping("paper_abc", tmp_path, concept_index=[])
    names = [c["concept_name"] for c in result["concept_contributions"]]
    assert "scVI (Lopez et al., 2018)" not in names


def test_roadmap_edges_enrich_existing_concept(tmp_path):
    """Roadmap edges should enrich a concept already identified from knowledge items."""
    _write_staging(tmp_path,
        knowledge={
            "knowledge_items": [
                {"id": "k1", "claim": "X", "evidence": "", "confidence": "high",
                 "related_concepts": ["variational autoencoder"]}
            ]
        },
        roadmap={
            "relationships": [
                {"target_entity": "variational autoencoder", "relationship_type": "uses",
                 "description": "uses VAE", "significance": "high"}
            ]
        },
    )
    result = generate_concept_mapping("paper_abc", tmp_path, concept_index=[])
    contribs = result["concept_contributions"]
    names = [c["concept_name"] for c in contribs]
    assert "variational autoencoder" in names
    vae = next(c for c in contribs if c["concept_name"] == "variational autoencoder")
    assert "r0" in vae["roadmap_edges"]


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


def test_methodological_terms_routed_to_pattern_signals(tmp_path):
    """Methodological terms go to pattern_signals, not concept_contributions."""
    _write_staging(tmp_path, knowledge={
        "knowledge_items": [
            {"id": "k1", "claim": "Scales to 1M cells", "evidence_type": "experimental",
             "confidence": "high", "supporting_data": None, "domain_tags": [],
             "related_concepts": ["scalability", "single-cell analysis"],
             "quantitative_result": None},
            {"id": "k2", "claim": "Ablation confirms attention is key",
             "evidence_type": "experimental", "confidence": "high",
             "supporting_data": None, "domain_tags": [],
             "related_concepts": ["ablation studies", "attention mechanism"],
             "quantitative_result": None},
        ]
    })
    result = generate_concept_mapping("paper_abc", tmp_path, concept_index=[])

    concept_names = [c["concept_name"] for c in result["concept_contributions"]]
    method_tags = result["pattern_signals"]["methodological_tags"]

    assert "single-cell analysis" in concept_names
    assert "attention mechanism" in concept_names
    assert "scalability" in method_tags
    assert "ablation studies" in method_tags
    assert "scalability" not in concept_names
    assert "ablation studies" not in concept_names


def test_methodological_routing_case_insensitive(tmp_path):
    """Routing should be case-insensitive."""
    _write_staging(tmp_path, knowledge={
        "knowledge_items": [
            {"id": "k1", "claim": "X", "evidence_type": "experimental", "confidence": "high",
             "supporting_data": None, "domain_tags": [],
             "related_concepts": ["Benchmarking", "SCALABILITY", "real concept"],
             "quantitative_result": None},
        ]
    })
    result = generate_concept_mapping("paper_abc", tmp_path, concept_index=[])

    concept_names = [c["concept_name"] for c in result["concept_contributions"]]
    method_tags = result["pattern_signals"]["methodological_tags"]

    assert "real concept" in concept_names
    assert "Benchmarking" not in concept_names
    assert "SCALABILITY" not in concept_names
    assert len(method_tags) == 2


def test_pattern_signals_always_has_methodological_tags(tmp_path):
    """methodological_tags key is always present, even if empty."""
    _write_staging(tmp_path)
    result = generate_concept_mapping("paper_abc", tmp_path, concept_index=[])
    assert "methodological_tags" in result["pattern_signals"]
    assert result["pattern_signals"]["methodological_tags"] == []


def test_broad_concept_qualified_with_domain_context(tmp_path):
    """Broad concepts get qualified with the paper's domain tags."""
    _write_staging(tmp_path, knowledge={
        "knowledge_items": [
            {"id": "k1", "claim": "Transfer learning enables cross-tissue prediction.",
             "evidence_type": "experimental", "confidence": "high",
             "supporting_data": None,
             "domain_tags": ["single-cell genomics", "deep learning", "genomics"],
             "related_concepts": ["transfer learning"],
             "quantitative_result": None},
        ]
    })
    result = generate_concept_mapping("paper_abc", tmp_path, concept_index=[])
    names = [c["concept_name"] for c in result["concept_contributions"]]

    # "transfer learning" alone should not appear — it must be qualified
    assert "transfer learning" not in names
    # Qualified form should exist
    assert any("transfer learning for" in n for n in names)


def test_broad_concept_unqualified_when_no_context(tmp_path):
    """Broad concept without domain_tags or topic_area stays unqualified (best effort)."""
    _write_staging(tmp_path, knowledge={
        "knowledge_items": [
            {"id": "k1", "claim": "X", "evidence_type": "experimental", "confidence": "high",
             "supporting_data": None, "domain_tags": [],
             "related_concepts": ["transfer learning"],
             "quantitative_result": None},
        ]
    })
    result = generate_concept_mapping("paper_abc", tmp_path, concept_index=[])
    names = [c["concept_name"] for c in result["concept_contributions"]]
    # No qualifier available — falls back to original name
    assert "transfer learning" in names


def test_pretraining_variants_deduplicated(tmp_path):
    """pre-training, pretraining, pre training all normalize to the same concept."""
    _write_staging(tmp_path, knowledge={
        "knowledge_items": [
            {"id": "k1", "claim": "X", "evidence_type": "experimental", "confidence": "high",
             "supporting_data": None, "domain_tags": [],
             "related_concepts": ["pre-training"],
             "quantitative_result": None},
            {"id": "k2", "claim": "Y", "evidence_type": "experimental", "confidence": "high",
             "supporting_data": None, "domain_tags": [],
             "related_concepts": ["pretraining"],
             "quantitative_result": None},
            {"id": "k3", "claim": "Z", "evidence_type": "experimental", "confidence": "high",
             "supporting_data": None, "domain_tags": [],
             "related_concepts": ["pre training"],
             "quantitative_result": None},
        ]
    })
    result = generate_concept_mapping("paper_abc", tmp_path, concept_index=[])
    names = [c["concept_name"] for c in result["concept_contributions"]]

    # All three spelling variants should merge into one concept entry
    pre_training_entries = [n for n in names if "pre" in n.lower() and "train" in n.lower()]
    assert len(pre_training_entries) == 1
