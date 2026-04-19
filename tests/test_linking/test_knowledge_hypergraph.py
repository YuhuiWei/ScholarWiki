from pathlib import Path
import pytest
from scholarwiki.linking.knowledge_hypergraph import write_concept_page


def test_write_concept_page_creates_file(tmp_path):
    wiki = tmp_path / "wiki"
    (wiki / "concepts").mkdir(parents=True)
    write_concept_page(wiki, "batch_correction", "# Batch Correction\n\nSome content.\n")
    page = wiki / "concepts" / "batch_correction.md"
    assert page.exists()
    assert "# Batch Correction" in page.read_text()


def test_write_concept_page_overwrites_existing(tmp_path):
    wiki = tmp_path / "wiki"
    (wiki / "concepts").mkdir(parents=True)
    page = wiki / "concepts" / "my_concept.md"
    page.write_text("OLD CONTENT")
    write_concept_page(wiki, "my_concept", "NEW CONTENT")
    assert page.read_text() == "NEW CONTENT"


def test_write_concept_page_atomic_no_tmp_leftover(tmp_path):
    wiki = tmp_path / "wiki"
    (wiki / "concepts").mkdir(parents=True)
    write_concept_page(wiki, "my_concept", "content")
    assert not (wiki / "concepts" / "my_concept.md.tmp").exists()


def test_write_concept_page_creates_concepts_dir(tmp_path):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    # concepts/ does not exist yet
    write_concept_page(wiki, "new_concept", "content")
    assert (wiki / "concepts" / "new_concept.md").exists()
