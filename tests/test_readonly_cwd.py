"""On SEPAL the CWD is a read-only mount: a build must never write there."""

import os
import shutil

import pytest

from component.scripts import grid_builder as gb

pytestmark = [
    pytest.mark.skipif(shutil.which("dggrid") is None, reason="dggrid binary not on PATH"),
    pytest.mark.skipif(os.geteuid() == 0, reason="root ignores directory permissions"),
]


def test_build_with_read_only_cwd(results_root, chaco_aoi, tmp_path, monkeypatch):
    ro = tmp_path / "ro_cwd"
    ro.mkdir()
    ro.chmod(0o555)
    for var in ("CPL_TMPDIR", "TMPDIR", "TEMP", "TMP"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.chdir(ro)
    try:
        res = gb.build_grid(gb.BuildRequest(chaco_aoi, 17, "ro"))
        assert res.cell_count > 0
        assert list(ro.iterdir()) == []
    finally:
        ro.chmod(0o755)
