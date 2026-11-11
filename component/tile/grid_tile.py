"""Grid tab: level, centroids, name and Generate.

The job's progress, Cancel and outcome live on the Outputs tab (and in the
notification pill): Generate switches there once the job has started.
"""

import logging
from datetime import date
from pathlib import Path

import reacton.ipyvuetify as rv
import solara
from pysepal.solara import use_notifications

from component.i18n import t
from component.model.generate_job import job_texts, start_generation
from component.parameter import grid as g
from component.parameter.directory import results_dir
from component.scripts import map_layers
from component.scripts.aoi_prep import default_grid_name
from component.scripts.dggrid_engine import EngineUnavailable, dggrid_executable
from component.scripts.grid_builder import BuildRequest
from component.scripts.levels import estimate_levels, estimated_size_bytes
from component.scripts.metadata import AOI_FILE
from component.scripts.notify_bridge import ERROR_TOAST_TIMEOUT
from component.scripts.outputs_index import name_status, validate_grid_name
from component.scripts.writers import human_size
from component.widget.confirm_dialog import ConfirmDialog
from component.widget.levels_table import LevelsTable

logger = logging.getLogger(g.LOGGER_NAME)


def block_reason(*, running, name_error, name_state, verdict, engine_ok):
    if not engine_ok:
        return "grid.engine_missing"
    if running:
        return "grid.generate"
    if name_error is not None:
        return f"grid.name_error.{name_error}"
    if name_state == "taken":
        return "grid.name_taken"
    if verdict == "blocked":
        return "grid.blocked_hint"
    return None


def confirm_steps(verdict: str, name_state: str) -> list:
    steps = []
    if verdict == "warn":
        steps.append("warn")
    if name_state == "grid":
        steps.append("overwrite")
    return steps


def show_on_map(state, map_, folder, name: str, metadata: dict, notifier=None, failed_text=None) -> bool:
    """Show one grid's preview (PMTiles or GeoJSON) and record it in the state.

    ``failed_text`` is the error toast template (``{error}``), resolved beforehand on a worker.
    """
    plan = map_layers.plan_preview(folder, name, metadata)
    if map_ is None or not plan.available:
        return False
    bbox = metadata.get("aoi", {}).get("bbox")
    try:
        minzoom = map_layers.show_preview(map_, plan, name=name, bounds=bbox, aoi_path=Path(folder) / AOI_FILE)
    except Exception as exc:
        logger.exception("Map preview failed")
        if notifier is not None:
            failed_text = failed_text or t("common.preview_failed", error="{error}")
            notifier.error(failed_text.format(error=str(exc) or type(exc).__name__),
                           timeout=ERROR_TOAST_TIMEOUT)
        return False
    state.preview_minzoom.set(minzoom)
    state.preview_name.set(name)
    return True


def hide_from_map(state, map_) -> None:
    map_layers.remove_grid(map_)
    state.preview_minzoom.set(None)
    state.preview_name.set(None)


def zoom_hint_visible(state, name: str) -> bool:
    return state.preview_name.value == name and map_layers.zoom_hint_needed(
        state.map_zoom.value, state.preview_minzoom.value
    )


def _engine_ok() -> bool:
    try:
        dggrid_executable()
        return True
    except EngineUnavailable:
        return False


