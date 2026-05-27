#!/usr/bin/env bash
# Cleanly stop the Scout streamer and cycle emitter.
echo ">>> Stopping pipeline..."
pkill -f "src.scout.streamer"          2>/dev/null && echo "    Scout stopped."   || echo "    Scout was not running."
pkill -f "src.executor.cycle_emitter"  2>/dev/null && echo "    Emitter stopped." || echo "    Emitter was not running."
echo ">>> Done."
