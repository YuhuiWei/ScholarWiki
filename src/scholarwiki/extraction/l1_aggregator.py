from __future__ import annotations
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..models import PaperEntry


@dataclass
class L1Profile:
    core_contribution: str
    domain: str
    key_concepts: list[str] = field(default_factory=list)
    methods_used: str = ""
    connects_to: list[str] = field(default_factory=list)


def aggregate_l1_profile(modules: dict[str, Any], entry: PaperEntry) -> L1Profile:
    """Derive L1 mini-profile from 5 module dicts. Pure function — no I/O."""
    knowledge = modules.get("knowledge") or {}
    roadmap = modules.get("roadmap") or {}
    experiment = modules.get("experiment") or {}

    # Core contribution: top knowledge item claim → abstract → title
    items = knowledge.get("knowledge_items") or []
    if items:
        core_contribution = items[0].get("claim") or ""
    elif entry.abstract:
        core_contribution = entry.abstract[:200]
    else:
        core_contribution = entry.title

    # Domain: category + first 3 tags
    parts = []
    if entry.domain_category:
        parts.append(entry.domain_category)
    parts.extend(entry.domain_tags[:3])
    domain = ", ".join(parts) if parts else "unknown"

    # Key concepts: union of related_concepts from top 3 knowledge items
    concept_set: list[str] = []
    seen: set[str] = set()
    for item in items[:3]:
        for concept in item.get("related_concepts") or []:
            if concept not in seen:
                concept_set.append(concept)
                seen.add(concept)
    key_concepts = concept_set or list(entry.domain_tags)

    # Methods used: first pipeline step action + tools
    pipeline = experiment.get("experimental_pipeline") or []
    if pipeline:
        first = pipeline[0]
        action = first.get("action") or ""
        tools = first.get("tools") or []
        methods_used = f"{action} ({', '.join(tools)})" if tools else action
    else:
        methods_used = ""

    # Connects to: high-significance relationship targets only
    relationships = roadmap.get("relationships") or []
    connects_to = [
        r.get("target_entity") or ""
        for r in relationships
        if r.get("significance") == "high" and r.get("target_entity")
    ]

    return L1Profile(
        core_contribution=core_contribution,
        domain=domain,
        key_concepts=key_concepts,
        methods_used=methods_used,
        connects_to=connects_to,
    )


_PENDING_PATTERN = re.compile(
    r"## Summary\n<!-- Backfilled after LLM extraction -->\n_Pending extraction\._",
    re.MULTILINE,
)


def update_source_page_summary(page_path: Path, profile: L1Profile) -> None:
    """Replace the pending Summary block with the L1 mini-profile. Idempotent."""
    if not page_path.exists():
        return
    text = page_path.read_text(encoding="utf-8")
    if not _PENDING_PATTERN.search(text):
        return  # Already updated — idempotent

    concepts_str = ", ".join(profile.key_concepts) if profile.key_concepts else "—"
    connects_str = ", ".join(profile.connects_to) if profile.connects_to else "—"

    replacement = (
        f"## Summary\n"
        f"- **Core contribution:** {profile.core_contribution}\n"
        f"- **Domain:** {profile.domain}\n"
        f"- **Key concepts:** {concepts_str}\n"
        f"- **Methods used:** {profile.methods_used or '—'}\n"
        f"- **Connects to:** {connects_str}"
    )

    updated = _PENDING_PATTERN.sub(replacement, text)
    tmp = page_path.with_suffix(".md.tmp")
    tmp.write_text(updated, encoding="utf-8")
    tmp.replace(page_path)
