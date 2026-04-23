from __future__ import annotations
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from ..config import Config
from ..models import IngestResult, PaperEntry
from ..registry import load_registry, save_registry, add_paper, has_paper
from ..l1_page import write_l1_page, l1_page_slug
from ..manual_queue import load_manual_queue, append_pending, ManualEntry
from ..wiki import update_index, append_log
from ..zotero import push_paper, fetch_citation
from .nexus_schema import NexusRunResult, NexusPaper


def _paper_entry_from_nexus(paper: NexusPaper, file_path: str, result_path: str) -> PaperEntry:
    return PaperEntry(
        paper_id=paper.paper_id,
        title=paper.title,
        doi=paper.doi,
        arxiv_id=paper.arxiv_id,
        authors=paper.authors,
        year=paper.year,
        venue=paper.venue,
        domain_category=paper.resolved_domain_category(),
        domain_tags=paper.domain_tags,
        abstract=paper.abstract,
        source="nexus",
        source_result_path=result_path,
        file_path=file_path,
        file_type="pdf",
        ingested_at=datetime.now(timezone.utc),
        extraction_status="pending",
    )


def _manual_entry_from_nexus(paper: NexusPaper, added_date: str) -> ManualEntry:
    return ManualEntry(
        paper_id=paper.paper_id,
        title=paper.title,
        authors=paper.authors,
        year=paper.year,
        venue=paper.venue,
        doi=paper.doi,
        added_date=added_date,
    )


def ingest_nexus_inbox(cfg: Config, templates_dir: Path | None = None) -> IngestResult:
    result = IngestResult()
    inbox = cfg.paths.nexus_inbox
    raw_dir = cfg.paths.raw
    papers_dir = raw_dir / "papers"
    papers_dir.mkdir(parents=True, exist_ok=True)

    registry = load_registry(raw_dir)
    manual_queue = load_manual_queue(raw_dir)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    json_files = list(inbox.glob("*.json")) if inbox.exists() else []
    ingested_titles: list[str] = []

    for json_path in json_files:
        try:
            run = NexusRunResult.model_validate(json.loads(json_path.read_text()))
        except Exception as e:
            result.errors.append(f"Failed to parse {json_path.name}: {e}")
            continue

        for paper in run.papers:
            if has_paper(registry, paper.paper_id):
                result.skipped_duplicates += 1
                continue

            if paper.download_status == "success" and paper.download_file_path:
                src = Path(paper.download_file_path)
                if not src.exists():
                    result.errors.append(f"PDF not found: {src}")
                    continue
                dest = papers_dir / src.name
                shutil.move(str(src), dest)
                rel_file = str(dest.relative_to(raw_dir.parent) if raw_dir.parent in dest.parents else dest)

                entry = _paper_entry_from_nexus(paper, str(dest), str(json_path))
                entry.zotero_key = push_paper(entry, cfg)
                if entry.zotero_key is None:
                    result.zotero_failed += 1
                else:
                    entry.citation = fetch_citation(entry.zotero_key, cfg)
                page_path = write_l1_page(entry, cfg.paths.wiki, templates_dir)
                entry.wiki_source_page = str(page_path)

                add_paper(registry, entry)
                result.new_papers += 1
                ingested_titles.append(paper.title)

            elif paper.download_status in ("failed", "not_attempted", None):
                if not has_paper(registry, paper.paper_id):
                    append_pending(manual_queue, _manual_entry_from_nexus(paper, today), raw_dir)
                    result.manual_pending += 1

    save_registry(registry, raw_dir)
    if ingested_titles:
        update_index(cfg.paths.wiki, registry)
        append_log(cfg.paths.wiki, f"Ingested {result.new_papers} papers from nexus_inbox: {', '.join(ingested_titles[:5])}")

    return result
