"""Graph-aware suggested papers ranking.

Algorithm:
1. Parse `connections` frontmatter from all concept/pattern/writing wiki pages.
2. Compute a hub score for each page = in-degree + out-degree (number of connections).
3. Score each missing roadmap reference = sum of hub scores of pages that cite it +
   breadth bonus (0.5 × number of distinct citing pages).
4. Return top-N, grouped into Critical / High / Lower tiers.
"""
from __future__ import annotations
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

from ..models import Registry

_PROJECT_ROOT = Path(__file__).parent.parent.parent.parent

# ── Frontmatter parsing ───────────────────────────────────────────────────────

def _parse_connections(md_text: str) -> list[dict]:
    """Extract the `connections` list from YAML frontmatter.

    Handles the simple list-of-mappings format written by GPT-5:
        connections:
          - target: "[[slug]]"
            edge_type: "enables"
            description: "..."
    Returns list of {target_slug, edge_type} dicts. Ignores malformed entries.
    """
    # Extract frontmatter block
    fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", md_text, re.DOTALL)
    if not fm_match:
        return []
    fm_text = fm_match.group(1)

    # Find connections block
    conn_match = re.search(r"^connections:\s*\n((?:[ \t]+-[^\n]*\n(?:[ \t]+\S[^\n]*\n)*)*)",
                           fm_text, re.MULTILINE)
    if not conn_match:
        return []

    connections: list[dict] = []
    block = conn_match.group(1)

    # Parse each item
    for item_m in re.finditer(r"-\s+target:\s*[\"']?\[\[([^\]]+)\]\][\"']?", block):
        slug = item_m.group(1).strip()
        # Find edge_type and via_paper on the next few lines after this item start
        pos = item_m.end()
        snippet = block[pos:pos + 300]
        et_m = re.search(r"edge_type:\s*[\"']?(\w+)[\"']?", snippet)
        edge_type = et_m.group(1) if et_m else "related_to"
        vp_m = re.search(r"via_paper:\s*[\"']?\[\[([^\]]+)\]\][\"']?", snippet)
        via_paper = vp_m.group(1).strip() if vp_m else None
        connections.append({"target_slug": slug, "edge_type": edge_type, "via_paper": via_paper})

    return connections


def _build_concept_graph(wiki_dir: Path) -> dict[str, set[str]]:
    """Return adjacency dict: slug → set of slugs it connects to.

    Reads connections from concepts/, patterns/, and writing/ pages.
    """
    adj: dict[str, set[str]] = defaultdict(set)
    for subdir in ("concepts", "patterns", "writing"):
        d = wiki_dir / subdir
        if not d.exists():
            continue
        for md in d.glob("*.md"):
            src = md.stem
            for conn in _parse_connections(md.read_text(encoding="utf-8", errors="replace")):
                tgt = conn["target_slug"]
                adj[src].add(tgt)
                adj[tgt]  # ensure target is in the graph (even if no outgoing)
    return dict(adj)


def _compute_hub_scores(adj: dict[str, set[str]]) -> dict[str, float]:
    """Hub score = out-degree + in-degree for each node."""
    in_degree: dict[str, int] = defaultdict(int)
    out_degree: dict[str, int] = defaultdict(int)
    for src, targets in adj.items():
        out_degree[src] += len(targets)
        for tgt in targets:
            in_degree[tgt] += 1
    all_slugs = set(adj.keys()) | set(in_degree.keys())
    return {s: out_degree.get(s, 0) + in_degree.get(s, 0) for s in all_slugs}


# ── Roadmap reference collection ─────────────────────────────────────────────

def _page_slug_for(paper_id: str, registry: Registry) -> str:
    entry = registry.papers.get(paper_id)
    if entry and entry.wiki_source_page:
        return Path(entry.wiki_source_page).stem
    return paper_id


