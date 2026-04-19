# tests/test_zotero.py
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from scholarwiki.models import PaperEntry
from scholarwiki.zotero import _detect_item_type, _build_item


def _entry(**kwargs) -> PaperEntry:
    defaults = dict(
        paper_id="abc123",
        title="Test Paper",
        source="nexus",
        ingested_at=datetime.now(timezone.utc),
        extraction_status="pending",
    )
    return PaperEntry(**(defaults | kwargs))


# --- _detect_item_type ---

def test_detect_preprint_arxiv_no_doi():
    entry = _entry(arxiv_id="1706.03762", doi=None)
    assert _detect_item_type(entry) == "preprint"


def test_detect_preprint_arxiv_doi():
    entry = _entry(arxiv_id="1706.03762", doi="10.48550/arXiv.1706.03762")
    assert _detect_item_type(entry) == "preprint"


def test_detect_preprint_non_arxiv_doi_is_journal():
    """Real DOI (non-arxiv) with arxiv_id → journal because DOI overrides."""
    entry = _entry(arxiv_id="1706.03762", doi="10.1038/nature12345")
    assert _detect_item_type(entry) == "journalArticle"


def test_detect_conference_by_venue():
    entry = _entry(venue="NeurIPS 2017", arxiv_id=None, doi="10.1234/x")
    assert _detect_item_type(entry) == "conferencePaper"


def test_detect_conference_by_publication_type():
    entry = _entry(publication_type="Conference", venue="Some Conf", arxiv_id=None, doi="10.1234/x")
    assert _detect_item_type(entry) == "conferencePaper"


def test_detect_journal_default():
    entry = _entry(venue="Nature", arxiv_id=None, doi="10.1038/nature12345")
    assert _detect_item_type(entry) == "journalArticle"


def test_detect_journal_no_venue():
    entry = _entry(venue=None, arxiv_id=None, doi="10.1038/nature12345")
    assert _detect_item_type(entry) == "journalArticle"


# --- _build_item ---

def test_build_journal_item():
    entry = _entry(
        title="Some Journal Paper",
        authors=["Smith, J.", "Doe, A."],
        year=2023,
        venue="Nature",
        doi="10.1038/nature12345",
        abstract="Great paper.",
        domain_tags=["ml", "bio"],
        arxiv_id=None,
    )
    item = _build_item(entry, collection_key="COLL1")
    assert item["itemType"] == "journalArticle"
    assert item["title"] == "Some Journal Paper"
    assert item["publicationTitle"] == "Nature"
    assert item["DOI"] == "10.1038/nature12345"
    assert item["abstractNote"] == "Great paper."
    assert item["date"] == "2023"
    assert {"tag": "ml"} in item["tags"]
    assert item["collections"] == ["COLL1"]
    assert len(item["creators"]) == 2
    assert item["creators"][0] == {"creatorType": "author", "name": "Smith, J."}


def test_build_conference_item():
    entry = _entry(
        title="A Conference Paper",
        venue="NeurIPS 2017",
        doi="10.5555/x",
        arxiv_id=None,
    )
    item = _build_item(entry, collection_key="COLL2")
    assert item["itemType"] == "conferencePaper"
    assert item["proceedingsTitle"] == "NeurIPS 2017"
    assert "publicationTitle" not in item


def test_build_preprint_item():
    entry = _entry(
        title="Attention Is All You Need",
        arxiv_id="1706.03762",
        doi=None,
    )
    item = _build_item(entry, collection_key="COLL3")
    assert item["itemType"] == "preprint"
    assert item["repository"] == "arXiv"
    assert item["archiveID"] == "1706.03762"
    assert "publicationTitle" not in item


def test_build_item_collection_key_none():
    """collection_key=None means no collections field (or empty list)."""
    entry = _entry(arxiv_id=None, doi="10.1/x")
    item = _build_item(entry, collection_key=None)
    assert item.get("collections") is None or item.get("collections") == []


# --- _get_or_create_collection ---

def test_get_collection_reuses_existing():
    zot = MagicMock()
    zot.collections.return_value = [
        {"key": "EXIST1", "data": {"name": "cs_ml"}},
        {"key": "EXIST2", "data": {"name": "biology"}},
    ]
    from scholarwiki.zotero import _get_or_create_collection
    key = _get_or_create_collection(zot, "cs_ml")
    assert key == "EXIST1"
    zot.create_collections.assert_not_called()


def test_get_collection_creates_when_absent():
    zot = MagicMock()
    zot.collections.return_value = []
    zot.create_collections.return_value = {"successful": {"0": {"key": "NEWKEY"}}}
    from scholarwiki.zotero import _get_or_create_collection
    key = _get_or_create_collection(zot, "neuroscience")
    assert key == "NEWKEY"
    zot.create_collections.assert_called_once_with([{"name": "neuroscience"}])


# --- push_paper ---

def test_push_paper_returns_key_on_success():
    from scholarwiki.config import Config
    from scholarwiki.zotero import push_paper
    cfg = Config()
    cfg.zotero.library_id = "12345"
    cfg.zotero.library_type = "user"
    cfg.zotero.api_key = "fakekey"

    entry = _entry(
        paper_id="abc",
        title="Test",
        domain_category="cs_ml",
        arxiv_id=None,
        doi="10.1/x",
    )

    with patch("scholarwiki.zotero.zotero") as mock_zotero_module:
        mock_zot = MagicMock()
        mock_zotero_module.Zotero.return_value = mock_zot
        mock_zot.collections.return_value = [{"key": "COLL1", "data": {"name": "cs_ml"}}]
        mock_zot.create_items.return_value = {"successful": {"0": {"key": "ITEMKEY1"}}, "failed": {}}
        result = push_paper(entry, cfg)

    assert result == "ITEMKEY1"


