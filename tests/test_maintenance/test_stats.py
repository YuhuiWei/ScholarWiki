from __future__ import annotations
from pathlib import Path
from scholarwiki.maintenance.stats import generate_stats
from scholarwiki.models import PaperEntry, Registry


def _make_registry(*papers: PaperEntry) -> Registry:
    reg = Registry()
    for p in papers:
        reg.papers[p.paper_id] = p
    return reg


def _paper(paper_id: str, status: str) -> PaperEntry:
    return PaperEntry(paper_id=paper_id, title="T", source="nexus",
                      extraction_status=status)


def _setup_wiki(tmp_path: Path, *, concepts=0, patterns=0, styles=0) -> Path:
    for subdir in ["sources", "concepts", "patterns", "writing"]:
        (tmp_path / subdir).mkdir()
    for i in range(concepts):
        (tmp_path / "concepts" / f"concept_{i}.md").write_text(f"# C{i}\n")
    for i in range(patterns):
        (tmp_path / "patterns" / f"pattern_{i}.md").write_text(f"# P{i}\n")
    for i in range(styles):
        (tmp_path / "writing" / f"style_{i}.md").write_text(f"# S{i}\n")
    return tmp_path


def test_empty_wiki_and_registry(tmp_path):
    wiki = _setup_wiki(tmp_path)
    output = generate_stats(wiki, _make_registry())
    assert "0 total" in output
    assert "Concepts:   0" in output
    assert "Patterns:   0" in output
    assert "Styles:     0" in output
    assert "Suggested:  0" in output


def test_paper_counts_by_status(tmp_path):
    wiki = _setup_wiki(tmp_path)
    reg = _make_registry(
        _paper("a", "linked"),
        _paper("b", "linked"),
        _paper("c", "extracted"),
        _paper("d", "submitted"),
        _paper("e", "pending"),
    )
    output = generate_stats(wiki, reg)
    assert "5 total" in output
    assert "linked: 2" in output
    assert "extracted: 1" in output
    assert "submitted: 1" in output
    assert "pending: 1" in output


def test_page_counts(tmp_path):
    wiki = _setup_wiki(tmp_path, concepts=3, patterns=2, styles=4)
    output = generate_stats(wiki, _make_registry())
    assert "Concepts:   3" in output
    assert "Patterns:   2" in output
    assert "Styles:     4" in output


def test_suggested_papers_count(tmp_path):
    wiki = _setup_wiki(tmp_path)
    sf = wiki / "suggested_papers.md"
    sf.write_text(
        "# Suggested Papers\n\n### Paper One\n\n### Paper Two\n\n### Paper Three\n"
    )
    output = generate_stats(wiki, _make_registry())
    assert "Suggested:  3" in output


def test_missing_wiki_subdirs_return_zero(tmp_path):
    """If concept/pattern/writing dirs don't exist, count as 0."""
    output = generate_stats(tmp_path, _make_registry())
    assert "Concepts:   0" in output
    assert "Patterns:   0" in output
    assert "Styles:     0" in output


def test_output_has_header(tmp_path):
    wiki = _setup_wiki(tmp_path)
    output = generate_stats(wiki, _make_registry())
    assert "ScholarWiki Knowledge Base" in output
