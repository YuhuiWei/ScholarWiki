#!/usr/bin/env bash
# Submit and collect writing style pages independently of the main link batch.
# Run this AFTER the main batch completes (i.e., after you receive the email).
#
# Usage:
#   NOTIFY_EMAIL=weiy@ohsu.edu bash scripts/submit_collect_styles.sh

NOTIFY_EMAIL="${NOTIFY_EMAIL:-}"
POLL_INTERVAL=120
MAX_WAIT=10800   # 3 hours
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
STYLE_BATCH_FILE="$PROJECT_DIR/staging/style_only_batch_id.txt"
LOG="$PROJECT_DIR/logs/styles_$(date +%Y%m%d_%H%M%S).log"

mkdir -p "$PROJECT_DIR/logs"

log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG"; }

send_email() {
    local subject="$1" body="$2"
    [ -z "$NOTIFY_EMAIL" ] && { log "No NOTIFY_EMAIL — skipping."; return; }
    if command -v mail &>/dev/null; then
        echo "$body" | mail -s "$subject" "$NOTIFY_EMAIL"
        log "Email sent to $NOTIFY_EMAIL"
    else
        log "mail not found. Subject: $subject"
    fi
}

if [ -f "/home/exacloud/gscratch/BDRL/Yuhui/.venv/bin/activate" ]; then
    source "/home/exacloud/gscratch/BDRL/Yuhui/.venv/bin/activate"
fi
cd "$PROJECT_DIR" || exit 1

log "=== Style-only submit+collect ==="

# ── Submit style batch ────────────────────────────────────────────────────────
log "Submitting style batch..."
SUBMIT_OUT=$(python3 - <<'PYEOF' 2>&1
import asyncio, json, io, sys
from pathlib import Path
sys.path.insert(0, "src")
from scholarwiki.config import load_config
from scholarwiki.registry import load_registry
from scholarwiki.linking.pending_styles import resolve_styles_for_linking, save_pending_styles
from scholarwiki.linking.synthesis_prompts import STYLE_SYNTHESIS_SYSTEM
from openai import AsyncOpenAI
from datetime import datetime, timezone

cfg = load_config(Path("config.yaml"))
registry = load_registry(cfg.paths.raw)

def _paper_slug(entry):
    if entry and entry.wiki_source_page:
        return Path(entry.wiki_source_page).stem
    return entry.paper_id if entry else "unknown"

def _load_staging_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

async def main():
    style_clusters, updated_pending = resolve_styles_for_linking(
        cfg.paths.staging, min_papers=cfg.linking.min_papers_for_style
    )
    print(f"Style groups: {len(style_clusters)}", flush=True)
    if not style_clusters:
        print("NO_STYLES", flush=True)
        return

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    model = cfg.linking.style_model
    client = AsyncOpenAI()
    requests = []

    for slug, cluster in style_clusters.items():
        existing_page = ""
        page_path = cfg.paths.wiki / "writing" / f"{slug}.md"
        if page_path.exists():
            existing_page = page_path.read_text(encoding="utf-8")

        papers_text = ""
        for pid in cluster["paper_ids"]:
            entry = registry.papers.get(pid)
            paper_slug = _paper_slug(entry)
            writing = _load_staging_json(cfg.paths.staging / pid / "writing.json")
            papers_text += (
                f"\n[[{paper_slug}]] ({getattr(entry, 'year', '?') if entry else '?'}) — {writing.get('venue', '')}\n"
                f"  Venue type: {writing.get('venue_type', '')}\n"
                f"  Sections: {writing.get('structure', {}).get('section_order', [])}\n"
                f"  Opening sentence: {writing.get('introduction_pattern', {}).get('opening_sentence', '')}\n"
                f"  Intro strategy: {writing.get('introduction_pattern', {}).get('strategy', '')}\n"
                f"  Results headers: {writing.get('results_pattern', {}).get('example_headers', [])}\n"
                f"  Figure ref style: {writing.get('results_pattern', {}).get('figure_reference_style', '')}\n"
                f"  Quant reporting: {writing.get('results_pattern', {}).get('quantitative_reporting', '')}\n"
                f"  Discussion opening: {writing.get('discussion_pattern', {}).get('opening', '')}\n"
                f"  Hedging: {writing.get('discussion_pattern', {}).get('hedging_level', '')} — "
                f"{writing.get('discussion_pattern', {}).get('hedging_examples', [])}\n"
                f"  Transitions: {writing.get('language_patterns', {}).get('transition_phrases', [])}\n"
                f"  Common phrases: {writing.get('language_patterns', {}).get('common_phrases_by_context', {})}\n"
            )

        confidence = "high" if len(cluster["paper_ids"]) >= 2 else "low"
        venue = cluster["title"].split(" — ")[0] if " — " in cluster["title"] else cluster["title"]
        user_content = (
            f"Style slug: {slug}\nStyle title: {cluster['title']}\n"
            f"Venue: {venue}\nConfidence: {confidence}\n\n"
            f"EXISTING PAGE:\n{existing_page or '(new style page)'}\n\n"
            f"PAPERS IN THIS GROUP:\n{papers_text}\n\ntoday: {today}"
        )
        requests.append({
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
        })

    jsonl = "\n".join(json.dumps(r) for r in requests).encode("utf-8")
    file_obj = await client.files.create(
        file=("style_only.jsonl", io.BytesIO(jsonl), "application/jsonl"),
        purpose="batch",
    )
    batch = await client.batches.create(
        input_file_id=file_obj.id,
        endpoint="/v1/chat/completions",
        completion_window="24h",
    )
    save_pending_styles(cfg.paths.staging, updated_pending)
    print(f"BATCH_ID={batch.id}", flush=True)
    print(f"Submitted {len(requests)} style requests", flush=True)

asyncio.run(main())
PYEOF
)

