from __future__ import annotations
import json
import re
from pathlib import Path

from rapidfuzz import fuzz
from ..linking.concept_match import match_concept

# Patterns that indicate a value is a paper citation, not a concept name.
# e.g. "Vaswani et al. 2017 — Attention Is All You Need"
#      "Lopez et al. 2018"
#      "CLIP — Radford et al. 2021"
_CITATION_RE = re.compile(
    r"et al\.[\s,]|\b(19|20)\d{2}\b.*—|—.*\b(19|20)\d{2}\b|\b(19|20)\d{2}\s*$"
)


def _is_citation(name: str) -> bool:
    """Return True if the string looks like a paper citation rather than a concept."""
    return bool(_CITATION_RE.search(name))


# Terms that describe HOW research is done, not WHAT it's about.
# Routed to pattern_signals.methodological_tags instead of concept_contributions.
METHODOLOGICAL_TERMS: frozenset[str] = frozenset({
    # Evaluation approach
    "benchmarking", "benchmark datasets", "benchmark creation",
    "model benchmarking", "performance benchmarks",
    "evaluation methodology", "domain-specific evaluation",
    "diagnostic metrics",
    # Experimental methodology
    "ablation studies", "data ablation",
    "model comparison", "model evaluation",
    "model selection guidance",
    # Quality dimensions
    "generalization", "cross-domain generalization",
    "out-of-distribution generalization", "cross-task generalization",
    "scalability", "model robustness",
    "reproducibility", "research reproducibility",
    "calibration",
    # Efficiency dimensions
    "computational efficiency", "training efficiency",
    "inference efficiency", "parameter efficiency",
    "data efficiency", "sample efficiency",
    "llm efficiency", "llm inference cost",
    # Data methodology
    "data quality", "data quality control",
    "data preprocessing", "noise filtering",
    "dataset curation",
    # Training methodology
    "training stability", "training stabilization",
    "model initialization", "compute optimization",
    # Generic outcome terms
    "state-of-the-art performance", "classification",
    "imbalanced classification", "multiclass classification",
})


def _is_methodological(name: str) -> bool:
    """Return True if the concept is a methodological term, not a topical concept."""
    return name.lower() in METHODOLOGICAL_TERMS


# Concepts too broad to be useful wiki pages on their own (textbook-chapter level).
# When one of these appears, it gets qualified with the paper's domain context
# so "transfer learning" → "transfer learning for single-cell analysis".
BROAD_CONCEPTS: frozenset[str] = frozenset({
    "large language models", "deep learning", "machine learning",
    "transfer learning", "fine-tuning", "fine tuning",
    "representation learning",
    "self-supervised learning", "self supervised learning",
    "few-shot learning", "few shot learning",
    "zero-shot learning", "zero shot learning",
    "pre-training", "pretraining", "pre training",
    "scaling laws", "transformer architecture", "transformers",
    "predictive modeling", "predictive modelling",
    "multi-task learning", "multi task learning", "multitask learning",
    "prompt engineering", "neural networks", "generative models",
    "attention mechanism", "contrastive learning",
    "reinforcement learning", "supervised learning", "unsupervised learning",
    "protein structure", "gene expression", "cell biology",
    "drug discovery", "clinical trials", "statistical analysis",
})

_BROAD_LOWER: frozenset[str] = frozenset(t.lower() for t in BROAD_CONCEPTS)


def _qualify_broad_concept(name: str, domain_tags: list[str], topic_area: str) -> str:
    """
    Qualify a textbook-level concept with the paper's domain context.

    "transfer learning" + domain_tags=["single-cell genomics", ...]
    → "transfer learning for single-cell genomics"

    Falls back to topic_area first word if no domain_tags available.
    Returns name unchanged if no qualifier can be derived.
    """
    # Prefer domain_tags: pick the most specific (longest) from the first 3
    qualifier = ""
    specific_tags = [t for t in domain_tags[:3] if t.lower() not in ("machine learning", "deep learning", "artificial intelligence")]
    if specific_tags:
        qualifier = max(specific_tags, key=len)
    elif topic_area:
        qualifier = topic_area.split(",")[0].strip()

    return f"{name} for {qualifier}" if qualifier else name


def _normalize(name: str) -> str:
    """Normalize a concept name for deduplication comparison."""
    n = name.lower()
    # Collapse all separator variants (hyphen, underscore, space) to single space
    # so pre-training == pretraining == pre_training == pre training
    n = re.sub(r"[-_\s]+", " ", n).strip()
    # Strip trailing 's' for basic plural handling (but not 'ss')
    if n.endswith("s") and not n.endswith("ss"):
        n = n[:-1]
    return n


def _deduplicate_concepts(concept_refs: dict[str, dict]) -> dict[str, dict]:
    """
    Merge near-duplicate concept names into a canonical representative.

    Uses a two-pass approach:
    1. Exact match after normalization (catches pre-training/pretraining, etc.)
    2. Fuzzy token_sort_ratio >= 92 (catches chain-of-thought/chain-of-thought reasoning)

    The first name encountered (insertion order) is kept as canonical.
    """
    canonical: dict[str, str] = {}  # normalized_key → canonical original name
    merged: dict[str, dict] = {}    # canonical name → merged refs

    for name, refs in concept_refs.items():
        norm = _normalize(name)

        # Check for exact normalized match first
        if norm in canonical:
            canon = canonical[norm]
            merged[canon]["knowledge_items"].extend(refs["knowledge_items"])
            merged[canon]["roadmap_edges"].extend(refs["roadmap_edges"])
            continue

        # Check for fuzzy match against already-seen canonical names
        best_canon = None
        best_score = 0
        for seen_norm, seen_canon in canonical.items():
            score = fuzz.token_sort_ratio(norm, seen_norm)
            if score > best_score:
                best_score = score
                best_canon = seen_canon

        if best_canon and best_score >= 92:
            merged[best_canon]["knowledge_items"].extend(refs["knowledge_items"])
            merged[best_canon]["roadmap_edges"].extend(refs["roadmap_edges"])
            canonical[norm] = best_canon
        else:
            canonical[norm] = name
            merged[name] = {
                "knowledge_items": list(refs["knowledge_items"]),
                "roadmap_edges": list(refs["roadmap_edges"]),
            }

    return merged


