from __future__ import annotations
import asyncio
import io
import json
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from ..config import Config
from ..linking.concept_match import list_concept_index
from ..models import PaperEntry, Registry
from ..registry import save_registry
from .concept_mapping import generate_concept_mapping
from ..linking.pending_concepts import update_pending_from_mappings
from ..linking.pending_styles import update_pending_styles
from .l1_aggregator import aggregate_l1_profile, update_source_page_summary
from .prompts.experiment import MODULE_NAME as EXPERIMENT_MODULE
from .prompts.experiment import SYSTEM_PROMPT as EXPERIMENT_PROMPT
from .prompts.knowledge import MODULE_NAME as KNOWLEDGE_MODULE
from .prompts.knowledge import SYSTEM_PROMPT as KNOWLEDGE_PROMPT
from .prompts.logic import MODULE_NAME as LOGIC_MODULE
from .prompts.logic import SYSTEM_PROMPT as LOGIC_PROMPT
from .prompts.roadmap import MODULE_NAME as ROADMAP_MODULE
from .prompts.roadmap import SYSTEM_PROMPT as ROADMAP_PROMPT
from .prompts.writing import MODULE_NAME as WRITING_MODULE
from .prompts.writing import SYSTEM_PROMPT as WRITING_PROMPT
from .text_extractor import extract_text

_POLL_INTERVAL = 60   # seconds between status checks during auto-retry waits


async def _poll_until_complete(client: AsyncOpenAI, batch_id: str, timeout: int = 3600) -> object:
    """Poll batch until completed/failed/cancelled. Returns final batch object."""
    elapsed = 0
    while elapsed < timeout:
        batch = await client.batches.retrieve(batch_id)
        if batch.status in ("completed", "failed", "cancelled", "expired"):
            return batch
        await asyncio.sleep(_POLL_INTERVAL)
        elapsed += _POLL_INTERVAL
    return await client.batches.retrieve(batch_id)


def _extract_503_ids(error_file_text: str) -> list[str]:
    """Return custom_ids from error file entries that are 503 Service Unavailable."""
    ids: list[str] = []
    for line in error_file_text.strip().split("\n"):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
            if item.get("response", {}).get("status_code") == 503:
                ids.append(item["custom_id"])
        except json.JSONDecodeError:
            continue
    return ids


_MODULES: list[tuple[str, str]] = [
    (KNOWLEDGE_MODULE, KNOWLEDGE_PROMPT),
    (ROADMAP_MODULE, ROADMAP_PROMPT),
    (EXPERIMENT_MODULE, EXPERIMENT_PROMPT),
    (WRITING_MODULE, WRITING_PROMPT),
    (LOGIC_MODULE, LOGIC_PROMPT),
]

_ALL_MODULE_NAMES = {name for name, _ in _MODULES}


class BatchSubmitResult(BaseModel):
    batch_id: str
    paper_ids: list[str] = Field(default_factory=list)
    request_count: int = 0


class BatchCollectResult(BaseModel):
    extracted: int = 0
    partial: int = 0
    failed_modules: dict[str, list[str]] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)


def _make_client(cfg: Config) -> AsyncOpenAI:
    return AsyncOpenAI()


def _build_request(paper_id: str, module_name: str, system_prompt: str,
                   text: str, model: str, max_tokens: int) -> dict:
    return {
        "custom_id": f"{paper_id}_{module_name}",
        "method": "POST",
        "url": "/v1/chat/completions",
        "body": {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
            "response_format": {"type": "json_object"},
            "max_completion_tokens": max_tokens,
        },
    }


async def submit_batch(
    papers: list[PaperEntry],
    raw_dir: Path,
    cfg: Config,
) -> BatchSubmitResult:
    """Extract text from papers, build JSONL, upload to OpenAI, submit batch job."""
    client = _make_client(cfg)
    model = cfg.extraction.model
    max_tokens = cfg.extraction.max_tokens_per_request

    requests: list[dict] = []
    for paper in papers:
        if not paper.file_path:
            continue
        text = extract_text(raw_dir.parent / paper.file_path, paper.file_type or "pdf")
        for module_name, system_prompt in _MODULES:
            requests.append(
                _build_request(paper.paper_id, module_name, system_prompt, text, model, max_tokens)
            )

    jsonl_bytes = "\n".join(json.dumps(r) for r in requests).encode("utf-8")
    file_obj = await client.files.create(
        file=("batch_requests.jsonl", io.BytesIO(jsonl_bytes), "application/jsonl"),
        purpose="batch",
    )
    batch = await client.batches.create(
        input_file_id=file_obj.id,
        endpoint="/v1/chat/completions",
        completion_window="24h",
    )

    return BatchSubmitResult(
        batch_id=batch.id,
        paper_ids=[p.paper_id for p in papers if p.file_path],
        request_count=len(requests),
    )


