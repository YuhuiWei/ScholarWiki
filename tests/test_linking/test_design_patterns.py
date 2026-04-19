from __future__ import annotations
import json
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from scholarwiki.linking.design_patterns import write_pattern_page, cluster_patterns


def test_write_pattern_page_creates_file(tmp_path):
    wiki = tmp_path / "wiki"
    (wiki / "patterns").mkdir(parents=True)
    write_pattern_page(wiki, "benchmark_comparison", "# Benchmark Comparison\n\ncontent\n")
    page = wiki / "patterns" / "benchmark_comparison.md"
    assert page.exists()
    assert "# Benchmark Comparison" in page.read_text()


def test_write_pattern_page_overwrites(tmp_path):
    wiki = tmp_path / "wiki"
    (wiki / "patterns").mkdir(parents=True)
    page = wiki / "patterns" / "my_pattern.md"
    page.write_text("OLD")
    write_pattern_page(wiki, "my_pattern", "NEW")
    assert page.read_text() == "NEW"


def test_write_pattern_page_atomic(tmp_path):
    wiki = tmp_path / "wiki"
    (wiki / "patterns").mkdir(parents=True)
    write_pattern_page(wiki, "my_pattern", "content")
    assert not (wiki / "patterns" / "my_pattern.md.tmp").exists()


@pytest.mark.asyncio
async def test_cluster_patterns_returns_dict(tmp_path):
    """cluster_patterns returns {pattern_slug: {paper_ids, title}} via mocked GPT-5 call."""
    from scholarwiki.config import Config, PathsConfig, LinkingConfig

    cfg = Config(
        paths=PathsConfig(raw=tmp_path, staging=tmp_path, wiki=tmp_path),
        linking=LinkingConfig(synthesis_model="gpt-5", style_model="gpt-4.1"),
    )
    papers = [
        {"paper_id": "p1", "title": "Paper 1", "logic_pattern": "premise → innovation → validation"},
        {"paper_id": "p2", "title": "Paper 2", "logic_pattern": "gap → method → benchmark"},
    ]
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock(message=MagicMock(content=json.dumps({
        "assignments": {"benchmark_comparison_ablation": ["p1", "p2"]},
        "new_pattern_titles": {"benchmark_comparison_ablation": "Benchmark comparison with ablation"},
        "unassigned": [],
    })))]
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)

    with patch("scholarwiki.linking.design_patterns.AsyncOpenAI", return_value=mock_client), \
         patch.dict("sys.modules", {"scholarwiki.linking.synthesis_prompts": MagicMock(PATTERN_CLUSTER_SYSTEM="sys")}):
        result = await cluster_patterns(papers, existing_pattern_index=[], cfg=cfg)

    assert "benchmark_comparison_ablation" in result
    assert set(result["benchmark_comparison_ablation"]["paper_ids"]) == {"p1", "p2"}
    assert result["benchmark_comparison_ablation"]["title"] == "Benchmark comparison with ablation"


@pytest.mark.asyncio
async def test_cluster_patterns_filters_single_paper_clusters(tmp_path):
    """Patterns with only 1 paper are excluded from result."""
    from scholarwiki.config import Config, PathsConfig, LinkingConfig

    cfg = Config(
        paths=PathsConfig(raw=tmp_path, staging=tmp_path, wiki=tmp_path),
        linking=LinkingConfig(synthesis_model="gpt-5", style_model="gpt-4.1"),
    )
    papers = [{"paper_id": "p1", "title": "Solo", "logic_pattern": "premise → conclusion"}]
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock(message=MagicMock(content=json.dumps({
        "assignments": {"solo_pattern": ["p1"]},
        "new_pattern_titles": {"solo_pattern": "Solo Pattern"},
        "unassigned": [],
    })))]
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)

    with patch("scholarwiki.linking.design_patterns.AsyncOpenAI", return_value=mock_client), \
         patch.dict("sys.modules", {"scholarwiki.linking.synthesis_prompts": MagicMock(PATTERN_CLUSTER_SYSTEM="sys")}):
        result = await cluster_patterns(papers, existing_pattern_index=[], cfg=cfg)

    # Single-paper clusters excluded
    assert "solo_pattern" not in result
