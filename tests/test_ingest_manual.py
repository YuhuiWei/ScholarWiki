import shutil
import pytest
from pathlib import Path
from scholarwiki.config import Config, PathsConfig
from scholarwiki.registry import load_registry
from scholarwiki.manual_queue import load_manual_queue, append_pending, ManualEntry
from scholarwiki.ingest.manual import ingest_manual_inbox


@pytest.fixture
def project(tmp_path, fixtures_dir):
    manual_inbox = tmp_path / "manual_inbox"
    manual_inbox.mkdir()
    raw = tmp_path / "raw"
    raw.mkdir()
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    templates = tmp_path / "templates"
    shutil.copytree(Path("templates"), templates)
    cfg = Config(paths=PathsConfig(
        nexus_inbox=tmp_path / "nexus_inbox",
        manual_inbox=manual_inbox,
        raw=raw,
        wiki=wiki,
    ))
    return {"tmp": tmp_path, "cfg": cfg, "templates": templates, "fixtures": fixtures_dir}


def test_matched_pdf_is_moved_and_registered(project):
    cfg = project["cfg"]
    # Put a pending entry in manual.md
    queue = load_manual_queue(cfg.paths.raw)
    append_pending(queue, ManualEntry(
        paper_id="a3f8c2e1d9b47f12",
        title="Attention Is All You Need",
        authors=["Vaswani, A."],
        year=2017,
        venue="NeurIPS",
        doi="10.48550/arXiv.1706.03762",
        added_date="2026-04-09",
    ), cfg.paths.raw)
    # Drop sample PDF in manual_inbox
    shutil.copy(project["fixtures"] / "sample_paper.pdf", cfg.paths.manual_inbox / "attention.pdf")
    result = ingest_manual_inbox(cfg, templates_dir=project["templates"])
    assert result.manual_matched == 1
    papers = list((cfg.paths.raw / "papers").glob("*.pdf"))
    assert len(papers) == 1


def test_matched_pdf_updates_manual_md(project):
    cfg = project["cfg"]
    queue = load_manual_queue(cfg.paths.raw)
    append_pending(queue, ManualEntry(
        paper_id="a3f8c2e1d9b47f12",
        title="Attention Is All You Need",
        authors=["Vaswani, A."],
        year=2017, venue="NeurIPS",
        doi="10.48550/arXiv.1706.03762",
        added_date="2026-04-09",
    ), cfg.paths.raw)
    shutil.copy(project["fixtures"] / "sample_paper.pdf", cfg.paths.manual_inbox / "attention.pdf")
    ingest_manual_inbox(cfg, templates_dir=project["templates"])
    reloaded = load_manual_queue(cfg.paths.raw)
    assert len(reloaded.pending) == 0
    assert len(reloaded.downloaded) == 1


def test_unmatched_pdf_is_registered_as_manual_unmatched(project):
    cfg = project["cfg"]
    # No pending entry — drop PDF that won't fuzzy-match anything
    shutil.copy(project["fixtures"] / "sample_paper.pdf", cfg.paths.manual_inbox / "attention.pdf")
    result = ingest_manual_inbox(cfg, templates_dir=project["templates"], interactive=False)
    reg = load_registry(cfg.paths.raw)
    # Should be registered with source="manual_unmatched"
    entries = [e for e in reg.papers.values() if e.source == "manual_unmatched"]
    assert len(entries) == 1


def test_ingest_manual_sets_zotero_key_when_push_succeeds(project):
    from unittest.mock import patch
    import shutil
    cfg = project["cfg"]
    cfg.zotero.library_id = "12345"
    cfg.zotero.api_key = "fakekey"
    queue = load_manual_queue(cfg.paths.raw)
    append_pending(queue, ManualEntry(
        paper_id="a3f8c2e1d9b47f12", title="Attention Is All You Need",
        authors=["Vaswani, A."], year=2017, venue="NeurIPS",
        doi="10.48550/arXiv.1706.03762", added_date="2026-04-09",
    ), cfg.paths.raw)
    shutil.copy(project["fixtures"] / "sample_paper.pdf", cfg.paths.manual_inbox / "attention.pdf")
    with patch("scholarwiki.ingest.manual.push_paper", return_value="ZOTKEY2"):
        ingest_manual_inbox(cfg, templates_dir=project["templates"])
    reg = load_registry(cfg.paths.raw)
    assert reg.papers["a3f8c2e1d9b47f12"].zotero_key == "ZOTKEY2"