async def get_batch_status(batch_id: str, cfg: Config) -> dict:
    """Return status dict for a batch job."""
    client = _make_client(cfg)
    batch = await client.batches.retrieve(batch_id)
    return {
        "id": batch.id,
        "status": batch.status,
        "request_counts": {
            "total": batch.request_counts.total,
            "completed": batch.request_counts.completed,
            "failed": batch.request_counts.failed,
        },
    }


async def collect_batch(
    batch_id: str,
    registry: Registry,
    raw_dir: Path,
    staging_dir: Path,
    wiki_dir: Path,
    cfg: Config,
) -> BatchCollectResult:
    """Download batch results, write staging files, run L1 aggregator, update registry."""
    client = _make_client(cfg)
    batch = await client.batches.retrieve(batch_id)
    result = BatchCollectResult()

    if batch.status != "completed":
        result.errors.append(
            f"Batch {batch_id} status is '{batch.status}', not 'completed'"
        )
        return result

    file_content = await client.files.content(batch.output_file_id)
    output_lines = file_content.text

    # Auto-retry 503 failures: wait 10 min, retry up to 3 total attempts
    # If a retry has >50% failure rate, wait 30 min before the next attempt.
    model = cfg.extraction.model
    max_tokens = cfg.extraction.max_tokens_per_request
    module_map = dict(_MODULES)
    attempt = 1
    max_attempts = 3

    while attempt <= max_attempts and batch.error_file_id:
        err_content = await client.files.content(batch.error_file_id)
        failed_503_ids = _extract_503_ids(err_content.text)
        if not failed_503_ids:
            break  # no 503s to retry

        total_requests = batch.request_counts.total
        failure_rate = len(failed_503_ids) / total_requests if total_requests else 0
        wait_minutes = 30 if (attempt > 1 and failure_rate > 0.5) else 10
        result.errors.append(
            f"503 retry {attempt}/{max_attempts}: {len(failed_503_ids)} failed "
            f"({failure_rate:.0%} rate) — waiting {wait_minutes} min before retry"
        )

        if attempt >= max_attempts:
            result.errors.append(
                f"Reached max retry attempts ({max_attempts}). "
                f"{len(failed_503_ids)} module(s) still failed: "
                + ", ".join(failed_503_ids)
            )
            break

        await asyncio.sleep(wait_minutes * 60)

        # Rebuild requests for only the 503'd custom_ids
        retry_requests: list[dict] = []
        for custom_id in failed_503_ids:
            paper_id, module_name = custom_id.rsplit("_", 1)
            entry = registry.papers.get(paper_id)
            if not entry or not entry.file_path or module_name not in module_map:
                continue
            text = extract_text(raw_dir.parent / entry.file_path, entry.file_type or "pdf")
            retry_requests.append(
                _build_request(paper_id, module_name, module_map[module_name],
                               text, model, max_tokens)
            )

        if not retry_requests:
            break

        jsonl_bytes = "\n".join(json.dumps(r) for r in retry_requests).encode("utf-8")
        file_obj = await client.files.create(
            file=("retry_503.jsonl", io.BytesIO(jsonl_bytes), "application/jsonl"),
            purpose="batch",
        )
        retry_batch_obj = await client.batches.create(
            input_file_id=file_obj.id,
            endpoint="/v1/chat/completions",
            completion_window="24h",
        )
        batch = await _poll_until_complete(client, retry_batch_obj.id)
        if batch.output_file_id:
            extra = await client.files.content(batch.output_file_id)
            output_lines += "\n" + extra.text

        attempt += 1

    lines = output_lines.strip().split("\n")

    # Parse and group results by paper_id
    paper_modules: dict[str, dict[str, Any]] = {}
    for line in lines:
        if not line.strip():
            continue
        item = json.loads(line)
        custom_id: str = item["custom_id"]
        # custom_id format: "{paper_id}_{module_name}"
        # module names don't contain underscores, paper_ids might — split from right
        paper_id, module_name = custom_id.rsplit("_", 1)

        if item.get("error"):
            result.errors.append(f"{custom_id}: {item['error']}")
            continue

        try:
            content = json.loads(
                item["response"]["body"]["choices"][0]["message"]["content"]
            )
            paper_modules.setdefault(paper_id, {})[module_name] = content
        except (KeyError, json.JSONDecodeError) as exc:
            result.errors.append(f"{custom_id}: parse error — {exc}")

    # Process each paper
    concept_index = list_concept_index(wiki_dir / "concepts")
    collected_paper_ids: list[str] = []
    for paper_id, modules in paper_modules.items():
        if paper_id not in registry.papers:
            continue
        entry = registry.papers[paper_id]

        # Write staging files for modules that succeeded
        paper_staging = staging_dir / paper_id
        paper_staging.mkdir(parents=True, exist_ok=True)
        for module_name, content in modules.items():
            (paper_staging / f"{module_name}.json").write_text(
                json.dumps(content, indent=2), encoding="utf-8"
            )

        # Check which modules are now present in staging (handles retry merging)
        present = {f.stem for f in paper_staging.glob("*.json")}
        still_missing = sorted(_ALL_MODULE_NAMES - present)
        entry.failed_modules = still_missing

        if not still_missing:
            result.extracted += 1
            # Load all 5 from staging for L1 aggregation
            all_modules = {
                name: json.loads((paper_staging / f"{name}.json").read_text())
                for name in _ALL_MODULE_NAMES
            }
            profile = aggregate_l1_profile(all_modules, entry)
            if entry.wiki_source_page:
                update_source_page_summary(wiki_dir.parent / entry.wiki_source_page, profile)

            # Phase 3 concept mapping: fuzzy-match concepts for Phase 4 to consume
            mapping = generate_concept_mapping(paper_id, paper_staging, concept_index)
            tmp = paper_staging / "concept_mapping.json.tmp"
            tmp.write_text(json.dumps(mapping, indent=2), encoding="utf-8")
            tmp.replace(paper_staging / "concept_mapping.json")

            entry.extraction_status = "extracted"
            collected_paper_ids.append(paper_id)
        else:
            result.partial += 1
            result.failed_modules[paper_id] = still_missing

    if collected_paper_ids:
        update_pending_from_mappings(staging_dir, collected_paper_ids)
        update_pending_styles(staging_dir, collected_paper_ids)

    save_registry(registry, raw_dir)
    return result


