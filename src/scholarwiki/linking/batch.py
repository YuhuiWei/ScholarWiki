from __future__ import annotations
import io
import json
from datetime import datetime, timezone
from pathlib import Path

from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from ..config import Config
from ..models import PaperEntry, Registry
from ..registry import save_registry
from .backfill import backfill_source_page
from .pending_concepts import resolve_concepts_for_linking, save_pending
from .concept_match import list_concept_index, slug_from_title
from .design_patterns import cluster_patterns, write_pattern_page
from .knowledge_hypergraph import write_concept_page
from .suggested_papers import rebuild_suggested_papers
from .synthesis_prompts import (
    CONCEPT_SYNTHESIS_SYSTEM,
    PATTERN_SYNTHESIS_SYSTEM,
    STYLE_SYNTHESIS_SYSTEM,
)
from .writing_styles import cluster_writing_styles, write_style_page


class LinkBatchSubmitResult(BaseModel):
    gpt5_batch_id: str = ""
    gpt41_batch_id: str = ""
    concept_count: int = 0
    pattern_count: int = 0
    style_count: int = 0


class LinkBatchCollectResult(BaseModel):
    linked: int = 0
    errors: list[str] = Field(default_factory=list)


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _atomic_write_json(path: Path, data: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(path)


def _load_staging_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _paper_slug(entry: PaperEntry) -> str:
    if entry.wiki_source_page:
        return Path(entry.wiki_source_page).stem
    return entry.paper_id


def _parse_edge_index(rid: str) -> int | None:
    """Parse 'r{int}' edge reference; return None on malformed input."""
    if not rid.startswith("r") or len(rid) < 2:
        return None
    try:
        return int(rid[1:])
    except ValueError:
        return None


async def _upload_and_submit(
    client: AsyncOpenAI,
    requests: list[dict],
    model: str,
    filename: str,
) -> str:
    """Upload a JSONL file and submit a batch job. Returns batch ID."""
    jsonl = "\n".join(json.dumps(r) for r in requests).encode("utf-8")
    file_obj = await client.files.create(
        file=(filename, io.BytesIO(jsonl), "application/jsonl"),
        purpose="batch",
    )
    batch = await client.batches.create(
        input_file_id=file_obj.id,
        endpoint="/v1/chat/completions",
        completion_window="24h",
    )
    return batch.id


def _build_concept_request(
    slug: str,
    concept_name: str,
    contributions: list[dict],
    existing_page: str,
    today: str,
    model: str,
) -> dict:
    """Build a GPT-5 batch request for concept page synthesis."""
    findings_text = ""
    for c in contributions:
        findings_text += f"\n[[{c['paper_slug']}]] findings about this concept:\n"
        for item in c["knowledge_items"]:
            findings_text += f"  - {item.get('claim', '')} (confidence: {item.get('confidence', '')})"
            if item.get("quantitative_result"):
                findings_text += f" [{item['quantitative_result']}]"
            findings_text += "\n"

    edges_text = ""
    for c in contributions:
        for edge in c["roadmap_edges"]:
            edges_text += (
                f"  [[{c['paper_slug']}]] {edge.get('relationship_type', 'relates_to')} "
                f"{edge.get('target_entity', '')}: {edge.get('description', '')}\n"
            )

    user_content = (
        f"Concept slug: {slug}\n"
        f"Concept name: {concept_name}\n\n"
        f"EXISTING PAGE (replace entirely — use as context):\n{existing_page or '(new concept page)'}\n\n"
        f"FINDINGS:\n{findings_text or '(none)'}\n\n"
        f"RESEARCH RELATIONSHIPS:\n{edges_text or '(none)'}\n\n"
        f"today: {today}"
    )
    return {
        "custom_id": f"concept_{slug}",
        "method": "POST",
        "url": "/v1/chat/completions",
        "body": {
            "model": model,
            "messages": [
                {"role": "system", "content": CONCEPT_SYNTHESIS_SYSTEM},
                {"role": "user", "content": user_content},
            ],
            "max_completion_tokens": 4096,
        },
    }


def _build_pattern_request(
    slug: str,
    title: str,
    paper_ids: list[str],
    staging_dir: Path,
    registry: Registry,
    existing_page: str,
    today: str,
    model: str,
) -> dict:
    papers_text = ""
    for pid in paper_ids:
        entry = registry.papers.get(pid)
        paper_slug = _paper_slug(entry) if entry else pid
        logic = _load_staging_json(staging_dir / pid / "logic.json")
        experiment = _load_staging_json(staging_dir / pid / "experiment.json")
        papers_text += (
            f"\n[[{paper_slug}]]\n"
            f"  Logic: {logic.get('logic_pattern', '')}\n"
            f"  Pipeline steps: {len(experiment.get('experimental_pipeline', []))}\n"
            f"  Controls: {', '.join(c.get('control_type', '') for c in experiment.get('controls', []))}\n"
        )

    user_content = (
        f"Pattern slug: {slug}\n"
        f"Pattern title: {title}\n\n"
        f"EXISTING PAGE:\n{existing_page or '(new pattern page)'}\n\n"
        f"PAPERS USING THIS PATTERN:\n{papers_text}\n\n"
        f"today: {today}"
    )
    return {
        "custom_id": f"pattern_{slug}",
        "method": "POST",
        "url": "/v1/chat/completions",
        "body": {
            "model": model,
            "messages": [
                {"role": "system", "content": PATTERN_SYNTHESIS_SYSTEM},
                {"role": "user", "content": user_content},
            ],
            "max_completion_tokens": 4096,
        },
    }


def _build_style_request(
    slug: str,
    title: str,
    paper_ids: list[str],
    staging_dir: Path,
    registry: Registry,
    existing_page: str,
    today: str,
    model: str,
) -> dict:
    papers_text = ""
    for pid in paper_ids:
        entry = registry.papers.get(pid)
        paper_slug = _paper_slug(entry) if entry else pid
        writing = _load_staging_json(staging_dir / pid / "writing.json")
        papers_text += (
            f"\n[[{paper_slug}]] ({getattr(entry, 'year', '?') if entry else '?'}) — {writing.get('venue', '')}\n"
            f"  Venue type: {writing.get('venue_type', '')}\n"
            f"  Sections: {writing.get('structure', {}).get('section_order', [])}\n"
            f"  Intro strategy: {writing.get('introduction_pattern', {}).get('strategy', '')}\n"
            f"  Hedging: {writing.get('discussion_pattern', {}).get('hedging_level', '')} — "
            f"{writing.get('discussion_pattern', {}).get('hedging_examples', [])}\n"
            f"  Transitions: {writing.get('language_patterns', {}).get('transition_phrases', [])}\n"
        )

    confidence = "high" if len(paper_ids) >= 2 else "low"
    venue = title.split(" — ")[0] if " — " in title else title
    user_content = (
        f"Style slug: {slug}\n"
        f"Style title: {title}\n"
        f"Venue: {venue}\n"
        f"Confidence: {confidence}\n\n"
        f"EXISTING PAGE:\n{existing_page or '(new style page)'}\n\n"
        f"PAPERS IN THIS GROUP:\n{papers_text}\n\n"
        f"today: {today}"
    )
    return {
        "custom_id": f"style_{slug}",
        "method": "POST",
        "url": "/v1/chat/completions",
        "body": {
            "model": model,
            "messages": [
                {"role": "system", "content": STYLE_SYNTHESIS_SYSTEM},
                {"role": "user", "content": user_content},
            ],
            "max_completion_tokens": 4096,
        },
    }


async def submit_link_batches(
    papers: list[PaperEntry],
    registry: Registry,
    raw_dir: Path,
    staging_dir: Path,
    wiki_dir: Path,
    cfg: Config,
) -> LinkBatchSubmitResult:
    """
    Load concept_mapping.json for each paper, group by concept/pattern/style,
    and submit two batches: Batch 1 (GPT-5: concepts + patterns), Batch 2 (GPT-4.1: styles).
    """
    client = AsyncOpenAI()
    synthesis_model = cfg.linking.synthesis_model
    style_model = cfg.linking.style_model
    today = _today()

    # Step 1: Load concept mappings
    paper_mappings: dict[str, dict] = {}
    for entry in papers:
        mapping = _load_staging_json(staging_dir / entry.paper_id / "concept_mapping.json")
        if mapping:
            paper_mappings[entry.paper_id] = mapping

    # Step 2: Group knowledge items + roadmap edges by concept slug
    concept_groups: dict[str, dict] = {}

    for paper_id, mapping in paper_mappings.items():
        entry = registry.papers.get(paper_id)
        paper_slug = _paper_slug(entry) if entry else paper_id
        knowledge_items = {
            item["id"]: item
            for item in _load_staging_json(
                staging_dir / paper_id / "knowledge.json"
            ).get("knowledge_items", [])
        }
        roadmap_edges = _load_staging_json(
            staging_dir / paper_id / "roadmap.json"
        ).get("relationships", [])

        for contrib in mapping.get("concept_contributions", []):
            slug = contrib.get("matched_page") or slug_from_title(contrib["concept_name"])
            if slug not in concept_groups:
                concept_groups[slug] = {
                    "concept_name": contrib["concept_name"],
                    "contributions": [],
                }
            concept_groups[slug]["contributions"].append({
                "paper_slug": paper_slug,
                "knowledge_items": [
                    knowledge_items[kid]
                    for kid in contrib.get("knowledge_items", [])
                    if kid in knowledge_items
                ],
                "roadmap_edges": [
                    roadmap_edges[idx]
                    for rid in contrib.get("roadmap_edges", [])
                    if (idx := _parse_edge_index(rid)) is not None
                    and idx < len(roadmap_edges)
                ],
            })

    # Step 2b: Filter concept_groups through pending ledger — only synthesize
    # concepts that appear in ≥ min_papers_for_concept papers.
    concepts_to_link, updated_pending = resolve_concepts_for_linking(
        staging_dir, min_papers=cfg.linking.min_papers_for_concept
    )
    concept_groups = {
        slug: group for slug, group in concept_groups.items()
        if group["concept_name"] in concepts_to_link
    }

    # Step 3: Cluster design patterns (synchronous GPT-5 call)
    pattern_input = []
    for paper_id, mapping in paper_mappings.items():
        entry = registry.papers.get(paper_id)
        pattern_input.append({
            "paper_id": paper_id,
            "title": entry.title if entry else paper_id,
            "logic_pattern": mapping.get("pattern_signals", {}).get("logic_pattern", ""),
        })

    existing_pattern_index = list_concept_index(wiki_dir / "patterns")
    pattern_clusters = await cluster_patterns(pattern_input, existing_pattern_index, cfg)

    # Step 4: Cluster writing styles (programmatic Jaccard)
    style_input = []
    for paper_id, mapping in paper_mappings.items():
        ws = mapping.get("writing_signals", {})
        style_input.append({
            "paper_id": paper_id,
            "venue": ws.get("venue", ""),
            "topic_area": ws.get("topic_area", ""),
            "topic_tags": ws.get("topic_tags") or [ws.get("topic_area", "general")],
        })

    style_clusters = cluster_writing_styles(style_input)

    # Step 5: Build GPT-5 batch requests (concepts + patterns)
    gpt5_requests: list[dict] = []

    for slug, group in concept_groups.items():
        existing_page = ""
        page_path = wiki_dir / "concepts" / f"{slug}.md"
        if page_path.exists():
            existing_page = page_path.read_text(encoding="utf-8")
        gpt5_requests.append(_build_concept_request(
            slug, group["concept_name"], group["contributions"],
            existing_page, today, synthesis_model,
        ))

    for slug, cluster in pattern_clusters.items():
        existing_page = ""
        page_path = wiki_dir / "patterns" / f"{slug}.md"
        if page_path.exists():
            existing_page = page_path.read_text(encoding="utf-8")
        gpt5_requests.append(_build_pattern_request(
            slug, cluster["title"], cluster["paper_ids"],
            staging_dir, registry, existing_page, today, synthesis_model,
        ))

    # Step 6: Build GPT-4.1 batch requests (writing styles)
    gpt41_requests: list[dict] = []

    for slug, cluster in style_clusters.items():
        existing_page = ""
        page_path = wiki_dir / "writing" / f"{slug}.md"
        if page_path.exists():
            existing_page = page_path.read_text(encoding="utf-8")
        gpt41_requests.append(_build_style_request(
            slug, cluster["title"], cluster["paper_ids"],
            staging_dir, registry, existing_page, today, style_model,
        ))

    # Add noop placeholders if either list is empty (batch API requires >=1 request)
    if not gpt5_requests:
        gpt5_requests.append({
            "custom_id": "noop_concept",
            "method": "POST",
            "url": "/v1/chat/completions",
            "body": {"model": synthesis_model,
                     "messages": [{"role": "user", "content": "Say OK"}],
                     "max_completion_tokens": 5},
        })
    if not gpt41_requests:
        gpt41_requests.append({
            "custom_id": "noop_style",
            "method": "POST",
            "url": "/v1/chat/completions",
            "body": {"model": style_model,
                     "messages": [{"role": "user", "content": "Say OK"}],
                     "max_completion_tokens": 5},
        })

    gpt5_batch_id = await _upload_and_submit(
        client, gpt5_requests, synthesis_model, "link_gpt5.jsonl"
    )
    gpt41_batch_id = await _upload_and_submit(
        client, gpt41_requests, style_model, "link_gpt41.jsonl"
    )

    # Save updated pending ledger (promoted concepts removed)
    save_pending(staging_dir, updated_pending)

    # Write batch IDs to registry
    submitted_ids = {entry.paper_id for entry in papers}
    for entry in registry.papers.values():
        if entry.paper_id in submitted_ids:
            entry.linking_batch_ids = {"gpt5": gpt5_batch_id, "gpt41": gpt41_batch_id}

    save_registry(registry, raw_dir)

    return LinkBatchSubmitResult(
        gpt5_batch_id=gpt5_batch_id,
        gpt41_batch_id=gpt41_batch_id,
        concept_count=len(concept_groups),
        pattern_count=len(pattern_clusters),
        style_count=len(style_clusters),
    )


async def get_link_batch_status(batch_ids: dict[str, str], cfg: Config) -> dict[str, dict]:
    """Return status dict for each batch ID. Input: {category: batch_id}."""
    client = AsyncOpenAI()
    result = {}
    for category, bid in batch_ids.items():
        batch = await client.batches.retrieve(bid)
        rc = batch.request_counts
        result[category] = {
            "id": batch.id,
            "status": batch.status,
            "request_counts": {
                "total": getattr(rc, "total", 0),
                "completed": getattr(rc, "completed", 0),
                "failed": getattr(rc, "failed", 0),
            },
        }
    return result


async def collect_link_batches(
    registry: Registry,
    raw_dir: Path,
    staging_dir: Path,
    wiki_dir: Path,
    cfg: Config,
) -> LinkBatchCollectResult:
    """
    Download both batches (must both be completed), write wiki pages,
    backfill source pages, rebuild suggested_papers.md, set status=linked.
    """
    client = AsyncOpenAI()
    result = LinkBatchCollectResult()
    today = _today()

    # Collect unique batch ID pairs from papers with linking_batch_ids
    batch_pairs: set[tuple[str, str]] = set()
    for entry in registry.papers.values():
        ids = entry.linking_batch_ids
        if ids.get("gpt5") and ids.get("gpt41"):
            batch_pairs.add((ids["gpt5"], ids["gpt41"]))

    if not batch_pairs:
        result.errors.append("No papers with linking_batch_ids found.")
        return result

    # Check both batches are complete for each pair; cache retrieved batch objects
    all_complete = True
    retrieved_batches: dict[str, object] = {}
    for gpt5_id, gpt41_id in batch_pairs:
        for bid in [gpt5_id, gpt41_id]:
            if bid not in retrieved_batches:
                retrieved_batches[bid] = await client.batches.retrieve(bid)
        gpt5_batch = retrieved_batches[gpt5_id]
        gpt41_batch = retrieved_batches[gpt41_id]
        for batch in [gpt5_batch, gpt41_batch]:
            if batch.status != "completed":
                result.errors.append(
                    f"Batch {batch.id} status is '{batch.status}', not completed. "
                    "Run '--collect' again when both batches finish."
                )
                all_complete = False

    if not all_complete:
        return result

    # Download and process all batch outputs (reuse cached batch objects)
    processed_batch_ids: set[str] = set()
    any_output = False

    for gpt5_id, gpt41_id in batch_pairs:
        for batch_id in [gpt5_id, gpt41_id]:
            if batch_id in processed_batch_ids:
                continue
            processed_batch_ids.add(batch_id)

            batch = retrieved_batches[batch_id]
            if not batch.output_file_id:
                rc = batch.request_counts
                result.errors.append(
                    f"Batch {batch_id} has no output file "
                    f"(completed={rc.completed}, failed={rc.failed}, total={rc.total}). "
                    "All requests may have failed — check model name in config.yaml."
                )
                continue
            any_output = True
            file_content = await client.files.content(batch.output_file_id)

            for line in file_content.text.strip().split("\n"):
                if not line.strip():
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue

                custom_id: str = item.get("custom_id", "")
                if item.get("error"):
                    result.errors.append(f"{custom_id}: {item['error']}")
                    continue

                try:
                    markdown = item["response"]["body"]["choices"][0]["message"]["content"]
                except (KeyError, IndexError) as exc:
                    result.errors.append(f"{custom_id}: parse error — {exc}")
                    continue

                # Skip noop placeholders
                if custom_id.startswith("noop_"):
                    continue

                if custom_id.startswith("concept_"):
                    slug = custom_id[len("concept_"):]
                    write_concept_page(wiki_dir, slug, markdown)

                elif custom_id.startswith("pattern_"):
                    slug = custom_id[len("pattern_"):]
                    write_pattern_page(wiki_dir, slug, markdown)

                elif custom_id.startswith("style_"):
                    slug = custom_id[len("style_"):]
                    write_style_page(wiki_dir, slug, markdown)

    # If every batch had no output file, abort without marking papers linked
    if not any_output:
        return result

    # Backfill source pages and mark papers as linked
    for paper_id, entry in registry.papers.items():
        if not entry.linking_batch_ids:
            continue
        if entry.extraction_status == "linked":
            continue

        mapping = _load_staging_json(staging_dir / paper_id / "concept_mapping.json")
        paper_slug = _paper_slug(entry)

        contrib_concepts = [
            c["matched_page"] or slug_from_title(c["concept_name"])
            for c in mapping.get("concept_contributions", [])
            if c.get("matched_page") or c.get("concept_name")
        ]
        if contrib_concepts:
            knowledge_text = "- Contributed to concept pages: " + ", ".join(f"[[{s}]]" for s in contrib_concepts)
        else:
            knowledge_text = "- No concept contributions recorded."

        roadmap_data = _load_staging_json(staging_dir / paper_id / "roadmap.json")
        edges = roadmap_data.get("relationships", [])
        if edges:
            relationships_text = "\n".join(
                f"- **{e.get('relationship_type', 'relates_to')}:** "
                f"{e.get('target_entity', '')} — {e.get('description', '')}"
                for e in edges[:5]
            )
        else:
            relationships_text = "- No research relationships recorded."

        logic_data = _load_staging_json(staging_dir / paper_id / "logic.json")
        logic_pattern = logic_data.get("logic_pattern", "")
        experimental_text = f"- Logic pattern: {logic_pattern}" if logic_pattern else "- No design pattern recorded."
        logic_text = f"- Logic pattern: {logic_pattern}\n- Reasoning chain: {len(logic_data.get('reasoning_chain', []))} steps"

        writing_signals = mapping.get("writing_signals", {})
        writing_text = f"- Venue: {writing_signals.get('venue', 'unknown')}"

        if entry.wiki_source_page:
            source_page_val = entry.wiki_source_page
            source_page = (
                Path(source_page_val)
                if Path(source_page_val).is_absolute()
                else wiki_dir.parent / source_page_val
            )
            backfill_source_page(
                source_page, knowledge_text, relationships_text,
                experimental_text, logic_text, writing_text,
            )

        entry.extraction_status = "linked"
        entry.linked_at = datetime.now(timezone.utc)
        result.linked += 1

    # Rebuild suggested_papers.md
    rebuild_suggested_papers(wiki_dir, registry, staging_dir, today)

    save_registry(registry, raw_dir)
    return result
