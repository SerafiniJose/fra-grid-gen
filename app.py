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
from component.scripts.outputs_index import cleanup_stale
from component.scripts.scratch import configure_gdal_tmpdir
from component.tile.aoi_tile import AoiTile
from component.tile.grid_tile import GridTile
from component.tile.outputs_tile import OutputsTile

logger = setup_logging(logger_name=g.LOGGER_NAME)
# Tile milestones -> notification pill; also lifts the logger to INFO when
# logging_config.toml is missing (the root's WARNING would hide them).
install_task_log_handler()
# GDAL scratch files must never land in the read-only CWD on SEPAL.
configure_gdal_tmpdir()
# Leftovers of a run killed mid-write (server restart, instance stop).
_removed = cleanup_stale(results_dir())
if _removed:
    logger.info("Removed unfinished folders: %s", ", ".join(_removed))

setup_solara_server(extra_asset_locations=[])


@solara.lab.on_kernel_start
def on_kernel_start():
    """Reset per-kernel state and open the SEPAL sessions."""
    reset_translator()
    return setup_sessions()


def grid_tab_disabled(state) -> bool:
    """The Grid tab needs an AOI to estimate and generate for.

    It stays open while a job runs, even when the AOI is cleared or being
    re-resolved, so Cancel and the progress stay reachable.
    """
    return state.aoi_info.value is None and not state.job.value.running


@solara.component
def WorkflowTabs(map_):
    active = app_state.active_tab.value
    grid_disabled = grid_tab_disabled(app_state)

    # AOI cleared while on the Grid tab: fall back to the AOI tab (in an
    # effect, never during render). Never while a job runs: grid_disabled is
    # False then.
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


@solara.component
@with_sepal_sessions(module_name="fra_grid_generator")
def Page():
    gee_interface = get_current_gee_interface()
    theme_state = get_current_theme_state()
    use_app_locale()

    def create_map():
        return sm.SepalMap(
            zoom=3,
            min_zoom=2,
            center=[0, 0],
            gee=True,
            gee_interface=gee_interface,
            theme_state=theme_state,
            fullscreen=True,
        )

    sepal_map = solara.use_memo(create_map, [id(gee_interface)])

    solara.Title(t("app.title"))
    solara.Style(".dialog-content { overflow-x: hidden !important; }")
    # Must be mounted before MapApp: pysepal 4's use_notifications() raises
    # when no provider exists yet.
    NotificationProvider()

    MapApp.element(
        app_title=t("app.title"),
        app_icon="mdi-hexagon-multiple",
        main_map=[sepal_map],
        theme_state=theme_state,
        locales=app_available_locales(),
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
