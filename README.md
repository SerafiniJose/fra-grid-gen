# FRA Grid Generator

SEPAL module that generates FRA ISEA3H hexagon grids (FRA RSS level r17 and the
finer r18–r21) for an area of interest, with the FRA sphere→WGS84 latitude
correction ported to Python from the FRA RSS R script (`FRA RSS_ISEA3H generation 20sep26.R`,
dggridR), which is not part of this repository.

- One level per run. Cells finer than r17 carry `fra_r17_id`, the FRA cell that contains their centre.
- Outputs go to `~/module_results/fra_grid_generator/<name>/`. Each folder holds
  `<name>.gpkg` and/or the Shapefile set, `metadata.json` and `aoi.geojson`. The
  GeoPackage also embeds the metadata (`gpkg_metadata`).
- Map preview: every run also writes a hidden `.preview.pmtiles` (cell outlines, `global_id` only) into
  the grid folder with tippecanoe, so "Show on map" works at any size. It is not a deliverable: it is not in
  `metadata.json`'s `run.files` nor in the file lists, and it goes with the folder. `metadata.json` records it as
  `"preview": {"file": ".preview.pmtiles", "minzoom": m, "maxzoom": M}`, or `null` when it was skipped
  (tippecanoe missing or failing only skips the preview, with a warning; the grid is kept). Zoom ranges:
  every level from zoom 6, up to r17 13, r18 14, r19 15, r20 15, r21 16. Where a cell is under a pixel,
  tippecanoe merges cells into small stand-in squares, so a fine grid reads as its footprint until the
  hexagons appear (r21 from z9, r17 from z6). Below zoom 6 the map shows only the AOI outline and a "Zoom in
  to see the cells" hint, past the max the browser overzooms. Cost: about 130 bytes and 30 µs per cell
  (7 s and 30 MB for 225k r17 cells, 21 s and 85 MB for 651k). The z6 tile carries every cell under it
  (6.8 MB for 651k r17 cells), so very large grids are slow to draw at that zoom. Grids without a preview
  (older folders) are drawn cell by cell, up to 50,000 cells. Grids built before the zoom 6 change keep their
  old min zoom until regenerated.
- Limits: a warning at 2,000,000 estimated cells, a block above 10,000,000. The Shapefile option is
  unavailable above 4,000,000 cells (2 GB per file, 10-character field names, no embedded metadata).

- `area_ha` is the geodesic cell area on the WGS84 ellipsoid (pyproj `Geod`). The R script's
  spherical s2 `st_area` differs from it by about −0.45 % at the equator to +0.9 % at the poles.
- Antimeridian: an AOI that crosses 180° is refused; split it at 180° and generate each part.
  The column of cells straddling ±180° belongs to the part that ends at +180° (the R script's
  unwrap moves those cells to +180°), so a part touching −180° generated alone lacks that column.

- In-app help: the left drawer's About and Documentation open Markdown pages from
  `component/doc/<locale>/` (`about.md`, `documentation.md`). Keep the level table and the correction
  constants there in sync with `component/parameter/grid.py` (`tests/test_docs.py` checks the cell counts).

## Run

```bash
micromamba create -f sepal_environment.yml        # env "fra-grid", includes the dggrid and tippecanoe binaries
micromamba run -n fra-grid ./run_solara.sh        # http://localhost:8911
micromamba run -n fra-grid ./run_voila.sh         # ui.ipynb under voila, as on SEPAL: http://localhost:8866
```

Or `micromamba activate fra-grid` first, then `./run_solara.sh`. A local run needs SEPAL dev
credentials in a `.env` file at the repo root (both launchers load it through `local_env.sh`): `PYSEPAL_DEV_AUTH=1`,
`LOCAL_SEPAL_USER`, `LOCAL_SEPAL_PASSWORD` and `SEPAL_HOST`. Never commit `.env` (it is git-ignored).
`run_voila.sh` registers the notebook's SEPAL kernel name (`venv-fra-grid-gen`) for the env's Python in a
private `JUPYTER_PATH`, so a local machine needs no extra kernel.

On SEPAL the module runs through `ui.ipynb` (kernel `venv-fra-grid-gen`). There the map preview's
tile server is reached through SEPAL's jupyter-server-proxy (`LOCALTILESERVER_CLIENT_PREFIX`, copied to
`VECTORTILESERVER_CLIENT_PREFIX` at startup); locally through the jupyter-loopback comm bridge.

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
`reference_data/output/isea3hr17_528.*`, taken from the FRA reference archive
`hexagonos_19_03.zip` (not in this repository). Without it they are skipped:

```bash
unzip -j hexagonos_19_03.zip 'output/isea3hr17_528.*' -d reference_data/output/
```

## Manual check on SEPAL (before each release)

1. Chaco box (−60.10, −22.40, −60.00, −22.30), r17, GeoPackage + Shapefile: 330 cells, two tiles, both formats in the folder.
2. The same box at r19: the warning-free run finishes, and `fra_r17_id` is filled in.
3. An ADMIN2 unit at r17: the summary card appears in a few seconds, and the pill shows tile milestones.
4. Generate a multi-tile run: the app switches to the Outputs tab, whose job card shows each step (cells,
   Shapefile, PMTiles map preview, files), the elapsed time and the time left. When it finishes the card
   says "Ready" for 2 s, then the new grid's card opens in the list (one card open at a time; a click on a
   card's header opens or closes it, the eye shows it on the map without opening it). Cancel another run:
   you get a cancel toast, the card keeps the reason until Dismiss, and no folder is left behind.
5. Delete a grid shown on the map: its layer disappears and the folder is gone.
6. Show a grid of 1M+ cells on the map: the outlines appear from its min zoom, the AOI outline and the
   zoom hint below it, and tiles load through the proxy (no `blob:` URLs in the network tab).
7. Switch the language to Spanish: every label changes.

## Licence note

The engine wrapper `dggrid4py` is AGPL-3.0. Confirm with the module owner before
publishing. If it is not acceptable, only `component/scripts/dggrid_engine.py` changes,
to call the `dggrid` binary directly.
