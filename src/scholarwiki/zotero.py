from __future__ import annotations
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field

from .models import PaperEntry, Registry
from pyzotero import zotero
from .config import Config


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------

class ZoteroSyncResult(BaseModel):
    synced: int = 0
    failed: int = 0
    errors: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Conference venue keywords (checked as substrings, case-sensitive)
# ---------------------------------------------------------------------------

_CONFERENCE_VENUES = {
    "NeurIPS", "ICML", "ICLR", "CVPR", "ICCV", "ECCV", "MICCAI",
    "ACL", "EMNLP", "NAACL", "AAAI", "IJCAI", "SIGKDD", "ICSE",
    "SOSP", "OSDI", "USENIX",
}


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

def _detect_item_type(entry: PaperEntry) -> str:
    """Return Zotero item type: 'preprint', 'conferencePaper', or 'journalArticle'."""
    # Preprint: arxiv_id set AND (no DOI or arxiv-proxy DOI)
    if entry.arxiv_id and (
        entry.doi is None or entry.doi.startswith("10.48550/")
    ):
        return "preprint"
    # Conference: publication_type flag or venue substring match
    if entry.publication_type == "Conference":
        return "conferencePaper"
    if entry.venue and any(kw in entry.venue for kw in _CONFERENCE_VENUES):
        return "conferencePaper"
    return "journalArticle"


def _build_item(entry: PaperEntry, collection_key: Optional[str]) -> dict:
    """Build pyzotero-compatible item dict from PaperEntry."""
    item_type = _detect_item_type(entry)
    creators = [{"creatorType": "author", "name": a} for a in entry.authors]
    tags = [{"tag": t} for t in entry.domain_tags]

    item: dict = {
        "itemType": item_type,
        "title": entry.title,
        "creators": creators,
        "abstractNote": entry.abstract or "",
        "date": str(entry.year) if entry.year else "",
        "tags": tags,
    }

    if item_type == "journalArticle":
        item["publicationTitle"] = entry.venue or ""
        if entry.doi:
            item["DOI"] = entry.doi
    elif item_type == "conferencePaper":
        item["proceedingsTitle"] = entry.venue or ""
        if entry.doi:
            item["DOI"] = entry.doi
    elif item_type == "preprint":
        item["repository"] = "arXiv"
        item["archiveID"] = entry.arxiv_id or ""

    if collection_key:
        item["collections"] = [collection_key]

    return item


def _get_or_create_collection(zot, name: str) -> str:
    """Return collection key matching name; create collection if absent."""
    existing = zot.collections()
    for col in existing:
        if col["data"]["name"] == name:
            return col["key"]
    resp = zot.create_collections([{"name": name}])
    return resp["successful"]["0"]["key"]


def push_paper(entry: PaperEntry, cfg: Config) -> Optional[str]:
    """Push paper metadata to Zotero. Returns zotero_key on success, None on failure."""
    if not cfg.zotero.api_key or not cfg.zotero.library_id:
        return None
    try:
        zot = zotero.Zotero(cfg.zotero.library_id, cfg.zotero.library_type, cfg.zotero.api_key)
        collection_name = entry.domain_category or "uncategorized"
        collection_key = _get_or_create_collection(zot, collection_name)
        item = _build_item(entry, collection_key)
        resp = zot.create_items([item])
        if resp.get("successful"):
            return resp["successful"]["0"]["key"]
        return None
    except Exception:
        return None


def sync_pending(registry: Registry, cfg: Config, raw_dir: Path) -> ZoteroSyncResult:
    """Push all papers with zotero_key=None. Saves registry on any success."""
    from .registry import save_registry
    from .l1_page import update_l1_zotero_key

    result = ZoteroSyncResult()
    unsynced = [p for p in registry.papers.values() if p.zotero_key is None]

    for entry in unsynced:
        key = push_paper(entry, cfg)
        if key:
            entry.zotero_key = key
            if entry.wiki_source_page:
                update_l1_zotero_key(Path(entry.wiki_source_page), key)
            result.synced += 1
        else:
            result.failed += 1
            result.errors.append(f"Failed to sync {entry.paper_id} ({entry.title[:50]})")

    if result.synced > 0:
        save_registry(registry, raw_dir)

    return result
