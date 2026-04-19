from pathlib import Path
import pytest
from scholarwiki.linking.concept_match import (
    slug_from_title, list_concept_index, match_concept
)


def test_slug_from_title_basic():
    assert slug_from_title("Batch Correction in scRNA-seq") == "batch_correction_in_scrna_seq"


def test_slug_from_title_special_chars():
    assert slug_from_title("VAE (Variational Autoencoder)") == "vae_variational_autoencoder"


def test_slug_from_title_leading_trailing():
    assert slug_from_title("  hello world  ") == "hello_world"


def test_list_concept_index_empty(tmp_path):
    assert list_concept_index(tmp_path / "concepts") == []


def test_list_concept_index_reads_frontmatter_title(tmp_path):
    concepts = tmp_path / "concepts"
    concepts.mkdir()
    (concepts / "batch_correction.md").write_text(
        '---\ntitle: "Batch correction in scRNA-seq"\ntype: concept\n---\n\n# Body\n'
    )
    index = list_concept_index(concepts)
    assert index == [("Batch correction in scRNA-seq", "batch_correction")]


def test_list_concept_index_fallback_to_stem(tmp_path):
    concepts = tmp_path / "concepts"
    concepts.mkdir()
    (concepts / "my_concept.md").write_text("No frontmatter here")
    index = list_concept_index(concepts)
    assert index == [("my concept", "my_concept")]


def test_match_concept_exact(tmp_path):
    index = [("Batch correction in scRNA-seq", "batch_correction")]
    result = match_concept("Batch correction in scRNA-seq", index)
    assert result == ("Batch correction in scRNA-seq", "batch_correction")


def test_match_concept_fuzzy_above_threshold():
    index = [("Batch correction in scRNA-seq", "batch_correction")]
    result = match_concept("scRNA-seq batch correction", index)
    assert result is not None
    assert result[1] == "batch_correction"


def test_match_concept_below_threshold():
    index = [("Transformer architecture", "transformer")]
    result = match_concept("variational autoencoder", index)
    assert result is None


def test_match_concept_empty_index():
    result = match_concept("anything", [])
    assert result is None


def test_match_concept_custom_threshold():
    index = [("Batch correction", "batch_correction")]
    result = match_concept("Batch correction method", index, threshold=100)
    assert result is None
