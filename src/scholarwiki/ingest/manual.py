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
_YEAR_RE = re.compile(r"(?<!\d)(20[12]\d)(?!\d)")  # exact 4-digit year, not part of longer number
_CREATION_YEAR_RE = re.compile(r"D:(\d{4})")  # PDF creation date "D:YYYYMMDD..."
_AFFIL_KW = frozenset([
    "university", "institute", "laboratory", "department", "school",
    "college", "center", "centre", "hospital", "foundation", "academy",
    "ministry", "national", "@", "correspondence", "contributed equally",
    "co-corresponding", "equal contribution",
])
_VENUE_MAP = [
    ("biorxiv", "bioRxiv"), ("arxiv", "arXiv"),
    ("neurips", "NeurIPS"), ("iclr", "ICLR"), ("icml", "ICML"),
    ("cvpr", "CVPR"), ("iccv", "ICCV"), ("aaai", "AAAI"),
    ("nature", "Nature"), ("science", "Science"), ("cell ", "Cell"),
]


def _clean_author_name(raw: str) -> str:
    """Strip superscript markers and symbols from a single author name."""
    name = re.sub(r"[\d#†§*+∗‡¶]+", "", raw).strip(" ,")
    return name if len(name) > 3 and re.match(r"[A-Z]", name) else ""


def _extract_pdf_metadata(pdf_path: Path) -> dict:
    """Extract title, authors, year, doi, venue, abstract from PDF text."""
    try:
        doc = fitz.open(str(pdf_path))
        pages_text = [doc[i].get_text() for i in range(min(3, len(doc)))]
        full_text = "\n".join(pages_text)
        lines = [l.strip() for l in full_text.split("\n") if l.strip()]
        doc_meta = doc.metadata or {}
        doc.close()

        # --- DOI (first 80 lines) ---
        doi = None
        for line in lines[:80]:
            m = _DOI_RE.search(line)
            if m:
                doi = m.group(1).rstrip(".,;)")
                break

        # --- Year: DOI > PDF creation date > first-page text (narrow scan) ---
        year = None
        if doi:
            m = _YEAR_RE.search(doi)
            if m:
                year = int(m.group(1))
        if not year:
            creation = doc_meta.get("creationDate", "")  # e.g. "D:20250219015347Z"
            m = _CREATION_YEAR_RE.search(creation)
            if m:
                year = int(m.group(1))
        if not year:
            # Only scan first 30 lines to avoid picking up citation years
            for line in lines[:30]:
                m = _YEAR_RE.search(line)
                if m:
                    year = int(m.group(1))
                    break

        # --- Blind review format (ICLR/NeurIPS anon): line numbers 000–059 ---
        is_blind = sum(1 for l in lines[:40] if re.match(r"^\d{3}$", l)) > 8

        # --- Title ---
        title = doc_meta.get("title", "").strip()
        if not title or is_blind:
            content_lines = [l for l in lines if not re.match(r"^\d+$", l) and len(l) > 10]
            # Take the first content line as the title; join a second line only if
            # the first ends with a hyphen (indicating a wrapped title).
            title_parts: list[str] = []
            for line in content_lines[:4]:
                title_parts.append(line)
                if not line.rstrip().endswith("-"):
                    break
            title = " ".join(title_parts)[:250] if title_parts else pdf_path.stem

        # --- Venue: PDF subject/keywords field first, then text scan ---
        venue = None
        for field in [doc_meta.get("subject", ""), doc_meta.get("keywords", "")]:
            if not field:
                continue
            for kw, label in _VENUE_MAP:
                if kw in field.lower():
                    venue = label
                    break
            if venue:
                break
        if not venue:
            text_lower = full_text[:3000].lower()
            for kw, label in _VENUE_MAP:
                if kw in text_lower:
                    venue = label
                    break

        # --- Authors: PDF metadata first (most reliable), else text heuristic ---
        authors: list[str] = []
        pdf_author = doc_meta.get("author", "").strip()
        # Use PDF author field if it's Latin characters (not CJK submitter metadata)
        if pdf_author and all(ord(c) < 0x4E00 for c in pdf_author) and len(pdf_author) > 3:
            for part in re.split(r"[;,]\s*| and ", pdf_author):
                name = _clean_author_name(part)
                # Skip "Team" entries and single-word non-names
                if name and " " in name and "Team" not in name:
                    authors.append(name)

        if not authors and not is_blind:
            abstract_pos = next(
                (i for i, l in enumerate(lines) if re.match(r"^abstract\s*$", l, re.IGNORECASE)),
                None,
            )
            search_end = min(abstract_pos, 40) if abstract_pos else 30
            for line in lines[2:search_end]:
                if any(kw in line.lower() for kw in _AFFIL_KW):
                    continue
                if re.match(r"^\d+$", line) or len(line) < 5:
                    continue
                words = line.split()
                # Author lines: ≥2 capitalized words, contains comma or "and"
                caps = sum(1 for w in words if w and w[0].isupper())
                if caps >= 2 and ("," in line or " and " in line.lower()):
                    for part in re.split(r",\s*| and ", line):
                        name = _clean_author_name(part)
                        if name:
                            authors.append(name)
                    if authors:
                        break  # stop after first author line

        # --- Abstract ---
        abstract = None
        for i, line in enumerate(lines):
            if re.match(r"^abstract\s*$", line, re.IGNORECASE):
                parts = []
                for l in lines[i + 1: i + 25]:
                    if re.match(r"^(introduction|keywords|1\s*\.|background)", l, re.IGNORECASE):
                        break
                    parts.append(l)
                abstract = " ".join(parts)[:1200] if parts else None
                break

        return {
            "title": title, "doi": doi, "authors": authors,
            "year": year, "venue": venue, "abstract": abstract,
        }
    except Exception:
        return {"title": pdf_path.stem, "doi": None, "authors": [], "year": None, "venue": None, "abstract": None}


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
                authors=meta.get("authors", []),
                year=meta.get("year"),
                venue=meta.get("venue"),
                abstract=meta.get("abstract"),
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
