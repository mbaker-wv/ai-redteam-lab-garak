#!/usr/bin/env bash
# Run the same garak probes against each model, in raw mode and agent mode,
# so every run differs by exactly one variable. Reports land in ./runs/.
#
# Usage:   ./run_matrix.sh                 (uses MODELS and PROBES below)
#          MODELS="qwen3:8b" ./run_matrix.sh
#          MODES="agent" MODELS="llama3.1:8b mistral:7b" bash run_matrix.sh
# Needs:   .venv active, Ollama running, models already pulled (ollama pull <tag>)

set -euo pipefail

MODELS="${MODELS:-qwen3:8b llama3.1:8b gemma3:12b mistral:7b}"
PROBES="${PROBES:-promptinject,latentinjection.LatentInjectionReport,latentinjection.LatentInjectionResume,latentinjection.LatentInjectionFactSnippetLegal,encoding.InjectBase64,encoding.InjectROT13,encoding.InjectHex,dan.DanInTheWild}"
MODES="${MODES:-raw agent}"
CONFIG="${CONFIG:-scan_fast.yaml}"
DOC="docs/contract_clean.txt"
PORT=8000
GARAK_RUNS="${GARAK_RUNS:-$HOME/.local/share/garak/garak_runs}"
mkdir -p runs logs

wait_for_agent() {
  for _ in $(seq 1 30); do
    if curl -sf -o /dev/null "http://127.0.0.1:${PORT}/chat" \
         -H 'Content-Type: application/json' -d '{"message":"ping"}'; then
      return 0
    fi
    sleep 2
  done
  echo "Agent did not come up on port ${PORT}. See logs/." >&2
  return 1
}

run_one() {  # $1 = model, $2 = mode (raw|agent)
  local model="$1" mode="$2"
  local tag="matrix_${mode}_${model//:/-}"
  local args=(--model "$model" --port "$PORT")
  [[ "$mode" == "raw" ]] && args+=(--raw) || args+=(--doc "$DOC")

  echo "=== ${tag} ==="
  # Refuse to run if something else already owns the port. Otherwise garak
  # would quietly scan whatever old agent is still listening there.
  if lsof -nP -iTCP:"${PORT}" -sTCP:LISTEN > /dev/null 2>&1; then
    echo "Port ${PORT} is already in use. Stop the old agent first:" >&2
    lsof -nP -iTCP:"${PORT}" -sTCP:LISTEN >&2
    echo "Skipping ${tag}." >&2
    return 0
  fi

  python3 agent.py "${args[@]}" > "logs/${tag}.agent.log" 2>&1 &
  local pid=$!
  trap 'kill $pid 2>/dev/null || true' EXIT

  if wait_for_agent && kill -0 "$pid" 2>/dev/null; then
    echo "Agent for ${tag} is up (pid ${pid}): $(head -1 "logs/${tag}.agent.log")"
    if ! garak --config "$CONFIG" --target_type rest -G rest_agent.json \
          --probes "$PROBES" --report_prefix "${tag}" \
          2>&1 | tee "logs/${tag}.garak.log"; then
      echo "garak failed for ${tag}, see logs/${tag}.garak.log. Moving on." >&2
    fi
    # garak writes under its own report dir; copy the results next to the lab files
    cp "${GARAK_RUNS}/${tag}".report.* runs/ 2>/dev/null || \
      echo "No report found for ${tag} in ${GARAK_RUNS}" >&2
  else
    echo "Agent for ${tag} did not start. See logs/${tag}.agent.log" >&2
  fi

  kill "$pid" 2>/dev/null || true
  wait "$pid" 2>/dev/null || true
  trap - EXIT
}

for model in $MODELS; do
  if ! ollama show "$model" > /dev/null 2>&1; then
    echo "Skipping ${model}: not pulled. Run: ollama pull ${model}" >&2
    continue
  fi
  for mode in $MODES; do
    run_one "$model" "$mode"
  done
done

echo
echo "Done. Summarize with:"
echo "  python3 summarize.py runs/*.report.jsonl --csv results.csv"
