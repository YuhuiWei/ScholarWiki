from __future__ import annotations
import pytest
from scholarwiki.models import PaperEntry, Registry
from scholarwiki.pipeline import PipelineStep, determine_next_step, parse_timeout


def _make_registry(*papers: PaperEntry) -> Registry:
    reg = Registry()
    for p in papers:
        reg.papers[p.paper_id] = p
    return reg


def _paper(paper_id: str, status: str, **kwargs) -> PaperEntry:
    return PaperEntry(paper_id=paper_id, title="Test", source="nexus",
                      extraction_status=status, **kwargs)


# ---------- determine_next_step ----------

def test_empty_registry_returns_done():
    reg = _make_registry()
    state = determine_next_step(reg)
    assert state.current_step == PipelineStep.DONE


def test_pending_paper_returns_submit_extraction():
    reg = _make_registry(_paper("a", "pending"))
    state = determine_next_step(reg)
    assert state.current_step == PipelineStep.SUBMIT_EXTRACTION
    assert state.papers_pending == 1


def test_queued_paper_treated_as_pending():
    reg = _make_registry(_paper("a", "queued"))
    state = determine_next_step(reg)
    assert state.current_step == PipelineStep.SUBMIT_EXTRACTION
    assert state.papers_pending == 1


def test_pending_and_queued_combined():
    reg = _make_registry(_paper("a", "pending"), _paper("b", "queued"))
    state = determine_next_step(reg)
    assert state.current_step == PipelineStep.SUBMIT_EXTRACTION
    assert state.papers_pending == 2


def test_submitted_paper_returns_poll_extraction():
    reg = _make_registry(
        _paper("a", "submitted", extraction_batch_id="batch_1")
    )
    state = determine_next_step(reg)
    assert state.current_step == PipelineStep.POLL_EXTRACTION
    assert state.extraction_batch_id == "batch_1"


def test_extracted_no_linking_returns_submit_linking():
    reg = _make_registry(_paper("a", "extracted"))
    state = determine_next_step(reg)
    assert state.current_step == PipelineStep.SUBMIT_LINKING


def test_extracted_with_linking_batch_returns_poll_linking():
    reg = _make_registry(
        _paper("a", "extracted", linking_batch_ids={"gpt5": "b1", "gpt41": "b2"})
    )
    state = determine_next_step(reg)
    assert state.current_step == PipelineStep.POLL_LINKING
    assert state.linking_batch_ids == {"gpt5": "b1", "gpt41": "b2"}


def test_all_linked_returns_done():
    reg = _make_registry(_paper("a", "linked"))
    state = determine_next_step(reg)
    assert state.current_step == PipelineStep.DONE
    assert state.papers_linked == 1


def test_mixed_linked_and_pending_returns_submit_extraction():
    """Pending papers take priority over linked ones."""
    reg = _make_registry(
        _paper("a", "linked"),
        _paper("b", "pending"),
    )
    state = determine_next_step(reg)
    assert state.current_step == PipelineStep.SUBMIT_EXTRACTION


def test_state_counts_are_correct():
    reg = _make_registry(
        _paper("a", "pending"),
        _paper("b", "submitted", extraction_batch_id="batch_1"),
        _paper("c", "extracted"),
        _paper("d", "linked"),
    )
    # pending takes priority; counts reflect all papers
    state = determine_next_step(reg)
    assert state.current_step == PipelineStep.SUBMIT_EXTRACTION
    assert state.papers_pending == 1
    assert state.papers_submitted == 1
    assert state.papers_extracted == 1
    assert state.papers_linked == 1


# ---------- parse_timeout ----------

def test_parse_timeout_hours():
    assert parse_timeout("6h") == 21600


def test_parse_timeout_minutes():
    assert parse_timeout("30m") == 1800


def test_parse_timeout_seconds_suffix():
    assert parse_timeout("90s") == 90


def test_parse_timeout_bare_integer():
    assert parse_timeout("3600") == 3600


def test_parse_timeout_fractional():
    assert parse_timeout("1.5h") == 5400
