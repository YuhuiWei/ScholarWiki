from __future__ import annotations
import pytest
from pathlib import Path
from scholarwiki.maintenance.lint import run_lint, LintReport
from scholarwiki.models import PaperEntry, Registry


def _make_registry(*papers: PaperEntry) -> Registry:
    reg = Registry()
    for p in papers:
        reg.papers[p.paper_id] = p
    return reg


def _setup_wiki(tmp_path: Path) -> Path:
    """Create minimal wiki directory structure."""
    for subdir in ["sources", "concepts", "patterns", "writing"]:
        (tmp_path / subdir).mkdir()
    return tmp_path


# ---------- empty wiki ----------

def test_empty_wiki_no_issues(tmp_path):
    wiki = _setup_wiki(tmp_path)
    report = run_lint(wiki, _make_registry())
    assert report.issues == []
    assert report.error_count == 0
    assert report.warning_count == 0
    assert report.info_count == 0


# ---------- orphan concept ----------

def test_orphan_concept_detected(tmp_path):
    wiki = _setup_wiki(tmp_path)
    (wiki / "concepts" / "batch_correction.md").write_text("# Batch Correction\n")
    # No source pages link to it
    report = run_lint(wiki, _make_registry())
    orphans = [i for i in report.issues if i.category == "orphan_concept"]
    assert len(orphans) == 1
    assert "batch_correction" in orphans[0].message


def test_linked_concept_not_orphan(tmp_path):
    wiki = _setup_wiki(tmp_path)
    (wiki / "concepts" / "scvi.md").write_text("# scVI\n")
    (wiki / "sources" / "lopez2018.md").write_text("See [[scvi]] for details.\n")
    report = run_lint(wiki, _make_registry())
    orphans = [i for i in report.issues if i.category == "orphan_concept"]
    assert orphans == []


# ---------- missing wikilinks ----------

def test_missing_wikilink_detected(tmp_path):
    wiki = _setup_wiki(tmp_path)
    (wiki / "sources" / "paper_a.md").write_text("See [[nonexistent_concept]] here.\n")
    report = run_lint(wiki, _make_registry())
    missing = [i for i in report.issues if i.category == "missing_link"]
    assert len(missing) == 1
    assert "nonexistent_concept" in missing[0].message
    assert missing[0].severity == "error"


def test_valid_wikilink_no_error(tmp_path):
    wiki = _setup_wiki(tmp_path)
    (wiki / "concepts" / "batch_correction.md").write_text("# Batch Correction\n")
    (wiki / "sources" / "paper_a.md").write_text("See [[batch_correction]].\n")
    report = run_lint(wiki, _make_registry())
    missing = [i for i in report.issues if i.category == "missing_link"]
    assert missing == []


def test_wikilink_with_alias_checked(tmp_path):
    """[[target|display text]] — only target slug is checked."""
    wiki = _setup_wiki(tmp_path)
    (wiki / "sources" / "paper_a.md").write_text("See [[missing_page|display text]].\n")
    report = run_lint(wiki, _make_registry())
    missing = [i for i in report.issues if i.category == "missing_link"]
    assert len(missing) == 1
    assert "missing_page" in missing[0].message


# ---------- weak patterns ----------

def test_weak_pattern_detected(tmp_path):
    wiki = _setup_wiki(tmp_path)
    (wiki / "patterns" / "vae_pattern.md").write_text("# VAE Pattern\nSee [[paper_a]].\n")
    (wiki / "sources" / "paper_a.md").write_text("# Paper A\n")
    report = run_lint(wiki, _make_registry())
    weak = [i for i in report.issues if i.category == "weak_pattern"]
    assert len(weak) == 1
    assert weak[0].severity == "info"


def test_strong_pattern_not_flagged(tmp_path):
    wiki = _setup_wiki(tmp_path)
    (wiki / "sources" / "paper_a.md").write_text("# Paper A\n")
    (wiki / "sources" / "paper_b.md").write_text("# Paper B\n")
    (wiki / "patterns" / "vae_pattern.md").write_text(
        "# VAE Pattern\nSee [[paper_a]] and [[paper_b]].\n"
    )
    report = run_lint(wiki, _make_registry())
    weak = [i for i in report.issues if i.category == "weak_pattern"]
    assert weak == []


# ---------- missing source pages ----------

def test_missing_source_page_detected(tmp_path):
    wiki = _setup_wiki(tmp_path)
    reg = _make_registry(PaperEntry(
        paper_id="abc",
        title="Test Paper",
        source="nexus",
        extraction_status="linked",
        wiki_source_page="sources/test_paper.md",
    ))
    # The file does not exist on disk
    report = run_lint(wiki, reg)
    missing = [i for i in report.issues if i.category == "missing_source_page"]
    assert len(missing) == 1
    assert missing[0].severity == "error"


def test_present_source_page_not_flagged(tmp_path):
    wiki = _setup_wiki(tmp_path)
    (wiki / "sources" / "test_paper.md").write_text("# Test\n")
    reg = _make_registry(PaperEntry(
        paper_id="abc",
        title="Test Paper",
        source="nexus",
        extraction_status="linked",
        wiki_source_page="sources/test_paper.md",
    ))
    report = run_lint(wiki, reg)
    missing = [i for i in report.issues if i.category == "missing_source_page"]
    assert missing == []


def test_non_linked_paper_not_checked(tmp_path):
    """Papers that are not 'linked' should not trigger missing_source_page."""
    wiki = _setup_wiki(tmp_path)
    reg = _make_registry(PaperEntry(
        paper_id="abc",
        title="Test Paper",
        source="nexus",
        extraction_status="extracted",
        wiki_source_page="sources/test_paper.md",
    ))
    report = run_lint(wiki, reg)
    missing = [i for i in report.issues if i.category == "missing_source_page"]
    assert missing == []


# ---------- index drift ----------

def test_index_drift_detected(tmp_path):
    wiki = _setup_wiki(tmp_path)
    (wiki / "index.md").write_text("# Index\n\nNothing here yet.\n")
    (wiki / "sources" / "orphan_paper.md").write_text("# Orphan\n")
    report = run_lint(wiki, _make_registry())
    drift = [i for i in report.issues if i.category == "index_drift"]
    assert len(drift) == 1
    assert drift[0].severity == "warning"


def test_no_index_drift_when_referenced(tmp_path):
    wiki = _setup_wiki(tmp_path)
    (wiki / "index.md").write_text("# Index\n\n- [[paper_a]]\n")
    (wiki / "sources" / "paper_a.md").write_text("# Paper A\n")
    report = run_lint(wiki, _make_registry())
    drift = [i for i in report.issues if i.category == "index_drift"]
    assert drift == []


def test_no_index_file_no_drift_issues(tmp_path):
    """If index.md doesn't exist, index drift check is skipped."""
    wiki = _setup_wiki(tmp_path)
    (wiki / "sources" / "paper_a.md").write_text("# Paper A\n")
    report = run_lint(wiki, _make_registry())
    drift = [i for i in report.issues if i.category == "index_drift"]
    assert drift == []
