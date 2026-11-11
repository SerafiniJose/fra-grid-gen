from pathlib import Path

from component.parameter import grid
from component.parameter.directory import results_dir


def test_results_dir_honours_env_and_is_created(tmp_path, monkeypatch):
    target = tmp_path / "custom" / "results"
    monkeypatch.setenv("FRA_GRID_RESULTS_DIR", str(target))
    got = results_dir()
    assert got == target
    assert got.is_dir() and got.is_absolute()


def test_results_dir_default_is_module_results(tmp_path, monkeypatch):
    monkeypatch.delenv("FRA_GRID_RESULTS_DIR", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert results_dir() == tmp_path / "module_results" / "fra_grid_generator"


def test_level_constants_are_consistent():
    assert grid.LEVELS == (17, 18, 19, 20, 21)
    assert grid.FRA_LEVEL == grid.MIN_LEVEL == 17
    assert set(grid.TILE_DEG) == set(grid.LEVELS)
    assert grid.WARN_CELLS < grid.SHP_MAX_CELLS < grid.BLOCK_CELLS
    assert grid.LOGGER_NAME == "fra_grid"
    assert Path(grid.__file__).parent.name == "parameter"


def test_preview_constants():
    assert set(grid.PREVIEW_ZOOMS) == set(grid.LEVELS)
    assert all(0 <= lo < hi <= 16 for lo, hi in grid.PREVIEW_ZOOMS.values())
    assert all(lo == grid.PREVIEW_MIN_ZOOM == 3 for lo, _ in grid.PREVIEW_ZOOMS.values())  # continent-scale overview
    assert grid.PREVIEW_FILE.startswith(".") and grid.PREVIEW_FILE.endswith(".pmtiles")
