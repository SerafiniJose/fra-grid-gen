# FRA Grid Generator

SEPAL module that generates FRA ISEA3H hexagon grids (FRA RSS level r17 and the
finer r18–r21) for an area of interest, with the FRA sphere→WGS84 latitude
correction from `reference/FRA RSS_ISEA3H generation 20sep26.R`, in Python.

- One level per run. Cells finer than r17 carry `fra_r17_id`, the FRA cell that contains their centre.
- Outputs go to `~/module_results/fra_grid_generator/<name>/`. Each folder holds
  `<name>.gpkg` and/or the Shapefile set, `metadata.json` and `aoi.geojson`. The
  GeoPackage also embeds the metadata (`gpkg_metadata`).
- Limits: a warning at 2,000,000 estimated cells, a block above 10,000,000. The Shapefile option is
  unavailable above 4,000,000 cells (2 GB per file, 10-character field names, no embedded metadata).

## Run

```bash
micromamba create -f sepal_environment.yml   # env "fra-grid", includes the dggrid binary
./run_solara.sh                               # http://localhost:8911
```

On SEPAL the module runs through `ui.ipynb` (kernel `venv-fra_grid_generator`).

Environment overrides (all optional):

| Variable | Default | Purpose |
|---|---|---|
| `FRA_GRID_RESULTS_DIR` | `~/module_results/fra_grid_generator` | output root |
| `FRA_GRID_SCRATCH` | `<tmp>/fra_grid_<uid>` | GDAL `CPL_TMPDIR` |
| `FRA_GRID_LOCAL_SCRATCH` | `/var/tmp/fra_grid_<uid>` | dggrid work dir, temporary GeoPackage |
| `FRA_GRID_DGGRID` | `$CONDA_PREFIX/bin/dggrid` | dggrid executable |

## Test

```bash
micromamba run -n fra-grid pytest -q
```

Golden tests (`-m golden`) compare against the original R/dggridR r17 cells and need
`reference_data/output/isea3hr17_528.*`:

```bash
unzip -j hexagonos_19_03.zip 'output/isea3hr17_528.*' -d reference_data/output/
```

## Manual check on SEPAL (before each release)

1. Chaco box (−60.10, −22.40, −60.00, −22.30), r17, GeoPackage + Shapefile: 330 cells, two tiles, both formats in the folder.
2. The same box at r19: the warning-free run finishes, and `fra_r17_id` is filled in.
3. An ADMIN2 unit at r17: the summary card appears in a few seconds, and the pill shows tile milestones.
4. Cancel a multi-tile run: you get a cancel toast and no folder is left behind.
5. Delete a grid shown on the map: its layer disappears and the folder is gone.
6. Switch the language to Spanish: every label changes.

## Licence note

The engine wrapper `dggrid4py` is AGPL-3.0. Confirm with the module owner before
publishing. If it is not acceptable, only `component/scripts/dggrid_engine.py` changes,
to call the `dggrid` binary directly.
