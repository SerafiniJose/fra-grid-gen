"""Grid preview layer and AOI draw-control visibility on the shared SepalMap."""

import json

GRID_LAYER_KEY = "fra_grid_preview"


def show_grid(map_, gpkg_path, layer: str, *, name: str):
    """Show one grid as a GeoJSON outline layer (replacing any previous one)."""
    import ipyleaflet
    import pyogrio

    gdf = pyogrio.read_dataframe(gpkg_path, layer=layer, columns=["global_id"])
    geo = ipyleaflet.GeoJSON(data=json.loads(gdf.to_json()), name=name)
    map_.add_layer(geo, key=GRID_LAYER_KEY)
    # SepalMap.add_layer applied its primary-colour default style; keep the
    # colour, drop the fill so the basemap stays readable under the hexagons.
    geo.style = {**(geo.style or {}), "fillOpacity": 0.0, "weight": 1}
    bounds = tuple(float(v) for v in gdf.total_bounds)
    map_.zoom_bounds(bounds)
    return bounds


def remove_grid(map_) -> bool:
    if map_ is None:
        return False
    layer = map_.find_layer(GRID_LAYER_KEY, none_ok=True)
    if layer is None:
        return False
    map_.remove_layer(layer)
    return True


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
