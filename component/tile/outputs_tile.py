"""Outputs tab: the job's row, then every grid folder under the results dir, newest first.

One table, laid out like the deforestation-alerts lists: a flexible name column
(with the AOI under it), level, cells, a Status cell that holds the job's
action (Cancel, Retry, Generate), and four action icons that never move and
only switch on and off, each with its tooltip. The job's progress lives in the
notification pill; a grid's files, preview and metadata in its Details dialog.
"""

import logging

import reacton.ipyvuetify as rv
import solara
from pysepal.solara import use_notifications

from component.i18n import t
from component.model.generate_job import busy_names, cancel_generation, dismiss_job, retry_generation
from component.parameter import grid as g
from component.parameter.directory import results_dir
from component.scripts import map_layers
from component.scripts.notify_bridge import ERROR_TOAST_TIMEOUT
from component.scripts.outputs_index import DeleteRefused, delete_output, list_outputs
from component.scripts.solara_threads import spawn_in_context
from component.scripts.writers import human_size
from component.tile.grid_tile import hide_from_map, show_on_map, zoom_hint_visible
from component.widget.confirm_dialog import ConfirmDialog
from component.widget.download_dialog import DownloadDialog
from component.widget.levels_table import compact
from component.widget.metadata_dialog import MetadataDialog

logger = logging.getLogger(g.LOGGER_NAME)


def toggle_preview(state, map_, output, notifier=None) -> None:
    """Hide the grid, or add it on a worker: the map buttons stay off until it is on the map."""
    if state.preview_loading.value is not None:  # clicks queued while a grid was being added
        return
    if state.preview_name.value == output.name:
        hide_from_map(state, map_)
        return
    failed_text = t("common.preview_failed", error="{error}")  # t() must not run on the worker
    state.preview_loading.set(output.name)

    def add():
        try:
            show_on_map(state, map_, output.folder, output.name, output.metadata, notifier, failed_text)
        finally:
            state.preview_loading.set(None)

    spawn_in_context(add)


def delete_texts(name: str) -> dict:
    """The delete's toasts, resolved now: ``t()`` must not run on the worker."""
    return {"busy": t("outputs.busy"), "not_a_grid": t("outputs.not_a_grid", name=name),
            "failed": t("outputs.delete_failed", name=name, error="{error}"), "deleted": t("outputs.deleted", name=name)}


def perform_delete(state, map_, root, output, notifier, texts=None) -> bool:
    """Delete one grid folder (seconds on NFS for a big grid: run it on a worker)."""
    texts = texts or delete_texts(output.name)
    try:
        delete_output(root, output.name, busy=busy_names(state))
    except DeleteRefused as exc:
        if exc.reason == "busy":
            notifier.warning(texts["busy"])
        else:  # removed or replaced outside this session: re-list
            notifier.error(texts["not_a_grid"], timeout=ERROR_TOAST_TIMEOUT)
            state.outputs_signal.set(state.outputs_signal.value + 1)
        return False
    except OSError as exc:
        logger.exception("Delete failed")
        notifier.error(texts["failed"].format(error=exc.strerror or str(exc)), timeout=ERROR_TOAST_TIMEOUT)
        state.outputs_signal.set(state.outputs_signal.value + 1)  # a partial delete changes the list
        return False
    if state.preview_name.value == output.name:
        hide_from_map(state, map_)
    last = state.last_output.value
    if last is not None and last.name == output.name:
        state.last_output.set(None)
    state.outputs_signal.set(state.outputs_signal.value + 1)
    notifier.success(texts["deleted"])
    return True


def start_delete(state, map_, root, output, notifier) -> bool:
    """Delete on a worker; every row's delete stays off until it is done."""
    if state.deleting.value is not None:
        return False
    texts = delete_texts(output.name)
    state.deleting.set(output.name)

    def run():
        try:
            perform_delete(state, map_, root, output, notifier, texts)
        finally:
            state.deleting.set(None)

    spawn_in_context(run)
    return True


# Grid | Level | Cells | Status | four 24 px actions (+8). The name keeps about
# 136 px in the 520 px panel (deforestation-alerts asks at least 120).
_GRID = ("display: grid; grid-template-columns: minmax(0, 1fr) 48px 56px 96px 104px; align-items: center; "
         "column-gap: 8px; width: 100%;")
