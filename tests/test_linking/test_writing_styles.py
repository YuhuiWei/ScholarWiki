from __future__ import annotations
from pathlib import Path
import pytest
from scholarwiki.linking.writing_styles import write_style_page, cluster_writing_styles


def test_write_style_page_creates_file(tmp_path):
    wiki = tmp_path / "wiki"
    (wiki / "writing").mkdir(parents=True)
    write_style_page(wiki, "nature_scrna_seq", "# Style Guide\n\ncontent\n")
    page = wiki / "writing" / "nature_scrna_seq.md"
    assert page.exists()
    assert "# Style Guide" in page.read_text()


def test_write_style_page_overwrites(tmp_path):
    wiki = tmp_path / "wiki"
    (wiki / "writing").mkdir(parents=True)
    page = wiki / "writing" / "my_style.md"
    page.write_text("OLD")
    write_style_page(wiki, "my_style", "NEW")
    assert page.read_text() == "NEW"


def test_write_style_page_atomic(tmp_path):
    wiki = tmp_path / "wiki"
    (wiki / "writing").mkdir(parents=True)
    write_style_page(wiki, "my_style", "content")
    assert not (wiki / "writing" / "my_style.md.tmp").exists()


def test_cluster_writing_styles_by_venue(tmp_path):
    """Papers with same venue are grouped together."""
    papers = [
        {"paper_id": "p1", "venue": "Nature Methods", "topic_area": "scRNA-seq",
         "topic_tags": ["scrna-seq", "integration"]},
        {"paper_id": "p2", "venue": "Nature Methods", "topic_area": "scRNA-seq",
         "topic_tags": ["scrna-seq", "deep-learning"]},
        {"paper_id": "p3", "venue": "Cell", "topic_area": "cancer",
         "topic_tags": ["cancer", "immunology"]},
    ]
    result = cluster_writing_styles(papers)
    # p1 and p2 should be in the same slug (same venue)
    # p3 should be in a different slug
    slugs_with_p1 = [slug for slug, info in result.items() if "p1" in info["paper_ids"]]
    slugs_with_p3 = [slug for slug, info in result.items() if "p3" in info["paper_ids"]]
    assert len(slugs_with_p1) == 1
    assert len(slugs_with_p3) == 1
    assert slugs_with_p1[0] != slugs_with_p3[0]


def test_cluster_writing_styles_jaccard_splits_dissimilar(tmp_path):
    """Papers with same venue but no tag overlap (Jaccard=0) go to different sub-clusters."""
    papers = [
        {"paper_id": "p1", "venue": "Nature", "topic_area": "genomics",
         "topic_tags": ["genomics", "sequencing", "epigenetics"]},
        {"paper_id": "p2", "venue": "Nature", "topic_area": "neuroscience",
         "topic_tags": ["neuroscience", "cortex", "fMRI"]},
        {"paper_id": "p3", "venue": "Nature", "topic_area": "neuroscience",
         "topic_tags": ["neuroscience", "cortex", "connectivity"]},
    ]
    result = cluster_writing_styles(papers)
    slug_p1 = next(s for s, info in result.items() if "p1" in info["paper_ids"])
    slug_p2 = next(s for s, info in result.items() if "p2" in info["paper_ids"])
    # p1 (genomics) should be separate from p2/p3 (neuroscience)
    assert slug_p1 != slug_p2
    # p2 and p3 share enough tags to be in the same cluster
    slug_p3 = next(s for s, info in result.items() if "p3" in info["paper_ids"])
    assert slug_p2 == slug_p3


def test_cluster_writing_styles_empty_input():
    result = cluster_writing_styles([])
    assert result == {}
