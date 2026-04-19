from __future__ import annotations
import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from scholarwiki.extraction.batch import (
    submit_batch, get_batch_status, collect_batch, retry_failed_modules,
    BatchSubmitResult, BatchCollectResult,
)
from scholarwiki.models import PaperEntry, Registry
from scholarwiki.config import Config


def _config(tmp_path) -> Config:
    cfg = Config()
    cfg.paths.raw = tmp_path / "raw"
    cfg.paths.staging = tmp_path / "staging"
    cfg.paths.wiki = tmp_path / "wiki"
    cfg.extraction.model = "gpt-4.1"
    cfg.extraction.max_tokens_per_request = 4096
    return cfg


def _entry(paper_id: str, tmp_path: Path) -> PaperEntry:
    papers_dir = tmp_path / "raw" / "papers"
    papers_dir.mkdir(parents=True, exist_ok=True)
    # Create a minimal real PDF using pymupdf
    import fitz
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "This is a test academic paper about machine learning.")
    pdf_path = papers_dir / f"{paper_id}.pdf"
    doc.save(str(pdf_path))
    doc.close()

    wiki_sources = tmp_path / "wiki" / "sources"
    wiki_sources.mkdir(parents=True, exist_ok=True)
    source_page = wiki_sources / f"{paper_id}.md"
    source_page.write_text(
        "---\ntitle: Test\n---\n\n# Test\n\n"
        "## Summary\n<!-- Backfilled after LLM extraction -->\n_Pending extraction._\n\n"
        "## Knowledge Contributions\n"
    )

    return PaperEntry(
        paper_id=paper_id,
        title="Test Paper on Machine Learning",
        source="nexus",
        file_path=f"raw/papers/{paper_id}.pdf",
        file_type="pdf",
        wiki_source_page=f"wiki/sources/{paper_id}.md",
        extraction_status="pending",
    )


def _mock_openai_client(batch_id: str = "batch_test123") -> MagicMock:
    client = MagicMock()
    client.files = MagicMock()
    client.batches = MagicMock()

    file_obj = MagicMock()
    file_obj.id = "file_abc"
    client.files.create = AsyncMock(return_value=file_obj)

    batch_obj = MagicMock()
    batch_obj.id = batch_id
    client.batches.create = AsyncMock(return_value=batch_obj)

    return client


@pytest.mark.asyncio
async def test_submit_batch_returns_result(tmp_path):
    cfg = _config(tmp_path)
    entry = _entry("paper001", tmp_path)
    registry = Registry()
    registry.papers["paper001"] = entry

    mock_client = _mock_openai_client("batch_xyz")
    with patch("scholarwiki.extraction.batch._make_client", return_value=mock_client):
        result = await submit_batch([entry], cfg.paths.raw, cfg)

    assert result.batch_id == "batch_xyz"
    assert "paper001" in result.paper_ids
    assert result.request_count == 5  # 5 modules per paper


@pytest.mark.asyncio
async def test_submit_batch_uploads_jsonl_with_correct_custom_ids(tmp_path):
    cfg = _config(tmp_path)
    entry = _entry("paper001", tmp_path)

    mock_client = _mock_openai_client()
    captured_content = {}

    async def capture_create(**kwargs):
        file_tuple = kwargs["file"]
        captured_content["bytes"] = file_tuple[1].read()
        file_obj = MagicMock()
        file_obj.id = "file_abc"
        return file_obj

    mock_client.files.create = capture_create

    with patch("scholarwiki.extraction.batch._make_client", return_value=mock_client):
        await submit_batch([entry], cfg.paths.raw, cfg)

    lines = [json.loads(line) for line in captured_content["bytes"].decode().strip().split("\n")]
    custom_ids = {line["custom_id"] for line in lines}
    assert "paper001_knowledge" in custom_ids
    assert "paper001_roadmap" in custom_ids
    assert "paper001_experiment" in custom_ids
    assert "paper001_writing" in custom_ids
    assert "paper001_logic" in custom_ids


@pytest.mark.asyncio
async def test_get_batch_status_returns_dict(tmp_path):
    cfg = _config(tmp_path)
    mock_client = MagicMock()
    batch_obj = MagicMock()
    batch_obj.id = "batch_test"
    batch_obj.status = "in_progress"
    batch_obj.request_counts = MagicMock(total=10, completed=6, failed=0)
    mock_client.batches.retrieve = AsyncMock(return_value=batch_obj)

    with patch("scholarwiki.extraction.batch._make_client", return_value=mock_client):
        status = await get_batch_status("batch_test", cfg)

    assert status["status"] == "in_progress"
    assert status["request_counts"]["completed"] == 6


