"""Steps, elapsed and remaining time of a grid job, for the Outputs tab (Solara-free).

The builder reports ``on_step(step, fraction)``: ``fraction`` is 0..1 for a
step that can measure itself (cells, map preview) and None for one that
cannot (Shapefile conversion, final writes). Time left is projected from the
current step's own rate only: how long the preview takes next to the cells
depends too much on the AOI for a whole-run estimate to be honest.
"""

STEPS = ("cells", "shp", "preview", "finish")
MIN_FRACTION = 0.02
"""Below this a step's rate is mostly start-up noise: no estimate yet."""
MIN_ELAPSED_S = 3.0


def plan_steps(formats) -> tuple:
    return tuple(s for s in STEPS if s != "shp" or "shp" in formats)


def step_states(steps, current) -> list:
    """``[(step, "done" | "current" | "pending"), ...]`` in plan order."""
    if current not in steps:
        return [(s, "pending") for s in steps]
    at = steps.index(current)
    return [(s, "done" if i < at else "current" if i == at else "pending") for i, s in enumerate(steps)]


def remaining_seconds(step_elapsed: float, fraction):
    if fraction is None or not MIN_FRACTION <= fraction < 1 or step_elapsed < MIN_ELAPSED_S:
        return None
    return step_elapsed * (1 - fraction) / fraction


def format_duration(seconds: float) -> str:
    """``m:ss`` under an hour, ``h:mm:ss`` above."""
    s = max(int(seconds), 0)
    h, rest = divmod(s, 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
