from __future__ import annotations
import re
from dataclasses import dataclass, field
from pathlib import Path

from ..models import Registry

WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")

_SKIP_FILES = {"index.md", "log.md", "suggested_papers.md"}


@dataclass
class LintIssue:
    severity: str  # "error", "warning", "info"
    category: str
    message: str
    file: str | None = None


@dataclass
class LintReport:
    issues: list[LintIssue] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "warning")

    @property
    def info_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "info")


def run_lint(wiki_dir: Path, registry: Registry) -> LintReport:
    """Health-check the wiki for structural issues. Read-only."""
    report = LintReport()

    # Collect outbound wikilinks from source pages
    source_outlinks: set[str] = set()
    sources_dir = wiki_dir / "sources"
    if sources_dir.exists():
        for f in sources_dir.glob("*.md"):
            source_outlinks.update(WIKILINK_RE.findall(f.read_text(encoding="utf-8")))

    # Build set of all known slugs across all wiki subdirectories
    all_slugs: set[str] = set()
    _SUBDIRS = ["sources", "concepts", "patterns", "writing", "roadmap"]
    for subdir in _SUBDIRS:
        d = wiki_dir / subdir
        if d.exists():
            all_slugs.update(f.stem for f in d.glob("*.md"))

    # 1. Orphan concept pages — concept pages with zero inbound links from source pages
    concepts_dir = wiki_dir / "concepts"
    if concepts_dir.exists():
        for f in concepts_dir.glob("*.md"):
            if f.stem not in source_outlinks:
                report.issues.append(LintIssue(
                    severity="warning",
                    category="orphan_concept",
                    message=f"Concept page '{f.stem}' has no inbound links from source pages",
                    file=str(f.relative_to(wiki_dir)),
                ))

    # 2. Missing wikilinks — [[target]] in text but no target.md exists
    for md_file in wiki_dir.rglob("*.md"):
        if md_file.name in _SKIP_FILES:
            continue
        content = md_file.read_text(encoding="utf-8")
        for target in WIKILINK_RE.findall(content):
            if target not in all_slugs:
                report.issues.append(LintIssue(
                    severity="error",
                    category="missing_link",
                    message=f"[[{target}]] referenced but no page exists",
                    file=str(md_file.relative_to(wiki_dir)),
                ))

    # 3. Weak patterns — pattern pages citing fewer than 2 source papers
    patterns_dir = wiki_dir / "patterns"
    if patterns_dir.exists():
        sources_set = {
            f.stem for f in sources_dir.glob("*.md")
        } if sources_dir.exists() else set()
        for f in patterns_dir.glob("*.md"):
            content = f.read_text(encoding="utf-8")
            refs = set(WIKILINK_RE.findall(content)) & sources_set
            if len(refs) < 2:
                report.issues.append(LintIssue(
                    severity="info",
                    category="weak_pattern",
                    message=f"Pattern '{f.stem}' references fewer than 2 source papers",
                    file=str(f.relative_to(wiki_dir)),
                ))

    # 4. Missing source pages — linked papers without a wiki source page on disk
    for paper_id, entry in registry.papers.items():
        if entry.extraction_status == "linked" and entry.wiki_source_page:
            page_path = wiki_dir / entry.wiki_source_page
            if not page_path.exists():
                report.issues.append(LintIssue(
                    severity="error",
                    category="missing_source_page",
                    message=f"Paper '{entry.title}' is linked but source page missing",
                    file=entry.wiki_source_page,
                ))

    # 5. Index drift — pages on disk not mentioned in index.md
    index_file = wiki_dir / "index.md"
    if index_file.exists():
        index_content = index_file.read_text(encoding="utf-8")
        for subdir in ["sources", "concepts", "patterns", "writing"]:
            d = wiki_dir / subdir
            if d.exists():
                for f in d.glob("*.md"):
                    if f.stem not in index_content:
                        report.issues.append(LintIssue(
                            severity="warning",
                            category="index_drift",
                            message=f"Page '{subdir}/{f.name}' exists but not referenced in index.md",
                            file=f"{subdir}/{f.name}",
                        ))

    return report
