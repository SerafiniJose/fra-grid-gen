# Shared setup for the local launchers (run_solara.sh, run_voila.sh); source it, do not run it.
# cd to the repo, make `component` importable, export .env, point GDAL's temp files away from the CWD.

cd "$(dirname "${BASH_SOURCE[0]}")" || exit 1

# Make the module root importable (so `import component...` works)
export PYTHONPATH="$PWD${PYTHONPATH:+:$PYTHONPATH}"

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
