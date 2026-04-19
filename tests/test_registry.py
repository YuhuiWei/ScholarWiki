import pytest
from datetime import datetime, timezone
from scholarwiki.models import PaperEntry, Registry, RegistryStats
from scholarwiki.config import LinkingConfig


def _make_entry(**kwargs) -> PaperEntry:
    defaults = dict(
        paper_id="abc123",
        title="Test Paper",
        source="nexus",
        ingested_at=datetime.now(timezone.utc),
        extraction_status="pending",
    )
    return PaperEntry(**(defaults | kwargs))


def test_paper_entry_defaults():
    entry = _make_entry()
    assert entry.extraction_status == "pending"
    assert entry.authors == []
    assert entry.domain_tags == []
    assert entry.zotero_key is None


def test_registry_stats_computed_correctly():
    papers = {
        "a": _make_entry(paper_id="a", extraction_status="pending"),
        "b": _make_entry(paper_id="b", extraction_status="extracted"),
        "c": _make_entry(paper_id="c", extraction_status="linked"),
    }
    stats = RegistryStats.from_papers(papers)
    assert stats.total == 3
    assert stats.pending_extraction == 1
    assert stats.extracted == 1
    assert stats.linked == 1
    assert stats.queued == 0


def test_registry_paper_ids_are_keys():
    entry = _make_entry(paper_id="xyz")
    registry = Registry(papers={"xyz": entry}, stats=RegistryStats())
    assert "xyz" in registry.papers


import json
from pathlib import Path
from scholarwiki.registry import load_registry, save_registry, add_paper, has_paper


def test_load_returns_empty_when_missing(tmp_path):
    reg = load_registry(tmp_path)
    assert reg.papers == {}
    assert reg.stats.total == 0


def test_save_and_reload(tmp_path):
    reg = load_registry(tmp_path)
    entry = _make_entry(paper_id="p1")
    add_paper(reg, entry)
    save_registry(reg, tmp_path)
    reloaded = load_registry(tmp_path)
    assert "p1" in reloaded.papers
    assert reloaded.stats.total == 1


def test_save_is_atomic(tmp_path):
    """Saving writes to .tmp then replaces — no partial writes visible."""
    reg = load_registry(tmp_path)
    add_paper(reg, _make_entry(paper_id="p1"))
    save_registry(reg, tmp_path)
    assert not (tmp_path / "registry.json.tmp").exists()
    assert (tmp_path / "registry.json").exists()


def test_add_paper_updates_stats(tmp_path):
    reg = load_registry(tmp_path)
    add_paper(reg, _make_entry(paper_id="p1", extraction_status="pending"))
    add_paper(reg, _make_entry(paper_id="p2", extraction_status="extracted"))
    assert reg.stats.total == 2
    assert reg.stats.pending_extraction == 1
    assert reg.stats.extracted == 1


def test_has_paper(tmp_path):
    reg = load_registry(tmp_path)
    add_paper(reg, _make_entry(paper_id="known"))
    assert has_paper(reg, "known")
    assert not has_paper(reg, "unknown")


def test_registry_stats_zotero_unsynced():
    papers = {
        "a": _make_entry(paper_id="a", zotero_key=None),
        "b": _make_entry(paper_id="b", zotero_key="ABCD1234"),
        "c": _make_entry(paper_id="c", zotero_key=None),
    }
    stats = RegistryStats.from_papers(papers)
    assert stats.zotero_unsynced == 2


def test_ingest_result_has_zotero_failed():
    from scholarwiki.models import IngestResult
    r = IngestResult(zotero_failed=3)
    assert r.zotero_failed == 3


def test_paper_entry_has_linking_batch_ids():
    p = PaperEntry(paper_id="abc", title="T", source="manual")
    assert p.linking_batch_ids == {}

def test_linking_config_has_synthesis_and_style_models():
    assert LinkingConfig().synthesis_model == "gpt-5"
    assert LinkingConfig().style_model == "gpt-4.1"
