"""Run one grid generation on a thread that carries the Solara kernel context.

``start_generation`` is called from the Generate click handler. The start is
guarded by a process lock plus the job status, so a double click or a second
tab cannot start a second job. Reactive writes from the worker reach the
browser because ``spawn_in_context`` registers the kernel context on the
thread. Every user-facing string is resolved by ``job_texts`` in the click
handler (``t()`` must not run on a worker); the worker only fills templates.
"""

import errno
import logging
import threading
from dataclasses import dataclass, replace

from component.i18n import t
from component.model.state_manager import JobState
from component.parameter.grid import LOGGER_NAME
from component.scripts.dggrid_engine import EngineUnavailable
from component.scripts.grid_builder import BuildCancelled, build_grid
from component.scripts.notify_bridge import tile_progress_reporter, tracked_job
from component.scripts.outputs_index import NotAGridFolder
from component.scripts.solara_threads import spawn_in_context

logger = logging.getLogger(LOGGER_NAME)
_START_LOCK = threading.Lock()


@dataclass(frozen=True)
class JobTexts:
    title: str
    success: str  # template: {cells} {file}
    cancelled: str
    failed: str  # template: {error}
    engine_missing: str
    disk_full: str
    name_taken: str
    progress: str  # template: {done} {total} {cells}


def job_texts(level: int, aoi_label: str, name: str) -> JobTexts:
    """Resolve the job's strings now, leaving the worker's values as {placeholders}."""
    return JobTexts(
        title=t("grid.task_title", level=level, aoi=aoi_label),
        success=t("grid.success", level=level, cells="{cells}", file="{file}"),
        cancelled=t("grid.cancelled"),
        failed=t("grid.failed", error="{error}"),
        engine_missing=t("grid.engine_missing"),
        disk_full=t("grid.disk_full", name=name),
        name_taken=t("grid.name_taken"),
        progress=t("grid.progress", done="{done}", total="{total}", cells="{cells}"),
    )


def format_error(exc: BaseException, texts: JobTexts) -> str:
    if isinstance(exc, EngineUnavailable):
        return texts.engine_missing
    if isinstance(exc, NotAGridFolder):
        return texts.name_taken
    if isinstance(exc, OSError) and exc.errno == errno.ENOSPC:
        return texts.disk_full
    return texts.failed.format(error=str(exc) or type(exc).__name__)


def busy_names(state) -> tuple:
    job = state.job.value
    return (job.name,) if job.running else ()


def start_generation(state, request, notifier, texts: JobTexts, *, build=build_grid) -> bool:
    with _START_LOCK:
        if state.job.value.running:
            return False
        cancel = threading.Event()
        state.cancel_event.set(cancel)
        state.job.set(JobState(status="running", name=request.name, level=request.level))
    spawn_in_context(_run, (state, request, notifier, texts, cancel, build))
    return True


def cancel_generation(state) -> bool:
    cancel = state.cancel_event.value
    if cancel is None or not state.job.value.running:
        return False
    cancel.set()
    return True


def _run(state, request, notifier, texts, cancel, build):
    # The final status is set last, after every side effect and after the cancel
    # event is cleared: observers treat done/cancelled/failed as "job finished".
    try:
        with tracked_job(notifier, texts.title, error_format=lambda e: format_error(e, texts)) as task:
            report = tile_progress_reporter(
                task, lambda d, n, c: texts.progress.format(done=d, total=n, cells=f"{c:,}")
            )

            def on_progress(done, total, cells):
                report(done, total, cells)
                state.job.set(replace(state.job.value, done=done, total=total, cells=cells))

            result = build(request, on_progress=on_progress, cancel=cancel)
    except BuildCancelled:
        notifier.cancel(texts.cancelled)
        state.cancel_event.set(None)
        state.job.set(replace(state.job.value, status="cancelled", message=texts.cancelled))
    except Exception as exc:  # tracked_job already failed the task and showed the toast
        logger.error("Grid generation failed: %r", exc)
        state.cancel_event.set(None)
        state.job.set(replace(state.job.value, status="failed", message=format_error(exc, texts)))
    except BaseException:
        state.cancel_event.set(None)
        state.job.set(replace(state.job.value, status="failed"))
        raise
    else:
        message = texts.success.format(cells=f"{result.cell_count:,}", file=result.files[0].name)
        notifier.success(message)
        state.last_output.set(result)
        state.outputs_signal.set(state.outputs_signal.value + 1)
        state.cancel_event.set(None)
        state.job.set(replace(state.job.value, status="done", cells=result.cell_count, message=message))
    finally:
        state.cancel_event.set(None)  # defensive; every branch above already cleared it
