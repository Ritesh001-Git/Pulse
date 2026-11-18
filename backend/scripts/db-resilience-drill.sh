#!/usr/bin/env bash
# Pulse DB-resilience drill: verifies the API and monitoring loop survive a DB outage.
# Usage: bash scripts/db-resilience-drill.sh
set -u
BASE=http://localhost:8000

step() { echo; echo "=== $1 ==="; }

step "0. Baseline (DB up)"
curl -s -o /dev/null -w "app: %{http_code}\n" "$BASE/health"
curl -s "$BASE/health/db"; echo

step "1. Stopping PostgreSQL"
brew services stop postgresql@18 >/dev/null
sleep 3

step "2. Requests while DB is down (expect 200 / 503 / 503)"
curl -s -o /dev/null -w "/health: %{http_code}\n" "$BASE/health"
curl -s -w " [%{http_code}]" "$BASE/health/db"; echo
curl -s -w " [%{http_code}]" -X POST "$BASE/dev/seed"; echo

step "3. Waiting 35s to observe the monitoring loop"
sleep 35
LOG=${PULSE_LOG:-/tmp/pulse-uvicorn.log}
echo "monitor log lines during outage:"
grep "pulse.monitor" "$LOG" | tail -6

step "4. App process still alive?"
pgrep -f "uvicorn app.main" >/dev/null && echo "uvicorn: RUNNING" || echo "uvicorn: DEAD"

step "5. Restarting PostgreSQL (recovery)"
brew services start postgresql@18 >/dev/null
sleep 6

step "6. Post-recovery requests"
curl -s -w " [%{http_code}]" "$BASE/health/db"; echo

step "7. Monitoring loop recovered? (check_results should grow)"
sleep 35
curl -s "$BASE/health/db"; echo
echo
echo "=== drill complete ==="
