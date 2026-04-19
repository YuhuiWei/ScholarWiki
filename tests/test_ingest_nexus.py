import shutil
import pytest
from pathlib import Path
from scholarwiki.config import Config, PathsConfig
from scholarwiki.registry import load_registry
from scholarwiki.ingest.nexus import ingest_nexus_inbox


@pytest.fixture
def project(tmp_path, sample_nexus_json, fixtures_dir):
    # Set up a fake project tree
    nexus_inbox = tmp_path / "nexus_inbox"
    nexus_inbox.mkdir()
    raw = tmp_path / "raw"
    raw.mkdir()
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    templates = tmp_path / "templates"
    # Copy templates from project root for rendering
    shutil.copytree(Path("templates"), templates)
    # Put the sample NEXUS JSON in the inbox
    result_json = nexus_inbox / "2026-04-09_attention_top10.json"
    shutil.copy(sample_nexus_json, result_json)
    # Create a fake PDF file as the "downloaded" paper
    fake_pdf = tmp_path / "rank_01_attention_is_all_you_need.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4 fake")
    # Patch the download_file_path to point to our fake PDF
    import json
    data = json.loads(result_json.read_text())
    data["papers"][0]["download_file_path"] = str(fake_pdf)
    result_json.write_text(json.dumps(data))
    cfg = Config(paths=PathsConfig(
        nexus_inbox=nexus_inbox,
        manual_inbox=tmp_path / "manual_inbox",
        raw=raw,
        wiki=wiki,
    ))
    return {"tmp": tmp_path, "cfg": cfg, "templates": templates}


def test_ingest_nexus_moves_pdf(project):
    cfg = project["cfg"]
    result = ingest_nexus_inbox(cfg, templates_dir=project["templates"])
    # PDF should be moved to raw/papers/
    papers_dir = cfg.paths.raw / "papers"
    pdfs = list(papers_dir.glob("*.pdf"))
    assert len(pdfs) == 1, f"Expected 1 PDF in raw/papers/, got: {pdfs}"


def test_ingest_nexus_registers_paper(project):
    cfg = project["cfg"]
    ingest_nexus_inbox(cfg, templates_dir=project["templates"])
    reg = load_registry(cfg.paths.raw)
    assert "a3f8c2e1d9b47f12" in reg.papers
    assert reg.papers["a3f8c2e1d9b47f12"].extraction_status == "pending"


def test_ingest_nexus_skips_duplicate(project):
    cfg = project["cfg"]
    result1 = ingest_nexus_inbox(cfg, templates_dir=project["templates"])
    result2 = ingest_nexus_inbox(cfg, templates_dir=project["templates"])
    assert result1.new_papers == 1
    assert result2.new_papers == 0
    assert result2.skipped_duplicates == 1


def test_ingest_nexus_failed_paper_goes_to_manual_md(project):
    cfg = project["cfg"]
    ingest_nexus_inbox(cfg, templates_dir=project["templates"])
    manual_md = cfg.paths.raw / "manual.md"
    assert manual_md.exists()
    content = manual_md.read_text()
    assert "b4g9d3f2e0c58a23" in content


def test_ingest_nexus_creates_l1_page(project):
    cfg = project["cfg"]
    ingest_nexus_inbox(cfg, templates_dir=project["templates"])
    sources = list((cfg.paths.wiki / "sources").glob("*.md"))
    assert len(sources) == 1
    content = sources[0].read_text()
    assert "paper_id: a3f8c2e1d9b47f12" in content


def test_ingest_nexus_sets_zotero_key_when_push_succeeds(project):
    from unittest.mock import patch
    cfg = project["cfg"]
    cfg.zotero.library_id = "12345"
    cfg.zotero.api_key = "fakekey"
    with patch("scholarwiki.ingest.nexus.push_paper", return_value="ZOTKEY1"):
        ingest_nexus_inbox(cfg, templates_dir=project["templates"])
    reg = load_registry(cfg.paths.raw)
    assert reg.papers["a3f8c2e1d9b47f12"].zotero_key == "ZOTKEY1"


def test_ingest_nexus_zotero_failed_counted_when_push_fails(project):
    from unittest.mock import patch
    cfg = project["cfg"]
    cfg.zotero.library_id = "12345"
    cfg.zotero.api_key = "fakekey"
    with patch("scholarwiki.ingest.nexus.push_paper", return_value=None):
        result = ingest_nexus_inbox(cfg, templates_dir=project["templates"])
    assert result.zotero_failed == 1
