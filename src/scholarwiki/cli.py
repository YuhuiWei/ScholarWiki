from __future__ import annotations
from pathlib import Path
from typing import Optional
import asyncio
import typer
from .config import load_config
from .registry import load_registry, get_pending, save_registry
from .ingest.nexus import ingest_nexus_inbox
from .ingest.manual import ingest_manual_inbox
from .zotero import sync_pending
from .extraction.batch import (
    submit_batch, get_batch_status, collect_batch, retry_failed_modules,
)
from .linking.batch import (
    submit_link_batches,
    get_link_batch_status,
    collect_link_batches,
    LinkBatchCollectResult,
)

app = typer.Typer(help="ScholarWiki — academic knowledge wiki builder")

_DEFAULT_CONFIG = Path("config.yaml")


@app.command()
def ingest(
    config: Path = typer.Option(_DEFAULT_CONFIG, "--config", "-c"),
) -> None:
    """Process nexus_inbox and manual_inbox: move PDFs, register, create L1 pages."""
    cfg = load_config(config)
    nexus_result = ingest_nexus_inbox(cfg)
    manual_result = ingest_manual_inbox(cfg, interactive=False)
    total = nexus_result.new_papers + manual_result.new_papers
    if total == 0:
        typer.echo("Nothing new to ingest.")
    else:
        typer.echo(f"Ingested {total} new paper(s).")
    if nexus_result.skipped_duplicates + manual_result.skipped_duplicates > 0:
        typer.echo(f"Skipped {nexus_result.skipped_duplicates + manual_result.skipped_duplicates} duplicate(s).")
    if nexus_result.manual_pending > 0:
        typer.echo(f"{nexus_result.manual_pending} paper(s) added to manual.md (download failed).")
    if manual_result.manual_matched > 0:
        typer.echo(f"{manual_result.manual_matched} manual PDF(s) matched and ingested.")
    zotero_failures = nexus_result.zotero_failed + manual_result.zotero_failed
    if zotero_failures > 0:
        typer.echo(f"{zotero_failures} paper(s) failed Zotero sync. Run 'scholarwiki zotero-sync' to retry.")
    for err in nexus_result.errors + manual_result.errors:
        typer.echo(f"  ERROR: {err}", err=True)


@app.command()
def status(
    config: Path = typer.Option(_DEFAULT_CONFIG, "--config", "-c"),
) -> None:
    """Show pipeline status summary."""
    cfg = load_config(config)
    reg = load_registry(cfg.paths.raw)
    s = reg.stats
    typer.echo(f"Total papers:       {s.total}")
    typer.echo(f"Pending extraction: {s.pending_extraction}")
    typer.echo(f"Queued:             {s.queued}")
    typer.echo(f"Submitted (batch):  {s.submitted}")
    typer.echo(f"Extracted:          {s.extracted}")
    typer.echo(f"Linked:             {s.linked}")
    typer.echo(f"Zotero unsynced:    {s.zotero_unsynced}")


@app.command()
def queue(
    config: Path = typer.Option(_DEFAULT_CONFIG, "--config", "-c"),
    add: Optional[str] = typer.Option(None, "--add", help="paper_id to add to queue"),
) -> None:
    """List papers pending extraction, or add one by paper_id."""
    cfg = load_config(config)
    reg = load_registry(cfg.paths.raw)
    if add:
        if add not in reg.papers:
            typer.echo(f"paper_id {add!r} not found in registry.", err=True)
            raise typer.Exit(1)
        reg.papers[add].extraction_status = "queued"
        from .registry import save_registry
        save_registry(reg, cfg.paths.raw)
        typer.echo(f"Added {add} to extraction queue.")
        return
    pending = get_pending(reg)
    if not pending:
        typer.echo("No papers pending extraction.")
        return
    typer.echo(f"{len(pending)} paper(s) pending extraction:\n")
    for p in pending:
        typer.echo(f"  {p.paper_id}  {p.year or '?'}  {p.title[:70]}")


