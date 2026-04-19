from __future__ import annotations
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from scholarwiki.models import PaperEntry, Registry
from scholarwiki.config import Config, PathsConfig, LinkingConfig


def _make_config(tmp_path: Path) -> Config:
    return Config(
        paths=PathsConfig(raw=tmp_path / "raw", staging=tmp_path / "staging",
                          wiki=tmp_path / "wiki"),
        linking=LinkingConfig(synthesis_model="gpt-5", style_model="gpt-4.1"),
    )


def _make_paper(paper_id: str, status: str = "extracted") -> PaperEntry:
    return PaperEntry(
        paper_id=paper_id, title=f"Paper {paper_id}", source="manual",
        extraction_status=status,
        wiki_source_page=f"wiki/sources/{paper_id}.md",
    )


def _write_concept_mapping(staging: Path, paper_id: str,
                            concepts=None, logic_pattern="premise → conclusion",
                            venue="Nature", topic_area="genomics",
                            topic_tags=None) -> None:
    d = staging / paper_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "concept_mapping.json").write_text(json.dumps({
        "paper_id": paper_id,
        "concept_contributions": concepts or [
            {"concept_name": "batch correction", "matched_page": "batch_correction",
             "match_type": "existing", "knowledge_items": ["k1"], "roadmap_edges": []}
        ],
        "pattern_signals": {"logic_pattern": logic_pattern},
        "writing_signals": {"venue": venue, "topic_area": topic_area,
                            "topic_tags": topic_tags or ["genomics"]},
    }))
    # Also write the 5 module JSONs (needed for prompt building)
    for module, content in [
        ("knowledge", {"knowledge_items": [{"id": "k1", "claim": "X", "related_concepts": ["batch correction"],
            "evidence_type": "experimental", "confidence": "high",
            "supporting_data": None, "domain_tags": [], "quantitative_result": None}]}),
        ("roadmap", {"relationships": [], "positioned_as": None, "gap_filled": None, "field_context": None}),
        ("experiment", {"experimental_pipeline": [], "datasets": [], "controls": [],
            "evaluation_metrics": [], "key_parameters": {}, "reproducibility_notes": None}),
        ("logic", {"logic_pattern": logic_pattern, "hypothesis": None,
            "reasoning_chain": [], "assumptions": [], "limitations_acknowledged": [],
            "strengths_of_argument": []}),
        ("writing", {"venue": venue, "topic_area": topic_area, "venue_type": "journal",
            "word_count_estimate": None, "figure_count": None, "extended_data_figures": None,
            "structure": {"section_order": [], "results_before_methods": None,
                         "separate_methods": None, "supplementary_materials": None},
            "introduction_pattern": {"paragraphs": None, "strategy": None, "how_gap_introduced": None},
            "results_pattern": {"subsection_style": None, "example_headers": [],
                               "figure_reference_style": None, "quantitative_reporting": None},
            "discussion_pattern": {"opening": None, "structure": None, "hedging_level": None,
                                  "hedging_examples": []},
            "language_patterns": {"voice": None, "tense": None, "transition_phrases": [],
                                 "common_phrases_by_context": {}},
            "citation_style": None, "data_availability": None}),
    ]:
        (d / f"{module}.json").write_text(json.dumps(content))


@pytest.mark.asyncio
async def test_submit_returns_two_batch_ids(tmp_path):
    """submit_link_batches returns gpt5 and gpt41 batch IDs."""
    from scholarwiki.linking.batch import submit_link_batches, LinkBatchSubmitResult
    cfg = _make_config(tmp_path)
    staging = cfg.paths.staging
    wiki = cfg.paths.wiki
    (wiki / "concepts").mkdir(parents=True)
    (wiki / "patterns").mkdir(parents=True)

    paper = _make_paper("p1")
    reg = Registry(papers={"p1": paper})
    _write_concept_mapping(staging, "p1")

    mock_cluster_resp = MagicMock()
    mock_cluster_resp.choices = [MagicMock(message=MagicMock(content=json.dumps({
        "assignments": {}, "new_pattern_titles": {}, "unassigned": ["p1"]
    })))]
    mock_file = MagicMock(id="file_001")
    mock_batch_gpt5 = MagicMock(id="batch_gpt5_001")
    mock_batch_gpt41 = MagicMock(id="batch_gpt41_001")

    batch_calls = [mock_batch_gpt5, mock_batch_gpt41]
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_cluster_resp)
    mock_client.files.create = AsyncMock(return_value=mock_file)
    mock_client.batches.create = AsyncMock(side_effect=batch_calls)

    with patch("scholarwiki.linking.batch.AsyncOpenAI", return_value=mock_client), \
         patch("scholarwiki.linking.design_patterns.AsyncOpenAI", return_value=mock_client):
        result = await submit_link_batches(
            [paper], reg, cfg.paths.raw, staging, wiki, cfg
        )

    assert result.gpt5_batch_id == "batch_gpt5_001"
    assert result.gpt41_batch_id == "batch_gpt41_001"


