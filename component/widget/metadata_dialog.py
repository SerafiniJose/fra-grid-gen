"""Read-only view of a grid's metadata.json, with its absolute folder path."""

import json

import reacton.ipyvuetify as rv
import solara

from component.i18n import t

_MONO = "font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 0.78rem; overflow-wrap: anywhere;"


def _fmt(value) -> str:
    if value is None:
        return "—"
    if isinstance(value, (list, tuple)):
        return ", ".join(str(v) for v in value)
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def metadata_sections(record: dict) -> list:
    """(section i18n key, [(label, value), ...]) in display order. Labels are field names, not translated."""
    gen, dggs, aoi, run, corr = (record.get(k, {}) for k in ("generator", "dggs", "aoi", "run", "correction"))
    return [
        ("metadata.generated", [("Date (UTC)", _fmt(record.get("generated_at"))),
                                ("App", f"{gen.get('app', '')} {gen.get('app_version', '')}".strip()),
                                ("DGGRID", _fmt(gen.get("dggrid"))), ("dggrid4py", _fmt(gen.get("dggrid4py"))),
                                ("User", _fmt(gen.get("sepal_user")))]),
        ("metadata.dggs", [("Type", _fmt(dggs.get("type"))), ("Resolution", _fmt(dggs.get("resolution"))),
                           ("FRA RSS level", _fmt(dggs.get("is_fra_rss_level")))]),
        ("metadata.aoi", [("Method", _fmt(aoi.get("method"))), ("Label", _fmt(aoi.get("label"))),
                          ("Area (km²)", _fmt(aoi.get("area_km2"))), ("Points", _fmt(aoi.get("n_points"))),
                          ("Bounding box", _fmt(aoi.get("bbox")))]),
        ("metadata.run", [("Cells", _fmt(run.get("cell_count"))), ("Tiles", _fmt(run.get("n_tiles"))),
                          ("Tile size (°)", _fmt(run.get("tile_deg"))), ("Duration (s)", _fmt(run.get("duration_s"))),
                          ("Formats", _fmt(run.get("formats")))]),
        ("metadata.correction", [("Spec", _fmt(corr.get("spec"))),
                                 ("Validated at levels", _fmt(corr.get("validated_at_levels")))]),
    ]


@solara.component
def MetadataDialog(output, on_close):
    open_ = output is not None
    with rv.Dialog(v_model=open_, on_v_model=lambda v: None if v else on_close(), max_width="560px", scrollable=True):
        if output is None:
            return
        with rv.Card():
            with rv.CardTitle():
                solara.Text(t("metadata.title", name=output.name))
            with rv.CardText():
                solara.Text(t("metadata.folder"), style="font-weight: 600;")
                solara.Text(str(output.folder), style=_MONO + "user-select: all;")
                for key, items in metadata_sections(output.metadata):
                    solara.Text(t(key), style="font-weight: 600; margin-top: 12px;")
                    with rv.SimpleTable(dense=True):
                        with rv.Html(tag="tbody"):
                            for label, value in items:
                                rv.Html(tag="tr", children=[rv.Html(tag="td", children=[label]),
                                                            rv.Html(tag="td", children=[value])])
                with rv.ExpansionPanels(flat=True, class_="mt-3"):
                    with rv.ExpansionPanel():
                        rv.ExpansionPanelHeader(children=[t("metadata.raw")])
                        with rv.ExpansionPanelContent():
                            rv.Html(tag="pre", style_=_MONO,
                                    children=[json.dumps(output.metadata, indent=2, ensure_ascii=False)])
            with rv.CardActions(style_="justify-content: flex-end;"):
                solara.Button(t("common.close"), on_click=on_close, text=True, small=True)
