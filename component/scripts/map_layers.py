"""Grid preview layers and AOI draw-control visibility on the shared SepalMap.

A grid is previewed from its hidden PMTiles archive (``g.PREVIEW_FILE``, any
size) when the folder has one, else as a GeoJSON layer read from the GPKG/SHP,
which is capped at ``g.PREVIEW_MAX_CELLS``. The PMTiles path also draws the
grid's AOI outline, the only thing visible below the archive's min zoom.

PMTiles go through ``vectortileserver``'s range-request server; on SEPAL the
browser reaches it through jupyter-server-proxy (``tile_proxy``), locally
through the jupyter-loopback comm bridge mounted by the app.
"""

import functools
import json
import logging
from dataclasses import dataclass
from pathlib import Path

from component.parameter import grid as g

logger = logging.getLogger(g.LOGGER_NAME)

GRID_LAYER_KEY = "fra_grid_preview"
AOI_LAYER_KEY = "fra_grid_preview_aoi"
_SOURCE = "grid"
_FALLBACK_COLOR = "#76591e"  # pysepal's primary, if its colour module is unavailable


@dataclass(frozen=True)
class PreviewPlan:
    """How one grid folder can be shown on the map."""

    pmtiles: Path | None = None
    minzoom: int | None = None
    maxzoom: int | None = None
    vector: tuple | None = None  # (gpkg/shp path, layer) for the GeoJSON path, only <= cap

    @property
    def available(self) -> bool:
        return self.pmtiles is not None or self.vector is not None


def preview_source(folder, name: str, formats):
    """The grid's GPKG (preferred) or Shapefile as ``(path, layer)``, or None."""
    folder = Path(folder)
    for fmt in ("gpkg", "shp"):
        path = folder / f"{name}.{fmt}"
        if fmt in formats and path.exists():
            return path, name
    return None


def plan_preview(folder, name: str, metadata: dict) -> PreviewPlan:
    folder = Path(folder)
    run = metadata.get("run", {}) if isinstance(metadata, dict) else {}
    preview = metadata.get("preview") if isinstance(metadata, dict) else None
    pmtiles = minzoom = maxzoom = None
    # Only ever the fixed hidden name: metadata.json is user-editable.
    if isinstance(preview, dict) and preview.get("file") == g.PREVIEW_FILE and (folder / g.PREVIEW_FILE).is_file():
        try:
            minzoom, maxzoom = int(preview["minzoom"]), int(preview["maxzoom"])
            pmtiles = folder / g.PREVIEW_FILE
        except (KeyError, TypeError, ValueError):
            minzoom = maxzoom = None
    vector = None
    if int(run.get("cell_count", 0)) <= g.PREVIEW_MAX_CELLS:
        vector = preview_source(folder, name, run.get("formats", ()))
    return PreviewPlan(pmtiles=pmtiles, minzoom=minzoom, maxzoom=maxzoom, vector=vector)


def primary_color() -> str:
    try:
        from pysepal import color

        return str(color.primary)
    except Exception:
        return _FALLBACK_COLOR


def theme_style(make) -> dict:
    """``{is_dark: make(primary)}``: SepalMap merges the entry for the current theme
    into the layer's ``style`` on add and on every theme switch (as pysepal's AOI)."""
    from pysepal.frontend import styles as ss

    return {is_dark: make(colors["primary"]) for is_dark, colors in ss.THEMES.items()}


def preview_style(url: str, color: str) -> dict:
    """Cell outlines and, when the archive has them, 1 ha plots; scalar paint only.

    protomaps-leaflet's json_style copies paint values verbatim into canvas
    styles: an expression would render black (see spatial_risk pmtiles_map).
    A source-layer missing from the archive (no plots) simply draws nothing.
    """
    return {
        "version": 8,
        "sources": {_SOURCE: {"type": "vector", "url": url}},
        "layers": [
            {
                "id": "cells",
                "type": "line",
                "source": _SOURCE,
                "source-layer": g.PREVIEW_LAYER,
                "paint": {"line-color": color, "line-width": 1},
            },
            {
                "id": "plots",
                "type": "line",
                "source": _SOURCE,
                "source-layer": g.PREVIEW_PLOTS_LAYER,
                "paint": {"line-color": color, "line-width": 1},
            },
        ],
    }


@functools.cache
def _pmtiles_layer_class():
    import ipyleaflet
    from traitlets import Int

    class GridPMTilesLayer(ipyleaflet.PMTilesLayer):
        """PMTilesLayer with protomaps-leaflet's data-zoom options.

        ``max_data_zoom`` must be the archive's max zoom (the default is 14:
        deeper display zooms would ask for tiles the archive lacks instead of
        overzooming). ``level_diff`` 0 maps display zoom to data zoom 1:1 (the
        default 2 would draw nothing for the first two zooms of the archive).
        Both reach the JS options because they are tagged ``o=True``.
        """

        max_data_zoom = Int(14).tag(sync=True, o=True)
        level_diff = Int(0).tag(sync=True, o=True)

    return GridPMTilesLayer


