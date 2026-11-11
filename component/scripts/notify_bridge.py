"""Bridge the ``fra_grid`` logger to pysepal notification TaskTrackers.

Adapted from spatial_risk's gui/scripts/notify_bridge.py. A background job
wraps its body in ``tracked_job(notifier, title)``; while it runs, every INFO+
record the ``fra_grid`` logger emits *on that job's thread* becomes a
``task.step(...)`` milestone in the notification pill. Run job bodies through
``solara_threads.spawn_in_context`` so the tracker's bus updates reach the
browser.
"""

import asyncio
import logging
import threading
from contextlib import contextmanager

from component.parameter.grid import LOGGER_NAME

ERROR_TOAST_TIMEOUT = 10.0
"""Seconds an error toast stays on screen (successes keep pysepal's default)."""

_trackers = {}
_install_lock = threading.Lock()


class TaskStepLogHandler(logging.Handler):
    """Forward INFO+ records from tracked-job threads as task milestones."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            tracker = _trackers.get(threading.get_ident())
            if tracker is not None:
                tracker.step(record.getMessage())
        except Exception:  # a logging handler must never raise into caller code
            pass


def install_task_log_handler(level: int = logging.INFO) -> TaskStepLogHandler:
    """Attach one handler to the ``fra_grid`` logger (idempotent).

    Also lowers the logger's own level to ``level`` when it is unset or higher:
    without a logging config the logger inherits WARNING from the root and the
    INFO milestones would never be emitted.
    """
    logger = logging.getLogger(LOGGER_NAME)
    with _install_lock:
        if logger.level == logging.NOTSET or logger.level > level:
            logger.setLevel(level)
        for handler in logger.handlers:
            if isinstance(handler, TaskStepLogHandler):
                return handler
        handler = TaskStepLogHandler()
        handler.setLevel(level)
        logger.addHandler(handler)
        return handler


def tile_progress_reporter(task):
    """``on_progress(done, total, cells)`` -> ``task.set_progress`` at whole-percent steps."""
    last_pct = None

    def on_progress(done, total, cells):
        nonlocal last_pct
        if not total:
            return
        pct = int(done * 100 / total)
        if pct != last_pct:
            last_pct = pct
            task.set_progress(done / total)

    return on_progress


@contextmanager
def tracked_job(notifier, title: str, error_format=None):
    """Track a job as a pysepal notification task, echoing its log milestones.

    Enter it on the thread that runs the job body. ``asyncio.CancelledError``
    (and ``BuildCancelled``) re-raises untouched so pysepal marks the task
    cancelled. Other exceptions fail the task with ``error_format(exc)`` before
    the single error toast is published, then re-raise.
    """
    if notifier is None:
        from pysepal.solara.notifications.notifier import NoopNotifier

        notifier = NoopNotifier()
    install_task_log_handler()
    with notifier.track(title) as task:
        tid = threading.get_ident()
        previous = _trackers.get(tid)
        _trackers[tid] = task
        try:
            yield task
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            try:
                message = error_format(exc) if error_format is not None else str(exc)
            except Exception:
                logging.getLogger(LOGGER_NAME).exception("error_format failed")
                message = str(exc)
            if hasattr(task, "fail"):
                task.fail(message)
            notifier.error(message, timeout=ERROR_TOAST_TIMEOUT)
            raise
        finally:
            if previous is not None:
                _trackers[tid] = previous
            else:
                _trackers.pop(tid, None)
