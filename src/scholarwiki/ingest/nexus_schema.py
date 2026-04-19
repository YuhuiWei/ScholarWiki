"""Pydantic models for parsing NEXUS RunResult JSON output."""
from __future__ import annotations
from datetime import datetime
from typing import Literal, Optional, Union
from pydantic import BaseModel, Field, field_validator


class NexusPaper(BaseModel):
    paper_id: str
    title: str
    abstract: Optional[str] = None
    year: Optional[int] = None
    authors: list[str] = Field(default_factory=list)
    venue: Optional[str] = None
    doi: Optional[str] = None
    arxiv_id: Optional[str] = None
    domain_category: Optional[Union[str, list[str]]] = None
    domain_tags: list[str] = Field(default_factory=list)
    open_access_pdf_url: Optional[str] = None
    citation_count: Optional[int] = None
    sources: list[str] = Field(default_factory=list)
    download_status: Optional[Literal["success", "failed", "not_attempted"]] = None
    download_file_path: Optional[str] = None

    def resolved_domain_category(self) -> Optional[str]:
        if isinstance(self.domain_category, list):
            return self.domain_category[0] if self.domain_category else None
        return self.domain_category


class NexusRunResult(BaseModel):
    query: str
    domain_category: Union[str, list[str]] = Field(default_factory=list)
    timestamp: Optional[datetime] = None
    sources_used: list[str] = Field(default_factory=list)
    papers: list[NexusPaper] = Field(default_factory=list)