@app.command()
def extract(
    config: Path = typer.Option(_DEFAULT_CONFIG, "--config", "-c"),
    submit: bool = typer.Option(False, "--submit", help="Submit pending papers to OpenAI Batch API"),
    status: bool = typer.Option(False, "--status", help="Check status of submitted batch jobs"),
    collect: bool = typer.Option(False, "--collect", help="Collect completed batch results"),
    retry_failed: bool = typer.Option(False, "--retry-failed", help="Resubmit failed modules"),
) -> None:
    """Submit papers to OpenAI Batch API, check status, or collect results."""
    flags = [submit, status, collect, retry_failed]
    if sum(flags) != 1:
        typer.echo("Specify exactly one of: --submit, --status, --collect, --retry-failed", err=True)
        raise typer.Exit(1)

    cfg = load_config(config)
    reg = load_registry(cfg.paths.raw)

    if submit:
        pending = [p for p in reg.papers.values() if p.extraction_status in ("pending", "queued")]
        if not pending:
            typer.echo("No papers pending extraction.")
            return
        typer.echo(f"Submitting {len(pending)} paper(s) to OpenAI Batch API...")
        result = asyncio.run(submit_batch(pending, cfg.paths.raw, cfg))
        for paper in pending:
            reg.papers[paper.paper_id].extraction_status = "submitted"
            reg.papers[paper.paper_id].extraction_batch_id = result.batch_id
        save_registry(reg, cfg.paths.raw)
        typer.echo(f"Submitted batch {result.batch_id}: {len(pending)} papers, {result.request_count} requests.")

    elif status:
        submitted = [p for p in reg.papers.values() if p.extraction_status == "submitted"]
        if not submitted:
            typer.echo("No submitted batches.")
            return
        batch_ids = {p.extraction_batch_id for p in submitted if p.extraction_batch_id}
        for bid in sorted(batch_ids):
            info = asyncio.run(get_batch_status(bid, cfg))
            counts = info["request_counts"]
            typer.echo(
                f"Batch {bid}: {info['status']} "
                f"({counts['completed']}/{counts['total']} requests complete)"
            )

    elif collect:
        submitted = [p for p in reg.papers.values() if p.extraction_status == "submitted"]
        if not submitted:
            typer.echo("No submitted batches to collect.")
            return
        batch_ids = {p.extraction_batch_id for p in submitted if p.extraction_batch_id}
        collect_result = None
        for bid in sorted(batch_ids):
            typer.echo(f"Collecting batch {bid}...")
            collect_result = asyncio.run(
                collect_batch(bid, reg, cfg.paths.raw, cfg.paths.staging, cfg.paths.wiki, cfg)
            )
            if collect_result is None:
                typer.echo(f"  Batch {bid}: no result returned.", err=True)
                continue
            typer.echo(f"  Extracted: {collect_result.extracted}  Partial: {collect_result.partial}")
            for pid, mods in collect_result.failed_modules.items():
                typer.echo(f"  {pid}: failed modules: {', '.join(mods)}")
            for err in collect_result.errors:
                typer.echo(f"  ERROR: {err}", err=True)
        if collect_result and collect_result.partial > 0:
            typer.echo("Run 'scholarwiki extract --retry-failed' to resubmit failures.")

    elif retry_failed:
        needs_retry = [p for p in reg.papers.values() if p.failed_modules]
        if not needs_retry:
            typer.echo("No papers with failed modules.")
            return
        total_mods = sum(len(p.failed_modules) for p in needs_retry)
        typer.echo(f"{len(needs_retry)} paper(s) with failed modules. Resubmitting {total_mods} requests...")
        result = asyncio.run(retry_failed_modules(reg, cfg.paths.raw, cfg))
        if result.batch_id:
            typer.echo(f"Submitted retry batch {result.batch_id}.")
        else:
            typer.echo("Nothing to retry.")


