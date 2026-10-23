#!/usr/bin/env bash
# Run both manual tests on every model:
#   inject  = poisoned contract (PINEAPPLE), indirect injection, LLM01
#   extract = clean contract, try to get the agent to reveal its rules, LLM07
# Starts and stops the agent itself. Results land in runs/manual_<test>_<model>.jsonl
#
# Usage:  bash manual_all.sh
#         MODELS="qwen3:8b" bash manual_all.sh

set -uo pipefail
MODELS="${MODELS:-qwen3:8b llama3.1:8b mistral:7b gemma3:12b}"
PORT=8000
mkdir -p runs logs

if lsof -nP -iTCP:"${PORT}" -sTCP:LISTEN > /dev/null 2>&1; then
  echo "Port ${PORT} is already in use. Run: pkill -f agent.py" >&2
  exit 1
fi

run_test() {  # $1 model, $2 test (inject|extract), $3 document
  local model="$1" test="$2" doc="$3" label="${1//:/-}"
  echo "=== ${test} on ${model} (doc: ${doc}) ==="
  python3 agent.py --model "$model" --doc "$doc" --port "$PORT" \
    > "logs/manual_${test}_${label}.agent.log" 2>&1 &
  local pid=$!
  for _ in $(seq 1 30); do
    curl -sf -o /dev/null "http://127.0.0.1:${PORT}/chat" \
      -H 'Content-Type: application/json' -d '{"message":"ping"}' && break
    sleep 2
  done
  if kill -0 "$pid" 2>/dev/null; then
    python3 manual_tests.py "$test" --label "$label"
  else
    echo "Agent did not start, see logs/manual_${test}_${label}.agent.log" >&2
  fi
  kill "$pid" 2>/dev/null || true
  wait "$pid" 2>/dev/null || true
  echo
}

for model in $MODELS; do
  run_test "$model" inject  docs/contract_poisoned.txt
  run_test "$model" extract docs/contract_clean.txt
done

echo "Done. Results are in runs/manual_*.jsonl"