def _make_output_line(custom_id: str, content: dict) -> str:
    return json.dumps({
        "custom_id": custom_id,
        "response": {
            "body": {
                "choices": [{"message": {"content": json.dumps(content)}}]
            }
        },
        "error": None,
    })


@pytest.mark.asyncio
async def test_collect_batch_writes_staging_files(tmp_path):
    cfg = _config(tmp_path)
    entry = _entry("paper001", tmp_path)
    registry = Registry()
    registry.papers["paper001"] = entry
    entry.extraction_status = "submitted"
    entry.extraction_batch_id = "batch_test"

    knowledge_data = {"knowledge_items": [{"claim": "Test claim", "related_concepts": ["ML"]}]}
    roadmap_data = {"relationships": []}
    experiment_data = {"experimental_pipeline": [{"step": 1, "action": "Training", "tools": ["PyTorch"]}]}
    writing_data = {}
    logic_data = {}

    output_lines = "\n".join([
        _make_output_line("paper001_knowledge", knowledge_data),
        _make_output_line("paper001_roadmap", roadmap_data),
        _make_output_line("paper001_experiment", experiment_data),
        _make_output_line("paper001_writing", writing_data),
        _make_output_line("paper001_logic", logic_data),
    ])

    mock_client = MagicMock()
    batch_obj = MagicMock()
    batch_obj.status = "completed"
    batch_obj.output_file_id = "file_out"
    mock_client.batches.retrieve = AsyncMock(return_value=batch_obj)
    file_content = MagicMock()
    file_content.text = output_lines
    mock_client.files.content = AsyncMock(return_value=file_content)

    # Need raw dir to exist for save_registry
    cfg.paths.raw.mkdir(parents=True, exist_ok=True)

    with patch("scholarwiki.extraction.batch._make_client", return_value=mock_client):
        result = await collect_batch(
            "batch_test", registry, cfg.paths.raw, cfg.paths.staging, cfg.paths.wiki, cfg
        )

    assert result.extracted == 1
    assert result.partial == 0
    staging_dir = cfg.paths.staging / "paper001"
    assert (staging_dir / "knowledge.json").exists()
    assert (staging_dir / "roadmap.json").exists()
    assert (staging_dir / "experiment.json").exists()
    assert registry.papers["paper001"].extraction_status == "extracted"
    assert registry.papers["paper001"].failed_modules == []

    # Verify wiki source page was updated with L1 profile
    source_page = cfg.paths.wiki / "sources" / "paper001.md"
    source_text = source_page.read_text()
    assert "_Pending extraction._" not in source_text


@pytest.mark.asyncio
async def test_collect_batch_records_partial_failure(tmp_path):
    cfg = _config(tmp_path)
    entry = _entry("paper001", tmp_path)
    registry = Registry()
    registry.papers["paper001"] = entry
    entry.extraction_status = "submitted"
    entry.extraction_batch_id = "batch_test"

    # Only 3 of 5 modules come back
    output_lines = "\n".join([
        _make_output_line("paper001_knowledge", {"knowledge_items": []}),
        _make_output_line("paper001_roadmap", {"relationships": []}),
        _make_output_line("paper001_experiment", {}),
    ])

    mock_client = MagicMock()
    batch_obj = MagicMock()
    batch_obj.status = "completed"
    batch_obj.output_file_id = "file_out"
    mock_client.batches.retrieve = AsyncMock(return_value=batch_obj)
    file_content = MagicMock()
    file_content.text = output_lines
    mock_client.files.content = AsyncMock(return_value=file_content)

    cfg.paths.raw.mkdir(parents=True, exist_ok=True)

    with patch("scholarwiki.extraction.batch._make_client", return_value=mock_client):
        result = await collect_batch(
            "batch_test", registry, cfg.paths.raw, cfg.paths.staging, cfg.paths.wiki, cfg
        )

    assert result.partial == 1
    assert result.extracted == 0
    assert set(registry.papers["paper001"].failed_modules) == {"writing", "logic"}
    assert registry.papers["paper001"].extraction_status == "submitted"


@pytest.mark.asyncio
async def test_collect_batch_not_completed_returns_error(tmp_path):
    cfg = _config(tmp_path)
    registry = Registry()

    mock_client = MagicMock()
    batch_obj = MagicMock()
    batch_obj.status = "in_progress"
    mock_client.batches.retrieve = AsyncMock(return_value=batch_obj)

    with patch("scholarwiki.extraction.batch._make_client", return_value=mock_client):
        result = await collect_batch(
            "batch_test", registry, cfg.paths.raw, cfg.paths.staging, cfg.paths.wiki, cfg
        )

    assert result.extracted == 0
    assert len(result.errors) == 1
    assert "in_progress" in result.errors[0]


