"""Outputs tab: the grid being generated (JobCard), then every grid folder under the results dir, newest first.

Each grid is a slim card; clicking its header opens its details and actions,
one card at a time (``state.open_output``).
"""

import logging

import reacton.ipyvuetify as rv
import solara
from pysepal.solara import use_notifications

from component.i18n import t
from component.model.generate_job import busy_names
from component.parameter import grid as g
from component.parameter.directory import results_dir
from component.scripts import map_layers
from component.scripts.notify_bridge import ERROR_TOAST_TIMEOUT
from component.scripts.outputs_index import DeleteRefused, delete_output, list_outputs
from component.scripts.writers import human_size
from component.tile.grid_tile import hide_from_map, show_on_map, zoom_hint_visible
from component.widget.confirm_dialog import ConfirmDialog
from component.widget.job_card import JobCard
from component.widget.metadata_dialog import MetadataDialog

logger = logging.getLogger(g.LOGGER_NAME)


def toggle_preview(state, map_, output, notifier=None) -> None:
    if state.preview_name.value == output.name:
        hide_from_map(state, map_)
        return
    show_on_map(state, map_, output.folder, output.name, output.metadata, notifier)


def perform_delete(state, map_, root, output, notifier) -> bool:
    try:
        delete_output(root, output.name, busy=busy_names(state))
    except DeleteRefused as exc:
        if exc.reason == "busy":
            notifier.warning(t("outputs.busy"))
        else:  # removed or replaced outside this session: re-list
            notifier.error(t("outputs.not_a_grid", name=output.name), timeout=ERROR_TOAST_TIMEOUT)
            state.outputs_signal.set(state.outputs_signal.value + 1)
        return False
    except OSError as exc:
        logger.exception("Delete failed")
        notifier.error(t("outputs.delete_failed", name=output.name, error=exc.strerror or str(exc)),
                       timeout=ERROR_TOAST_TIMEOUT)
        state.outputs_signal.set(state.outputs_signal.value + 1)  # a partial delete changes the list
        return False
    if state.preview_name.value == output.name:
        hide_from_map(state, map_)
    last = state.last_output.value
    if last is not None and last.name == output.name:
        state.last_output.set(None)
    if state.open_output.value == output.name:
        state.open_output.set(None)
    state.outputs_signal.set(state.outputs_signal.value + 1)
    notifier.success(t("outputs.deleted", name=output.name))
    return True


_HINT = "display: block; font-size: 0.8rem; opacity: 0.7;"
_MONO = "font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 0.75rem; overflow-wrap: anywhere;"
_PRIMARY = "var(--v-primary-base, #76591e)"
_OPEN_STYLE = (f"border-color: {_PRIMARY}; box-shadow: inset 3px 0 0 {_PRIMARY}; "
               "background: rgba(0, 128, 96, 0.06);")


def summary_line(out) -> str:
    """The closed card's line: level, cells, AOI, generation time (UTC, to the minute)."""
    when = out.generated_at[:16].replace("T", " ")
    parts = [f"r{out.level}", t("outputs.cells", cells=f"{out.cell_count:,}"), out.aoi_label, when]
    return " · ".join(p for p in parts if p)


def aoi_line(out) -> str:
    aoi = out.metadata.get("aoi", {})
    if aoi.get("n_points"):
        extent = t("outputs.points", n=f"{aoi['n_points']:,}")
    elif aoi.get("area_km2") is not None:
        extent = f"{aoi['area_km2']:,.0f} km²"
    else:
        extent = ""
    return " · ".join(p for p in (aoi.get("method"), aoi.get("label"), extent) if p)


def run_line(out) -> str:
    run = out.metadata.get("run", {})
    parts = []
    if run.get("n_tiles"):
        parts.append(t("outputs.tiles", n=run["n_tiles"]))
    if run.get("duration_s") is not None:
        parts.append(f"{run['duration_s']:.1f} s")
    parts.append(t("outputs.total", size=human_size(out.size_bytes)))
    return " · ".join(parts)


def preview_line(plan) -> str:
    if plan.pmtiles is not None:
        return t("outputs.preview_pmtiles", min=plan.minzoom, max=plan.maxzoom)
    if plan.vector is not None:
        return t("outputs.preview_geojson")
    return t("outputs.preview_none")


def _detail_row(label, value):
    with solara.Row(style="gap: 8px; flex-wrap: nowrap; font-size: 0.8rem;"):
        solara.Text(label, style="flex: none; width: 96px; opacity: 0.65;")
        solara.Text(value, style="overflow-wrap: anywhere;")


