import logging

from component.scripts import notify_bridge as nb


class _Task:
    def __init__(self):
        self.values = []

    def set_progress(self, value):  # pysepal 4.1 signature: no detail kwarg
        self.values.append(value)


class _DetailTask:
    def __init__(self):
        self.calls = []

    def set_progress(self, value, detail=None):
        self.calls.append((value, detail))


def test_reporter_throttles_to_whole_percent():
    task = _Task()
    report = nb.tile_progress_reporter(task)
    for done in range(1, 1001):
        report(done, 1000, done * 10)
    assert len(task.values) == 101 and task.values[-1] == 1.0


def test_reporter_sends_detail_when_supported():
    task = _DetailTask()
    report = nb.tile_progress_reporter(task, format_detail=lambda d, t, c: f"{d}/{t}:{c}")
    report(1, 4, 99)
    assert task.calls == [(0.25, "1/4:99")]


def test_install_handler_is_idempotent_and_enables_info():
    logger = logging.getLogger("fra_grid")
    logger.setLevel(logging.NOTSET)
    h1 = nb.install_task_log_handler()
    h2 = nb.install_task_log_handler()
    assert h1 is h2 and logger.isEnabledFor(logging.INFO)


def test_log_lines_become_steps_only_on_the_job_thread():
    class Tracker:
        def __init__(self):
            self.steps = []

        def step(self, message):
            self.steps.append(message)

    class Notifier:
        def __init__(self, tracker):
            self.tracker = tracker

        def track(self, title, total_steps=None):
            tracker = self.tracker

            class _Ctx:
                def __enter__(self):
                    return tracker

                def __exit__(self, *exc):
                    return False

            return _Ctx()

        def error(self, message, *, timeout=None):
            pass

    tracker = Tracker()
    with nb.tracked_job(Notifier(tracker), "t"):
        logging.getLogger("fra_grid").info("Tile %d/%d: %s cells", 1, 2, "10")
    logging.getLogger("fra_grid").info("after the job")
    assert tracker.steps == ["Tile 1/2: 10 cells"]
