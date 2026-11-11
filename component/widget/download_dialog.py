"""Download one layer of a grid (hexagons or centroids) as a zipped GPKG or Shapefile.

Rendered once per tile and opened by setting ``output`` (see ConfirmDialog for why).
The zip is built on solara's download thread in local scratch, read into memory
and sent to the browser through the widget comm, then removed.
"""

import logging
import shutil
import tempfile

import reacton.ipyvuetify as rv
import solara

from component.i18n import t
from component.parameter import grid as g
from component.scripts.notify_bridge import ERROR_TOAST_TIMEOUT
from component.scripts.scratch import local_scratch_dir
from component.scripts.writers import export_zip

logger = logging.getLogger(g.LOGGER_NAME)


def zip_bytes(folder, layer: str, fmt: str) -> bytes:
    # shortcut: the whole zip is held in memory (kernel and browser), fine up to a few hundred MB;
    # past that, serve the file over HTTP (the PMTiles proxy route) instead.
    work = tempfile.mkdtemp(prefix="download_", dir=local_scratch_dir())
    try:
        return export_zip(folder, layer, fmt, work).read_bytes()
    finally:
        shutil.rmtree(work, ignore_errors=True)


@solara.component
def DownloadDialog(output, on_close, notifier):
    kind, set_kind = solara.use_state("cells")
    fmt, set_fmt = solara.use_state("gpkg")
    centroids = (output.metadata.get("centroids") or {}).get("layer") if output else None
    shp_ok = output is not None and output.cell_count <= g.SHP_MAX_CELLS
    kind = kind if centroids else "cells"
    fmt = fmt if shp_ok else "gpkg"
    layer = centroids if kind == "centroids" else (output.name if output else "")
    failed = t("download.failed", error="{error}")  # t() must not run on the worker

    def build():
        try:
            return zip_bytes(output.folder, layer, fmt)
        except Exception as exc:
            logger.exception("Download failed")
            notifier.error(failed.format(error=exc), timeout=ERROR_TOAST_TIMEOUT)
            on_close()  # unmounts the download button, so the next try starts clean
            return None

    # FileDownload resets whenever ``data`` changes: keep one callable per choice.
    data = solara.use_memo(lambda: build, [output and output.name, layer, fmt])

    with rv.Dialog(v_model=output is not None, on_v_model=lambda v: None if v else on_close(), max_width="400px"):
        if output is not None:
            with rv.Card():
                with rv.CardTitle():
                    solara.Text(t("download.title", name=output.name))
                with rv.CardText():
                    solara.Text(t("download.layer"), style="font-weight: 600;")
                    with rv.RadioGroup(v_model=kind, on_v_model=set_kind, row=True, dense=True, hide_details=True):
                        rv.Radio(label=t("download.cells"), value="cells")
                        rv.Radio(label=t("download.centroids"), value="centroids", disabled=not centroids)
                    solara.Text(t("download.format"), style="display: block; margin-top: 12px; font-weight: 600;")
                    with rv.RadioGroup(v_model=fmt, on_v_model=set_fmt, row=True, dense=True, hide_details=True):
                        rv.Radio(label=t("download.gpkg"), value="gpkg")
                        rv.Radio(label=t("download.shp"), value="shp", disabled=not shp_ok)
                    if not shp_ok or fmt == "shp":
                        solara.Text(t("download.shp_hint") if shp_ok else t("download.shp_disabled"),
                                    style="display: block; font-size: 0.78rem; opacity: 0.7;")
                with rv.CardActions(style_="justify-content: flex-end; gap: 8px;"):
                    solara.Button(t("common.close"), on_click=on_close, text=True, small=True)
                    solara.FileDownload(data, filename=f"{layer}_{fmt}.zip", label=t("download.button"),
                                        mime_type="application/zip")
