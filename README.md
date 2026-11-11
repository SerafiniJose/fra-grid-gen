# FRA Grid Generator

SEPAL module that generates FRA ISEA3H hexagon grids (FRA RSS level r17 and the
finer r18–r21) for an area of interest, with the FRA sphere→WGS84 latitude
correction ported to Python from the FRA RSS R script (`FRA RSS_ISEA3H generation 20sep26.R`,
dggridR), which is not part of this repository.

- One level per run. Cells finer than r17 carry `fra_r17_id`, the FRA cell that contains their centre.
- Outputs go to `~/module_results/fra_grid_generator/<name>/`. Each folder holds
  `<name>.gpkg` and/or the Shapefile set, `metadata.json` and `aoi.geojson`. The
  GeoPackage also embeds the metadata (`gpkg_metadata`).
- Optional centroids (r17–r19): a 1 ha north-up square at each cell's centroid, written as a second
  GeoPackage layer `<name>_centroids` (and `<name>_centroids.shp` with Shapefile). `metadata.json` records it
  under `"centroids": {"layer": ..., "side_m": 100.0}`, or `null`.
- Map preview: every run also writes a hidden `.preview.pmtiles` (cell outlines, `global_id` only) into
  the grid folder with tippecanoe, so "Show on map" works at any size. The centroids, when present, are a
  second source-layer (`centroids`) of the same archive from zoom 12, drawn as their own map layer. It is not a deliverable: it is not in
  `metadata.json`'s `run.files` nor in the file lists, and it goes with the folder. `metadata.json` records it as
  `"preview": {"file": ".preview.pmtiles", "minzoom": m, "maxzoom": M}`, or `null` when it was skipped
  (tippecanoe missing or failing only skips the preview, with a warning; the grid is kept). Zoom ranges:
  every level from zoom 3, up to r17 13, r18 14, r19 15, r20 15, r21 16. Where a cell is under a pixel,
  tippecanoe merges cells into small stand-in squares, so a fine grid reads as its footprint until the
  hexagons appear (r21 from z9, r17 from z6). Below zoom 3 the map shows only the AOI outline and a "Zoom in
  to see the cells" hint, past the max the browser overzooms. Cost: about 130 bytes and 30 µs per cell
  (7 s and 30 MB for 225k r17 cells, 21 s and 85 MB for 651k). The lowest-zoom tiles carry every cell under them
  (6.8 MB at z6 for 651k r17 cells, more at z3), so very large grids are slow to draw at those zooms. Grids without a preview
  (older folders) are drawn cell by cell, up to 50,000 cells. Grids built before the zoom 3 change keep their
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
  The About page opens when the app starts. Locales: `en`, `es-ES`, `fr-FR`, `pt-PT` (messages in
  `component/message/<locale>/locale.json`); the header's language selector lists the folders.
- Map: the layers control offers the SEPAL basemap (light or dark with the theme) and Google Satellite. The
  grid, centroids and AOI outlines follow the theme's primary colour.

## Licence note

The engine wrapper `dggrid4py` is AGPL-3.0. Confirm with the module owner before
publishing. If it is not acceptable, only `component/scripts/dggrid_engine.py` changes,
to call the `dggrid` binary directly.
