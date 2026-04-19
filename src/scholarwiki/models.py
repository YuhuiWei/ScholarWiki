from __future__ import annotations
from datetime import datetime, timezone
from typing import Literal, Optional
from pydantic import BaseModel, Field


ExtractionStatus = Literal["pending", "queued", "submitted", "extracted", "linked"]
FileType = Literal["pdf", "xml"]
PaperSource = Literal["nexus", "manual", "manual_unmatched"]


class PaperEntry(BaseModel):
    paper_id: str
    title: str
    doi: Optional[str] = None
    arxiv_id: Optional[str] = None
    authors: list[str] = Field(default_factory=list)
    year: Optional[int] = None
    venue: Optional[str] = None
    publication_type: Optional[str] = None   # e.g. "Conference" from Semantic Scholar
    domain_category: Optional[str] = None
    domain_tags: list[str] = Field(default_factory=list)
    abstract: Optional[str] = None
    source: PaperSource
    source_result_path: Optional[str] = None   # path to NEXUS result JSON
    file_path: Optional[str] = None            # relative: raw/papers/<filename>
    file_type: Optional[FileType] = None
    zotero_key: Optional[str] = None
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    extraction_status: ExtractionStatus = "pending"
    extraction_batch_id: Optional[str] = None
    failed_modules: list[str] = Field(default_factory=list)
    linking_batch_ids: dict[str, str] = Field(default_factory=dict)  # {"gpt5": batch_id, "gpt41": batch_id}
    linked_at: Optional[datetime] = None
    wiki_source_page: Optional[str] = None     # relative: wiki/sources/<slug>.md


class RegistryStats(BaseModel):
    total: int = 0
    pending_extraction: int = 0
    queued: int = 0
    submitted: int = 0
    extracted: int = 0
    linked: int = 0
    zotero_unsynced: int = 0

    @classmethod
    def from_papers(cls, papers: dict[str, PaperEntry]) -> "RegistryStats":
        counts: dict[str, int] = {
            "pending": 0, "queued": 0, "submitted": 0, "extracted": 0, "linked": 0
        }
        for p in papers.values():
            counts[p.extraction_status] += 1
        return cls(
            total=len(papers),
            pending_extraction=counts["pending"],
            queued=counts["queued"],
            submitted=counts["submitted"],
            extracted=counts["extracted"],
            linked=counts["linked"],
            zotero_unsynced=sum(1 for p in papers.values() if p.zotero_key is None),
        )


class Registry(BaseModel):
    papers: dict[str, PaperEntry] = Field(default_factory=dict)
    stats: RegistryStats = Field(default_factory=RegistryStats)


class IngestResult(BaseModel):
    new_papers: int = 0
    skipped_duplicates: int = 0
    manual_pending: int = 0    # papers added to manual.md
    manual_matched: int = 0    # manual PDFs matched to pending entries
    zotero_failed: int = 0
    errors: list[str] = Field(default_factory=list)