@pytest.mark.asyncio
async def test_submit_writes_batch_ids_to_registry(tmp_path):
    """After submit, registry papers have linking_batch_ids set."""
    from scholarwiki.linking.batch import submit_link_batches
    cfg = _make_config(tmp_path)
    cfg.paths.raw.mkdir(parents=True)
    staging = cfg.paths.staging
    wiki = cfg.paths.wiki
    (wiki / "concepts").mkdir(parents=True)

    paper = _make_paper("p1")
    reg = Registry(papers={"p1": paper})
    _write_concept_mapping(staging, "p1")

    mock_cluster_resp = MagicMock()
    mock_cluster_resp.choices = [MagicMock(message=MagicMock(content=json.dumps({
        "assignments": {}, "new_pattern_titles": {}, "unassigned": ["p1"]
    })))]
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_cluster_resp)
    mock_client.files.create = AsyncMock(return_value=MagicMock(id="f1"))
    mock_client.batches.create = AsyncMock(side_effect=[
        MagicMock(id="batch_gpt5"), MagicMock(id="batch_gpt41")
    ])

    with patch("scholarwiki.linking.batch.AsyncOpenAI", return_value=mock_client), \
         patch("scholarwiki.linking.design_patterns.AsyncOpenAI", return_value=mock_client), \
         patch("scholarwiki.linking.batch.save_registry") as mock_save:
        await submit_link_batches([paper], reg, cfg.paths.raw, staging, wiki, cfg)

    assert reg.papers["p1"].linking_batch_ids == {"gpt5": "batch_gpt5", "gpt41": "batch_gpt41"}
    mock_save.assert_called_once()


@pytest.mark.asyncio
async def test_collect_requires_both_batches_complete(tmp_path):
    """collect_link_batches returns early if either batch is not completed."""
    from scholarwiki.linking.batch import collect_link_batches, LinkBatchCollectResult
    cfg = _make_config(tmp_path)
    paper = _make_paper("p1")
    paper.linking_batch_ids = {"gpt5": "batch_gpt5", "gpt41": "batch_gpt41"}
    reg = Registry(papers={"p1": paper})

    mock_batch_gpt5 = MagicMock(status="in_progress", id="batch_gpt5")
    mock_batch_gpt41 = MagicMock(status="completed", output_file_id="f1", id="batch_gpt41")
    mock_client = MagicMock()
    mock_client.batches.retrieve = AsyncMock(side_effect=[mock_batch_gpt5, mock_batch_gpt41])

    with patch("scholarwiki.linking.batch.AsyncOpenAI", return_value=mock_client):
        result = await collect_link_batches(
            reg, cfg.paths.raw, cfg.paths.staging, cfg.paths.wiki, cfg
        )

    assert result.linked == 0
    assert any("not completed" in e or "in_progress" in e for e in result.errors)


@pytest.mark.asyncio
async def test_collect_writes_concept_page(tmp_path):
    """collect_link_batches writes GPT-5 markdown to wiki/concepts/{slug}.md."""
    from scholarwiki.linking.batch import collect_link_batches
    cfg = _make_config(tmp_path)
    cfg.paths.raw.mkdir(parents=True)
    wiki = cfg.paths.wiki
    staging = cfg.paths.staging
    (wiki / "sources").mkdir(parents=True)
    (wiki / "concepts").mkdir(parents=True)

    paper = _make_paper("p1")
    paper.linking_batch_ids = {"gpt5": "batch_gpt5", "gpt41": "batch_gpt41"}
    reg = Registry(papers={"p1": paper})
    _write_concept_mapping(staging, "p1")

    gpt5_output = json.dumps({
        "custom_id": "concept_batch_correction",
        "response": {"body": {"choices": [{"message": {
            "content": "---\ntitle: Batch Correction\ntype: concept\n---\n\n# Batch Correction\n\nSynthesized content.\n"
        }}]}}
    })
    gpt41_output = json.dumps({
        "custom_id": "style_nature_genomics",
        "response": {"body": {"choices": [{"message": {
            "content": "---\ntitle: Nature Genomics Style\ntype: writing_style\n---\n\n# Style\n"
        }}]}}
    })

    mock_batch_gpt5 = MagicMock(**{"status": "completed", "output_file_id": "f_gpt5",
                                    "id": "batch_gpt5"})
    mock_batch_gpt41 = MagicMock(**{"status": "completed", "output_file_id": "f_gpt41",
                                     "id": "batch_gpt41"})
    mock_file_gpt5 = MagicMock(text=gpt5_output)
    mock_file_gpt41 = MagicMock(text=gpt41_output)

    mock_client = MagicMock()
    mock_client.batches.retrieve = AsyncMock(side_effect=[mock_batch_gpt5, mock_batch_gpt41])
    mock_client.files.content = AsyncMock(side_effect=[mock_file_gpt5, mock_file_gpt41])

    with patch("scholarwiki.linking.batch.AsyncOpenAI", return_value=mock_client), \
         patch("scholarwiki.linking.batch.save_registry"), \
         patch("scholarwiki.linking.batch.rebuild_suggested_papers"), \
         patch("scholarwiki.linking.batch.backfill_source_page"):
        result = await collect_link_batches(
            reg, cfg.paths.raw, staging, wiki, cfg
        )

    concept_page = wiki / "concepts" / "batch_correction.md"
    assert concept_page.exists()
    assert "Synthesized content" in concept_page.read_text()