def _enable_loopback(client) -> None:
    """Best-effort comm-bridge wiring for the tile port (no-op when a proxy is set)."""
    try:
        client.enable_jupyter_loopback()
    except Exception:
        logger.warning("jupyter-loopback bridge unavailable; map preview tiles may not reach the browser",
                       exc_info=True)


def _aoi_layer(aoi_path, color, name):
    import ipyleaflet

    data = json.loads(Path(aoi_path).read_text(encoding="utf-8"))
    layer = ipyleaflet.GeoJSON(
        data=data, name=name, style={"color": color, "weight": 2, "fillOpacity": 0.0, "dashArray": "6 4"}
    )
    layer.theme_style = theme_style(lambda c: {"color": c})
    return layer


def show_grid_pmtiles(map_, pmtiles_path, *, name: str, maxzoom: int, bounds=None, aoi_path=None):
    """Show the grid's PMTiles outlines (replacing any previous preview)."""
    from vectortileserver.client import TileClient

    color = primary_color()
    client = TileClient(str(pmtiles_path))
    _enable_loopback(client)
    layer = _pmtiles_layer_class()(url=client.pmtiles_url, style=preview_style(client.pmtiles_url, color),
                                   max_data_zoom=int(maxzoom), name=name)
    # The PMTiles view ignores later style changes; it picks the new one up because
    # SepalMap's basemap swap on a theme switch rebuilds every layer view above it.
    layer.theme_style = theme_style(lambda c: preview_style(client.pmtiles_url, c))
    remove_grid(map_)
    if aoi_path is not None and Path(aoi_path).is_file():
        map_.add_layer(_aoi_layer(aoi_path, color, f"{name} AOI"), key=AOI_LAYER_KEY)
    map_.add_layer(layer, key=GRID_LAYER_KEY)
    if bounds:
        map_.zoom_bounds(tuple(float(v) for v in bounds))
    return layer


def show_grid(map_, gpkg_path, layer: str, *, name: str):
    """Show one grid as a GeoJSON outline layer (replacing any previous one)."""
    import ipyleaflet
    import pyogrio

    gdf = pyogrio.read_dataframe(gpkg_path, layer=layer, columns=["global_id"])
    geo = ipyleaflet.GeoJSON(data=json.loads(gdf.to_json()), name=name)
    geo.theme_style = theme_style(lambda c: {"color": c})
    remove_grid(map_)
    map_.add_layer(geo, key=GRID_LAYER_KEY)
    # SepalMap.add_layer applied its primary-colour default style; keep the
    # colour, drop the fill so the basemap stays readable under the hexagons.
    geo.style = {**(geo.style or {}), "fillOpacity": 0.0, "weight": 1}
    bounds = tuple(float(v) for v in gdf.total_bounds)
    map_.zoom_bounds(bounds)
    return bounds


def show_preview(map_, plan: PreviewPlan, *, name: str, bounds=None, aoi_path=None):
    """Show ``plan`` on the map; the PMTiles min zoom, or None for the GeoJSON path.

    A PMTiles failure falls back to the GeoJSON path when the grid is small
    enough, else it propagates.
    """
    if plan.pmtiles is not None:
        try:
            show_grid_pmtiles(map_, plan.pmtiles, name=name, maxzoom=plan.maxzoom, bounds=bounds, aoi_path=aoi_path)
            return plan.minzoom
        except Exception:
            if plan.vector is None:
                raise
            logger.warning("PMTiles preview failed, showing the cells as GeoJSON", exc_info=True)
    if plan.vector is None:
        raise ValueError(f"no map preview available for {name!r}")
    show_grid(map_, plan.vector[0], plan.vector[1], name=name)
    return None


def zoom_hint_needed(zoom, minzoom) -> bool:
    """The PMTiles preview draws nothing below its min zoom."""
    return minzoom is not None and zoom is not None and float(zoom) < minzoom


def remove_grid(map_) -> bool:
    if map_ is None:
        return False
    removed = False
    for key in (GRID_LAYER_KEY, AOI_LAYER_KEY):
        layer = map_.find_layer(key, none_ok=True)
        if layer is not None:
            map_.remove_layer(layer)
            removed = True
    return removed


def sync_draw_control_visibility(map_, aoi_active: bool, was_hidden: bool) -> bool:
    """Keep AoiView's draw control on the map only while the AOI tab is active.

    ``rv.TabsItems`` keeps inactive tabs mounted, so AoiView never removes its
    Geoman toolbar on a tab switch. Uses add/remove_control directly:
    ``dc.show()/hide()`` would wipe the drawn shape. Returns the new
    ``was_hidden`` for the caller to carry to the next call (from spatial_risk).
    """
    dc = getattr(map_, "dc", None)
    if map_ is None or dc is None:
        return was_hidden
    if aoi_active:
        if was_hidden and dc not in map_.controls:
            map_.add_control(dc)
        return False
    if dc in map_.controls:
        map_.remove_control(dc)
        return True
    return was_hidden
