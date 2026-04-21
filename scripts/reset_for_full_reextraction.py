#!/usr/bin/env python3
"""Reset all papers for full re-extraction (Option B).

- Deletes staging JSONs for all papers
- Resets extraction_status to 'pending'
- Clears extraction_batch_id and linking_batch_ids
- Clears pending_concepts.json and pending_styles.json
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

REPO = Path(__file__).parent.parent
REGISTRY_PATH = REPO / "raw" / "registry.json"
STAGING_DIR = REPO / "staging"

STAGING_FILES = [
    "knowledge.json",
    "roadmap.json",
    "logic.json",
    "writing.json",
    "experiment.json",
    "concept_mapping.json",
]


def main() -> None:
    reg_data = json.loads(REGISTRY_PATH.read_text())
    papers = reg_data.get("papers", {})

    deleted_files = 0
    reset_papers = 0

    for paper_id, entry in papers.items():
        paper_staging = STAGING_DIR / paper_id
        if paper_staging.exists():
            for fname in STAGING_FILES:
                fpath = paper_staging / fname
                if fpath.exists():
                    fpath.unlink()
                    deleted_files += 1
                    print(f"  deleted {paper_id}/{fname}")

        # Reset registry entry
        entry["extraction_status"] = "pending"
        entry["extraction_batch_id"] = None
        entry["linking_batch_ids"] = {}
        entry["linked_at"] = None
        reset_papers += 1
        print(f"  reset {paper_id} ({entry.get('title', '')[:50]})")

    # Atomic write registry
    tmp = REGISTRY_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(reg_data, indent=2, default=str))
    tmp.replace(REGISTRY_PATH)
    print(f"\nRegistry updated: {reset_papers} papers reset to 'pending'")

    # Clear pending ledgers
    for ledger in ["pending_concepts.json", "pending_styles.json"]:
        lpath = STAGING_DIR / ledger
        if ledger == "pending_concepts.json":
            lpath.write_text(json.dumps({"concepts": {}}, indent=2))
        else:
            lpath.write_text(json.dumps({"papers": {}}, indent=2))
        print(f"Cleared {ledger}")

    # Remove style_only_batch_id.txt if present
    sid = STAGING_DIR / "style_only_batch_id.txt"
    if sid.exists():
        sid.unlink()
        print("Removed style_only_batch_id.txt")

    print(f"\nDone. Deleted {deleted_files} staging files, reset {reset_papers} papers.")


if __name__ == "__main__":
    main()
