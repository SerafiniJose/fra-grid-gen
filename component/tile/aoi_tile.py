"""AOI tab: pysepal's AoiView, then a background read of the geometry into AoiInfo.

AoiView publishes an AoiResult as soon as the user picks an area. Turning it
into an AoiInfo (an EE getInfo for admin/asset AOIs, file reads, make_valid,
geodesic area) can take seconds, so it runs on a context thread, and a result
that was replaced meanwhile is dropped: only ``state.aoi_result.value is
result`` may publish.
"""

import logging

import reacton.ipyvuetify as rv
import solara
from pysepal.solara.components.aoi import AoiView

from component.i18n import t
from component.parameter import grid as g
from component.scripts.aoi_prep import AoiError, aoi_info_from_result
from component.scripts.levels import estimate_cells
from component.scripts.solara_threads import spawn_in_context

logger = logging.getLogger(g.LOGGER_NAME)


def resolve_aoi_into(state, result, *, resolve=aoi_info_from_result) -> None:
    def current() -> bool:
        return state.aoi_result.value is result

    try:
        info = resolve(result)
    except AoiError as exc:
        if current():
            state.aoi_error.set((exc.key, exc.detail))
    except Exception as exc:
        logger.exception("AOI resolution failed")
        if current():
            state.aoi_error.set(("fetch", str(exc)))
    else:
        if current():
            state.aoi_info.set(info)
    finally:
        if current():
            state.aoi_resolving.set(False)


def _row(label, value):
    rv.Html(tag="tr", children=[rv.Html(tag="td", style_="opacity: 0.7;", children=[label]),
                                rv.Html(tag="td", children=[value])])


@solara.component
def AoiSummary(info, on_continue):
    r17 = estimate_cells(g.FRA_LEVEL, info.area_km2, info.perimeter_km[g.FRA_LEVEL], info.n_points)
    w, s, e, n = info.bbox
    with rv.Card(outlined=True):
        with rv.CardTitle():
            solara.Text(f"{t('aoi.summary_title')} · {info.label}")
        with rv.CardText():
            with rv.SimpleTable(dense=True):
                with rv.Html(tag="tbody"):
                    _row(t("aoi.method"), info.method)
                    if info.is_points:
                        _row(t("aoi.points"), f"{info.n_points:,}")
                    else:
                        _row(t("aoi.area"), f"{info.area_km2:,.1f} km²")
                    _row(t("aoi.bbox"), f"{w:.4f}, {s:.4f} → {e:.4f}, {n:.4f}")
                    _row(t("aoi.estimate_r17"), f"{r17:,}")
        with rv.CardActions(style_="justify-content: flex-end;"):
            solara.Button(t("aoi.continue"), on_click=on_continue, color="primary", small=True)


@solara.component
def AoiTile(state, map_):
    result = state.aoi_result.value

    def start_resolution():
        state.aoi_info.set(None)
        state.aoi_error.set(None)
        if result is None:
            state.aoi_resolving.set(False)
            return
        state.aoi_resolving.set(True)
        spawn_in_context(resolve_aoi_into, (state, result))

    # id(): AoiResult holds a GeoDataFrame, which cannot be compared with ==.
    solara.use_effect(start_resolution, [id(result)])

    with solara.Column(style="gap: 16px;"):
        solara.Text(t("aoi.description"))
        AoiView(value=state.aoi_result, loading=state.aoi_loading, methods="ALL", map_=map_, gee=True)
        if state.aoi_resolving.value:
            rv.ProgressLinear(indeterminate=True, color="primary")
            solara.Text(t("aoi.resolving"), style="opacity: 0.7;")
        elif state.aoi_error.value is not None:
            key, detail = state.aoi_error.value
            solara.Error(t(f"aoi.error.{key}", error=detail or ""))
        elif state.aoi_info.value is not None:
            AoiSummary(info=state.aoi_info.value, on_continue=lambda: state.active_tab.set(1))
