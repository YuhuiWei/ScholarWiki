from __future__ import annotations
import pytest
from pathlib import Path
from scholarwiki.mcp.tools import search_wiki, read_page, read_style_page, read_source_pdf_section
from scholarwiki.models import PaperEntry, Registry


def _setup_wiki(tmp_path: Path) -> Path:
    for subdir in ["sources", "concepts", "patterns", "writing"]:
        (tmp_path / subdir).mkdir()
    return tmp_path


# ---------- search_wiki ----------

def test_search_empty_wiki(tmp_path):
    wiki = _setup_wiki(tmp_path)
    results = search_wiki("batch correction", wiki)
    assert results == []


def test_search_finds_matching_page(tmp_path):
    wiki = _setup_wiki(tmp_path)
    (wiki / "concepts" / "batch_correction.md").write_text(
        "# Batch Correction\nBatch correction removes technical variation."
    )
    results = search_wiki("batch correction", wiki)
    assert len(results) == 1
    assert results[0]["path"] == "concepts/batch_correction.md"
    assert results[0]["score"] > 0


def test_search_no_match_returns_empty(tmp_path):
    wiki = _setup_wiki(tmp_path)
    (wiki / "concepts" / "scvi.md").write_text("# scVI\nVariational autoencoder.")
    results = search_wiki("quantum physics", wiki)
    assert results == []


def test_search_ranks_by_score(tmp_path):
    wiki = _setup_wiki(tmp_path)
    # Page with more term hits should rank higher
    (wiki / "concepts" / "vae.md").write_text("# VAE\nVariational autoencoder method.")
    (wiki / "concepts" / "batch_vae.md").write_text(
        "# Batch VAE\nVariational autoencoder for batch correction. VAE architecture."
    )
    results = search_wiki("variational autoencoder", wiki)
    assert len(results) == 2
    assert results[0]["score"] >= results[1]["score"]


def test_search_skips_index_and_log(tmp_path):
    wiki = _setup_wiki(tmp_path)
    (wiki / "index.md").write_text("Index with keyword batch correction.")
    (wiki / "log.md").write_text("Log with keyword batch correction.")
    (wiki / "concepts" / "scvi.md").write_text("# scVI\nSomething else.")
    results = search_wiki("batch correction", wiki)
    paths = [r["path"] for r in results]
    assert "index.md" not in paths
    assert "log.md" not in paths


def test_search_respects_max_results(tmp_path):
    wiki = _setup_wiki(tmp_path)
    for i in range(10):
        (wiki / "concepts" / f"page_{i}.md").write_text(f"# Page {i}\nkeyword here.")
    results = search_wiki("keyword", wiki, max_results=3)
    assert len(results) <= 3


def test_search_extracts_title_from_frontmatter(tmp_path):
    wiki = _setup_wiki(tmp_path)
    (wiki / "concepts" / "my_concept.md").write_text(
        '---\ntitle: "My Custom Title"\n---\nContent with keyword.\n'
    )
    results = search_wiki("keyword", wiki)
    assert results[0]["title"] == "My Custom Title"


def test_search_excerpt_truncated(tmp_path):
    wiki = _setup_wiki(tmp_path)
    long_content = "keyword " + "word " * 200
    (wiki / "concepts" / "long.md").write_text(long_content)
    results = search_wiki("keyword", wiki)
    assert results[0]["excerpt"].endswith("...")


# ---------- read_page ----------

def test_read_page_exact_match(tmp_path):
    wiki = _setup_wiki(tmp_path)
    (wiki / "concepts" / "scvi.md").write_text("# scVI\nContent here.\n")
    result = read_page(wiki, "concepts", "scvi")
    assert result is not None
    assert "scVI" in result


def test_read_page_not_found_returns_none(tmp_path):
    wiki = _setup_wiki(tmp_path)
    result = read_page(wiki, "concepts", "nonexistent")
    assert result is None


def test_read_page_fuzzy_match(tmp_path):
    wiki = _setup_wiki(tmp_path)
    (wiki / "concepts" / "batch_correction_methods.md").write_text("# BCM\n")
    # "batch correction" should fuzzy-match "batch_correction_methods"
    result = read_page(wiki, "concepts", "batch correction methods")
    assert result is not None
    assert "BCM" in result


def test_read_page_no_fuzzy_below_threshold(tmp_path):
    wiki = _setup_wiki(tmp_path)
    (wiki / "concepts" / "scvi.md").write_text("# scVI\n")
    # "quantum physics" should not fuzzy-match "scvi"
    result = read_page(wiki, "concepts", "quantum physics totally different")
    assert result is None


def test_read_page_missing_subdir_returns_none(tmp_path):
    wiki = _setup_wiki(tmp_path)
    # "roadmap" subdir doesn't exist in our setup
    result = read_page(tmp_path, "nonexistent_subdir", "anything")
    assert result is None


def test_read_page_sources(tmp_path):
    wiki = _setup_wiki(tmp_path)
    (wiki / "sources" / "lopez2018_scvi.md").write_text("# Lopez 2018\n")
    result = read_page(wiki, "sources", "lopez2018_scvi")
    assert result is not None


# ---------- read_style_page ----------

