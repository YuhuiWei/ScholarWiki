from __future__ import annotations
import re
from pathlib import Path
from pydantic import BaseModel


class ManualEntry(BaseModel):
    paper_id: str
    title: str
    authors: list[str]
    year: int | None
    venue: str | None
    doi: str | None
    added_date: str
    downloaded_date: str | None = None


class ManualQueue(BaseModel):
    pending: list[ManualEntry] = []
    downloaded: list[ManualEntry] = []


_PAPER_ID_RE = re.compile(r"<!--\s*paper_id:\s*(\S+)\s*-->")
_SECTION_RE = re.compile(r"^##\s+(Pending|Downloaded)", re.MULTILINE)
_ENTRY_RE = re.compile(
    r"<!--\s*paper_id:\s*(\S+)\s*-->\s*\n\*\*\[([^\]]+)\]\([^)]*\)\s*\(([^)]*)\)\*\*\s*—\s*([^\n]*)\n([^\n]*)\s*—\s*(?:added|downloaded)\s+(\S+)",
    re.MULTILINE,
)

_MANUAL_MD = "manual.md"


def _entry_to_md(entry: ManualEntry, section: str) -> str:
    authors = ", ".join(entry.authors[:3])
    doi_url = f"https://doi.org/{entry.doi}" if entry.doi else "#"
    date = entry.downloaded_date if section == "Downloaded" else entry.added_date
    date_label = "downloaded" if section == "Downloaded" else "added"
    return (
        f"<!-- paper_id: {entry.paper_id} -->\n"
        f"**[{entry.title}]({doi_url}) ({entry.year or '?'})** — {authors}\n"
        f"{entry.venue or 'Unknown venue'} — {date_label} {date}\n\n"
    )


def _save(queue: ManualQueue, raw_dir: Path) -> None:
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / _MANUAL_MD
    lines = ["# Manual Download Queue\n\n## Pending\n\n"]
    for e in queue.pending:
        lines.append(_entry_to_md(e, "Pending"))
    lines.append("## Downloaded\n\n")
    for e in queue.downloaded:
        lines.append(_entry_to_md(e, "Downloaded"))
    tmp = path.with_suffix(".md.tmp")
    tmp.write_text("".join(lines), encoding="utf-8")
    tmp.replace(path)


def load_manual_queue(raw_dir: Path) -> ManualQueue:
    path = raw_dir / _MANUAL_MD
    if not path.exists():
        return ManualQueue()
    text = path.read_text(encoding="utf-8")
    sections = _SECTION_RE.split(text)
    # sections[0] = header, then alternating section_name, section_body
    pending: list[ManualEntry] = []
    downloaded: list[ManualEntry] = []
    pairs = list(zip(sections[1::2], sections[2::2]))
    for section_name, body in pairs:
        target = pending if section_name.strip() == "Pending" else downloaded
        for m in _ENTRY_RE.finditer(body):
            pid, title, year_str, authors_str, venue, date = m.groups()
            try:
                year = int(year_str) if year_str.strip().isdigit() else None
            except ValueError:
                year = None
            authors = [a.strip() for a in authors_str.split(",") if a.strip()]
            target.append(ManualEntry(
                paper_id=pid,
                title=title,
                authors=authors,
                year=year,
                venue=venue.strip() or None,
                doi=None,
                added_date=date.strip(),
            ))
    return ManualQueue(pending=pending, downloaded=downloaded)


def append_pending(queue: ManualQueue, entry: ManualEntry, raw_dir: Path) -> None:
    if any(e.paper_id == entry.paper_id for e in queue.pending):
        return
    queue.pending.append(entry)
    _save(queue, raw_dir)


def mark_downloaded(queue: ManualQueue, paper_id: str, downloaded_date: str, raw_dir: Path) -> None:
    idx = next((i for i, e in enumerate(queue.pending) if e.paper_id == paper_id), None)
    if idx is None:
        return
    entry = queue.pending.pop(idx)
    entry.downloaded_date = downloaded_date
    queue.downloaded.append(entry)
    _save(queue, raw_dir)
