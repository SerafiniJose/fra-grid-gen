"""Session reactives shared by the three tabs.

Solara reactives are kernel-scoped, so each browser session gets its own
values. Mutable values (AoiResult, AoiInfo, BuildResult, the cancel Event) use
identity equality: a new object always re-renders, even when it compares equal.
"""

from dataclasses import dataclass

import solara

from component.parameter import grid as g


def _same(a, b) -> bool:
    return a is b


@dataclass(frozen=True)
class JobState:
    status: str = "idle"  # idle | running | done | failed | cancelled
    name: str = ""
    level: int = 0
    done: int = 0
    total: int = 0
    cells: int = 0
    message: str = ""

    @property
    def running(self) -> bool:
        return self.status == "running"


class AppState:
    def __init__(self):
        # AOI tab
        self.aoi_result = solara.reactive(None, equals=_same)  # pysepal AoiResult
        self.aoi_loading = solara.reactive(False)  # AoiView is fetching
        self.aoi_info = solara.reactive(None, equals=_same)  # AoiInfo (geometry ready)
        self.aoi_error = solara.reactive(None)  # (key, detail) or None
        self.aoi_resolving = solara.reactive(False)  # our worker builds AoiInfo
        # Grid tab
        self.level = solara.reactive(g.FRA_LEVEL)
        self.out_name = solara.reactive("")
        self.name_edited = solara.reactive(False)  # user typed: stop auto-naming
        self.formats = solara.reactive(frozenset({"gpkg"}))
        # Job
        self.job = solara.reactive(JobState())
        self.cancel_event = solara.reactive(None, equals=_same)
        self.last_output = solara.reactive(None, equals=_same)  # BuildResult
        # Outputs tab and navigation
        self.outputs_signal = solara.reactive(0)  # bump to re-list the results folder
        self.preview_name = solara.reactive(None)  # grid shown on the map
        self.active_tab = solara.reactive(0)


app_state = AppState()