@app.command()
def link(
    config: Path = typer.Option(_DEFAULT_CONFIG, "--config", "-c"),
    status: bool = typer.Option(False, "--status", help="Check status of in-progress link batch jobs"),
    collect: bool = typer.Option(False, "--collect", help="Collect completed link batches and run backfill"),
) -> None:
    """Submit linking batches, check status, or collect results."""
    if status and collect:
        typer.echo("Specify at most one of: --status, --collect", err=True)
        raise typer.Exit(1)

    cfg = load_config(config)
    reg = load_registry(cfg.paths.raw)

    if status:
        # Collect all unique (category, batch_id) pairs from registry entries
        batch_ids_by_cat: dict[str, set[str]] = {}
        for entry in reg.papers.values():
            for category, bid in entry.linking_batch_ids.items():
                if bid:
                    batch_ids_by_cat.setdefault(category, set()).add(bid)
        if not batch_ids_by_cat:
            typer.echo("No in-progress link batches.")
            return
        # Check status for every unique batch ID across all categories
        all_unique_bids = {bid for bids in batch_ids_by_cat.values() for bid in bids}
        # Build a flat dict mapping each unique bid to one of its categories (for display)
        bid_to_category: dict[str, str] = {}
        for category, bids in batch_ids_by_cat.items():
            for bid in bids:
                bid_to_category[bid] = category
        for bid in sorted(all_unique_bids):
            # get_link_batch_status expects dict[str, str] category -> bid
            status_map = asyncio.run(get_link_batch_status({bid_to_category[bid]: bid}, cfg))
            for category, info in status_map.items():
                rc = info.get("request_counts", {})
                typer.echo(
                    f"{category} ({bid}): {info['status']} "
                    f"({rc.get('completed', 0)}/{rc.get('total', 0)} requests complete)"
                )

    elif collect:
        linked_papers = [p for p in reg.papers.values() if p.linking_batch_ids]
        if not linked_papers:
            typer.echo("No papers with link batches to collect.")
            return
        typer.echo("Collecting link batches...")
        result = asyncio.run(
            collect_link_batches(reg, cfg.paths.raw, cfg.paths.staging, cfg.paths.wiki, cfg)
        )
        typer.echo(f"  Linked: {result.linked}")
        for err in result.errors:
            typer.echo(f"  ERROR: {err}", err=True)

    else:
        # Submit
        to_link = [
            p for p in reg.papers.values()
            if p.extraction_status == "extracted" and not p.linking_batch_ids
        ]
        if not to_link:
            typer.echo("No extracted papers to link.")
            return
        typer.echo(f"Submitting link batches for {len(to_link)} paper(s)...")
        result = asyncio.run(
            submit_link_batches(
                to_link, reg, cfg.paths.raw, cfg.paths.staging, cfg.paths.wiki, cfg
            )
        )
        typer.echo(
            f"Submitted: gpt5={result.gpt5_batch_id}, gpt41={result.gpt41_batch_id}"
        )
        typer.echo(
            f"Concepts: {result.concept_count}  Patterns: {result.pattern_count}  Styles: {result.style_count}"
        )


