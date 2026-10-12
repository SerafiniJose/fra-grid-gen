"""Grid tab: level, name, formats, Generate/Cancel, inline progress, result card."""

import logging
from datetime import date
from pathlib import Path

import reacton.ipyvuetify as rv
import solara
from pysepal.solara import use_notifications

from component.i18n import t
from component.model.generate_job import cancel_generation, job_texts, start_generation
from component.parameter import grid as g
from component.parameter.directory import results_dir
from component.scripts import map_layers
from component.scripts.aoi_prep import default_grid_name
from component.scripts.dggrid_engine import EngineUnavailable, dggrid_executable
from component.scripts.grid_builder import BuildRequest
from component.scripts.levels import estimate_levels, estimated_size_bytes
from component.scripts.metadata import AOI_FILE
from component.scripts.notify_bridge import ERROR_TOAST_TIMEOUT
from component.scripts.outputs_index import load_output, name_status, validate_grid_name
from component.scripts.writers import human_size
from component.widget.confirm_dialog import ConfirmDialog
from component.widget.levels_table import LevelsTable
from component.widget.metadata_dialog import MetadataDialog

logger = logging.getLogger(g.LOGGER_NAME)

_HINT = "display: block; font-size: 0.8rem; opacity: 0.7;"
_MONO = "display: block; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 0.78rem; overflow-wrap: anywhere;"


def effective_formats(formats, shp_allowed: bool) -> tuple:
    return tuple(sorted(f for f in formats if f != "shp" or shp_allowed))


def block_reason(*, running, name_error, name_state, formats, verdict, engine_ok):
    if not engine_ok:
        return "grid.engine_missing"
    if running:
        return "grid.generate"
    if name_error is not None:
        return f"grid.name_error.{name_error}"
    if name_state == "taken":
        return "grid.name_taken"
    if not formats:
        return "grid.formats_empty"
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


