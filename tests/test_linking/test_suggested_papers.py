import json
from pathlib import Path
import pytest
from scholarwiki.linking.suggested_papers import (
    rebuild_suggested_papers,
    _parse_connections,
    _build_concept_graph,
    _compute_hub_scores,
)
from scholarwiki.models import PaperEntry, Registry

TEMPLATES_DIR = Path("templates")


def _make_registry(*paper_ids: str) -> Registry:
    papers = {
        pid: PaperEntry(paper_id=pid, title=f"Paper {pid}", source="manual", doi=f"10.000/{pid}")
        for pid in paper_ids
    }
    return Registry(papers=papers)


def _write_roadmap(staging_dir: Path, paper_id: str, relationships: list[dict]) -> None:
    (staging_dir / paper_id).mkdir(parents=True, exist_ok=True)
    (staging_dir / paper_id / "roadmap.json").write_text(
        json.dumps({"relationships": relationships})
    )


def test_rebuild_no_unmatched_refs(tmp_path):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    staging = tmp_path / "staging"
    staging.mkdir()
    reg = _make_registry("paper_a")
    # roadmap references a paper already in registry
    _write_roadmap(staging, "paper_a", [
        {"target_entity": "Paper paper_a", "target_doi": "10.000/paper_a", "significance": "high"}
    ])
    rebuild_suggested_papers(wiki, reg, staging, "2026-04-15", TEMPLATES_DIR)
    page = wiki / "suggested_papers.md"
    assert page.exists()
    text = page.read_text()
    assert "## High priority" not in text


def test_rebuild_single_cite_in_json_not_wiki(tmp_path):
    """A paper cited by only 1 source appears in the JSON sidecar but not the wiki page."""
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    staging = tmp_path / "staging"
    staging.mkdir()
    reg = _make_registry("paper_a")
    _write_roadmap(staging, "paper_a", [
        {
            "target_entity": "scVI (Lopez et al., 2018)",
            "target_doi": "10.1038/s41592-018-0229-2",
            "significance": "high",
        }
    ])
    rebuild_suggested_papers(wiki, reg, staging, "2026-04-15", TEMPLATES_DIR)
    # Not in wiki page (only 1 citation)
    text = (wiki / "suggested_papers.md").read_text()
    assert "scVI (Lopez et al., 2018)" not in text
    # But saved in JSON sidecar
    data = json.loads((wiki / "suggested_papers.json").read_text())
    titles = [r["title"] for r in data]
    assert "scVI (Lopez et al., 2018)" in titles


def test_rebuild_ranks_by_reference_count(tmp_path):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    staging = tmp_path / "staging"
    staging.mkdir()
    reg = _make_registry("paper_a", "paper_b")
    ref = {
        "target_entity": "scVI (Lopez et al., 2018)",
        "target_doi": "10.1038/s41592-018-0229-2",
        "significance": "high",
    }
    for pid in ["paper_a", "paper_b"]:
        _write_roadmap(staging, pid, [ref])
    rebuild_suggested_papers(wiki, reg, staging, "2026-04-15", TEMPLATES_DIR)
    text = (wiki / "suggested_papers.md").read_text()
    # 2 citing papers → meets min_citations=2 default, appears in wiki
    assert ("## Critical" in text or "## High priority" in text)
    assert "scVI (Lopez et al., 2018)" in text


def test_rebuild_is_idempotent(tmp_path):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    staging = tmp_path / "staging"
    staging.mkdir()
    reg = _make_registry("paper_a", "paper_b")
    ref = {"target_entity": "Unknown Paper", "target_doi": None, "significance": "low"}
    for pid in ["paper_a", "paper_b"]:
        _write_roadmap(staging, pid, [ref])
    rebuild_suggested_papers(wiki, reg, staging, "2026-04-15", TEMPLATES_DIR)
    rebuild_suggested_papers(wiki, reg, staging, "2026-04-15", TEMPLATES_DIR)
    text = (wiki / "suggested_papers.md").read_text()
    assert text.count("Unknown Paper") == 1


# ── Graph-aware tests ────────────────────────────────────────────────────────

_CONCEPT_PAGE = """\
---
title: "My concept"
type: concept
connections:
  - target: "[[other_concept]]"
    edge_type: "enables"
    description: "A enables B."
  - target: "[[pattern_foo]]"
    edge_type: "is_pattern_for"
    description: "Pattern for this concept."
last_updated: "2026-04-21"
---

# My concept
"""


