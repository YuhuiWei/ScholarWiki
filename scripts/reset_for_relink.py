#!/usr/bin/env python3
"""
Reset all papers from 'linked' → 'extracted' and regenerate concept_mapping.json
using the updated generate_concept_mapping (which now includes key_experiment_summary).
Also rebuilds pending_concepts.json and pending_styles.json from the new mappings.

Run from ScholarWiki project root:
    python scripts/reset_for_relink.py
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from scholarwiki.config import load_config
from scholarwiki.registry import load_registry, save_registry
from scholarwiki.extraction.concept_mapping import generate_concept_mapping
from scholarwiki.linking.concept_match import list_concept_index
from scholarwiki.linking.pending_concepts import save_pending, update_pending_from_mappings
from scholarwiki.linking.pending_styles import save_pending_styles, update_pending_styles


def main():
    cfg = load_config(Path("config.yaml"))
    registry = load_registry(cfg.paths.raw)
    staging_dir = cfg.paths.staging
    wiki_dir = cfg.paths.wiki

    # Accept both "linked" (full reset) and "extracted" (just regenerate mappings + ledger)
    papers_to_reset = [p for p in registry.papers.values() if p.extraction_status == "linked"]
    papers_extracted = [p for p in registry.papers.values() if p.extraction_status == "extracted"]
    papers = papers_to_reset + papers_extracted
    print(f"Resetting {len(papers_to_reset)} papers from 'linked' → 'extracted'")
    print(f"Regenerating mappings for {len(papers_extracted)} already-extracted papers")

    # Step 1: Reset linked papers and clear all batch IDs (to allow resubmit)
    for paper in papers_to_reset:
        paper.extraction_status = "extracted"
    for paper in papers:
        paper.linking_batch_ids = {}

    # Step 2: Regenerate concept_mapping.json for each paper
    concept_index = list_concept_index(wiki_dir / "concepts")
    regenerated = []
    for paper in papers:
        paper_staging = staging_dir / paper.paper_id
        required = ["knowledge.json", "roadmap.json", "logic.json", "writing.json", "experiment.json"]
        missing = [f for f in required if not (paper_staging / f).exists()]
        if missing:
            print(f"  SKIP {paper.paper_id[:8]}  {paper.title[:50]} — missing: {', '.join(missing)}")
            continue

        mapping = generate_concept_mapping(paper.paper_id, paper_staging, concept_index)
        out_path = paper_staging / "concept_mapping.json"
        tmp = out_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(mapping, indent=2), encoding="utf-8")
        tmp.replace(out_path)
        regenerated.append(paper.paper_id)
        n_concepts = len(mapping["concept_contributions"])
        kex = mapping["pattern_signals"].get("key_experiment_summary", "")[:60]
        print(f"  OK   {paper.paper_id[:8]}  {paper.title[:40]}  ({n_concepts} concepts, kex={kex!r})")

    print(f"\nRegenerated {len(regenerated)}/{len(papers)} concept mappings")

    # Step 3: Rebuild pending ledgers from scratch
    save_pending(staging_dir, {"concepts": {}})
    save_pending_styles(staging_dir, {"papers": {}})
    if regenerated:
        update_pending_from_mappings(staging_dir, regenerated)
        update_pending_styles(staging_dir, regenerated)

    pending_path = staging_dir / "pending_concepts.json"
    pending_data = json.loads(pending_path.read_text())
    n_concepts = len(pending_data["concepts"])
    multi = sum(1 for v in pending_data["concepts"].values() if len(v.get("papers", {})) >= 2)
    print(f"Rebuilt pending_concepts.json: {n_concepts} concepts, {multi} with ≥2 papers")

    styles_path = staging_dir / "pending_styles.json"
    styles_data = json.loads(styles_path.read_text())
    print(f"Rebuilt pending_styles.json: {len(styles_data['papers'])} papers")

    # Step 4: Save registry
    save_registry(registry, cfg.paths.raw)
    print("\nRegistry saved. Ready for: scholarwiki link")


if __name__ == "__main__":
    main()