@app.command(name="process-batch")
def process_batch_cmd(
    config: Path = typer.Option(_DEFAULT_CONFIG, "--config", "-c"),
    wait: bool = typer.Option(False, "--wait", help="Poll until all batches complete"),
    no_wait: bool = typer.Option(False, "--no-wait", help="Submit and exit immediately"),
    continue_: bool = typer.Option(False, "--continue", help="Resume from current state"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show next step without executing"),
    timeout: str = typer.Option("6h", "--timeout", help="Max wait time (e.g., 6h, 30m, 3600)"),
    notify: Optional[str] = typer.Option(None, "--notify", help="Email address to notify when pipeline finishes"),
) -> None:
    """Full pipeline: ingest → extract → link. Chains all steps automatically."""
    from .pipeline import run_pipeline, parse_timeout

    cfg = load_config(config)

    if not dry_run:
        from .ingest.nexus import ingest_nexus_inbox
        from .ingest.manual import ingest_manual_inbox
        nexus_result = ingest_nexus_inbox(cfg)
        manual_result = ingest_manual_inbox(cfg, interactive=False)
        total_new = nexus_result.new_papers + manual_result.new_papers
        if total_new > 0:
            typer.echo(f"Ingested {total_new} new paper(s).")

    should_wait = wait or continue_
    timeout_seconds = parse_timeout(timeout)

    outcome = "completed"
    completed = False
    try:
        completed = asyncio.run(
            run_pipeline(
                cfg,
                wait=should_wait,
                timeout_seconds=timeout_seconds,
                dry_run=dry_run,
                on_status=typer.echo,
            )
        )
        if not completed:
            outcome = "paused"
    except Exception as exc:
        outcome = f"failed: {exc}"
        typer.echo(f"Pipeline error: {exc}", err=True)

    if not completed and not dry_run:
        typer.echo("Pipeline paused. Run with --continue to resume.")

    if notify and not dry_run:
        from .notify import send_notification
        from .registry import load_registry as _load_reg
        reg = _load_reg(cfg.paths.raw)
        s = reg.stats
        if outcome == "completed":
            subject = "ScholarWiki: pipeline complete"
            body = (
                f"Your ScholarWiki pipeline finished successfully.\n\n"
                f"Papers linked:    {s.linked}\n"
                f"Papers extracted: {s.extracted}\n"
                f"Papers pending:   {s.pending_extraction}\n\n"
                f"Open wiki/ in Obsidian to browse the results.\n"
            )
        elif outcome == "paused":
            subject = "ScholarWiki: pipeline paused (batch still running)"
            body = (
                f"The pipeline submitted its batches and is waiting for OpenAI to finish.\n\n"
                f"Run the following to resume when ready:\n"
                f"  scholarwiki process-batch --continue --notify {notify}\n\n"
                f"Current status — linked: {s.linked}, extracted: {s.extracted}, "
                f"submitted: {s.submitted}, pending: {s.pending_extraction}\n"
            )
        else:
            subject = "ScholarWiki: pipeline error"
            body = (
                f"The pipeline encountered an error:\n\n  {outcome}\n\n"
                f"Run 'scholarwiki status' to check the current state.\n"
            )
        try:
            send_notification(to=notify, subject=subject, body=body)
            typer.echo(f"Notification sent to {notify}.")
        except Exception as exc:
            typer.echo(f"Could not send notification: {exc}", err=True)


@app.command()
def lint(
    config: Path = typer.Option(_DEFAULT_CONFIG, "--config", "-c"),
) -> None:
    """Health-check the wiki for orphans, missing links, and inconsistencies."""
    from .maintenance.lint import run_lint

    cfg = load_config(config)
    reg = load_registry(cfg.paths.raw)
    report = run_lint(cfg.paths.wiki, reg)

    if not report.issues:
        typer.echo("All clear — no issues found.")
        return

    icons = {"error": "x", "warning": "!", "info": "i"}
    for issue in report.issues:
        icon = icons.get(issue.severity, "?")
        loc = f" ({issue.file})" if issue.file else ""
        typer.echo(f"  [{icon}] [{issue.category}] {issue.message}{loc}")

    typer.echo(
        f"\n{report.error_count} error(s), "
        f"{report.warning_count} warning(s), "
        f"{report.info_count} info"
    )

    if report.error_count:
        raise typer.Exit(1)


@app.command()
def stats(
    config: Path = typer.Option(_DEFAULT_CONFIG, "--config", "-c"),
) -> None:
    """Show knowledge base statistics."""
    from .maintenance.stats import generate_stats

    cfg = load_config(config)
    reg = load_registry(cfg.paths.raw)
    typer.echo(generate_stats(cfg.paths.wiki, reg))


@app.command(name="serve-mcp")
def serve_mcp_cmd(
    config: Path = typer.Option(_DEFAULT_CONFIG, "--config", "-c"),
) -> None:
    """Start MCP server for Claude Code integration (stdio transport)."""
    from .mcp.server import run_server
    asyncio.run(run_server(str(config)))


@app.command(name="zotero-sync")
def zotero_sync(
    config: Path = typer.Option(_DEFAULT_CONFIG, "--config", "-c"),
) -> None:
    """Retry pushing unsynced papers to Zotero."""
    cfg = load_config(config)
    reg = load_registry(cfg.paths.raw)
    unsynced_count = reg.stats.zotero_unsynced
    if unsynced_count == 0:
        typer.echo("All papers are synced to Zotero.")
        return
    typer.echo(f"Syncing {unsynced_count} unsynced paper(s) to Zotero...")
    result = sync_pending(reg, cfg, cfg.paths.raw)
    typer.echo(f"Synced: {result.synced}  Failed: {result.failed}")
    if result.failed > 0:
        for err in result.errors:
            typer.echo(f"  ERROR: {err}", err=True)
        typer.echo("Run 'scholarwiki zotero-sync' again to retry remaining failures.")
