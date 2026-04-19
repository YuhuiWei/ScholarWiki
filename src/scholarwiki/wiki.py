"""wiki/index.md and wiki/log.md management."""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
from .models import Registry


def update_index(wiki_dir: Path, registry: Registry) -> None:
    wiki_dir.mkdir(parents=True, exist_ok=True)
    index_path = wiki_dir / "index.md"
    lines = ["# ScholarWiki Index\n\n"]
    lines.append(f"**Papers:** {registry.stats.total} total, {registry.stats.linked} linked\n\n")
    lines.append("## Sources\n\n")
    for entry in registry.papers.values():
        page = entry.wiki_source_page or ""
        lines.append(f"- [[{Path(page).stem}]] ({entry.year or '?'}) — {entry.title}\n")
    index_path.write_text("".join(lines), encoding="utf-8")


def append_log(wiki_dir: Path, message: str) -> None:
    wiki_dir.mkdir(parents=True, exist_ok=True)
    log_path = wiki_dir / "log.md"
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    entry = f"\n### {ts}\n\n{message}\n"
    if log_path.exists():
        log_path.write_text(log_path.read_text(encoding="utf-8") + entry, encoding="utf-8")
    else:
        log_path.write_text(f"# ScholarWiki Log\n{entry}", encoding="utf-8")
