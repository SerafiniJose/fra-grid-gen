"""Run one grid generation on a thread that carries the Solara kernel context.

``start_generation`` is called from the Generate click handler. The start is
guarded by a process lock plus the session's job status, so a double click
cannot start a second job in the same session (kernel). Other sessions (on
SEPAL every tab is its own kernel process) may run their own job at the same
time, even for the same name: each run stages in its own ``.part`` folder and
the final commit refuses to replace a grid unless the run asked to overwrite.
Reactive writes from the worker reach the browser because ``spawn_in_context``
registers the kernel context on the thread. Every user-facing string is resolved by ``job_texts`` in the click
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
    name_exists: str


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
        name_exists=t("grid.name_exists_now"),
    )


def format_error(exc: BaseException, texts: JobTexts) -> str:
    if isinstance(exc, EngineUnavailable):
        return texts.engine_missing
    if isinstance(exc, NotAGridFolder):
        return texts.name_taken
    if isinstance(exc, FileExistsError):  # another session made this grid after the click
        return texts.name_exists
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
        state.job.set(JobState(status="running", name=request.name, level=request.level,
                               formats=tuple(request.formats), request=request))
    try:
        spawn_in_context(_run, (state, request, notifier, texts, cancel, build))
    except Exception as exc:  # no worker: undo the start so Generate stays usable
        logger.error("Could not start grid generation: %r", exc)
        _finish_failed(state, cancel, format_error(exc, texts))
        return False
    return True


def dismiss_job(state) -> bool:
    """Forget a failed or cancelled job (its Outputs row); a running one stays."""
    if state.job.value.running:
        return False
    state.job.set(JobState())
    return True


def retry_generation(state, notifier) -> bool:
    """Run a failed or cancelled job again with its own request (and AOI).

    Call it from a click handler: ``job_texts`` resolves strings with ``t()``.
    """
    job = state.job.value
    if job.status not in ("failed", "cancelled") or job.request is None:
        return False
    req = job.request
    return start_generation(state, req, notifier, job_texts(req.level, job.aoi_label, req.name))


def cancel_generation(state) -> bool:
    cancel = state.cancel_event.value
    if cancel is None or not state.job.value.running:
        return False
    cancel.set()
    return True


def _finish_failed(state, cancel, message: str) -> None:
    """Mark the job failed, clearing only this job's cancel event, status last."""
    if state.cancel_event.value is cancel:
        state.cancel_event.set(None)
    state.job.set(replace(state.job.value, status="failed", message=message))


def _run(state, request, notifier, texts, cancel, build):
    # Guarantees the job never stays "running": if a side effect of a normal
    # finish raises (a toast, a reactive publish), the job is failed here.
    # Only this job can be running (a new start needs a finished status).
    message = ""
    try:
        _execute(state, request, notifier, texts, cancel, build)
    except Exception as exc:
        logger.error("Grid job did not finish cleanly: %r", exc)
        message = format_error(exc, texts)
    finally:
        if state.job.value.running:
            _finish_failed(state, cancel, message)


def _execute(state, request, notifier, texts, cancel, build):
    # The final status is set last, after every side effect and after the cancel
    # event is cleared: observers treat done/cancelled/failed as "job finished".
    try:
        with tracked_job(notifier, texts.title, error_format=lambda e: format_error(e, texts)) as task:
            result = build(request, on_progress=tile_progress_reporter(task), cancel=cancel)
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
        state.job.set(replace(state.job.value, status="done", message=message))
