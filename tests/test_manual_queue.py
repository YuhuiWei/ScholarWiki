import pytest
from pathlib import Path
from scholarwiki.manual_queue import (
    load_manual_queue,
    append_pending,
    mark_downloaded,
    ManualEntry,
)


def _entry(paper_id: str = "abc", title: str = "Test Paper") -> ManualEntry:
    return ManualEntry(
        paper_id=paper_id,
        title=title,
        authors=["Smith, J."],
        year=2024,
        venue="Nature",
        doi="10.x/y",
        added_date="2026-04-09",
    )


def test_load_empty_file(tmp_path):
    queue = load_manual_queue(tmp_path)
    assert queue.pending == []
    assert queue.downloaded == []


def test_append_pending(tmp_path):
    queue = load_manual_queue(tmp_path)
    append_pending(queue, _entry("p1"), tmp_path)
    reloaded = load_manual_queue(tmp_path)
    assert len(reloaded.pending) == 1
    assert reloaded.pending[0].paper_id == "p1"


def test_mark_downloaded(tmp_path):
    queue = load_manual_queue(tmp_path)
    append_pending(queue, _entry("p1"), tmp_path)
    mark_downloaded(queue, "p1", "2026-04-10", tmp_path)
    reloaded = load_manual_queue(tmp_path)
    assert len(reloaded.pending) == 0
    assert len(reloaded.downloaded) == 1
    assert reloaded.downloaded[0].paper_id == "p1"


def test_append_deduplicates(tmp_path):
    queue = load_manual_queue(tmp_path)
    append_pending(queue, _entry("dup"), tmp_path)
    append_pending(queue, _entry("dup"), tmp_path)
    reloaded = load_manual_queue(tmp_path)
    assert len(reloaded.pending) == 1