@solara.component
def GridTile(state, map_):
    notifier = use_notifications()
    engine_ok = solara.use_memo(_engine_ok, [])
    pending, set_pending = solara.use_state([])  # confirm steps still to accept
    info = state.aoi_info.value
    level = state.level.value
    last_seen = solara.use_ref(state.last_output.value)

    def drop_replaced_preview():
        # A finished run that overwrote the grid on the map: its layer shows
        # the old cells (and its tile server the swapped file), so remove it.
        result = state.last_output.value
        if result is last_seen.current:
            return
        last_seen.current = result
        if result is not None and state.preview_name.value == result.name:
            hide_from_map(state, map_)

    solara.use_effect(drop_replaced_preview, [id(state.last_output.value)])

    def auto_name():
        if info is not None and not state.name_edited.value:
            state.out_name.set(default_grid_name(level, info.slug, date.today()))

    solara.use_effect(auto_name, [id(info), level])
    # Hooks run unconditionally (before the early return), in the same order every render.
    estimates = solara.use_memo(
        lambda: estimate_levels(info.area_km2, info.perimeter_km, info.n_points) if info is not None else [],
        [id(info)],
    )

    if info is None:
        solara.Info(t("grid.locked"))
        return

    est = next(e for e in estimates if e.stats.level == level)
    root = results_dir()
    name = state.out_name.value
    _ = state.outputs_signal.value  # re-check the name after a run or a delete
    name_error = validate_grid_name(name)
    name_state = name_status(root, name) if name_error is None else "free"
    centroids_allowed = level in g.CENTROID_LEVELS
    centroids = state.centroids.value and centroids_allowed
    job = state.job.value
    reason = block_reason(running=job.running, name_error=name_error, name_state=name_state,
                          verdict=est.verdict, engine_ok=engine_ok)

    def launch():
        request = BuildRequest(aoi=info, level=level, name=name,
                               overwrite=name_state == "grid", centroids=centroids)
        if start_generation(state, request, notifier, job_texts(level, info.label, name)):
            state.active_tab.set(2)  # Outputs: the job's row, with Cancel

    def advance(steps):
        if steps:
            set_pending(steps)
        else:
            set_pending([])
            launch()

    def on_name(value):
        state.name_edited.set(True)
        state.out_name.set(value.strip())

    with solara.Column(style="gap: 12px;"):
        if not engine_ok:
            solara.Error(t("grid.engine_missing"))

        solara.Text(t("grid.levels_title"), style="font-weight: 600;")
        LevelsTable(estimates=estimates, selected=level,
                    on_select=lambda lvl: None if job.running else state.level.set(lvl))
        solara.Text(t("grid.caption"), style="font-size: 0.8rem; opacity: 0.7;")

        solara.Checkbox(label=t("grid.centroids"), value=centroids, on_value=state.centroids.set,
                        disabled=job.running or not centroids_allowed)
        solara.Text(t("grid.centroids_hint") if centroids_allowed else t("grid.centroids_disabled"),
                    style="font-size: 0.8rem; opacity: 0.7;")

        rv.TextField(
            label=t("grid.name_label"), v_model=name, on_v_model=on_name, dense=True, outlined=True,
            hint=t("grid.name_hint"), persistent_hint=True, disabled=job.running,
            error_messages=[t(f"grid.name_error.{name_error}")] if name_error else [],
        )
        if name_state == "grid":
            solara.Warning(t("grid.name_exists"), dense=True)
        elif name_state == "taken":
            solara.Error(t("grid.name_taken"), dense=True)

        if reason == "grid.blocked_hint":
            solara.Error(t(reason, cells=f"{est.cells:,}"))

        with solara.Row(justify="end"):
            solara.Button(t("grid.generate"), color="primary", disabled=reason is not None,
                          on_click=lambda: advance(confirm_steps(est.verdict, name_state)))

    step = pending[0] if pending else None
    ConfirmDialog(
        open=step == "warn",
        on_cancel=lambda: set_pending([]),
        on_confirm=lambda: advance(pending[1:]),
        title=t("grid.warn_title"),
        message=t("grid.warn_message", cells=f"{est.cells:,}",
                  size=human_size(estimated_size_bytes(est.cells))),
        confirm_label=t("grid.warn_confirm"),
        confirm_color="warning",
    )
    ConfirmDialog(
        open=step == "overwrite",
        on_cancel=lambda: set_pending([]),
        on_confirm=lambda: advance(pending[1:]),
        title=t("grid.overwrite_title"),
        message=t("grid.overwrite_message", name=name),
        confirm_label=t("grid.overwrite_confirm"),
    )
