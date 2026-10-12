import importlib
import os
import sys
import time
from types import SimpleNamespace

import solara

from component.scripts.outputs_index import STALE_AGE_S


def test_app_imports_cleans_stale_folders_and_exposes_routes(results_root):
    stale = results_root / ".g.0123abcd.part"
    stale.mkdir()
    old = time.time() - 2 * STALE_AGE_S
    os.utime(stale, (old, old))
    (results_root / "keep").mkdir()
    sys.modules.pop("app", None)
    app = importlib.import_module("app")
    assert [r.path for r in app.routes] == ["/"]
    assert sorted(p.name for p in results_root.iterdir()) == ["keep"]


def test_grid_tab_disabled_until_aoi_exists(results_root):
    app = importlib.import_module("app")
    state = SimpleNamespace(aoi_info=solara.reactive(None))
    assert app.grid_tab_disabled(state) is True
    state.aoi_info.value = object()
    assert app.grid_tab_disabled(state) is False
