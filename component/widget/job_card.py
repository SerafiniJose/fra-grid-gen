"""Outputs tab card for the grid being generated: steps, progress, elapsed and time left.

A running job shows its steps (``job_progress.plan_steps``), the current
step's progress bar, the elapsed time (ticking every second) and Cancel. A
finished job shows "Ready" for ``READY_SECONDS``, then hands over to the new
grid's card in the list, opened (``settle_finished_job``). A failed or
cancelled job keeps its card, with the reason, until Dismiss or the next run.
"""

import threading
import time

import reacton.ipyvuetify as rv
import solara

from component.i18n import t
from component.model.generate_job import cancel_generation, dismiss_job, settle_finished_job
from component.scripts.job_progress import format_duration, plan_steps, remaining_seconds, step_states
from component.scripts.solara_threads import spawn_in_context

READY_SECONDS = 2.0
_HINT = "display: block; font-size: 0.8rem; opacity: 0.7;"
_BORDER = {  # theme colours when Vuetify exposes them, pysepal's defaults otherwise
    "running": "var(--v-primary-base, #76591e)",
    "done": "var(--v-success-base, #4caf50)",
    "failed": "var(--v-error-base, #c62828)",
    "cancelled": "var(--v-warning-base, #ef9a00)",
}
_STEP_ICON = {
    "done": ("mdi-check-circle", "success"),
    "current": ("mdi-progress-clock", "primary"),
    "pending": ("mdi-circle-outline", "grey"),
}


def step_detail(job, step: str, status: str):
    """The line under a step, or None."""
    if step == "cells" and status != "pending" and job.total:
        return t("grid.progress", done=job.done, total=job.total, cells=f"{job.cells:,}")
    if step == "preview" and status == "current" and job.step_fraction is not None:
        pct = int(job.step_fraction * 100)
        # build_preview: feeding cells is the first half, tippecanoe's tiling the second.
        return t("outputs.job.preview_feed" if job.step_fraction < 0.5 else "outputs.job.preview_tiles", pct=pct)
    return None


def time_line(job, now: float) -> str:
    text = t("outputs.job.elapsed", time=format_duration(now - job.started_at))
    if job.step_fraction is None:
        return text
    left = remaining_seconds(now - job.step_started_at, job.step_fraction)
    if left is None:
        return f"{text} · {t('outputs.job.estimating')}"
    return f"{text} · {t('outputs.job.remaining', time=format_duration(left))}"


def use_ticker(active: bool, seconds: float = 1.0) -> None:
    """Re-render the calling component every ``seconds`` while ``active``."""
    _, set_tick = solara.use_state(0)

    def run():
        if not active:
            return None
        stop = threading.Event()

        def loop():
            n = 0
            while not stop.wait(seconds):
                n += 1
                set_tick(n)

        spawn_in_context(loop)
        return stop.set

    solara.use_effect(run, [active])


@solara.component
def _Step(label: str, status: str, detail=None, about=None):
    icon, color = _STEP_ICON[status]
    with solara.Row(style="gap: 8px; align-items: flex-start; flex-wrap: nowrap;"):
        rv.Icon(small=True, color=color, children=[icon])
        with solara.Column(style="gap: 0;"):
            weight = "font-weight: 600;" if status == "current" else ""
            dim = "opacity: 0.6;" if status == "pending" else ""
            solara.Text(label, style=f"display: block; {weight}{dim}")
            if detail:
                solara.Text(detail, style=_HINT)
            if about:
                solara.Text(about, style=_HINT)


def use_settle_after_ready(state, job) -> None:
    """Hand a finished job over to its grid card after the "Ready" moment."""

    def run():
        if job.status != "done":
            return None
        stop = threading.Event()

        def wait():
            if not stop.wait(READY_SECONDS):
                settle_finished_job(state, job)

        spawn_in_context(wait)
        return stop.set

    solara.use_effect(run, [id(job)])


@solara.component
def JobCard(state):
    job = state.job.value
    use_ticker(job.running)
    use_settle_after_ready(state, job)
    if job.status not in ("running", "done", "failed", "cancelled"):
        return

    formats = ", ".join(f.upper() for f in job.formats)
    done = job.status == "done"
    with rv.Card(outlined=True, class_="pa-2", style_=f"border-color: {_BORDER[job.status]};"):
        with solara.Row(style="gap: 6px; align-items: center; flex-wrap: wrap;"):
            solara.Text(job.name, style="font-weight: 600; overflow-wrap: anywhere;")
            if done:
                rv.Chip(x_small=True, color="success", children=[
                    rv.Icon(x_small=True, left=True, children=["mdi-check"]), t("outputs.job.ready")])
        solara.Text(f"{job.title} · {formats}" if formats else job.title, style=_HINT)
        if done:
            with solara.Column(style="gap: 6px; margin-top: 8px;"):
                for step in plan_steps(job.formats):
                    _Step(label=t(f"outputs.job.steps.{step}"), status="done", detail=step_detail(job, step, "done"))
            rv.ProgressLinear(value=100, color="success", height=6, class_="mt-3")
            solara.Text(t("outputs.job.finished", time=format_duration(job.finished_at - job.started_at)),
                        style="display: block; font-size: 0.8rem; margin-top: 4px;")
        elif job.running:
            with solara.Column(style="gap: 6px; margin-top: 8px;"):
                for step, status in step_states(plan_steps(job.formats), job.step):
                    about = t("outputs.job.preview_about") if step == "preview" and status == "current" else None
                    _Step(label=t(f"outputs.job.steps.{step}"), status=status,
                          detail=step_detail(job, step, status), about=about)
            fraction = job.step_fraction
            rv.ProgressLinear(value=int(fraction * 100) if fraction is not None else 0,
                              indeterminate=fraction is None, color="primary", height=6, class_="mt-3")
            solara.Text(time_line(job, time.monotonic()), style="display: block; font-size: 0.8rem; margin-top: 4px;")
            with solara.Row(justify="end"):
                solara.Button(t("grid.cancel"), on_click=lambda: cancel_generation(state), small=True, outlined=True)
        else:
            if job.status == "failed":
                solara.Error(job.message, dense=True)
            else:
                solara.Warning(job.message, dense=True)
            with solara.Row(justify="end"):
                solara.Button(t("outputs.job.dismiss"), on_click=lambda: dismiss_job(state), small=True, text=True)
