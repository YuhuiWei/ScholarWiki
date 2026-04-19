from __future__ import annotations
import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from .config import Config
from .extraction.batch import get_batch_status, collect_batch, submit_batch
from .ingest.nexus import ingest_nexus_inbox
from .ingest.manual import ingest_manual_inbox
from .linking.batch import submit_link_batches, collect_link_batches
from .models import Registry
from .registry import load_registry, save_registry


class PipelineStep(str, Enum):
    INGEST = "ingest"
    SUBMIT_EXTRACTION = "submit_extraction"
    POLL_EXTRACTION = "poll_extraction"
    SUBMIT_LINKING = "submit_linking"
    POLL_LINKING = "poll_linking"
    DONE = "done"


@dataclass
class PipelineState:
    current_step: PipelineStep
    extraction_batch_id: str | None = None
    linking_batch_ids: dict[str, str] = field(default_factory=dict)
    papers_pending: int = 0
    papers_submitted: int = 0
    papers_extracted: int = 0
    papers_linked: int = 0


def determine_next_step(registry: Registry) -> PipelineState:
    """Read registry state and determine what needs to happen next."""
    papers = list(registry.papers.values())

    if not papers:
        return PipelineState(current_step=PipelineStep.DONE)

    # "pending" and "queued" both need extraction submission
    pending = [p for p in papers if p.extraction_status in ("pending", "queued")]
    submitted = [p for p in papers if p.extraction_status == "submitted"]
    extracted = [p for p in papers if p.extraction_status == "extracted"]
    linked = [p for p in papers if p.extraction_status == "linked"]

    state = PipelineState(
        current_step=PipelineStep.DONE,
        papers_pending=len(pending),
        papers_submitted=len(submitted),
        papers_extracted=len(extracted),
        papers_linked=len(linked),
    )

    if pending:
        state.current_step = PipelineStep.SUBMIT_EXTRACTION
    elif submitted:
        state.current_step = PipelineStep.POLL_EXTRACTION
        batch_ids = {p.extraction_batch_id for p in submitted if p.extraction_batch_id}
        state.extraction_batch_id = next(iter(batch_ids)) if batch_ids else None
    elif extracted:
        # Check if linking has been submitted
        papers_with_linking = [p for p in extracted if p.linking_batch_ids]
        if not papers_with_linking:
            state.current_step = PipelineStep.SUBMIT_LINKING
        else:
            state.current_step = PipelineStep.POLL_LINKING
            # Use batch IDs from the first paper that has them
            state.linking_batch_ids = papers_with_linking[0].linking_batch_ids

    return state


async def poll_until_complete(
    batch_id: str,
    cfg: Config,
    timeout_seconds: int,
    label: str = "Batch",
) -> bool:
    """Poll OpenAI batch status every 60s until complete or timeout."""
    start = time.monotonic()
    while time.monotonic() - start < timeout_seconds:
        status_info = await get_batch_status(batch_id, cfg)
        status = status_info["status"]
        counts = status_info.get("request_counts", {})

        if status == "completed":
            return True
        if status in ("failed", "expired", "cancelled"):
            return False

        elapsed = int(time.monotonic() - start)
        completed = counts.get("completed", 0)
        total = counts.get("total", "?")
        print(f"  [{elapsed}s] {label}: {completed}/{total} complete...", flush=True)
        await asyncio.sleep(60)

    return False


def parse_timeout(timeout_str: str) -> int:
    """Parse '6h', '30m', '3600s', or bare integer into seconds."""
    s = timeout_str.strip().lower()
    if s.endswith("h"):
        return int(float(s[:-1]) * 3600)
    if s.endswith("m"):
        return int(float(s[:-1]) * 60)
    if s.endswith("s"):
        return int(float(s[:-1]))
    return int(s)


