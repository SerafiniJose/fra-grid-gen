### Workflow

The right panel has three tabs. Work through them in order.

**1 · AOI.** Choose the area to cover: an administrative unit, a vector file from your
SEPAL folder, a shape drawn on the map, a set of points or an Earth Engine asset. The app
reads the geometry and shows its area, bounding box and the estimated number of r17
cells. Points give at most one cell each: the cell that contains the point.

**2 · Grid.** Pick a level in the table (r17 is the FRA level), check the output name and
pick the formats:

- **Output name**: letters, digits, `_` and `-`. It is also the folder name. If a grid
  with that name exists, generating replaces it once the new one is complete.
- **Formats**: GeoPackage (recommended) and/or Shapefile.

Then press **Generate grid**. Above 2,000,000 estimated cells the app asks you to
confirm first.

**3 · Outputs.** One row per grid in your results folder, newest first, with its AOI under
the name. The grid being generated is the top row; its progress shows in the notification
pill at the bottom right of the map, and **Cancel** stops it without leaving files. A grid
that failed or was cancelled keeps its row: **Retry** (or **Generate**) runs it again with
the same settings and AOI. Each grid has three icons, each with a tooltip:

- show or hide the grid on the map,
- details: its folder, files and sizes, map preview and metadata,
- delete its folder.

### Grid levels

ISEA3H has aperture 3: each level has three times as many cells as the one before, each
one third of the area.

| Level | Cell area | Spacing | Cells on Earth |
|---|---|---|---|
| **r17 (FRA RSS)** | 39.50 ha | 709 m | 1,291,401,632 |
| r18 | 13.17 ha | 409 m | 3,874,204,892 |
| r19 | 4.39 ha | 236 m | 11,622,614,672 |
| r20 | 1.46 ha | 137 m | 34,867,844,012 |
| r21 | 0.49 ha | 79 m | 104,603,532,032 |

Area is the mean cell area on DGGRID's sphere. Spacing is DGGRID's characteristic
length scale: the diameter of a circle with the cell's area. The table in the Grid tab
also estimates how many cells your area needs at each level.

### Output files

Each grid gets its own folder in `~/module_results/fra_grid_generator/<name>/`:

| File | Content |
|---|---|
| `<name>.gpkg` | The cells (GeoPackage). The metadata is embedded too. |
| `<name>.shp` + `.shx`, `.dbf`, `.prj`, `.cpg` | The cells (Shapefile), if selected. |
| `<name>_centroids` | Optional, r17 to r19: the centroids, a 1 ha square (100 m × 100 m, north-up) at each cell's centroid, with the cell's fields except `area_ha`. A second layer in the GeoPackage and, with Shapefile, `<name>_centroids.shp`. |
| `metadata.json` | How and when the grid was made: app and DGGRID versions, grid parameters, correction, AOI, files. |
| `aoi.geojson` | The area of interest used. |

The cells are polygons in WGS84 (EPSG:4326), with these fields:

| Field | Meaning |
|---|---|
| `global_id` | Cell ID in the ISEA3H grid of that level. At r17 it is the ID of the official FRA grid. |
| `fra_r17_id` | Levels r18 to r21 only: the `global_id` of the FRA r17 cell that contains the cell's centroid. |
| `level` | Grid level (17 to 21). |
| `lon`, `lat` | Cell centroid in WGS84 degrees. |
| `area_ha` | Cell area in hectares, measured on the WGS84 ellipsoid. |

A cell is kept when it touches your area. Cells along the edge therefore extend past the
boundary.

### How the cells are made

The app follows the FRA RSS ISEA3H specification v1.2, as implemented in the FRA R
script (dggridR):

1. **DGGRID** builds the ISEA3H cells: ISEA projection, aperture 3, hexagons, icosahedron
   vertex at 11.25° E, 58.28252559° N, azimuth 0°. Large areas are processed in tiles of
   0.25° to 1°.
2. **Sphere to WGS84.** DGGRID works on a sphere (radius 6,371,007.18 m). Each vertex
   latitude is taken as a point on that sphere and converted to a WGS84 geodetic latitude
   (10 fixed-point iterations).
3. **Calibration.** An empirical term then adjusts the latitude:
   `lat + −(C1·sin 2φ + C2·sin 4φ) / R`, with C1 = 24.26, C2 = 53.70 and R = 6,371,007 m.
4. Longitudes are never changed.
5. The cells that touch the AOI are kept. Each cell belongs to exactly one tile (the one
   holding its corrected centroid), so there are no duplicates.

For the R script, the FRA team checked this method against the official FRA grid on 192
samples around the world: identical IDs, at most 5.4 m apart (median 2.4 m). The app
reproduces the R script's cells, IDs and correction.

### Finer levels (r18 to r21)

The official FRA grid exists only at **r17**, and that is the only level where the
correction has been checked against it. The calibration constants (C1, C2) were fitted
for r17.

At r18 to r21 the app applies exactly the same steps. The correction depends only on
latitude, not on cell size, so finer cells are moved the same way as FRA cells at the same
place. But no official grid exists at those levels to compare with, so their positions
are an extension of the FRA method, not a validated product. The metadata records this:
`correction.validated_at_levels` is `[17]` and `dggs.is_fra_rss_level` is `false`.

Aperture-3 cells do not nest: an r18 cell is not inside a single r17 cell, and r17 cell
edges cut through finer cells. To link a finer cell to the FRA grid, use `fra_r17_id`: the
FRA cell that contains its centroid.

### Limits and notes

- **One level per run.** Run the app again for another level.
- **Size limits.** Above 2,000,000 estimated cells the app asks for confirmation; above
  10,000,000 it refuses. Use a smaller area or a coarser level.
- **Shapefile.** Not available above 4,000,000 cells (2 GB file limit). Shapefiles also cut
  field names to 10 characters and cannot embed the metadata. Prefer GeoPackage.
- **180° meridian.** An area that crosses 180° is refused. Split it at 180° and generate
  each part. The column of cells that straddles 180° comes with the part that ends at
  +180°.
- **`area_ha`.** Measured on the WGS84 ellipsoid. The R script measures on a sphere; the two
  differ by less than 1 %, depending on latitude.
- **Map preview.** Each grid has a hidden preview file that lets the map draw it at any
  size. Cells show from zoom 3; zoom in further to see the individual hexagons of finer
  levels. The centroids, when the grid has them, are a separate layer that shows from
  zoom 12. The preview is not
  one of the output files.
