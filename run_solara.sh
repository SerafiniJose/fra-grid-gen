#!/bin/bash
# Sources .env and runs the Solara app.
# Usage: ./run_solara.sh [filename] [--port PORT]   (defaults: app.py, 8911)

SOLARA_FILE="app.py"
PORT="8911"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --port) PORT="$2"; shift 2 ;;
    --port=*) PORT="${1#--port=}"; shift ;;
    -h|--help) echo "Usage: $0 [filename] [--port PORT]"; exit 0 ;;
    *) SOLARA_FILE="$1"; shift ;;
  esac
done

source "$(dirname "${BASH_SOURCE[0]}")/local_env.sh"

solara run "$SOLARA_FILE" --port "$PORT" --no-open
