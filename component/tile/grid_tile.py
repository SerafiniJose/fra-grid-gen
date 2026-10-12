"""Grid tab: level, name, formats, Generate/Cancel, inline progress, result card."""

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
from component.scripts.outputs_index import load_output, name_status, validate_grid_name
from component.scripts.writers import human_size
from component.widget.confirm_dialog import ConfirmDialog
from component.widget.levels_table import LevelsTable
from component.widget.metadata_dialog import MetadataDialog

_MONO = "font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 0.78rem; overflow-wrap: anywhere;"


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


def preview_source(folder, name: str, formats):
    folder = Path(folder)
    for fmt in ("gpkg", "shp"):
        path = folder / f"{name}.{fmt}"
        if fmt in formats and path.exists():
            return path, name
    return None


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
def ResultCard(result, map_, on_show, on_metadata):
    source = preview_source(result.folder, result.name, result.metadata["run"]["formats"])
    too_big = result.cell_count > g.PREVIEW_MAX_CELLS
    with rv.Card(outlined=True):
        with rv.CardTitle():
            solara.Text(t("grid.result_title"))
        with rv.CardText():
            solara.Text(t("grid.result_summary", cells=f"{result.cell_count:,}",
                          seconds=f"{result.duration_s:.1f}"))
            for line in file_lines(result.files):
                solara.Text(line, style=_MONO)
            solara.Text(str(result.folder), style=_MONO)
            if too_big:
                solara.Text(t("grid.preview_too_large"), style="font-size: 0.8rem; opacity: 0.7;")
        with rv.CardActions():
            solara.Button(t("grid.show_on_map"), on_click=on_show, small=True, text=True,
                          disabled=too_big or source is None or map_ is None)
            solara.Button(t("grid.view_metadata"), small=True, text=True, on_click=on_metadata)


@solara.component
def JobPanel(state, map_, root, on_metadata, show_cancel):
    """Job controls and outcome: Cancel, progress, failed/cancelled message, result card.

    Rendered with or without an AOI, so a job stays cancellable while the AOI
    tab re-resolves (``aoi_info`` is None then).
    """
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
        def show():
            source = preview_source(result.folder, result.name, result.metadata["run"]["formats"])
            if source is None or map_ is None:
                return
            map_layers.show_grid(map_, source[0], source[1], name=result.name)
            state.preview_name.set(result.name)

        ResultCard(result=result, map_=map_, on_show=show,
                   on_metadata=lambda: on_metadata(load_output(root, result.name)))


@solara.component
def GridTile(state, map_):
    notifier = use_notifications()
    engine_ok = solara.use_memo(_engine_ok, [])
    pending, set_pending = solara.use_state([])  # confirm steps still to accept
    meta_open, set_meta_open = solara.use_state(None)
    info = state.aoi_info.value
    level = state.level.value

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