_LINE = "rgba(127, 127, 127, 0.3)"
_HEAD = (f"{_GRID} padding: 4px 8px 6px; border-bottom: 2px solid {_LINE}; font-size: 0.72rem; font-weight: 600; "
         "text-transform: uppercase; letter-spacing: 0.05em;")
_ROW = f"{_GRID} padding: 5px 8px; border-bottom: 1px solid {_LINE};"
_CLIP = "min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;"
_CELL = "display: flex; align-items: center; gap: 4px; min-width: 0;"
_SUB = "font-size: 11px; line-height: 1.3; opacity: 0.7;"
_NOTE = "grid-column: 1 / -1; font-size: 0.75rem; padding-bottom: 2px;"
# 8 px sides: "Reintentar" and "Réessayer" fit the 96 px Status column (94 px).
_VERB = "text-transform: none; letter-spacing: normal; font-size: 11.5px; padding: 0 8px; height: 24px;"


def _tip(text, child):
    """A tooltip span around ``child``: a disabled button shows no title of its own."""
    with rv.Html(tag="span", style_="display: inline-flex;", attributes={"title": text, "aria-label": text}):
        child()


def _action(icon, tip, on_click, disabled=False, color=None, loading=False):
    _tip(tip, lambda: solara.Button("", icon_name=icon, on_click=on_click, icon=True, text=True, x_small=True,
                                    color=color, disabled=disabled, loading=loading))


def _verb(label, icon, tip, on_click, color=None):
    _tip(tip, lambda: solara.Button(label, icon_name=icon, on_click=on_click, outlined=True, rounded=True,
                                    small=True, color=color, style=_VERB))


def _name_cell(name, aoi):
    with rv.Html(tag="div", style_=f"{_CELL} flex-direction: column; align-items: stretch; gap: 0;"):
        rv.Html(tag="span", style_=_CLIP, attributes={"title": name}, children=[name])
        rv.Html(tag="span", style_=f"{_CLIP} {_SUB}", attributes={"title": aoi}, children=[aoi])


def _level_cell(level):
    with rv.Html(tag="div", style_=_CELL):
        rv.Chip(x_small=True, outlined=True, children=[f"r{level}"])


def _cells_cell(n):
    text, title = (compact(n), f"{n:,}") if n is not None else ("—", "")
    rv.Html(tag="div", style_=f"{_CELL} justify-content: flex-end; font-variant-numeric: tabular-nums;",
            attributes={"title": title}, children=[text])


def _actions(children):
    with rv.Html(tag="div", style_="display: flex; justify-content: flex-end; align-items: center;"):
        children()


def _header():
    with rv.Html(tag="div", style_=_HEAD):
        for key in ("grid", "level", "cells", "status"):
            rv.Html(tag="span", style_=_CLIP + ("text-align: right;" if key == "cells" else ""),
                    children=[t(f"outputs.col.{key}")])
        rv.Html(tag="span", style_=_CLIP + "text-align: right;", children=[t("outputs.col.actions")])


def job_row(state, job, notifier):
    """The job's row while it runs or after it failed or was cancelled (a done job is a grid row)."""
    settings = " · ".join(p for p in (f"r{job.level}", job.aoi_label) if p)
    wait = t("outputs.tip.wait_ready") if job.running else None
    with rv.Html(tag="div", style_=_ROW):
        _name_cell(job.name, job.aoi_label)
        _level_cell(job.level)
        _cells_cell(None)
        with rv.Html(tag="div", style_=_CELL):
            if job.running:
                _verb(t("outputs.cancel"), "mdi-stop-circle", t("outputs.tip.cancel"),
                      lambda: cancel_generation(state))
            elif job.status == "failed":
                _verb(t("outputs.retry"), "mdi-refresh", t("outputs.tip.retry", settings=settings),
                      lambda: retry_generation(state, notifier), color="error")
            else:
                _verb(t("outputs.generate"), "mdi-play", t("outputs.tip.retry", settings=settings),
                      lambda: retry_generation(state, notifier), color="primary")

        def actions():
            _action("mdi-map-plus", wait or t("outputs.tip.no_map"), None, disabled=True)
            _action("mdi-information-outline", wait or t("outputs.tip.no_details"), None, disabled=True)
            _action("mdi-download", wait or t("outputs.tip.no_download"), None, disabled=True)
            _action("mdi-delete-outline", t("outputs.tip.wait_finish") if job.running else t("outputs.tip.dismiss"),
                    lambda: dismiss_job(state), disabled=job.running)

        _actions(actions)
        if job.message and not job.running:
            rv.Html(tag="span", class_="error--text" if job.status == "failed" else "text--secondary",
                    style_=_NOTE, children=[job.message])


