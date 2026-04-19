from __future__ import annotations
import json
from pathlib import Path
from .models import PaperEntry, Registry, RegistryStats


def load_registry(raw_dir: Path) -> Registry:
    path = raw_dir / "registry.json"
    if not path.exists():
        return Registry()
    data = json.loads(path.read_text(encoding="utf-8"))
    return Registry.model_validate(data)


def save_registry(registry: Registry, raw_dir: Path) -> None:
    registry.stats = RegistryStats.from_papers(registry.papers)
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / "registry.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(registry.model_dump_json(indent=2), encoding="utf-8")
    tmp.replace(path)


def add_paper(registry: Registry, entry: PaperEntry) -> None:
    registry.papers[entry.paper_id] = entry
    registry.stats = RegistryStats.from_papers(registry.papers)


def has_paper(registry: Registry, paper_id: str) -> bool:
    return paper_id in registry.papers


def get_pending(registry: Registry) -> list[PaperEntry]:
    return [p for p in registry.papers.values() if p.extraction_status == "pending"]
