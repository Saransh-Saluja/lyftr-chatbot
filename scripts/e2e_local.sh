#!/usr/bin/env bash
# Offline end-to-end check: fake provider + REAL uvicorn processes + scripts/smoke_test.py.
# Proves our code against LiteLLM's real HTTP/cache paths. It does NOT prove a real
# provider (Gemini etc.) behaves the same - run smoke_test.py against real keys for that.
set -uo pipefail
cd "$(dirname "$0")/../backend"
PY="${PYTHON:-../.venv/bin/python}"
TMP="$(mktemp -d)"; PIDS=()
cleanup() { for p in "${PIDS[@]}"; do kill "$p" 2>/dev/null; done; rm -rf "$TMP"; }
trap cleanup EXIT

wait_for() { for _ in $(seq 1 80); do curl -fs "$1" >/dev/null 2>&1 && return 0; sleep 0.25; done; echo "timeout waiting for $1"; exit 2; }
start_api() { # port dbfile simulation
  LLM_API_KEYS=goodkey1,goodkey2 LLM_MODEL=openai/fake-model LLM_API_BASE=http://127.0.0.1:18080/v1 \
  DATABASE_URL="sqlite:///$TMP/$2" ENABLE_FAILURE_SIMULATION="$3" ALLOWED_ORIGINS=http://localhost:3000 \
  "$PY" -m uvicorn app.main:app --port "$1" >"$TMP/api-$1.log" 2>&1 &
  PIDS+=($!); LAST_PID=$!; wait_for "http://127.0.0.1:$1/health"
}

"$PY" -m tests.fake_provider 18080 >"$TMP/fake.log" 2>&1 & PIDS+=($!)
sleep 1.5
FAIL=0

echo "################ 1. simulation ON (port 8000) ################"
start_api 8000 on.db true; ON_PID=$LAST_PID
"$PY" ../scripts/smoke_test.py http://127.0.0.1:8000 --origin http://localhost:3000 --skip-semantic || FAIL=1

echo; echo "################ 2. simulation OFF (port 8001) ################"
start_api 8001 off.db false
"$PY" ../scripts/smoke_test.py http://127.0.0.1:8001 --no-simulation --skip-semantic | tail -3 || FAIL=1

echo; echo "################ 3. restart persistence (real process) ################"
curl -s -X POST 127.0.0.1:8000/chat -H 'content-type: application/json' \
  -d '{"session_id":"persist-demo","message":"remember this line"}' >/dev/null
kill "$ON_PID"; sleep 1.5; echo "(API process killed)"
start_api 8000 on.db true
OUT=$(curl -s 127.0.0.1:8000/sessions/persist-demo/messages)
echo "after restart: $OUT" | cut -c1-200
echo "$OUT" | grep -q "remember this line" && echo "[PASS] history survived restart" || { echo "[FAIL] history lost"; FAIL=1; }

echo; echo "################ 4. frontend api.ts vs REAL backend ################"
if [ -d ../frontend/node_modules ]; then
  if (cd ../frontend && INTEGRATION=1 VITE_API_BASE_URL=http://127.0.0.1:8000 npx vitest run src/__tests__/integration.test.ts >"$TMP/fe.log" 2>&1); then
    grep -E "Tests " "$TMP/fe.log" | sed 's/\x1b\[[0-9;]*m//g'
  else cat "$TMP/fe.log" | tail -25; FAIL=1; fi
else echo "(skipped: run 'npm install' in frontend/ first)"; fi

echo; echo "################ 5. log hygiene ################"
if grep -qiE "goodkey|Traceback" "$TMP"/api-*.log; then echo "[FAIL] key material or traceback in logs"; grep -iE "goodkey|Traceback" "$TMP"/api-*.log | head -3; FAIL=1; else echo "[PASS] no API keys or tracebacks in server logs"; fi
exit $FAIL