echo "$SUBMIT_OUT" | tee -a "$LOG"

if echo "$SUBMIT_OUT" | grep -q "NO_STYLES"; then
    log "No style groups to synthesize."
    exit 0
fi

BATCH_ID=$(echo "$SUBMIT_OUT" | grep "^BATCH_ID=" | cut -d= -f2)
if [ -z "$BATCH_ID" ]; then
    log "ERROR: Could not get batch ID."
    send_email "Style batch FAILED" "Submit failed. See $LOG"
    exit 1
fi
echo "$BATCH_ID" > "$STYLE_BATCH_FILE"
log "Batch ID: $BATCH_ID"

# ── Poll until complete ───────────────────────────────────────────────────────
log "Polling for completion..."
elapsed=0
while [ $elapsed -lt $MAX_WAIT ]; do
    sleep $POLL_INTERVAL
    elapsed=$((elapsed + POLL_INTERVAL))
    STATUS=$(python3 -c "
import asyncio, sys
sys.path.insert(0, 'src')
from openai import AsyncOpenAI
async def main():
    b = await AsyncOpenAI().batches.retrieve('$BATCH_ID')
    print(b.status, b.request_counts.completed, b.request_counts.total)
asyncio.run(main())
" 2>/dev/null)
    log "Status: $STATUS (${elapsed}s elapsed)"
    echo "$STATUS" | grep -q "^completed" && break
done

# ── Collect ───────────────────────────────────────────────────────────────────
log "Collecting style pages..."
COLLECT_OUT=$(python3 - <<'PYEOF' 2>&1
import asyncio, json, sys
from pathlib import Path
sys.path.insert(0, "src")
from scholarwiki.config import load_config
from scholarwiki.linking.writing_styles import write_style_page
from openai import AsyncOpenAI

cfg = load_config(Path("config.yaml"))
batch_id = Path("staging/style_only_batch_id.txt").read_text().strip()

async def main():
    client = AsyncOpenAI()
    batch = await client.batches.retrieve(batch_id)
    if not batch.output_file_id:
        print(f"ERROR: no output file for {batch_id}", file=sys.stderr)
        return
    file_content = await client.files.content(batch.output_file_id)
    written = 0
    for line in file_content.text.strip().split("\n"):
        if not line.strip():
            continue
        item = json.loads(line)
        custom_id = item.get("custom_id", "")
        if item.get("error"):
            print(f"ERROR {custom_id}: {item['error']}")
            continue
        try:
            markdown = item["response"]["body"]["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as e:
            print(f"PARSE ERROR {custom_id}: {e}")
            continue
        if custom_id.startswith("style_"):
            slug = custom_id[len("style_"):]
            write_style_page(cfg.paths.wiki, slug, markdown)
            print(f"  Wrote style page: {slug}")
            written += 1
    print(f"Total style pages written: {written}")

asyncio.run(main())
PYEOF
)
echo "$COLLECT_OUT" | tee -a "$LOG"

log "=== Style pages done ==="
STATS=$(scholarwiki stats 2>&1)
echo "$STATS" | tee -a "$LOG"

send_email "ScholarWiki style pages complete ✓" "$(cat <<EOF
Writing style pages have been synthesized.

$COLLECT_OUT

── Wiki stats ──
$STATS

Log: $LOG
EOF
)"
