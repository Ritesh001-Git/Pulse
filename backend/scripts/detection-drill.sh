#!/usr/bin/env bash
# Detection-scenario harness: drives on-demand checks through the API against
# the starter kit and asserts streak-based detection + worst-in-streak severity.
set -u
BASE=http://localhost:8000

jsonget() { python3 -c "import json,sys; d=json.load(sys.stdin); print($1)"; }

echo "== Scenario harness =="
# pick the payments service as the test target
PAY_ID=$(curl -s $BASE/api/services | python3 -c "import json,sys; d=json.load(sys.stdin); print([s['id'] for s in d if s['name']=='payments'][0])")

reset_state() {
  # clear check history + incidents for clean per-scenario runs
  psql postgres://pulse:pulse@localhost:5432/pulse -q -c "DELETE FROM timeline_events; DELETE FROM notifications; DELETE FROM incidents; DELETE FROM check_results;" >/dev/null
  curl -s -X POST localhost:7002/control/reset -o /dev/null
}

severity_of_active() {
  curl -s "$BASE/api/incidents?active=true" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d[0]['severity'] if d else 'none')"
}

expect() { # desc expected actual
  if [ "$2" = "$3" ]; then echo "  PASS: $1 ($3)"; else echo "  FAIL: $1 — expected $2, got $3"; fi
}

# --- S1: down, down, degraded (threshold 3) → outage, no downgrade ---
reset_state
curl -s -X POST localhost:7002/control/down -o /dev/null
curl -s -X POST $BASE/api/services/$PAY_ID/check -o /dev/null
curl -s -X POST $BASE/api/services/$PAY_ID/check -o /dev/null
curl -s -X POST "localhost:7002/control/slow?ms=1200" -o /dev/null
curl -s -X POST $BASE/api/services/$PAY_ID/check -o /dev/null
expect "S1 down,down,degraded opens outage" "outage" "$(severity_of_active)"

# --- S2: degraded streak escalated by later down ---
reset_state
curl -s -X POST "localhost:7002/control/slow?ms=1200" -o /dev/null
curl -s -X POST $BASE/api/services/$PAY_ID/check -o /dev/null
curl -s -X POST $BASE/api/services/$PAY_ID/check -o /dev/null
curl -s -X POST $BASE/api/services/$PAY_ID/check -o /dev/null
expect "S2 degraded streak opens degradation" "degradation" "$(severity_of_active)"
curl -s -X POST localhost:7002/control/down -o /dev/null
curl -s -X POST $BASE/api/services/$PAY_ID/check -o /dev/null
expect "S2 down during degradation escalates" "outage" "$(severity_of_active)"

# --- S3: flapping never opens ---
reset_state
for i in 1 2 3 4 5 6; do
  curl -s -X POST localhost:7002/control/down -o /dev/null
  curl -s -X POST $BASE/api/services/$PAY_ID/check -o /dev/null
  curl -s -X POST localhost:7002/control/reset -o /dev/null
  curl -s -X POST $BASE/api/services/$PAY_ID/check -o /dev/null
done
expect "S3 flapping opens nothing" "none" "$(severity_of_active)"

# --- S4: healthy streak resets threshold ---
reset_state
curl -s -X POST localhost:7002/control/down -o /dev/null
curl -s -X POST $BASE/api/services/$PAY_ID/check -o /dev/null
curl -s -X POST $BASE/api/services/$PAY_ID/check -o /dev/null
curl -s -X POST localhost:7002/control/reset -o /dev/null
curl -s -X POST $BASE/api/services/$PAY_ID/check -o /dev/null   # up → streak reset
curl -s -X POST localhost:7002/control/down -o /dev/null
curl -s -X POST $BASE/api/services/$PAY_ID/check -o /dev/null
expect "S4 two downs after up (streak=2 < 3) opens nothing" "none" "$(severity_of_active)"

echo "== done =="
