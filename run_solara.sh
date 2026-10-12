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

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Make the module root importable (so `import component...` works)
export PYTHONPATH="$SCRIPT_DIR${PYTHONPATH:+:$PYTHONPATH}"

if [[ -f .env ]]; then
  while IFS= read -r line || [[ -n $line ]]; do
    [[ $line =~ ^#.*$ || -z $line ]] && continue
    if [[ $line =~ ^([^=]+)=(.*)$ ]]; then
      name="${BASH_REMATCH[1]}"; value="${BASH_REMATCH[2]}"
      value="${value#\'}"; value="${value%\'}"; value="${value#\"}"; value="${value%\"}"
      export "$name=$value"
    fi
  done < .env
fi

# GDAL writes temp files to the CWD when CPL_TMPDIR/TMPDIR/TEMP are unset; on
# SEPAL the CWD is the read-only module mount. uid suffix: shared /tmp safety.
export CPL_TMPDIR="${CPL_TMPDIR:-${TMPDIR:-/tmp}/fra_grid_gdal_$(id -u)}"
mkdir -p "$CPL_TMPDIR"

solara run "$SOLARA_FILE" --port "$PORT" --no-open
