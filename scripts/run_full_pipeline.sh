#!/usr/bin/env bash
# Full pipeline: extract (submit → poll → collect) → link (submit → poll → collect)
# Usage:
#   NOTIFY_EMAIL=you@example.com nohup bash scripts/run_full_pipeline.sh > logs/pipeline.out 2>&1 &
NOTIFY_EMAIL="${NOTIFY_EMAIL:-}"

POLL_INTERVAL=120   # seconds between status checks
MAX_WAIT_EXTRACT=21600  # 6 hours for extraction
MAX_WAIT_LINK=14400     # 4 hours for linking
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG="$PROJECT_DIR/logs/full_pipeline_$(date +%Y%m%d_%H%M%S).log"

mkdir -p "$PROJECT_DIR/logs"

log()        { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG"; }
log_header() { log ""; log "═══ $* ═══"; }

send_email() {
    local subject="$1"
    local body="$2"
    if [ -z "$NOTIFY_EMAIL" ]; then
        log "No NOTIFY_EMAIL set — skipping email notification."
        return
    fi
    if command -v mail &>/dev/null; then
        echo "$body" | mail -s "$subject" "$NOTIFY_EMAIL"
        log "Email sent to $NOTIFY_EMAIL"
    elif command -v sendmail &>/dev/null; then
        printf "Subject: %s\n\n%s" "$subject" "$body" | sendmail "$NOTIFY_EMAIL"
        log "Email sent via sendmail to $NOTIFY_EMAIL"
    else
        log "WARNING: No mail command found — email skipped. Subject: $subject"
    fi
}

# ── Activate venv ─────────────────────────────────────────────────────────────
if [ -f "/home/exacloud/gscratch/BDRL/Yuhui/.venv/bin/activate" ]; then
    source "/home/exacloud/gscratch/BDRL/Yuhui/.venv/bin/activate"
elif [ -f "$HOME/.venv/bin/activate" ]; then
    source "$HOME/.venv/bin/activate"
fi

cd "$PROJECT_DIR" || exit 1

log_header "ScholarWiki full pipeline starting"
log "Project: $PROJECT_DIR"
log "Notify:  ${NOTIFY_EMAIL:-(none)}"

# ════════════════════════════════════════════════════════════
# PHASE 1: EXTRACTION
# ════════════════════════════════════════════════════════════
log_header "Phase 1: Extraction — submit"
scholarwiki extract --submit 2>&1 | tee -a "$LOG"
if [ ${PIPESTATUS[0]} -ne 0 ]; then
    log "ERROR: extract --submit failed. Aborting."
    send_email "ScholarWiki pipeline FAILED" "extract --submit failed. See $LOG"
    exit 1
fi

log ""
log "Polling for extraction completion (every ${POLL_INTERVAL}s, max ${MAX_WAIT_EXTRACT}s)..."
elapsed=0
all_done=false
while [ $elapsed -lt $MAX_WAIT_EXTRACT ]; do
    sleep $POLL_INTERVAL
    elapsed=$((elapsed + POLL_INTERVAL))

    STATUS_OUT=$(scholarwiki extract --status 2>&1)
    echo "$STATUS_OUT" | tee -a "$LOG"

    total=$(echo "$STATUS_OUT"    | grep -c "batch_")
    completed=$(echo "$STATUS_OUT" | grep -c "completed")
    if [ "$total" -gt 0 ] && [ "$completed" -eq "$total" ]; then
        log "All $total extraction batch(es) completed after ${elapsed}s."
        all_done=true
        break
    fi
    log "Waiting... ($elapsed/${MAX_WAIT_EXTRACT}s elapsed, $completed/$total batches done)"
done

if [ "$all_done" = false ]; then
    log "ERROR: Timed out waiting for extraction after ${MAX_WAIT_EXTRACT}s."
    send_email "ScholarWiki pipeline TIMED OUT (extraction)" "Extraction did not complete within ${MAX_WAIT_EXTRACT}s. See $LOG"
    exit 1
fi

log_header "Phase 1: Extraction — collect"
scholarwiki extract --collect 2>&1 | tee -a "$LOG"
if [ ${PIPESTATUS[0]} -ne 0 ]; then
    log "ERROR: extract --collect failed. Aborting."
    send_email "ScholarWiki pipeline FAILED" "extract --collect failed. See $LOG"
    exit 1
fi

# Verify papers reached 'extracted' state
EXTRACTED=$(python -c "
import json; from pathlib import Path
reg = json.loads(Path('raw/registry.json').read_text())
n = sum(1 for p in reg['papers'].values() if p.get('extraction_status') == 'extracted')
print(n)
" 2>/dev/null)
log "Papers now in 'extracted' state: ${EXTRACTED}"

# ════════════════════════════════════════════════════════════
# PHASE 2: LINKING
# ════════════════════════════════════════════════════════════
log_header "Phase 2: Linking — submit"
scholarwiki link 2>&1 | tee -a "$LOG"
if [ ${PIPESTATUS[0]} -ne 0 ]; then
    log "ERROR: scholarwiki link failed. Aborting."
    send_email "ScholarWiki pipeline FAILED" "Link submit failed. See $LOG"
    exit 1
fi

log ""
log "Polling for link batch completion (every ${POLL_INTERVAL}s, max ${MAX_WAIT_LINK}s)..."
elapsed=0
all_done=false
while [ $elapsed -lt $MAX_WAIT_LINK ]; do
    sleep $POLL_INTERVAL
    elapsed=$((elapsed + POLL_INTERVAL))

    STATUS_OUT=$(scholarwiki link --status 2>&1)
    echo "$STATUS_OUT" | tee -a "$LOG"

    total=$(echo "$STATUS_OUT"    | grep -c ":")
    completed=$(echo "$STATUS_OUT" | grep -c ": completed")
    if [ "$total" -gt 0 ] && [ "$completed" -eq "$total" ]; then
        log "All $total link batch(es) completed after ${elapsed}s."
        all_done=true
        break
    fi
    log "Waiting... ($elapsed/${MAX_WAIT_LINK}s elapsed, $completed/$total batches done)"
done

if [ "$all_done" = false ]; then
    log "ERROR: Timed out waiting for link batches after ${MAX_WAIT_LINK}s."
    send_email "ScholarWiki pipeline TIMED OUT (linking)" "Linking did not complete within ${MAX_WAIT_LINK}s. See $LOG"
    exit 1
fi

log_header "Phase 2: Linking — collect"
scholarwiki link --collect 2>&1 | tee -a "$LOG"

# ════════════════════════════════════════════════════════════
# DONE
# ════════════════════════════════════════════════════════════
log_header "Done"
STATUS_SUMMARY=$(scholarwiki status 2>&1)
STATS=$(scholarwiki stats 2>&1)
echo "$STATUS_SUMMARY" | tee -a "$LOG"
echo "$STATS" | tee -a "$LOG"

send_email "ScholarWiki full pipeline complete ✓" "$(cat <<EOF
ScholarWiki full pipeline (extract → link) finished successfully.

── Pipeline status ──
$STATUS_SUMMARY

── Wiki stats ──
$STATS

Full log: $LOG
EOF
)"

log "=== All done ==="
