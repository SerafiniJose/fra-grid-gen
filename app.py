"""FRA Grid Generator: Solara entry point (map-first single page, three tabs).

Run with ./run_solara.sh (dev) or through ui.ipynb (SEPAL / Voila).
"""

import reacton.ipyvuetify as rv
import solara
from pysepal import mapping as sm
from pysepal.logger import setup_logging
from pysepal.sepalwidgets.vue_app import MapApp
from pysepal.solara import (
    NotificationProvider,
    get_current_gee_interface,
    get_current_theme_state,
    setup_sessions,
    setup_solara_server,
    with_sepal_sessions,
)

from component.i18n import app_available_locales, reset_translator, t, use_app_locale
from component.model.state_manager import app_state
from component.parameter import grid as g
from component.parameter.directory import results_dir
from component.scripts.map_layers import sync_draw_control_visibility
from component.scripts.notify_bridge import install_task_log_handler
from component.scripts.outputs_index import STALE_AGE_S, cleanup_stale
from component.scripts.scratch import cleanup_local_scratch, configure_gdal_tmpdir
from component.scripts.tile_proxy import borrow_localtileserver_prefix, loopback_bridge_needed, prefer_http_proxy
from component.tile.aoi_tile import AoiTile
from component.tile.grid_tile import GridTile
from component.widget.dialog_nudge import NUDGE_CSS
from component.tile.outputs_tile import OutputsTile
from component.widget.doc_page import DocPage

logger = setup_logging(logger_name=g.LOGGER_NAME)
# Tile milestones -> notification pill; also lifts the logger to INFO when
# logging_config.toml is missing (the root's WARNING would hide them).
install_task_log_handler()
# On SEPAL, reuse the raster tiles' jupyter-server-proxy route for the PMTiles
# map preview server (vectortileserver never autodetects one), and keep it off
# the comm bridge then. Before any TileClient: they are built on "Show on map".
borrow_localtileserver_prefix()
prefer_http_proxy()
# GDAL scratch files must never land in the read-only CWD on SEPAL.
configure_gdal_tmpdir()
# Leftovers of a run killed mid-write (server restart, instance stop).
_removed = cleanup_stale(results_dir()) + cleanup_local_scratch(STALE_AGE_S)
if _removed:
    logger.info("Removed unfinished folders: %s", ", ".join(_removed))

setup_solara_server(extra_asset_locations=[])


def _loopback_bridge_widget():
    """The jupyter-loopback CommBridge singleton, or None (from spatial_risk).

    Mounted in the page from the first render: under voila a later
    ``display()`` from a click handler never reaches the browser, and the JS
    half must install its tile-URL interceptors before a PMTiles layer
    renders. None when the tile server goes through an HTTP proxy (SEPAL).
    """
    if not loopback_bridge_needed():
        return None
    try:
        import jupyter_loopback

        return jupyter_loopback.enable_comm_bridge(display=False)
    except Exception:  # anywidget missing / exotic runtime
        logger.warning("jupyter-loopback comm bridge unavailable; the map preview may not render locally",
                       exc_info=True)
        return None


@solara.lab.on_kernel_start
def on_kernel_start():
    """Reset per-kernel state and open the SEPAL sessions."""
    reset_translator()
    return setup_sessions()


def grid_tab_disabled(state) -> bool:
    """The Grid tab needs an AOI to estimate and generate for.

    A running job does not keep it open: its progress and Cancel are on the
    Outputs tab.
    """
    return state.aoi_info.value is None


