from pathlib import Path
from types import SimpleNamespace

import ipyvuetify as v
import reacton

from component.tile import grid_tile as gt

OK = dict(running=False, name_error=None, name_state="free", formats=("gpkg",), verdict="ok", engine_ok=True)


def test_effective_formats_drops_shp_when_not_allowed():
    assert gt.effective_formats(frozenset({"shp", "gpkg"}), True) == ("gpkg", "shp")
    assert gt.effective_formats(frozenset({"shp", "gpkg"}), False) == ("gpkg",)
    assert gt.effective_formats(frozenset({"shp"}), False) == ()


def test_block_reason_order():
    assert gt.block_reason(**OK) is None
    assert gt.block_reason(**{**OK, "engine_ok": False}) == "grid.engine_missing"
    assert gt.block_reason(**{**OK, "running": True}) == "grid.generate"
    assert gt.block_reason(**{**OK, "name_error": "invalid"}) == "grid.name_error.invalid"
    assert gt.block_reason(**{**OK, "name_state": "taken"}) == "grid.name_taken"
    assert gt.block_reason(**{**OK, "formats": ()}) == "grid.formats_empty"
    assert gt.block_reason(**{**OK, "verdict": "blocked"}) == "grid.blocked_hint"
    assert gt.block_reason(**{**OK, "name_state": "grid", "verdict": "warn"}) is None


def test_confirm_steps():
    assert gt.confirm_steps("ok", "free") == []
    assert gt.confirm_steps("warn", "free") == ["warn"]
    assert gt.confirm_steps("ok", "grid") == ["overwrite"]
    assert gt.confirm_steps("warn", "grid") == ["warn", "overwrite"]


def test_preview_source_prefers_gpkg(tmp_path):
    (tmp_path / "g.gpkg").touch()
    (tmp_path / "g.shp").touch()
    assert gt.preview_source(tmp_path, "g", ("gpkg", "shp")) == (tmp_path / "g.gpkg", "g")
    assert gt.preview_source(tmp_path, "g", ("shp",)) == (tmp_path / "g.shp", "g")
    assert gt.preview_source(Path("/nonexistent"), "g", ("gpkg",)) is None


def test_file_lines_show_name_and_size_and_skip_missing(tmp_path):
    f = tmp_path / "g.gpkg"
    f.write_bytes(b"x" * 2048)
    lines = gt.file_lines((f, tmp_path / "gone.shp"))
    assert len(lines) == 1
    assert lines[0].startswith("g.gpkg · ") and "KB" in lines[0]


def test_result_card_lists_files_with_sizes(tmp_path):
    f = tmp_path / "g.gpkg"
    f.write_bytes(b"x" * 2048)
    result = SimpleNamespace(name="g", folder=tmp_path, files=(f,), cell_count=10, duration_s=1.5,
                             metadata={"run": {"formats": ["gpkg"]}})
    box_, rc = reacton.render(
        gt.ResultCard(result=result, map_=None, on_show=lambda: None, on_metadata=lambda: None),
        handle_error=False)
    try:
        texts = [w.children[0] for w in rc.find(v.Html).widgets if w.children and isinstance(w.children[0], str)]
        assert any(s.startswith("g.gpkg · ") and "KB" in s for s in texts), texts
        assert str(tmp_path) in texts
    finally:
        rc.close()