@solara.component
def GridRow(out, plan, shown, can_preview, busy, zoom_hint, on_preview, on_details, on_delete, on_download=None,
            loading=None, deleting=None):
    with rv.Html(tag="div", style_=_ROW):
        _name_cell(out.name, out.aoi_label)
        _level_cell(out.level)
        _cells_cell(out.cell_count)
        with rv.Html(tag="div", style_=_CELL):
            rv.Icon(small=True, color="success", children=["mdi-check-circle"])
            rv.Html(tag="span", class_="text--secondary", style_=f"{_CLIP} font-size: 0.8rem;",
                    children=[t("outputs.ready")])

        def actions():
            if not can_preview:
                map_tip = t("outputs.preview_none")
            else:
                map_tip = t("outputs.hide") if shown else t("outputs.show")
            _action("mdi-map-minus" if shown else "mdi-map-plus", map_tip, on_preview,
                    disabled=not can_preview or loading is not None or deleting == out.name,
                    color="primary" if shown else None, loading=loading == out.name)
            _action("mdi-information-outline", t("outputs.tip.details"), on_details)
            _action("mdi-download", t("outputs.tip.download"), on_download, disabled=deleting == out.name)
            _action("mdi-delete-outline", t("outputs.busy") if busy else t("outputs.tip.delete"), on_delete,
                    disabled=busy or deleting is not None, loading=deleting == out.name)

        _actions(actions)
        if zoom_hint:
            rv.Html(tag="span", class_="text--secondary", style_=_NOTE, children=[t("common.zoom_hint")])


@solara.component
def OutputsTile(state, map_):
    notifier = use_notifications()
    to_delete, set_to_delete = solara.use_state(None)
    details, set_details = solara.use_state(None)
    to_download, set_to_download = solara.use_state(None)
    root = results_dir()
    # Re-listed on opening the tab too: another tab or the file manager may have changed the folder.
    on_tab = state.active_tab.value == 2
    outputs = solara.use_memo(lambda: list_outputs(root), [state.outputs_signal.value, on_tab])
    # Check each grid's files once per listing, not per render.
    plans = solara.use_memo(lambda: {o.name: map_layers.plan_preview(o.folder, o.name, o.metadata) for o in outputs},
                            [outputs])
    busy = busy_names(state)
    job = state.job.value
    show_job = job.status in ("running", "failed", "cancelled")

    if not outputs and not show_job:
        solara.Info(t("outputs.empty"))
    else:
        with rv.Html(tag="div", style_="width: 100%;"):
            _header()
            if show_job:
                job_row(state, job, notifier)
            for out in outputs:
                shown = state.preview_name.value == out.name
                GridRow(
                    out=out,
                    plan=plans[out.name],
                    shown=shown,
                    can_preview=map_ is not None and plans[out.name].available,
                    busy=out.name in busy,
                    zoom_hint=shown and zoom_hint_visible(state, out.name),
                    on_preview=lambda o=out: toggle_preview(state, map_, o, notifier),
                    on_details=lambda o=out: set_details(o),
                    on_delete=lambda o=out: set_to_delete(o),
                    on_download=lambda o=out: set_to_download(o),
                    loading=state.preview_loading.value,
                    deleting=state.deleting.value,
                ).key(out.name)

    def confirm_delete():
        target = to_delete
        set_to_delete(None)
        if target is not None:
            start_delete(state, map_, root, target, notifier)

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
    MetadataDialog(output=details, plan=plans.get(details.name) if details else None,
                   on_close=lambda: set_details(None))
    DownloadDialog(output=to_download, on_close=lambda: set_to_download(None), notifier=notifier)
