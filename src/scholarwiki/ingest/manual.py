from __future__ import annotations
import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path

import fitz  # pymupdf
from rapidfuzz import fuzz

from ..config import Config
from ..models import IngestResult, PaperEntry
from ..registry import load_registry, save_registry, add_paper, has_paper
from ..l1_page import write_l1_page
from ..manual_queue import load_manual_queue, mark_downloaded, ManualQueue, ManualEntry
from ..wiki import update_index, append_log
from ..zotero import push_paper


_FUZZY_THRESHOLD = 85
_DOI_RE = re.compile(r"\b(10\.\d{4,}/\S+)", re.IGNORECASE)


def _extract_pdf_metadata(pdf_path: Path) -> dict:
    """Return dict with title, doi from PDF metadata/first-page text."""
    try:
        doc = fitz.open(str(pdf_path))
        meta = doc.metadata or {}
        title = meta.get("title", "").strip()
        # Scan first 2 pages for DOI
        doi = None
        for i in range(min(2, len(doc))):
            text = doc[i].get_text()
            m = _DOI_RE.search(text)
            if m:
                doi = m.group(1).rstrip(".,;)")
                break
        if not title:
            # Fallback: first non-empty line of page 0
            first_page = doc[0].get_text().strip()
            title = first_page.split("\n")[0][:200]
        doc.close()
        return {"title": title, "doi": doi}
    except Exception:
        return {"title": pdf_path.stem, "doi": None}


def _derive_paper_id(doi: str | None, title: str, year: int | None = None) -> str:
    if doi:
        stable = doi.lower().strip()
    else:
        stable = f"{title.lower().strip()}_{year or 0}"
    return hashlib.sha256(stable.encode()).hexdigest()[:16]


def _fuzzy_match(title: str, queue: ManualQueue) -> ManualEntry | None:
    best_score = 0
    best_entry = None
    for entry in queue.pending:
        score = fuzz.token_sort_ratio(title.lower(), entry.title.lower())
        if score > best_score:
            best_score = score
            best_entry = entry
    if best_score >= _FUZZY_THRESHOLD:
        return best_entry
    return None


def ingest_manual_inbox(
    cfg: Config,
    templates_dir: Path | None = None,
    interactive: bool = True,
) -> IngestResult:
    result = IngestResult()
    inbox = cfg.paths.manual_inbox
    raw_dir = cfg.paths.raw
    papers_dir = raw_dir / "papers"
    papers_dir.mkdir(parents=True, exist_ok=True)

    registry = load_registry(raw_dir)
    manual_queue = load_manual_queue(raw_dir)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    pdfs = list(inbox.glob("*.pdf")) if inbox.exists() else []
    ingested_titles: list[str] = []

    for pdf_path in pdfs:
        meta = _extract_pdf_metadata(pdf_path)
        title = meta["title"]
        doi = meta["doi"]

        matched = _fuzzy_match(title, manual_queue)

        if matched:
            paper_id = matched.paper_id
            if has_paper(registry, paper_id):
                result.skipped_duplicates += 1
                pdf_path.unlink()
                continue

            dest = papers_dir / pdf_path.name
            pdf_path.rename(dest)

            entry = PaperEntry(
                paper_id=paper_id,
                title=matched.title,
                doi=matched.doi,
                authors=matched.authors,
                year=matched.year,
                venue=matched.venue,
                source="manual",
                file_path=str(dest),
                file_type="pdf",
                ingested_at=datetime.now(timezone.utc),
                extraction_status="pending",
            )
            entry.zotero_key = push_paper(entry, cfg)
            if entry.zotero_key is None:
                result.zotero_failed += 1
            page_path = write_l1_page(entry, cfg.paths.wiki, templates_dir)
            entry.wiki_source_page = str(page_path)
            add_paper(registry, entry)
            mark_downloaded(manual_queue, paper_id, today, raw_dir)
            result.manual_matched += 1
            result.new_papers += 1
            ingested_titles.append(entry.title)

        else:
            # Unmatched: register with extracted metadata
            paper_id = _derive_paper_id(doi, title)
            if has_paper(registry, paper_id):
                result.skipped_duplicates += 1
                pdf_path.unlink()
                continue

            dest = papers_dir / pdf_path.name
            pdf_path.rename(dest)

            entry = PaperEntry(
                paper_id=paper_id,
                title=title,
                doi=doi,
                source="manual_unmatched",
                file_path=str(dest),
                file_type="pdf",
                ingested_at=datetime.now(timezone.utc),
                extraction_status="pending",
            )
            entry.zotero_key = push_paper(entry, cfg)
            if entry.zotero_key is None:
                result.zotero_failed += 1
            page_path = write_l1_page(entry, cfg.paths.wiki, templates_dir)
            entry.wiki_source_page = str(page_path)
            add_paper(registry, entry)
            result.new_papers += 1
            ingested_titles.append(entry.title)

    save_registry(registry, raw_dir)
    if ingested_titles:
        update_index(cfg.paths.wiki, registry)
        append_log(cfg.paths.wiki, f"Ingested {result.new_papers} papers from manual_inbox")

    return result
