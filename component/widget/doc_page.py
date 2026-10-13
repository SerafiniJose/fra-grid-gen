"""A Markdown page (About, Documentation) in the current UI language."""

import solara
from pysepal.i18n import current_locale

from component.scripts.docs import doc_text


@solara.component
def DocPage(page: str):
    # current_locale() subscribes: the page follows the language selector.
    locale = current_locale()
    text = solara.use_memo(lambda: doc_text(page, locale), [page, locale])
    with solara.Column(style="padding: 8px 16px 16px; max-width: 860px;"):
        solara.Markdown(text)