@solara.component
def WorkflowTabs(map_):
    active = app_state.active_tab.value
    grid_disabled = grid_tab_disabled(app_state)

    # AOI cleared while on the Grid tab: fall back to the AOI tab (in an
    # effect, never during render).
    def back_to_aoi():
        if grid_disabled and app_state.active_tab.value == 1:
            app_state.active_tab.set(0)

    solara.use_effect(back_to_aoi, [grid_disabled, active])

    # TabsItems keeps inactive tabs mounted, so AoiView never removes its draw
    # toolbar when the user leaves the AOI tab: mirror the tab onto the map.
    # Re-run on the AOI loading flag too, because AoiView re-adds the control
    # while it loads.
    dc_hidden = solara.use_ref(False)

    def sync_draw_control():
        dc_hidden.current = sync_draw_control_visibility(
            map_, aoi_active=active == 0, was_hidden=dc_hidden.current
        )

    solara.use_effect(sync_draw_control, [active, app_state.aoi_loading.value])

    # The PMTiles preview draws nothing below its min zoom: the tabs show a
    # "zoom in" hint, so mirror the map's zoom into the state.
    def watch_zoom():
        if map_ is None:
            return None

        def on_zoom(change):
            app_state.map_zoom.set(change["new"])

        app_state.map_zoom.set(map_.zoom)
        map_.observe(on_zoom, "zoom")
        return lambda: map_.unobserve(on_zoom, "zoom")

    solara.use_effect(watch_zoom, [map_])

    with rv.Tabs(v_model=active, on_v_model=app_state.active_tab.set, grow=True):
        rv.Tab(children=[t("tabs.aoi")])
        rv.Tab(disabled=grid_disabled, children=[t("tabs.grid")])
        rv.Tab(children=[t("tabs.outputs")])
    with rv.TabsItems(v_model=active):
        with rv.TabItem():
            AoiTile(state=app_state, map_=map_)
        with rv.TabItem():
            GridTile(state=app_state, map_=map_)
        with rv.TabItem():
            OutputsTile(state=app_state, map_=map_)


REPO_URL = "https://github.com/SerafiniJose/fra-grid-gen"


@solara.component
@with_sepal_sessions(module_name="fra_grid_generator")
def Page():
    gee_interface = get_current_gee_interface()
    theme_state = get_current_theme_state()
    use_app_locale()

    def create_map():
        m = sm.SepalMap(
            zoom=3,
            min_zoom=2,
            center=[0, 0],
            gee=True,
            gee_interface=gee_interface,
            theme_state=theme_state,
            fullscreen=True,
        )
        # Added after init, not via basemaps=, so SepalMap still picks the
        # light/dark SEPAL basemap from the theme; start it hidden.
        m.add_basemap("SATELLITE")
        m.layers[-1].visible = False
        return m

    sepal_map = solara.use_memo(create_map, [id(gee_interface)])

    solara.Title(t("app.title"))
    solara.Style(".dialog-content { overflow-x: hidden !important; }" + NUDGE_CSS)
    # jupyter-loopback comm bridge (local runs), in the page from the first
    # render so tile-URL interception is live before a PMTiles layer is added.
    loopback_bridge = solara.use_memo(_loopback_bridge_widget, [])
    if loopback_bridge is not None:
        solara.display(loopback_bridge)
    # Must be mounted before MapApp: pysepal 4's use_notifications() raises
    # when no provider exists yet.
    NotificationProvider()

    # Left drawer: About and Documentation open as dialogs over the map; About
    # opens by itself when the page loads (initial_step).
    steps_data = [
        {
            "id": 1,
            "name": t("app.about"),
            "icon": "mdi-information-outline",
            "display": "dialog",
            "content": DocPage(page="about"),
            "width": 860,
        },
        {
            "id": 2,
            "name": t("app.documentation"),
            "icon": "mdi-book-open-page-variant-outline",
            "display": "dialog",
            "content": DocPage(page="documentation"),
            "width": 860,
        },
    ]

    MapApp.element(
        app_title=t("app.title"),
        app_icon="mdi-hexagon-multiple",
        main_map=[sepal_map],
        steps_data=steps_data,
        initial_step=1,
        theme_state=theme_state,
        locales=app_available_locales(),
        repo_url=REPO_URL,
        docs_url=f"{REPO_URL}/blob/main/component/doc/en/documentation.md",
        right_panel_config={
            "title": t("app.panel_title"),
            "icon": "mdi-hexagon-multiple-outline",
            "width": 520,
            "toggle_icon": "mdi-chevron-right",
        },
        right_panel_content=[{"content": [WorkflowTabs(map_=sepal_map)]}],
        right_panel_open=True,
        is_pinned=False,
    )


routes = [
    solara.Route(path="/", component=Page, label="FRA Grid Generator"),
]