def show_on_map(state, map_, folder, name: str, metadata: dict, notifier=None) -> bool:
    """Show one grid's preview (PMTiles or GeoJSON) and record it in the state."""
    plan = map_layers.plan_preview(folder, name, metadata)
    if map_ is None or not plan.available:
        return False
    bbox = metadata.get("aoi", {}).get("bbox")
    try:
        minzoom = map_layers.show_preview(map_, plan, name=name, bounds=bbox, aoi_path=Path(folder) / AOI_FILE)
    except Exception as exc:
        logger.exception("Map preview failed")
        if notifier is not None:
            notifier.error(t("common.preview_failed", error=str(exc) or type(exc).__name__),
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


def file_lines(files) -> list:
    """One "name · size" line per output file; files that vanished are skipped."""
    lines = []
    for path in files:
        try:
            lines.append(f"{path.name} · {human_size(path.stat().st_size)}")
        except OSError:
            continue
    return lines


def _engine_ok() -> bool:
    try:
        dggrid_executable()
        return True
    except EngineUnavailable:
        return False


@solara.component
def ResultCard(result, map_, on_show, on_metadata, zoom_hint=False):
    plan = map_layers.plan_preview(result.folder, result.name, result.metadata)
    with rv.Card(outlined=True):
        with rv.CardTitle():
            solara.Text(t("grid.result_title"))
        with rv.CardText():
            solara.Text(t("grid.result_summary", cells=f"{result.cell_count:,}",
                          seconds=f"{result.duration_s:.1f}"), style="display: block;")
            for line in file_lines(result.files):
                solara.Text(line, style=_MONO)
            solara.Text(str(result.folder), style=_MONO)
            if not plan.available and result.cell_count > g.PREVIEW_MAX_CELLS:
                solara.Text(t("grid.preview_too_large"), style=_HINT)
            if zoom_hint:
                solara.Text(t("common.zoom_hint"), style=_HINT)
        with rv.CardActions():
            solara.Button(t("grid.show_on_map"), on_click=on_show, small=True, text=True,
                          disabled=not plan.available or map_ is None)
            solara.Button(t("grid.view_metadata"), small=True, text=True, on_click=on_metadata)


@solara.component
def JobPanel(state, map_, root, on_metadata, show_cancel):
    """Job controls and outcome: Cancel, progress, failed/cancelled message, result card.

    Rendered with or without an AOI, so a job stays cancellable while the AOI
    tab re-resolves (``aoi_info`` is None then).
    """
    notifier = use_notifications()
    job = state.job.value
    if job.running:
        if show_cancel:
            with solara.Row(justify="end"):
                solara.Button(t("grid.cancel"), on_click=lambda: cancel_generation(state), outlined=True)
        pct = int(job.done * 100 / job.total) if job.total else 0
        rv.ProgressLinear(value=pct, indeterminate=job.total == 0, color="primary", height=6)
        if job.total:
            solara.Text(t("grid.progress", done=job.done, total=job.total, cells=f"{job.cells:,}"),
                        style="font-size: 0.8rem;")
    elif job.status == "failed":
        solara.Error(job.message)
    elif job.status == "cancelled":
        solara.Warning(job.message)

    result = state.last_output.value
    if job.status == "done" and result is not None:
        ResultCard(result=result, map_=map_,
                   on_show=lambda: show_on_map(state, map_, result.folder, result.name, result.metadata, notifier),
                   on_metadata=lambda: on_metadata(load_output(root, result.name)),
                   zoom_hint=zoom_hint_visible(state, result.name))


@solara.component
def GridTile(state, map_):
    notifier = use_notifications()
    engine_ok = solara.use_memo(_engine_ok, [])
    pending, set_pending = solara.use_state([])  # confirm steps still to accept
    meta_open, set_meta_open = solara.use_state(None)
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
        with solara.Column(style="gap: 12px;"):
            if not state.job.value.running:
                solara.Info(t("grid.locked"))
            JobPanel(state=state, map_=map_, root=results_dir(), on_metadata=set_meta_open, show_cancel=True)
        MetadataDialog(output=meta_open, on_close=lambda: set_meta_open(None))
        return

    est = next(e for e in estimates if e.stats.level == level)
    root = results_dir()
    name = state.out_name.value
    _ = state.outputs_signal.value  # re-check the name after a run or a delete
    name_error = validate_grid_name(name)
    name_state = name_status(root, name) if name_error is None else "free"
    formats = effective_formats(state.formats.value, est.shp_allowed)
    job = state.job.value
    reason = block_reason(running=job.running, name_error=name_error, name_state=name_state,
                          formats=formats, verdict=est.verdict, engine_ok=engine_ok)

    def launch():
        request = BuildRequest(aoi=info, level=level, name=name, formats=formats,
                               overwrite=name_state == "grid")
        start_generation(state, request, notifier, job_texts(level, info.label, name))

    def advance(steps):
        if steps:
            set_pending(steps)
        else:
            set_pending([])
            launch()

    def on_name(value):
        state.name_edited.set(True)
        state.out_name.set(value.strip())

    def toggle_format(fmt, on):
        current = set(state.formats.value)
        (current.add if on else current.discard)(fmt)
        state.formats.set(frozenset(current))

    with solara.Column(style="gap: 12px;"):
        if not engine_ok:
            solara.Error(t("grid.engine_missing"))

        solara.Text(t("grid.levels_title"), style="font-weight: 600;")
        LevelsTable(estimates=estimates, selected=level,
                    on_select=lambda lvl: None if job.running else state.level.set(lvl))
        solara.Text(t("grid.caption"), style="font-size: 0.8rem; opacity: 0.7;")
        if level > g.FRA_LEVEL:
            rv.Chip(small=True, outlined=True, color="warning", children=[t("grid.unvalidated")])

        rv.TextField(
            label=t("grid.name_label"), v_model=name, on_v_model=on_name, dense=True, outlined=True,
            hint=t("grid.name_hint"), persistent_hint=True, disabled=job.running,
            error_messages=[t(f"grid.name_error.{name_error}")] if name_error else [],
        )
        if name_state == "grid":
            solara.Warning(t("grid.name_exists"), dense=True)
        elif name_state == "taken":
            solara.Error(t("grid.name_taken"), dense=True)

        solara.Text(t("grid.formats_title"), style="font-weight: 600;")
        solara.Checkbox(label=t("grid.gpkg"), value="gpkg" in state.formats.value,
                        on_value=lambda on: toggle_format("gpkg", on), disabled=job.running)
        solara.Checkbox(label=t("grid.shp"), value="shp" in formats,
                        on_value=lambda on: toggle_format("shp", on),
                        disabled=job.running or not est.shp_allowed)
        solara.Text(t("grid.shp_hint") if est.shp_allowed else t("grid.shp_disabled"),
                    style="font-size: 0.8rem; opacity: 0.7;")

        solara.Text(t("grid.folder"), style="font-weight: 600;")
        solara.Text(str(root / name), style=_MONO)

        if reason == "grid.blocked_hint":
            solara.Error(t(reason, cells=f"{est.cells:,}"))
        elif reason == "grid.formats_empty":
            solara.Warning(t(reason), dense=True)

        with solara.Row(justify="end"):
            if job.running:
                solara.Button(t("grid.cancel"), on_click=lambda: cancel_generation(state), outlined=True)
            solara.Button(t("grid.generate"), color="primary", disabled=reason is not None,
                          on_click=lambda: advance(confirm_steps(est.verdict, name_state)))

        JobPanel(state=state, map_=map_, root=root, on_metadata=set_meta_open, show_cancel=False)

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
    MetadataDialog(output=meta_open, on_close=lambda: set_meta_open(None))
