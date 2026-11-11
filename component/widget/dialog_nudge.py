"""Dialogs that stay open on a click outside them and nudge instead (ported from spatial_risk).

The dialog is ``persistent``, so a backdrop click no longer closes it; ``click:outside`` (which
VDialog still emits) replays Vuetify's own scale bump on the ``.v-dialog`` element. Vuetify's
built-in shake is off (``no_click_animation``) because it also fires on ESC, which here still
closes the dialog: the form would wobble, then close.

The class goes on ``.v-dialog`` (``content_class``), never the card: ``.v-dialog`` is the scroll
box, and a card scaled inside it flashes scrollbars and re-wraps on every click.
"""

import reacton.ipyvuetify as rv
import solara

# Replaying a CSS animation needs a *different* animation name: re-applying the same one is a
# no-op. Two classes with identical keyframes, alternated per click, restart it every time.
# Values copied from Vuetify's `animate-dialog`. Rendered once, app-wide, in app.py.
_NUDGE_NAMES = ("fra-dialog-nudge-a", "fra-dialog-nudge-b")

NUDGE_CSS = "".join(
    f"@keyframes {n} {{ 0% {{ transform: scale(1); }} 50% {{ transform: scale(1.03); }}"
    f" 100% {{ transform: scale(1); }} }}\n"
    f".{n} {{ animation: {n} .15s cubic-bezier(.25, .8, .25, 1); }}\n"
    for n in _NUDGE_NAMES
)


def nudge_class(count: int) -> str:
    """Dialog class after ``count`` outside clicks ("" before the first one)."""
    return _NUDGE_NAMES[(count - 1) % 2] if count > 0 else ""


def nudging_dialog(is_open, on_close, **kwargs):
    """An ``rv.Dialog`` that ignores outside clicks (nudges instead) and closes on ESC.

    Use as ``with nudging_dialog(open_, close, max_width=...):``. Holds hooks: call it
    unconditionally. The click count resets on open/close, otherwise a dialog shown again
    would replay its stale animation the moment it reopens.
    """
    count, set_count = solara.use_state(0)
    solara.use_effect(lambda: set_count(0), [is_open])
    dialog = rv.Dialog(
        v_model=is_open,
        on_v_model=lambda v: None if v else on_close(),
        persistent=True,
        no_click_animation=True,
        content_class=nudge_class(count),
        **kwargs,
    )
    rv.use_event(dialog, "click:outside", lambda *_: set_count(lambda n: n + 1))
    # `persistent` also disables ESC; VDialog still emits keydown, so close from here.
    rv.use_event(dialog, "keydown.esc", lambda *_: on_close())
    return dialog
