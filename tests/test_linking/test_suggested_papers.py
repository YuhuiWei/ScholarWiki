import json
from pathlib import Path
import pytest
from scholarwiki.linking.suggested_papers import rebuild_suggested_papers
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


def test_rebuild_unmatched_ref_appears(tmp_path):
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
    text = (wiki / "suggested_papers.md").read_text()
    assert "scVI (Lopez et al., 2018)" in text


def test_rebuild_ranks_by_reference_count(tmp_path):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    staging = tmp_path / "staging"
    staging.mkdir()
    reg = _make_registry("paper_a", "paper_b", "paper_c")
    ref = {
        "target_entity": "scVI (Lopez et al., 2018)",
        "target_doi": "10.1038/s41592-018-0229-2",
        "significance": "high",
    }
    for pid in ["paper_a", "paper_b", "paper_c"]:
        _write_roadmap(staging, pid, [ref])
    rebuild_suggested_papers(wiki, reg, staging, "2026-04-15", TEMPLATES_DIR)
    text = (wiki / "suggested_papers.md").read_text()
    assert "## High priority" in text
    assert "scVI (Lopez et al., 2018)" in text


def test_rebuild_is_idempotent(tmp_path):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    staging = tmp_path / "staging"
    staging.mkdir()
    reg = _make_registry("paper_a")
    _write_roadmap(staging, "paper_a", [
        {"target_entity": "Unknown Paper", "target_doi": None, "significance": "low"}
    ])
    rebuild_suggested_papers(wiki, reg, staging, "2026-04-15", TEMPLATES_DIR)
    rebuild_suggested_papers(wiki, reg, staging, "2026-04-15", TEMPLATES_DIR)
    text = (wiki / "suggested_papers.md").read_text()
    assert text.count("Unknown Paper") == 1
