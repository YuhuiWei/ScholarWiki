#!/usr/bin/env bash
# Rerun the full linking phase for all 15 papers, then email NOTIFY_EMAIL when done.
# Usage:
#   NOTIFY_EMAIL=you@example.com bash scripts/rerun_linking.sh
# Or edit NOTIFY_EMAIL below:
NOTIFY_EMAIL="${NOTIFY_EMAIL:-}"

POLL_INTERVAL=120   # seconds between status checks
MAX_WAIT=14400      # 4 hours max before giving up
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG="$PROJECT_DIR/logs/rerun_linking_$(date +%Y%m%d_%H%M%S).log"

mkdir -p "$PROJECT_DIR/logs"

log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG"; }

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

# ── Activate venv ────────────────────────────────────────────────────────────
if [ -f "/home/exacloud/gscratch/BDRL/Yuhui/.venv/bin/activate" ]; then
    source "/home/exacloud/gscratch/BDRL/Yuhui/.venv/bin/activate"
elif [ -f "$HOME/.venv/bin/activate" ]; then
    source "$HOME/.venv/bin/activate"
fi

cd "$PROJECT_DIR" || exit 1

log "=== ScholarWiki relink run starting ==="
log "Project: $PROJECT_DIR"
log "Notify: ${NOTIFY_EMAIL:-(none)}"

# ── Step 1: Reset papers and regenerate concept mappings ─────────────────────
# Always run — handles both 'linked' → 'extracted' resets and ledger rebuilds
# for papers already in 'extracted' state.
log ""
log "Step 1: Resetting paper states and regenerating concept_mapping.json..."
python "$PROJECT_DIR/scripts/reset_for_relink.py" 2>&1 | tee -a "$LOG"
if [ ${PIPESTATUS[0]} -ne 0 ]; then
    log "ERROR: reset_for_relink.py failed. Aborting."
    send_email "ScholarWiki relink FAILED" "Reset step failed. See $LOG"
    exit 1
fi

# ── Step 2: Submit link batches ──────────────────────────────────────────────
log ""
log "Step 2: Submitting link batches..."
scholarwiki link 2>&1 | tee -a "$LOG"
if [ ${PIPESTATUS[0]} -ne 0 ]; then
    log "ERROR: scholarwiki link failed. Aborting."
    send_email "ScholarWiki relink FAILED" "Link submit failed. See $LOG"
    exit 1
fi

# ── Step 3: Poll until batches complete ─────────────────────────────────────
log ""
log "Step 3: Polling for batch completion (every ${POLL_INTERVAL}s, max ${MAX_WAIT}s)..."
elapsed=0
all_done=false
while [ $elapsed -lt $MAX_WAIT ]; do
    sleep $POLL_INTERVAL
    elapsed=$((elapsed + POLL_INTERVAL))

    STATUS_OUT=$(scholarwiki link --status 2>&1)
    echo "$STATUS_OUT" | tee -a "$LOG"

    total=$(echo "$STATUS_OUT" | grep -c ":")
    completed=$(echo "$STATUS_OUT" | grep -c ": completed")
    if [ "$total" -gt 0 ] && [ "$completed" -eq "$total" ]; then
        log "All $total batch(es) completed after ${elapsed}s."
        all_done=true
        break
    fi
    log "Waiting... ($elapsed/${MAX_WAIT}s elapsed, $completed/$total batches done)"
done

if [ "$all_done" = false ]; then
    log "ERROR: Timed out waiting for batches after ${MAX_WAIT}s."
    send_email "ScholarWiki relink TIMED OUT" "Batches did not complete within ${MAX_WAIT}s. See $LOG"
    exit 1
fi

# ── Step 4: Collect results ──────────────────────────────────────────────────
log ""
log "Step 4: Collecting link batch results..."
scholarwiki link --collect 2>&1 | tee -a "$LOG"

# ── Step 5: Final stats ──────────────────────────────────────────────────────
log ""
log "Step 5: Final status:"
STATUS_SUMMARY=$(scholarwiki status 2>&1)
STATS=$(scholarwiki stats 2>&1)
echo "$STATUS_SUMMARY" | tee -a "$LOG"
echo "$STATS" | tee -a "$LOG"

# ── Step 6: Email ─────────────────────────────────────────────────────────────
send_email "ScholarWiki relink complete ✓" "$(cat <<EOF
ScholarWiki linking run finished successfully.

── Pipeline status ──
$STATUS_SUMMARY

── Wiki stats ──
$STATS

Full log: $LOG
EOF
)"

log "=== Done ==="
