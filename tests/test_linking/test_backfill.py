from pathlib import Path
import pytest
from scholarwiki.linking.backfill import backfill_source_page

_PENDING_PAGE = """\
---
title: "Test Paper"
type: source
---

# Test Paper

## Summary
- **Core contribution:** Something important

## Knowledge Contributions
<!-- Populated by linking pass -->

## Research Relationships
<!-- Populated by linking pass -->

## Experimental Design
<!-- Populated by linking pass -->

## Research Logic
<!-- Populated by linking pass -->

## Writing Notes
<!-- Populated by linking pass -->
"""


def test_backfill_replaces_all_five_sections(tmp_path):
    page = tmp_path / "test_paper.md"
    page.write_text(_PENDING_PAGE)
    backfill_source_page(
        page_path=page,
        knowledge_text="- Contributed to concept pages: [[batch_correction]]\n- Key finding: scVI outperforms Combat.",
        relationships_text="- Extends: [[lopez2018_scvi]] — builds on scVI's VAE.",
        experimental_text="- Design pattern: [[knockout_validation_rescue]]\n- Key choice: 5 benchmark datasets.",
        logic_text="- Logic pattern: systematic_benchmark → ablation\n- Reasoning chain: 4 steps.",
        writing_text="- Style reference: [[nature_methods_integration]]\n- Structural note: Results-first.",
    )
    text = page.read_text()
    assert "<!-- Populated by linking pass -->" not in text
    assert "[[batch_correction]]" in text
    assert "[[lopez2018_scvi]]" in text
    assert "[[knockout_validation_rescue]]" in text
    assert "systematic_benchmark" in text
    assert "[[nature_methods_integration]]" in text


def test_backfill_idempotent_when_already_filled(tmp_path):
    page = tmp_path / "test_paper.md"
    page.write_text(_PENDING_PAGE)
    kwargs = dict(
        page_path=page,
        knowledge_text="- Key finding: X.",
        relationships_text="- Extends: [[y]].",
        experimental_text="- Pattern: [[z]].",
        logic_text="- Logic: A → B.",
        writing_text="- Style: [[w]].",
    )
    backfill_source_page(**kwargs)
    first = page.read_text()
    backfill_source_page(**kwargs)
    second = page.read_text()
    assert first == second


def test_backfill_no_tmp_leftover(tmp_path):
    page = tmp_path / "test_paper.md"
    page.write_text(_PENDING_PAGE)
    backfill_source_page(
        page_path=page,
        knowledge_text="- K.",
        relationships_text="- R.",
        experimental_text="- E.",
        logic_text="- L.",
        writing_text="- W.",
    )
    assert not (tmp_path / "test_paper.md.tmp").exists()


def test_backfill_skips_missing_page(tmp_path):
    # Should not raise if page does not exist
    backfill_source_page(
        page_path=tmp_path / "nonexistent.md",
        knowledge_text="K",
        relationships_text="R",
        experimental_text="E",
        logic_text="L",
        writing_text="W",
    )