def test_push_paper_returns_none_on_exception():
    from scholarwiki.config import Config
    from scholarwiki.zotero import push_paper
    cfg = Config()
    cfg.zotero.library_id = "12345"
    cfg.zotero.api_key = "fakekey"
    entry = _entry(arxiv_id=None, doi="10.1/x")

    with patch("scholarwiki.zotero.zotero") as mock_zotero_module:
        mock_zot = MagicMock()
        mock_zotero_module.Zotero.return_value = mock_zot
        mock_zot.collections.side_effect = Exception("connection timeout")
        result = push_paper(entry, cfg)

    assert result is None


def test_push_paper_returns_none_when_no_api_key():
    from scholarwiki.config import Config
    from scholarwiki.zotero import push_paper
    cfg = Config()  # api_key defaults to ""
    entry = _entry(arxiv_id=None, doi="10.1/x")
    result = push_paper(entry, cfg)
    assert result is None


def test_push_paper_returns_none_when_no_library_id():
    from scholarwiki.config import Config
    from scholarwiki.zotero import push_paper
    cfg = Config()
    cfg.zotero.api_key = "somekey"
    # library_id defaults to ""
    entry = _entry(arxiv_id=None, doi="10.1/x")
    result = push_paper(entry, cfg)
    assert result is None


# --- update_l1_zotero_key ---

def test_update_l1_zotero_key_replaces_empty(tmp_path):
    from scholarwiki.l1_page import update_l1_zotero_key
    page = tmp_path / "paper.md"
    page.write_text('---\ntitle: Test\nzotero_key: ""\nextraction_status: pending\n---\n\nBody.', encoding="utf-8")
    update_l1_zotero_key(page, "ABCD1234")
    assert 'zotero_key: "ABCD1234"' in page.read_text()


def test_update_l1_zotero_key_no_op_when_key_missing_from_page(tmp_path):
    """If frontmatter has no zotero_key line, file is left unchanged."""
    from scholarwiki.l1_page import update_l1_zotero_key
    page = tmp_path / "paper.md"
    original = '---\ntitle: Test\n---\n\nBody.'
    page.write_text(original, encoding="utf-8")
    update_l1_zotero_key(page, "ABCD1234")
    assert page.read_text() == original


# --- sync_pending ---

def test_sync_pending_pushes_unsynced(tmp_path):
    from scholarwiki.config import Config, PathsConfig
    from scholarwiki.models import PaperEntry
    from scholarwiki.registry import load_registry, save_registry, add_paper
    from scholarwiki.zotero import sync_pending
    from datetime import datetime, timezone

    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    wiki_dir = tmp_path / "wiki"
    (wiki_dir / "sources").mkdir(parents=True)

    cfg = Config(paths=PathsConfig(raw=raw_dir, wiki=wiki_dir))
    cfg.zotero.library_id = "12345"
    cfg.zotero.api_key = "fakekey"

    reg = load_registry(raw_dir)
    e1 = PaperEntry(paper_id="p1", title="Paper One", source="nexus",
                    ingested_at=datetime.now(timezone.utc), zotero_key=None)
    e2 = PaperEntry(paper_id="p2", title="Paper Two", source="nexus",
                    ingested_at=datetime.now(timezone.utc), zotero_key="ALREADY")
    add_paper(reg, e1)
    add_paper(reg, e2)

    # Create a stub L1 page for p1
    stub_page = wiki_dir / "sources" / "unknown_paper.md"
    stub_page.write_text('---\nzotero_key: ""\nextraction_status: pending\n---\n', encoding="utf-8")
    reg.papers["p1"].wiki_source_page = str(stub_page)
    save_registry(reg, raw_dir)

    with patch("scholarwiki.zotero.zotero") as mock_zotero_module:
        mock_zot = MagicMock()
        mock_zotero_module.Zotero.return_value = mock_zot
        mock_zot.collections.return_value = []
        mock_zot.create_collections.return_value = {"successful": {"0": {"key": "COLL1"}}}
        mock_zot.create_items.return_value = {"successful": {"0": {"key": "NEWKEY"}}, "failed": {}}
        result = sync_pending(reg, cfg, raw_dir)

    assert result.synced == 1
    assert result.failed == 0
    reloaded = load_registry(raw_dir)
    assert reloaded.papers["p1"].zotero_key == "NEWKEY"
    assert reloaded.papers["p2"].zotero_key == "ALREADY"


def test_sync_pending_counts_failures(tmp_path):
    from scholarwiki.config import Config, PathsConfig
    from scholarwiki.models import PaperEntry
    from scholarwiki.registry import load_registry, save_registry, add_paper
    from scholarwiki.zotero import sync_pending
    from datetime import datetime, timezone

    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()

    cfg = Config(paths=PathsConfig(raw=raw_dir, wiki=wiki_dir))
    cfg.zotero.library_id = "12345"
    cfg.zotero.api_key = "fakekey"

    reg = load_registry(raw_dir)
    e = PaperEntry(paper_id="p1", title="Paper", source="nexus",
                   ingested_at=datetime.now(timezone.utc), zotero_key=None)
    add_paper(reg, e)
    save_registry(reg, raw_dir)

    with patch("scholarwiki.zotero.zotero") as mock_zotero_module:
        mock_zot = MagicMock()
        mock_zotero_module.Zotero.return_value = mock_zot
        mock_zot.collections.side_effect = Exception("timeout")
        result = sync_pending(reg, cfg, raw_dir)

    assert result.synced == 0
    assert result.failed == 1
    assert len(result.errors) == 1
