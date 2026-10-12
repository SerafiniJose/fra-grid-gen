import ipyvuetify as v
import reacton
import solara

from component.scripts.levels import estimate_levels
from component.widget import levels_table as lt
from component.widget import metadata_dialog as mdd
from component.widget.confirm_dialog import ConfirmDialog

RECORD = {
    "schema": "fra-grid-metadata/1",
    "name": "chaco17",
    "generated_at": "2026-10-12T14:03:11Z",
    "generator": {"app": "fra_grid_generator", "app_version": "0.1.0", "dggrid": "8.44",
                  "dggrid4py": "0.6.0", "python": "3.11.9", "sepal_user": "u"},
    "dggs": {"type": "ISEA3H", "resolution": 17, "is_fra_rss_level": True},
    "correction": {"spec": "FRA RSS 20sep26", "validated_at_levels": [17]},
    "aoi": {"method": "DRAW", "label": "Drawn polygon", "area_km2": 114.065, "n_points": None,
            "bbox": [-60.1, -22.4, -60.0, -22.3]},
    "run": {"tile_deg": 1.0, "n_tiles": 2, "cell_count": 330, "duration_s": 1.2,
            "formats": ["gpkg", "shp"], "files": ["chaco17.gpkg"]},
    "fields": {},
}


def test_compact_numbers():
    assert lt.compact(330) == "330"
    assert lt.compact(52_410) == "52,410"
    assert lt.compact(2_400_000) == "2.40 M"
    assert lt.compact(1_291_401_632) == "1.29 B"


def test_table_rows_for_chaco():
    rows = lt.table_rows(estimate_levels(114.0647, {lvl: 42.7484 for lvl in range(17, 22)}, None))
    assert [r["level"] for r in rows] == [17, 18, 19, 20, 21]
    first = rows[0]
    assert first["label"] == "r17" and first["is_fra"] is True
    assert first["area"] == "39.5 ha" and first["spacing"] == "709 m"
    assert first["global_cells"] == "1.29 B" and first["estimate"] == "331"
    assert all(r["selectable"] for r in rows)


def test_blocked_rows_are_not_selectable():
    rows = lt.table_rows(estimate_levels(52_410.0, {lvl: 1_000.0 for lvl in range(17, 22)}, None))
    by_level = {r["level"]: r for r in rows}
    assert by_level[17]["verdict"] == "ok" and by_level[17]["selectable"]
    assert by_level[21]["verdict"] == "blocked" and not by_level[21]["selectable"]


def test_levels_table_click_selects_only_selectable_rows():
    picked = []
    ests = estimate_levels(52_410.0, {lvl: 1_000.0 for lvl in range(17, 22)}, None)

    box, rc = reacton.render(lt.LevelsTable(ests, 17, picked.append), handle_error=False)
    try:
        trs = [w for w in rc.find(v.Html, tag="tr").widgets if w.style_]
        assert len(trs) == 5
        trs[0].fire_event("click", {})
        trs[4].fire_event("click", {})
        assert picked == [17]
    finally:
        rc.close()


def test_metadata_sections_flatten_the_record():
    sections = dict(mdd.metadata_sections(RECORD))
    assert ("Type", "ISEA3H") in sections["metadata.dggs"]
    assert ("Resolution", "17") in sections["metadata.dggs"]
    assert ("Cells", "330") in sections["metadata.run"]
    assert ("Formats", "gpkg, shp") in sections["metadata.run"]
    assert ("Label", "Drawn polygon") in sections["metadata.aoi"]
    assert ("Validated at levels", "17") in sections["metadata.correction"]


def test_confirm_dialog_renders_and_confirms():
    clicks = []

    @solara.component
    def Host():
        ConfirmDialog(open=True, on_cancel=lambda: clicks.append("cancel"),
                      on_confirm=lambda: clicks.append("ok"), title="T", message="M",
                      confirm_label="Delete", details=["a.gpkg"])

    box, rc = reacton.render(Host(), handle_error=False)
    try:
        buttons = rc.find(v.Btn, children=["Delete"]).widget
        buttons.click()
        assert clicks == ["ok"]
    finally:
        rc.close()
