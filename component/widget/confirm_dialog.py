"""Reusable confirmation dialog for destructive actions.

Follows the proven ProjectPanel discard/overwrite pattern: a single ``rv.Dialog``
rendered at the component's top level and toggled by ``use_state`` (a row button
merely sets the pending target). Nested button -> Dialog toggles have proved
unreliable, so callers should render this once per tile, not inside a list row.
``details`` lists monospace lines under the message (the files a choice would touch).
"""

import reacton.ipyvuetify as rv
import solara

from component.i18n import t

MUTED = "opacity: 0.7;"

# Paths and file names: monospace keeps them scannable and stops a long one
# from re-flowing the sentence above it.
_DETAIL_STYLE = (
    "display: block; font-family: ui-monospace, SFMono-Regular, Menlo, monospace;"
    "font-size: 0.78rem; line-height: 1.5; overflow-wrap: anywhere;" + MUTED
)


@solara.component
def ConfirmDialog(
    open,
    on_cancel,
    on_confirm,
    title=None,
    message=None,
    confirm_label=None,
    confirm_color="error",
    details=None,
):
    """Modal confirm dialog for a destructive action.

    Args:
        open: bool — whether the dialog is shown.
        on_cancel: callback() — dismiss without acting (also on ESC / outside click).
        on_confirm: callback() — act; the caller is responsible for closing.
        title: dialog title.
        message: dialog body copy.
        confirm_label: label of the confirm button.
        confirm_color: colour of the confirm button.
        details: iterable of lines listed in monospace under the message.
    """
    title = title if title is not None else t("dialog.confirm_default_title")
    message = message if message is not None else t("dialog.confirm_default_message")
    if confirm_label is None:
        confirm_label = t("dialog.confirm_default_label")
    # A plain confirm keeps its narrow box; file paths need the extra room,
    # or every path wraps over three lines.
    with rv.Dialog(
        v_model=open,
        on_v_model=lambda v: None if v else on_cancel(),
        max_width="440px" if details else "380px",
        eager=True,
    ):
        with rv.Card():
            with rv.CardTitle():
                solara.Text(title)
            with rv.CardText():
                solara.Text(message, style="display: block;")
                for line in details or []:
                    solara.Text(str(line), style=_DETAIL_STYLE)
            with rv.CardActions(style_="justify-content: flex-end; gap: 8px;"):
                solara.Button(
                    t("common.cancel"), on_click=on_cancel, text=True, small=True
                )
                solara.Button(
                    confirm_label,
                    on_click=on_confirm,
                    color=confirm_color,
                    small=True,
                )
