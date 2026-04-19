from __future__ import annotations
from pathlib import Path
import pytest
from scholarwiki.extraction.l1_aggregator import aggregate_l1_profile, update_source_page_summary, L1Profile
from scholarwiki.models import PaperEntry


def _entry(**kwargs) -> PaperEntry:
    defaults = dict(paper_id="abc123", title="Test Paper", source="nexus",
                    domain_category="cs_ml", domain_tags=["deep learning", "NLP"])
    return PaperEntry(**{**defaults, **kwargs})


def _full_modules() -> dict:
    return {
        "knowledge": {
            "knowledge_items": [
                {
                    "claim": "Our method outperforms all baselines on 5 benchmarks",
                    "evidence_type": "experimental",
                    "confidence": "high",
                    "related_concepts": ["transfer learning", "fine-tuning", "BERT"],
                }
            ]
        },
        "roadmap": {
            "relationships": [
                {"relationship_type": "extends", "target_entity": "BERT (Devlin et al., 2019)", "significance": "high"},
                {"relationship_type": "compared_against", "target_entity": "GPT-2", "significance": "medium"},
            ]
        },
        "experiment": {
            "experimental_pipeline": [
                {"step": 1, "action": "Pre-training on Wikipedia", "tools": ["PyTorch", "HuggingFace"]}
            ]
        },
        "writing": {},
        "logic": {},
    }


def test_aggregate_l1_core_contribution_from_knowledge():
    profile = aggregate_l1_profile(_full_modules(), _entry())
    assert "outperforms all baselines" in profile.core_contribution


def test_aggregate_l1_domain_from_entry():
    profile = aggregate_l1_profile(_full_modules(), _entry())
    assert "cs_ml" in profile.domain
    assert "deep learning" in profile.domain


def test_aggregate_l1_key_concepts_from_knowledge():
    profile = aggregate_l1_profile(_full_modules(), _entry())
    assert "transfer learning" in profile.key_concepts


def test_aggregate_l1_methods_used_from_experiment():
    profile = aggregate_l1_profile(_full_modules(), _entry())
    assert "Pre-training" in profile.methods_used


def test_aggregate_l1_connects_to_high_significance_only():
    profile = aggregate_l1_profile(_full_modules(), _entry())
    assert "BERT (Devlin et al., 2019)" in profile.connects_to
    # GPT-2 is medium significance — not included
    assert "GPT-2" not in profile.connects_to


def test_aggregate_l1_fallback_to_abstract():
    modules = {"knowledge": {"knowledge_items": []}, "roadmap": {}, "experiment": {}, "writing": {}, "logic": {}}
    entry = _entry(abstract="This paper presents a novel approach.")
    profile = aggregate_l1_profile(modules, entry)
    assert "novel approach" in profile.core_contribution


def test_aggregate_l1_fallback_to_title():
    modules = {"knowledge": {"knowledge_items": []}, "roadmap": {}, "experiment": {}, "writing": {}, "logic": {}}
    entry = _entry(abstract=None)
    profile = aggregate_l1_profile(modules, entry)
    assert profile.core_contribution == "Test Paper"


def test_update_source_page_summary(tmp_path):
    page = tmp_path / "test_source.md"
    page.write_text(
        "---\ntitle: Test\n---\n\n# Test\n\n"
        "## Summary\n<!-- Backfilled after LLM extraction -->\n_Pending extraction._\n\n"
        "## Knowledge Contributions\n<!-- Populated by linking pass -->\n"
    )
    profile = L1Profile(
        core_contribution="Method X outperforms baselines",
        domain="cs_ml, deep learning",
        key_concepts=["transfer learning", "BERT"],
        methods_used="Pre-training on Wikipedia + fine-tuning",
        connects_to=["BERT (Devlin et al., 2019)"],
    )
    update_source_page_summary(page, profile)
    updated = page.read_text()
    assert "Method X outperforms baselines" in updated
    assert "_Pending extraction._" not in updated
    assert "## Knowledge Contributions" in updated  # other sections intact


def test_update_source_page_summary_idempotent(tmp_path):
    page = tmp_path / "test_source.md"
    page.write_text(
        "---\ntitle: Test\n---\n\n# Test\n\n"
        "## Summary\n<!-- Backfilled after LLM extraction -->\n_Pending extraction._\n\n"
        "## Knowledge Contributions\n"
    )
    profile = L1Profile(
        core_contribution="Method X",
        domain="cs_ml",
        key_concepts=["deep learning"],
        methods_used="Training",
        connects_to=[],
    )
    update_source_page_summary(page, profile)
    first_pass = page.read_text()
    update_source_page_summary(page, profile)  # call again
    second_pass = page.read_text()
    assert first_pass == second_pass


def test_update_source_page_nonexistent_does_nothing(tmp_path):
    missing = tmp_path / "missing.md"
    profile = L1Profile(core_contribution="X", domain="Y", key_concepts=[], methods_used="Z", connects_to=[])
    update_source_page_summary(missing, profile)  # should not raise
    assert not missing.exists()
