"""Internationalization (copy of spatial_risk v4 gui/i18n.py).

pysepal's Translator reads ``component/message/<locale>/*.json`` with an
es-ES -> en fallback. The active locale comes from ``pysepal.i18n`` and is
kernel-scoped; ``use_app_locale()`` (called by Page) swaps the translator when
the header's language selector changes it. Never resolve a string at import
time: call t() inside a render or an event handler.
"""

from pathlib import Path

import solara
from pysepal.i18n import current_locale
from pysepal.translator import Translator

MESSAGES_DIR = Path(__file__).parent / "message"

_translator = solara.reactive(None)


def _current_locale() -> str:
    return current_locale() or "en"


def get_translator() -> Translator:
    if _translator.value is None:
        _translator.value = Translator(MESSAGES_DIR, target=_current_locale())
    return _translator.value


def set_app_locale(code: str) -> None:
    _translator.value = Translator(MESSAGES_DIR, target=code or "en")


def reset_translator() -> None:
    """Drop the cached translator (call from on_kernel_start)."""
    _translator.value = None


def use_app_locale() -> str:
    """Render-time hook: rebuild the translator when pysepal's locale changes."""
    locale = current_locale()

    def _swap():
        set_app_locale(locale)

    solara.use_effect(_swap, [locale])
    return locale


def t(key: str, /, **fmt) -> str:
    """Dotted-key lookup (es->en->key); str.format(**fmt). Missing keys return the key."""
    node = get_translator()
    try:
        for part in key.split("."):
            node = node[part]
        text = str(node)
        return text.format(**fmt) if fmt else text
    except Exception:
        return key


def app_available_locales() -> list:
    return sorted(p.name for p in MESSAGES_DIR.glob("[!._]*") if p.is_dir())