def test_read_style_exact_venue_match(tmp_path):
    wiki = _setup_wiki(tmp_path)
    (wiki / "writing" / "nature_methods_scrna.md").write_text("# Nature Methods Style\n")
    result = read_style_page(wiki, "nature methods", "scrna")
    assert result is not None
    assert "Nature Methods Style" in result


def test_read_style_no_match_returns_none(tmp_path):
    wiki = _setup_wiki(tmp_path)
    (wiki / "writing" / "cell_genomics.md").write_text("# Cell Genomics\n")
    result = read_style_page(wiki, "science", "genetics")
    assert result is None


def test_read_style_empty_wiki(tmp_path):
    """No 'writing' subdir — returns None."""
    result = read_style_page(tmp_path, "nature", "rna-seq")
    assert result is None


def test_read_style_venue_in_content(tmp_path):
    wiki = _setup_wiki(tmp_path)
    (wiki / "writing" / "general_style.md").write_text(
        "# Style Guide\nThis guide covers Cell style conventions.\n"
    )
    result = read_style_page(wiki, "cell", "")
    assert result is not None


def test_read_style_topic_boosts_score(tmp_path):
    wiki = _setup_wiki(tmp_path)
    (wiki / "writing" / "nature_genomics.md").write_text("# Nature Genomics\n")
    (wiki / "writing" / "nature_methods.md").write_text("# Nature Methods\n")
    # "genomics" topic should prefer nature_genomics over nature_methods
    result = read_style_page(wiki, "nature", "genomics")
    assert result is not None
    assert "Nature Genomics" in result


# ---------- read_source_pdf_section ----------

def _make_registry_with_source_page(paper_id: str, title: str, source_page: str) -> Registry:
    entry = PaperEntry(
        paper_id=paper_id,
        title=title,
        source="manual",
        doi=f"10.000/{paper_id}",
        wiki_source_page=source_page,
    )
    return Registry(papers={paper_id: entry})


def test_pdf_no_pdf_found(tmp_path):
    raw_dir = tmp_path / "raw"
    (raw_dir / "papers").mkdir(parents=True)
    reg = _make_registry_with_source_page("abc123", "Test Paper", "sources/abc123.md")
    result = read_source_pdf_section("abc123", "abstract", raw_dir, reg)
    assert result.startswith("Error: No PDF found")


def test_pdf_unknown_slug(tmp_path):
    raw_dir = tmp_path / "raw"
    (raw_dir / "papers").mkdir(parents=True)
    reg = Registry(papers={})
    result = read_source_pdf_section("nonexistent", "abstract", raw_dir, reg)
    assert result.startswith("Error: No PDF found")


def test_pdf_unknown_section(tmp_path):
    """Unknown section name returns descriptive error without crashing."""
    import fitz
    raw_dir = tmp_path / "raw"
    papers_dir = raw_dir / "papers"
    papers_dir.mkdir(parents=True)

    # Create a minimal valid PDF
    pdf_path = papers_dir / "abc123.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Abstract\nThis is the abstract content.")
    doc.save(str(pdf_path))
    doc.close()

    reg = _make_registry_with_source_page("abc123", "Test Paper", "sources/abc123.md")
    result = read_source_pdf_section("abc123", "not_a_section", raw_dir, reg)
    assert result.startswith("Error: Unknown section")


def test_pdf_full_section_returns_text(tmp_path):
    """Section='full' returns all text up to max_chars."""
    import fitz
    raw_dir = tmp_path / "raw"
    papers_dir = raw_dir / "papers"
    papers_dir.mkdir(parents=True)

    pdf_path = papers_dir / "abc123.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Abstract\nThis paper describes methods for sequencing.")
    doc.save(str(pdf_path))
    doc.close()

    reg = _make_registry_with_source_page("abc123", "Test Paper", "sources/abc123.md")
    result = read_source_pdf_section("abc123", "full", raw_dir, reg, max_chars=500)
    assert "Abstract" in result or "sequencing" in result
    assert len(result) <= 500


def test_pdf_page_number_section(tmp_path):
    """Section='1' returns text of first page."""
    import fitz
    raw_dir = tmp_path / "raw"
    papers_dir = raw_dir / "papers"
    papers_dir.mkdir(parents=True)

    pdf_path = papers_dir / "abc123.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Page one content here.")
    doc.save(str(pdf_path))
    doc.close()

    reg = _make_registry_with_source_page("abc123", "Test Paper", "sources/abc123.md")
    result = read_source_pdf_section("abc123", "1", raw_dir, reg)
    assert "Page one content" in result


def test_pdf_out_of_range_page(tmp_path):
    """Page number beyond document length returns error."""
    import fitz
    raw_dir = tmp_path / "raw"
    papers_dir = raw_dir / "papers"
    papers_dir.mkdir(parents=True)

    pdf_path = papers_dir / "abc123.pdf"
    doc = fitz.open()
    doc.new_page()
    doc.save(str(pdf_path))
    doc.close()

    reg = _make_registry_with_source_page("abc123", "Test Paper", "sources/abc123.md")
    result = read_source_pdf_section("abc123", "99", raw_dir, reg)
    assert result.startswith("Error: Page")