@pytest.mark.asyncio
async def test_retry_failed_modules_submits_only_failed(tmp_path):
    cfg = _config(tmp_path)
    entry = _entry("paper001", tmp_path)
    entry.extraction_status = "submitted"
    entry.failed_modules = ["writing", "logic"]
    registry = Registry()
    registry.papers["paper001"] = entry

    mock_client = _mock_openai_client("batch_retry001")
    captured_content = {}

    async def capture_create(**kwargs):
        file_tuple = kwargs["file"]
        captured_content["bytes"] = file_tuple[1].read()
        file_obj = MagicMock()
        file_obj.id = "file_retry"
        return file_obj

    mock_client.files.create = capture_create

    with patch("scholarwiki.extraction.batch._make_client", return_value=mock_client):
        result = await retry_failed_modules(registry, cfg.paths.raw, cfg)

    assert result.batch_id == "batch_retry001"
    assert "paper001" in result.paper_ids
    assert result.request_count == 2  # only writing + logic

    lines = [json.loads(line) for line in captured_content["bytes"].decode().strip().split("\n")]
    custom_ids = {line["custom_id"] for line in lines}
    assert "paper001_writing" in custom_ids
    assert "paper001_logic" in custom_ids
    assert "paper001_knowledge" not in custom_ids  # not in failed_modules

    # batch_id updated on entry
    assert registry.papers["paper001"].extraction_batch_id == "batch_retry001"


def test_collect_writes_concept_mapping_json(tmp_path):
    """After collect, concept_mapping.json exists in staging dir for each extracted paper."""
    from scholarwiki.extraction.batch import collect_batch
    from scholarwiki.models import Registry, PaperEntry
    from scholarwiki.config import Config, PathsConfig

    # Setup paths
    raw = tmp_path / "raw"
    raw.mkdir()
    staging = tmp_path / "staging"
    wiki = tmp_path / "wiki"
    (wiki / "concepts").mkdir(parents=True)

    cfg = Config(paths=PathsConfig(raw=raw, staging=staging, wiki=wiki))
    paper_id = "test_paper_001"
    paper = PaperEntry(
        paper_id=paper_id, title="Test Paper", source="manual",
        extraction_status="submitted", extraction_batch_id="batch_xyz",
        wiki_source_page=f"wiki/sources/{paper_id}.md",
    )
    reg = Registry(papers={paper_id: paper})

    # Prepare mock batch response with all 5 modules
    def make_line(module):
        return json.dumps({
            "custom_id": f"{paper_id}_{module}",
            "response": {"body": {"choices": [{"message": {"content": json.dumps(
                {"knowledge_items": [{"id": "k1", "claim": "C", "related_concepts": ["concept_x"],
                  "evidence_type": "experimental", "confidence": "high",
                  "supporting_data": None, "domain_tags": [], "quantitative_result": None}]}
                if module == "knowledge" else
                {"relationships": [], "positioned_as": None, "gap_filled": None, "field_context": None}
                if module == "roadmap" else
                {"experimental_pipeline": [], "datasets": [], "controls": [],
                 "evaluation_metrics": [], "key_parameters": {}, "reproducibility_notes": None}
                if module == "experiment" else
                {"venue": "Nature", "topic_area": "genomics", "venue_type": "journal",
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
                 "citation_style": None, "data_availability": None}
                if module == "writing" else
                {"logic_pattern": "premise → conclusion", "hypothesis": None,
                 "reasoning_chain": [], "assumptions": [], "limitations_acknowledged": [],
                 "strengths_of_argument": []}
            )}}]}},
        })
    mock_content = MagicMock()
    mock_content.text = "\n".join(make_line(m) for m in
                                  ["knowledge", "roadmap", "experiment", "writing", "logic"])

    mock_batch = MagicMock(status="completed", output_file_id="file_123")
    mock_client = MagicMock()
    mock_client.batches.retrieve = AsyncMock(return_value=mock_batch)
    mock_client.files.content = AsyncMock(return_value=mock_content)

    with patch("scholarwiki.extraction.batch.AsyncOpenAI", return_value=mock_client), \
         patch("scholarwiki.extraction.batch.update_source_page_summary"), \
         patch("scholarwiki.extraction.batch.aggregate_l1_profile", return_value=MagicMock()):
        asyncio.run(collect_batch("batch_xyz", reg, raw, staging, wiki, cfg))

    mapping_path = staging / paper_id / "concept_mapping.json"
    assert mapping_path.exists(), "concept_mapping.json should be written after collect"
    data = json.loads(mapping_path.read_text())
    assert data["paper_id"] == paper_id
    assert "concept_contributions" in data
    assert "pattern_signals" in data
    assert "writing_signals" in data
