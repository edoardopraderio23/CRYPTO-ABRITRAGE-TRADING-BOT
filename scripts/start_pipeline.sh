#!/usr/bin/env bash
# One-shot launcher for the full data pipeline.
# Starts: Scout streamer + cycle emitter (both in background).
# Run this from the repo root: ./scripts/start_pipeline.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo ">>> Activating virtualenv"
# shellcheck disable=SC1091
source .venv/bin/activate

echo ">>> Setting DATABASE_URL"
export DATABASE_URL="postgresql://localhost:5432/omniarb"

echo ">>> Killing any old Scout / emitter processes"
pkill -f "src.scout.streamer"          2>/dev/null || true
pkill -f "src.executor.cycle_emitter"  2>/dev/null || true
sleep 1

echo ">>> Starting Scout streamer"
nohup python -m src.scout.streamer > scout.log 2>&1 &
SCOUT_PID=$!
echo "    Scout PID: $SCOUT_PID"

sleep 2

echo ">>> Starting cycle emitter"
nohup python -m src.executor.cycle_emitter > emitter.log 2>&1 &
EMITTER_PID=$!
echo "    Emitter PID: $EMITTER_PID"

sleep 3

echo
echo ">>> Verifying both processes are alive..."
if ps -p "$SCOUT_PID" > /dev/null && ps -p "$EMITTER_PID" > /dev/null; then
    echo "    ✓ Scout    (PID $SCOUT_PID)   is running."
    echo "    ✓ Emitter  (PID $EMITTER_PID) is running."
else
    echo "    !! At least one process died on startup."
    echo "       Check scout.log and emitter.log for errors."
    exit 1
fi

echo
echo ">>> Current database row counts:"
psql omniarb -c "SELECT venue, COUNT(*) FROM book_snapshots GROUP BY venue ORDER BY venue;"
psql omniarb -c "SELECT COUNT(*) AS cycles_total FROM cycles_detected;"

echo
echo ">>> Pipeline running. Tail logs with:"
echo "    tail -f scout.log      # Scout activity"
echo "    tail -f emitter.log    # Cycle detection activity"
echo
echo ">>> To stop the pipeline:"
echo "    ./scripts/stop_pipeline.sh"
echo
echo ">>> IMPORTANT: now run  'caffeinate -i'  in a separate terminal tab"
echo "    to prevent your Mac from sleeping overnight."
