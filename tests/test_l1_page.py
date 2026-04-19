import pytest
from datetime import datetime, timezone
from pathlib import Path
from scholarwiki.models import PaperEntry
from scholarwiki.l1_page import render_l1_page, l1_page_slug


def _make_entry(**kwargs) -> PaperEntry:
    defaults = dict(
        paper_id="abc123",
        title="Attention Is All You Need",
        authors=["Vaswani, A.", "Shazeer, N."],
        year=2017,
        venue="NeurIPS",
        doi="10.xxxx/xxxxx",
        arxiv_id="1706.03762",
        domain_category="cs_ml",
        domain_tags=["transformers", "attention"],
        source="nexus",
        ingested_at=datetime(2026, 4, 9, tzinfo=timezone.utc),
        extraction_status="pending",
    )
    return PaperEntry(**(defaults | kwargs))


def test_slug_format():
    entry = _make_entry()
    assert l1_page_slug(entry) == "vaswani2017_attention"


def test_slug_no_author_fallback():
    entry = _make_entry(authors=[], year=None)
    slug = l1_page_slug(entry)
    assert slug == "unknown_attention"


def test_render_contains_frontmatter(tmp_path):
    entry = _make_entry()
    content = render_l1_page(entry, templates_dir=Path("templates"))
    assert "paper_id: abc123" in content
    assert "extraction_status: pending" in content
    assert "type: source" in content


def test_render_contains_doi_link(tmp_path):
    entry = _make_entry()
    content = render_l1_page(entry, templates_dir=Path("templates"))
    assert "https://doi.org/10.xxxx/xxxxx" in content


def test_render_pending_summary_placeholder(tmp_path):
    entry = _make_entry()
    content = render_l1_page(entry, templates_dir=Path("templates"))
    assert "_Pending extraction._" in content