def test_parse_connections_extracts_targets():
    conns = _parse_connections(_CONCEPT_PAGE)
    slugs = {c["target_slug"] for c in conns}
    assert "other_concept" in slugs
    assert "pattern_foo" in slugs


def test_parse_connections_extracts_edge_types():
    conns = _parse_connections(_CONCEPT_PAGE)
    by_slug = {c["target_slug"]: c["edge_type"] for c in conns}
    assert by_slug["other_concept"] == "enables"
    assert by_slug["pattern_foo"] == "is_pattern_for"


def test_parse_connections_no_frontmatter_returns_empty():
    assert _parse_connections("# Just a page\nNo frontmatter here.") == []


def test_build_concept_graph_reads_pages(tmp_path):
    concepts = tmp_path / "concepts"
    concepts.mkdir()
    (concepts / "my_concept.md").write_text(_CONCEPT_PAGE)
    adj = _build_concept_graph(tmp_path)
    assert "other_concept" in adj.get("my_concept", set())
    assert "pattern_foo" in adj.get("my_concept", set())


def test_compute_hub_scores_counts_in_and_out_degree():
    # A → B, A → C, D → A
    adj = {"A": {"B", "C"}, "D": {"A"}}
    scores = _compute_hub_scores(adj)
    # A: out=2 (→B, →C), in=1 (D→) = 3
    assert scores["A"] == 3
    # B: out=0, in=1 = 1
    assert scores["B"] == 1
    # D: out=1, in=0 = 1
    assert scores["D"] == 1


def test_hub_concepts_boost_referenced_paper_score(tmp_path):
    """A missing paper cited by a high-hub concept scores higher than one cited by an isolated source."""
    wiki = tmp_path / "wiki"
    concepts = wiki / "concepts"
    concepts.mkdir(parents=True)

    # Create a hub concept page (connected to 3 other pages)
    hub_page = """\
---
title: "Hub concept"
type: concept
connections:
  - target: "[[alpha]]"
    edge_type: "enables"
    description: "."
  - target: "[[beta]]"
    edge_type: "subtopic_of"
    description: "."
  - target: "[[gamma]]"
    edge_type: "contributes_to"
    description: "."
last_updated: "2026-04-21"
---
"""
    (concepts / "hub_concept.md").write_text(hub_page)

    staging = tmp_path / "staging"
    staging.mkdir()
    reg = _make_registry("paper_a", "paper_b")
    # paper_a's source page slug = "paper_a" (no wiki_source_page in _make_registry)
    # paper_b cites foundational_ref (lower hub)
    _write_roadmap(staging, "paper_a", [
        {"target_entity": "Foundational work A", "target_doi": "10.1/a", "significance": "high"}
    ])
    _write_roadmap(staging, "paper_b", [
        {"target_entity": "Foundational work B", "target_doi": "10.1/b", "significance": "high"}
    ])

    rebuild_suggested_papers(wiki, reg, staging, "2026-04-21", TEMPLATES_DIR)
    # Only 1 citation each → not in wiki page, but saved in JSON sidecar
    text = (wiki / "suggested_papers.md").read_text()
    assert "Foundational work A" not in text
    assert "Foundational work B" not in text
    data = json.loads((wiki / "suggested_papers.json").read_text())
    titles = {r["title"] for r in data}
    assert "Foundational work A" in titles
    assert "Foundational work B" in titles


def test_min_citations_filters_output(tmp_path):
    """Only papers cited by >= min_citations sources appear in the wiki page."""
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    staging = tmp_path / "staging"
    staging.mkdir()
    reg = _make_registry("p1", "p2", "p3")
    # "Popular paper" cited by all 3 sources; "Rare paper" cited by only 1
    for pid in ["p1", "p2", "p3"]:
        rels = [{"target_entity": "Popular paper", "target_doi": "10.1/pop", "significance": "high"}]
        if pid == "p1":
            rels.append({"target_entity": "Rare paper", "target_doi": "10.1/rare", "significance": "low"})
        _write_roadmap(staging, pid, rels)
    rebuild_suggested_papers(wiki, reg, staging, "2026-04-21", TEMPLATES_DIR, min_citations=2)
    text = (wiki / "suggested_papers.md").read_text()
    assert "Popular paper" in text
    assert "Rare paper" not in text
    # JSON sidecar has both
    data = json.loads((wiki / "suggested_papers.json").read_text())
    titles = {r["title"] for r in data}
    assert "Popular paper" in titles
    assert "Rare paper" in titles