@solara.component
def OutputCard(out, plan, is_open, shown, can_preview, busy, zoom_hint, on_toggle, on_preview, on_metadata,
               on_delete):
    """One grid: a slim card (name, summary, map shortcut) that opens into its details and actions."""
    with rv.Card(outlined=True, class_="pa-2", style_=_OPEN_STYLE if is_open else ""):
        with solara.Row(style="gap: 4px; align-items: flex-start; flex-wrap: nowrap;"):
            with rv.Html(tag="div", class_="output-head",
                         style_="cursor: pointer; flex: 1 1 auto; min-width: 0;") as head:
                solara.Text(out.name, style="display: block; font-weight: 600; overflow-wrap: anywhere;")
                solara.Text(summary_line(out), style=_HINT)
            rv.use_event(head, "click", lambda *_: on_toggle())
            if not is_open:
                solara.Button(icon_name="mdi-eye-off" if shown else "mdi-eye", icon=True, small=True,
                              color="primary", classes=["output-eye"], disabled=not can_preview,
                              attributes={"title": t("outputs.hide") if shown else t("outputs.show")},
                              on_click=on_preview)
            solara.Button(icon_name="mdi-chevron-up" if is_open else "mdi-chevron-down", icon=True, small=True,
                          on_click=on_toggle)
        if zoom_hint:
            solara.Text(t("common.zoom_hint"), style=_HINT)
        if not is_open:
            return
        with solara.Column(style="gap: 2px; margin-top: 8px; padding-top: 8px; border-top: 1px dashed rgba(127, 127, 127, 0.4);"):
            _detail_row(t("outputs.aoi"), aoi_line(out))
            _detail_row(t("outputs.run"), run_line(out))
            _detail_row(t("outputs.preview"), preview_line(plan))
            with solara.Column(style="gap: 0; margin-top: 6px;"):
                for file_name, size in out.files:
                    with solara.Row(justify="space-between", style="gap: 8px; flex-wrap: nowrap;"):
                        solara.Text(file_name, style=_MONO)
                        solara.Text(human_size(size), style=f"{_MONO} flex: none;")
            solara.Text(str(out.folder), style=f"display: block; margin-top: 4px; opacity: 0.8; {_MONO}")
        with solara.Row(justify="end", style="gap: 4px;"):
            solara.Button(t("outputs.hide") if shown else t("outputs.show"), small=True, text=True,
                          icon_name="mdi-eye-off" if shown else "mdi-eye", disabled=not can_preview,
                          on_click=on_preview)
            solara.Button(t("outputs.metadata"), small=True, text=True, icon_name="mdi-information",
                          on_click=on_metadata)
            solara.Button(t("common.delete"), small=True, text=True, color="error", icon_name="mdi-delete",
                          disabled=busy, on_click=on_delete)


@solara.component
def OutputsTile(state, map_):
    notifier = use_notifications()
    to_delete, set_to_delete = solara.use_state(None)
    meta, set_meta = solara.use_state(None)
    root = results_dir()
    # Re-listed on opening the tab too: another tab or the file manager may have changed the folder.
    on_tab = state.active_tab.value == 2
    outputs = solara.use_memo(lambda: list_outputs(root), [state.outputs_signal.value, on_tab])
    # Each progress tick re-renders this tile: check each grid's files once per listing, not per render.
    plans = solara.use_memo(lambda: {o.name: map_layers.plan_preview(o.folder, o.name, o.metadata) for o in outputs},
                            [outputs])
    busy = busy_names(state)
    job = state.job.value
    # While the job card says "Ready" it stands for the new grid: no second entry below it.
    handing_over = job.name if job.status == "done" else None

    def toggle_open(name):
        state.open_output.set(None if state.open_output.value == name else name)

    with solara.Column(style="gap: 12px;"):
        solara.Text(t("outputs.title"), style="font-weight: 600;")
        JobCard(state=state)
        if not outputs and job.status == "idle":  # no job card above
            solara.Info(t("outputs.empty"))
        for out in outputs:
            if out.name == handing_over:
                continue
            shown = state.preview_name.value == out.name
            OutputCard(
                out=out,
                plan=plans[out.name],
                is_open=state.open_output.value == out.name,
                shown=shown,
                can_preview=map_ is not None and plans[out.name].available,
                busy=out.name in busy,
                zoom_hint=shown and zoom_hint_visible(state, out.name),
                on_toggle=lambda n=out.name: toggle_open(n),
                on_preview=lambda o=out: toggle_preview(state, map_, o, notifier),
                on_metadata=lambda o=out: set_meta(o),
                on_delete=lambda o=out: set_to_delete(o),
            ).key(out.name)

    def confirm_delete():
        target = to_delete
        set_to_delete(None)
        if target is not None:
            perform_delete(state, map_, root, target, notifier)

    ConfirmDialog(
        open=to_delete is not None,
        on_cancel=lambda: set_to_delete(None),
        on_confirm=confirm_delete,
        title=t("outputs.delete_title"),
        message=t("outputs.delete_message", name=to_delete.name if to_delete else "",
                  size=human_size(to_delete.size_bytes) if to_delete else ""),
        confirm_label=t("common.delete"),
        details=[f"{n} ({human_size(s)})" for n, s in to_delete.files] if to_delete else None,
    )
    MetadataDialog(output=meta, on_close=lambda: set_meta(None))