def _collect_missing_refs(
    staging_dir: Path,
    registry: Registry,
) -> dict[str, dict[str, Any]]:
    """Return {key: ref_dict} for roadmap refs NOT already in the registry."""
    known_dois = {p.doi.lower() for p in registry.papers.values() if p.doi}
    known_titles_lower = {p.title.lower() for p in registry.papers.values()}

    refs: dict[str, dict] = {}

    for paper_dir in staging_dir.iterdir():
        if not paper_dir.is_dir():
            continue
        roadmap_file = paper_dir / "roadmap.json"
        if not roadmap_file.exists():
            continue
        paper_id = paper_dir.name
        paper_slug = _page_slug_for(paper_id, registry)

        try:
            data = json.loads(roadmap_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        for rel in (data.get("relationships") or []):
            target_doi = (rel.get("target_doi") or "").lower().strip()
            target_entity = rel.get("target_entity") or ""
            significance = rel.get("significance") or "low"
            rel_type = rel.get("relationship_type") or "relates_to"

            if target_doi and target_doi in known_dois:
                continue
            if target_entity.lower() in known_titles_lower:
                continue

            key = target_doi or target_entity.lower()
            if not key:
                continue

            if key not in refs:
                refs[key] = {
                    "title": target_entity,
                    "doi": rel.get("target_doi"),
                    "cited_by_pages": set(),     # wiki page slugs that cite this
                    "relationship_types": set(),
                    "significance": "low",
                }
            r = refs[key]
            r["title"] = target_entity or r["title"]
            r["doi"] = rel.get("target_doi") or r["doi"]
            r["cited_by_pages"].add(paper_slug)
            r["relationship_types"].add(rel_type)
            if significance == "high":
                r["significance"] = "high"
            elif significance == "medium" and r["significance"] != "high":
                r["significance"] = "medium"

    return refs


# ── Main function ─────────────────────────────────────────────────────────────

def rebuild_suggested_papers(
    wiki_dir: Path,
    registry: Registry,
    staging_dir: Path,
    today: str,
    templates_dir: Path | None = None,
    top_n: int = 30,
) -> None:
    """Rebuild wiki/suggested_papers.md using graph-aware ranking.

    Papers are scored by the hub centrality of wiki concept/pattern pages that
    reference them via roadmap relationships. Top-N are returned.
    """
    tdir = templates_dir or (_PROJECT_ROOT / "templates")

    # Build concept graph and hub scores
    adj = _build_concept_graph(wiki_dir)
    hub_scores = _compute_hub_scores(adj)

    # Build bridge index: source paper slug → number of distinct concept/pattern/writing
    # connections that cite it via via_paper.  This measures how much a source paper's
    # findings are woven into the knowledge graph.
    bridge_index: dict[str, int] = defaultdict(int)
    for subdir in ("concepts", "patterns", "writing"):
        d = wiki_dir / subdir
        if not d.exists():
            continue
        for md in d.glob("*.md"):
            for conn in _parse_connections(md.read_text(encoding="utf-8", errors="replace")):
                if conn.get("via_paper"):
                    bridge_index[conn["via_paper"]] += 1

    def _page_hub(slug: str) -> float:
        return hub_scores.get(slug, 0.0)

    # Collect missing references and score them
    refs = _collect_missing_refs(staging_dir, registry)

    scored: list[dict] = []
    for ref in refs.values():
        citing_pages = ref["cited_by_pages"]
        # hub_score: sum of hub centrality scores of citing source pages
        structural_score = sum(_page_hub(pg) for pg in citing_pages)
        # breadth: each distinct citing page contributes
        breadth_bonus = len(citing_pages) * 2.0
        # bridge: how many concept/pattern connections are grounded via a source page
        # that references this missing paper
        bridge_bonus = sum(bridge_index.get(pg, 0) for pg in citing_pages) * 3.0
        total_score = structural_score + breadth_bonus + bridge_bonus

        # Build search query (first 6 words of title, minus last)
        words = ref["title"].split()
        n = min(6, max(1, len(words) - 1))
        search_query = " ".join(words[:n])

        scored.append({
            "title": ref["title"],
            "doi": ref["doi"],
            "cited_by_pages": sorted(citing_pages),
            "relationship_types": sorted(ref["relationship_types"]),
            "significance": ref["significance"],
            "score": total_score,
            "hub_score": structural_score,
            "search_query": search_query,
        })

    # Sort by score descending, cap at top_n
    scored.sort(key=lambda x: x["score"], reverse=True)
    scored = scored[:top_n]

    # Tier into Critical (score ≥ 3), High (score ≥ 1.5), Lower (rest)
    critical: list[dict] = []
    high: list[dict] = []
    lower: list[dict] = []
    for r in scored:
        if r["score"] >= 3.0:
            critical.append(r)
        elif r["score"] >= 1.5:
            high.append(r)
        else:
            lower.append(r)

    env = Environment(loader=FileSystemLoader(str(tdir)), keep_trailing_newline=True)
    tmpl = env.get_template("suggested_papers.md.j2")
    content = tmpl.render(
        last_updated=today,
        total_candidates=len(refs),
        shown=len(scored),
        critical=critical,
        high_priority=high,
        low_priority=lower,
    )

    wiki_dir.mkdir(parents=True, exist_ok=True)
    page_path = wiki_dir / "suggested_papers.md"
    tmp = page_path.with_suffix(".md.tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(page_path)