def _load_json(path: Path) -> dict:
    """Load JSON from path; return empty dict on missing or corrupt file."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def generate_concept_mapping(
    paper_id: str,
    staging_paper_dir: Path,
    concept_index: list[tuple[str, str]],
) -> dict:
    """
    Read staging module JSONs for one paper and produce concept_mapping.json content.

    Returns a dict matching the concept_mapping.json schema:
    {
      "paper_id": str,
      "concept_contributions": [{"concept_name", "matched_page", "match_type",
                                  "knowledge_items", "roadmap_edges"}, ...],
      "pattern_signals": {"logic_pattern": str},
      "writing_signals": {"venue": str, "topic_area": str},
    }
    """
    knowledge = _load_json(staging_paper_dir / "knowledge.json")
    roadmap = _load_json(staging_paper_dir / "roadmap.json")
    logic = _load_json(staging_paper_dir / "logic.json")
    writing = _load_json(staging_paper_dir / "writing.json")
    experiment = _load_json(staging_paper_dir / "experiment.json")

    # Collect concept → {knowledge_items, roadmap_edges} mapping.
    # Only knowledge items drive concept page creation.
    # Roadmap edges are citation relationships (paper → paper) — they enrich
    # existing concepts as context but never create new concept pages.
    concept_refs: dict[str, dict] = {}
    methodological_tags: list[str] = []

    # First pass: collect all domain_tags across items for broad-concept qualification
    all_domain_tags: list[str] = []
    for item in knowledge.get("knowledge_items", []):
        all_domain_tags.extend(item.get("domain_tags", []))
    # Deduplicate preserving order, filter generic ML terms that don't help qualify
    seen: set[str] = set()
    paper_domain_tags: list[str] = []
    for t in all_domain_tags:
        if t not in seen:
            seen.add(t)
            paper_domain_tags.append(t)
    topic_area_str = writing.get("topic_area", "") or ""

    for item in knowledge.get("knowledge_items", []):
        item_id = item.get("id", "")
        for concept_name in item.get("related_concepts", []):
            if not concept_name or _is_citation(concept_name):
                continue
            if _is_methodological(concept_name):
                if concept_name not in methodological_tags:
                    methodological_tags.append(concept_name)
                continue
            # Qualify textbook-level concepts with paper's domain context
            if concept_name.lower() in _BROAD_LOWER:
                concept_name = _qualify_broad_concept(concept_name, paper_domain_tags, topic_area_str)
            if concept_name not in concept_refs:
                concept_refs[concept_name] = {"knowledge_items": [], "roadmap_edges": []}
            if item_id:
                concept_refs[concept_name]["knowledge_items"].append(item_id)

    # Attach roadmap edges only to concepts already identified above.
    for i, edge in enumerate(roadmap.get("relationships", [])):
        target = edge.get("target_entity", "")
        if not target or _is_citation(target):
            continue
        # Only enrich existing concepts, never create new ones from roadmap edges.
        if target in concept_refs:
            concept_refs[target]["roadmap_edges"].append(f"r{i}")

    # Merge near-duplicates within this paper's concept list
    concept_refs = _deduplicate_concepts(concept_refs)

    # Fuzzy-match each concept against existing wiki pages
    concept_contributions = []
    for concept_name, refs in concept_refs.items():
        match = match_concept(concept_name, concept_index)
        if match:
            _, matched_slug = match
            contribution = {
                "concept_name": concept_name,
                "matched_page": matched_slug,
                "match_type": "existing",
                "knowledge_items": refs["knowledge_items"],
                "roadmap_edges": refs["roadmap_edges"],
            }
        else:
            contribution = {
                "concept_name": concept_name,
                "matched_page": None,
                "match_type": "new",
                "knowledge_items": refs["knowledge_items"],
                "roadmap_edges": refs["roadmap_edges"],
            }
        concept_contributions.append(contribution)

    # Build key_experiment_summary from pipeline steps
    pipeline_steps = experiment.get("experimental_pipeline", [])
    summary_parts = []
    for step in pipeline_steps[:5]:
        action = step.get("action", "")
        details = step.get("details", "")
        if action:
            summary_parts.append(f"{action}: {details}" if details else action)
    key_experiment_summary = "; ".join(summary_parts)

    topic_area = writing.get("topic_area", "") or ""
    # Split comma-separated topic_area into individual tags for Jaccard clustering
    topic_tags = [t.strip() for t in topic_area.split(",") if t.strip()] if topic_area else []

    return {
        "paper_id": paper_id,
        "concept_contributions": concept_contributions,
        "pattern_signals": {
            "logic_pattern": logic.get("logic_pattern", ""),
            "methodological_tags": methodological_tags,
            "key_experiment_summary": key_experiment_summary,
        },
        "writing_signals": {
            "venue": writing.get("venue", "") or "",
            "topic_area": topic_area,
            "topic_tags": topic_tags,
        },
    }
