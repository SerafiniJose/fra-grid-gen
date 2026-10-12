"""Levels table: global stats per level plus the AOI estimate and its verdict."""

import reacton.ipyvuetify as rv
import solara

from component.i18n import t

_VERDICT_COLOR = {"ok": "success", "warn": "warning", "blocked": "error"}


def compact(n: int) -> str:
    if n >= 1_000_000_000:
        return f"{n / 1e9:.2f} B"
    if n >= 1_000_000:
        return f"{n / 1e6:.2f} M"
    return f"{n:,}"


def _area(area_ha: float) -> str:
    return f"{area_ha:.1f} ha" if area_ha >= 1 else f"{area_ha:.2f} ha"


def table_rows(estimates) -> list:
    rows = []
    for est in estimates:
        s = est.stats
        rows.append(
            {
                "level": s.level,
                "label": f"r{s.level}",
                "is_fra": s.is_fra,
                "area": _area(s.area_ha),
                "spacing": f"{s.spacing_m:,.0f} m",
                "global_cells": compact(s.cells),
                "estimate": compact(est.cells),
                "verdict": est.verdict,
                "selectable": est.verdict != "blocked",
            }
        )
    return rows


@solara.component
def _LevelRow(row: dict, is_selected: bool, on_select):
    """One table row; owns its single click hook. Blocked rows ignore clicks."""
    style = "cursor: pointer;" if row["selectable"] else "opacity: 0.5;"
    if is_selected:
        style += "background: rgba(0, 128, 96, 0.12); font-weight: 600;"
    tr = rv.Html(
        tag="tr",
        style_=style,
        children=[
            rv.Html(tag="td", children=[
                rv.Icon(small=True, children=["mdi-radiobox-marked" if is_selected else "mdi-radiobox-blank"]),
                f" {row['label']}",
                *([rv.Chip(x_small=True, color="primary", class_="ml-1",
                           children=[t("grid.status.fra")])] if row["is_fra"] else []),
            ]),
            rv.Html(tag="td", children=[row["area"]]),
            rv.Html(tag="td", children=[row["spacing"]]),
            rv.Html(tag="td", children=[row["global_cells"]]),
            rv.Html(tag="td", children=[row["estimate"]]),
            rv.Html(tag="td", children=[
                rv.Chip(x_small=True, outlined=True, color=_VERDICT_COLOR[row["verdict"]],
                        children=[t(f"grid.status.{row['verdict']}")])
            ]),
        ],
    )
    rv.use_event(tr, "click", lambda *_: on_select(row["level"]) if row["selectable"] else None)


@solara.component
def LevelsTable(estimates, selected: int, on_select):
    rows = table_rows(estimates)
    with rv.SimpleTable(dense=True):
        with rv.Html(tag="thead"):
            with rv.Html(tag="tr"):
                for key in ("level", "area", "spacing", "global", "estimate", "status"):
                    rv.Html(tag="th", children=[t(f"grid.col.{key}")])
        with rv.Html(tag="tbody"):
            for row in rows:
                _LevelRow(row, row["level"] == selected, on_select)
