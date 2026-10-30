"""Run background work from Solara event handlers: ``spawn_in_context``.

One thread per user-fired action (a job, an AOI read, a ticker). Reactive
updates (``some_reactive.set(...)``) made from a *bare* ``threading.Thread``
never reach the browser session, so status cards stay stuck on "running" even
after the backend has finished. Registering the render thread's kernel context
onto the worker thread — exactly what ``solara.lab.use_task`` does internally —
lets those updates propagate.
"""

import threading


def spawn_in_context(target, args=(), *, daemon=True):
    """Start a daemon thread that inherits the caller's Solara kernel context.

    Falls back to a plain thread when there is no active context (e.g. unit
    tests), so the function is usable outside a running app.

    Parameters
    ----------
    target : callable
        Function to run in the background thread.
    args : tuple
        Positional arguments forwarded to ``target``.
    daemon : bool
        Whether the thread is a daemon (default ``True``).

    Returns:
    -------
    threading.Thread
        The started thread.
    """
    from solara.server import kernel_context

    thread = threading.Thread(target=target, args=args, daemon=daemon)
    try:
        ctx = kernel_context.get_current_context()
    except RuntimeError:
        ctx = None
    if ctx is not None:
        kernel_context.set_context_for_thread(ctx, thread)
    thread.start()
    return thread
