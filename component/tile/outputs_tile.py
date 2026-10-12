"""Outputs tab: every grid folder under the results dir, newest first."""

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
        else:
            notifier.error(t("outputs.delete_failed", name=output.name, error=exc.reason),
                           timeout=ERROR_TOAST_TIMEOUT)
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
    state.outputs_signal.set(state.outputs_signal.value + 1)
    notifier.success(t("outputs.deleted", name=output.name))
    return True


@solara.component
def OutputsTile(state, map_):
    notifier = use_notifications()
    to_delete, set_to_delete = solara.use_state(None)
    meta, set_meta = solara.use_state(None)
    root = results_dir()
    outputs = solara.use_memo(lambda: list_outputs(root), [state.outputs_signal.value])
    busy = busy_names(state)

    with solara.Column(style="gap: 12px;"):
        with solara.Row(justify="space-between", style="align-items: center;"):
            solara.Text(t("outputs.title"), style="font-weight: 600;")
            solara.Button(t("common.refresh"), icon_name="mdi-refresh", text=True, small=True,
                          on_click=lambda: state.outputs_signal.set(state.outputs_signal.value + 1))
        if not outputs:
            solara.Info(t("outputs.empty"))
        for out in outputs:
            shown = state.preview_name.value == out.name
            can_preview = map_ is not None and map_layers.plan_preview(out.folder, out.name, out.metadata).available
            with rv.Card(outlined=True, class_="pa-2"):
                solara.Text(out.name, style="display: block; font-weight: 600; overflow-wrap: anywhere;")
                solara.Text(
                    f"r{out.level} · {t('outputs.cells', cells=f'{out.cell_count:,}')} · {out.aoi_label} · "
                    f"{out.generated_at} · {human_size(out.size_bytes)} · {', '.join(out.formats)}",
                    style="display: block; font-size: 0.8rem; opacity: 0.7;",
                )
                if shown and zoom_hint_visible(state, out.name):
                    solara.Text(t("common.zoom_hint"), style="display: block; font-size: 0.8rem; opacity: 0.7;")
                with solara.Row(justify="end", style="gap: 4px;"):
                    solara.Button(t("outputs.hide") if shown else t("outputs.show"), small=True, text=True,
                                  icon_name="mdi-eye-off" if shown else "mdi-eye", disabled=not can_preview,
                                  on_click=lambda o=out: toggle_preview(state, map_, o, notifier))
                    solara.Button(t("outputs.metadata"), small=True, text=True, icon_name="mdi-information",
                                  on_click=lambda o=out: set_meta(o))
                    solara.Button(t("common.delete"), small=True, text=True, color="error",
                                  icon_name="mdi-delete", disabled=out.name in busy,
                                  on_click=lambda o=out: set_to_delete(o))

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
