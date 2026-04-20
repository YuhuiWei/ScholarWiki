from __future__ import annotations
import os
import re
from pathlib import Path
from typing import Optional
import yaml
from pydantic import BaseModel


def _expand_env(value: object) -> object:
    """Substitute ${VAR} in string values."""
    if isinstance(value, str):
        return re.sub(r"\$\{(\w+)\}", lambda m: os.environ.get(m.group(1), m.group(0)), value)
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env(v) for v in value]
    return value


class PathsConfig(BaseModel):
    nexus_inbox: Path = Path("./nexus_inbox")
    manual_inbox: Path = Path("./manual_inbox")
    raw: Path = Path("./raw")
    staging: Path = Path("./staging")
    wiki: Path = Path("./wiki")


class ZoteroConfig(BaseModel):
    library_id: str = ""
    library_type: str = "user"
    api_key: str = ""


class ExtractionConfig(BaseModel):
    model: str = "gpt-4.1"
    max_papers_per_batch: int = 50
    max_tokens_per_request: int = 4096


class LinkingConfig(BaseModel):
    synthesis_model: str = "gpt-5"   # GPT-5 for concept + pattern synthesis
    style_model: str = "gpt-4.1"     # GPT-4.1 for writing style synthesis
    min_papers_for_concept: int = 2  # concepts seen in fewer papers stay pending


class SyncConfig(BaseModel):
    method: str = "rsync"
    local_path: str = "~/Obsidian/ScholarWiki/"
    remote_path: str = ""


class Config(BaseModel):
    paths: PathsConfig = PathsConfig()
    zotero: ZoteroConfig = ZoteroConfig()
    extraction: ExtractionConfig = ExtractionConfig()
    linking: LinkingConfig = LinkingConfig()
    sync: SyncConfig = SyncConfig()


def load_config(path: Path) -> Config:
    if not path.exists():
        return Config()
    raw = yaml.safe_load(path.read_text()) or {}
    expanded = _expand_env(raw)
    return Config.model_validate(expanded)