async def run_pipeline(
    cfg: Config,
    wait: bool = False,
    timeout_seconds: int = 21600,
    dry_run: bool = False,
    on_status: Callable[[str], None] = print,
) -> bool:
    """
    Run the full pipeline from current state to completion.

    Returns True if pipeline completed (all done), False if paused or timed out.
    """
    reg = load_registry(cfg.paths.raw)

    while True:
        state = determine_next_step(reg)

        if state.current_step == PipelineStep.DONE:
            on_status(
                f"Pipeline complete. {state.papers_linked} paper(s) linked in wiki."
            )
            return True

        if dry_run:
            on_status(f"Next step would be: {state.current_step.value}")
            on_status(
                f"  Pending: {state.papers_pending}, Submitted: {state.papers_submitted}, "
                f"Extracted: {state.papers_extracted}, Linked: {state.papers_linked}"
            )
            return True

        if state.current_step == PipelineStep.SUBMIT_EXTRACTION:
            on_status(
                f"Submitting {state.papers_pending} paper(s) for extraction..."
            )
            pending = [
                p for p in reg.papers.values()
                if p.extraction_status in ("pending", "queued")
            ]
            result = await submit_batch(pending, cfg.paths.raw, cfg)
            for p in pending:
                reg.papers[p.paper_id].extraction_status = "submitted"
                reg.papers[p.paper_id].extraction_batch_id = result.batch_id
            save_registry(reg, cfg.paths.raw)
            on_status(
                f"Submitted batch {result.batch_id}: {result.request_count} request(s)."
            )

            if not wait:
                on_status("Run 'scholarwiki process-batch --continue' after batch completes.")
                return False

        elif state.current_step == PipelineStep.POLL_EXTRACTION:
            if not wait:
                on_status(
                    f"Extraction batch {state.extraction_batch_id} in progress. "
                    "Run with --wait to poll, or --continue to check and resume."
                )
                return False

            on_status(f"Polling extraction batch {state.extraction_batch_id}...")
            completed = await poll_until_complete(
                state.extraction_batch_id, cfg, timeout_seconds, "Extraction"
            )
            if not completed:
                on_status("Extraction batch not yet complete. Try again later.")
                return False

            on_status("Collecting extraction results...")
            collect_result = await collect_batch(
                state.extraction_batch_id,
                reg,
                cfg.paths.raw,
                cfg.paths.staging,
                cfg.paths.wiki,
                cfg,
            )
            on_status(
                f"Extracted: {collect_result.extracted}  Partial: {collect_result.partial}"
            )
            reg = load_registry(cfg.paths.raw)

        elif state.current_step == PipelineStep.SUBMIT_LINKING:
            extracted = [
                p for p in reg.papers.values()
                if p.extraction_status == "extracted" and not p.linking_batch_ids
            ]
            on_status(f"Submitting {len(extracted)} paper(s) for linking...")
            # submit_link_batches writes linking_batch_ids to registry internally
            result = await submit_link_batches(
                extracted, reg, cfg.paths.raw, cfg.paths.staging, cfg.paths.wiki, cfg
            )
            on_status(
                f"Submitted: gpt5={result.gpt5_batch_id}, gpt41={result.gpt41_batch_id}"
            )
            reg = load_registry(cfg.paths.raw)

            if not wait:
                on_status("Run 'scholarwiki process-batch --continue' after batches complete.")
                return False

        elif state.current_step == PipelineStep.POLL_LINKING:
            if not wait:
                on_status("Linking batches in progress.")
                return False

            on_status("Polling linking batches...")
            all_done = True
            for category, batch_id in state.linking_batch_ids.items():
                completed = await poll_until_complete(
                    batch_id, cfg, timeout_seconds, category
                )
                if not completed:
                    on_status(f"Batch {category} ({batch_id}) not yet complete.")
                    all_done = False

            if not all_done:
                return False

            on_status("Collecting linking results and backfilling wiki...")
            collect_result = await collect_link_batches(
                reg, cfg.paths.raw, cfg.paths.staging, cfg.paths.wiki, cfg
            )
            on_status(f"Linked: {collect_result.linked}")
            for err in collect_result.errors:
                on_status(f"  ERROR: {err}")
            reg = load_registry(cfg.paths.raw)
