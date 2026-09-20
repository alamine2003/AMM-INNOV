#!/usr/bin/env bash
# Enchaîne des scénarios ; un journal par scénario dans results/<nom>-<label>.log
#   ./run_batch.sh avant s01_backend_crash s11a_backend_sigterm ...
set -u
label="$1"; shift
cd "$(dirname "$0")"
for name in "$@"; do
  echo "[$(date +%H:%M:%S)] >>> $name ($label)"
  python3 scenarios.py "$name" --label "$label" > "results/$name-$label.log" 2>&1
  echo "[$(date +%H:%M:%S)] <<< $name exit=$?"
done