async def retry_failed_modules(
    registry: Registry,
    raw_dir: Path,
    cfg: Config,
) -> BatchSubmitResult:
    """Resubmit only the failed modules for papers with non-empty failed_modules."""
    client = _make_client(cfg)
    model = cfg.extraction.model
    max_tokens = cfg.extraction.max_tokens_per_request

    module_map = dict(_MODULES)
    requests: list[dict] = []
    paper_ids: list[str] = []

    for entry in registry.papers.values():
        if not entry.failed_modules:
            continue
        if not entry.file_path:
            continue
        text = extract_text(raw_dir.parent / entry.file_path, entry.file_type or "pdf")
        for module_name in entry.failed_modules:
            if module_name not in module_map:
                continue
            requests.append(
                _build_request(entry.paper_id, module_name, module_map[module_name],
                               text, model, max_tokens)
            )
        paper_ids.append(entry.paper_id)

    if not requests:
        return BatchSubmitResult(batch_id="", paper_ids=[], request_count=0)

    jsonl_bytes = "\n".join(json.dumps(r) for r in requests).encode("utf-8")
    file_obj = await client.files.create(
        file=("retry_requests.jsonl", io.BytesIO(jsonl_bytes), "application/jsonl"),
        purpose="batch",
    )
    batch = await client.batches.create(
        input_file_id=file_obj.id,
        endpoint="/v1/chat/completions",
        completion_window="24h",
    )

    # Update batch_id for retried papers
    for entry in registry.papers.values():
        if entry.paper_id in paper_ids:
            entry.extraction_batch_id = batch.id

    save_registry(registry, raw_dir)
    return BatchSubmitResult(
        batch_id=batch.id,
        paper_ids=paper_ids,
        request_count=len(requests),
    )
