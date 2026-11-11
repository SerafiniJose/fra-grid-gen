#!/bin/bash
# Runs ui.ipynb under voila, as SEPAL does. Usage: ./run_voila.sh [--port PORT]   (default 8866)
# Run it inside the fra-grid env: micromamba run -n fra-grid ./run_voila.sh

PORT="8866"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --port) PORT="$2"; shift 2 ;;
    --port=*) PORT="${1#--port=}"; shift ;;
    -h|--help) echo "Usage: $0 [--port PORT]"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

source "$(dirname "${BASH_SOURCE[0]}")/local_env.sh"

# ui.ipynb names SEPAL's module kernel (venv-<repo folder>), which a local machine lacks and
# voila cannot override: register that name for this env's python, in a private JUPYTER_PATH.
KERNEL="$(python -c "import json; print(json.load(open('ui.ipynb'))['metadata']['kernelspec']['name'])")"
KERNELS_DIR="${TMPDIR:-/tmp}/fra_grid_jupyter_$(id -u)"
mkdir -p "$KERNELS_DIR/kernels/$KERNEL"
cat > "$KERNELS_DIR/kernels/$KERNEL/kernel.json" <<JSON
{"argv": ["$(command -v python)", "-m", "ipykernel_launcher", "-f", "{connection_file}"],
 "display_name": "$KERNEL (local)", "language": "python"}
JSON
export JUPYTER_PATH="$KERNELS_DIR${JUPYTER_PATH:+:$JUPYTER_PATH}"

exec voila ui.ipynb --port="$PORT" --no-browser --show_tracebacks=True
