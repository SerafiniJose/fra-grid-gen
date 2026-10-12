import json
import re
from pathlib import Path

import pandas as pd

from component import i18n

ROOT = Path(__file__).resolve().parents[1]
_KEY = re.compile(r"""\b(?:t|plural)\(\s*["']([a-z0-9_.]+)["']""")
_KEY2 = re.compile(r"""\bplural\([^,]+,\s*["']([a-z0-9_.]+)["']\s*,\s*["']([a-z0-9_.]+)["']""")


def _keys(locale):
    data = json.loads((i18n.MESSAGES_DIR / locale / "locale.json").read_text(encoding="utf-8"))
    return set(pd.json_normalize(data).columns)


def _used_keys():
    used = set()
    for path in [ROOT / "app.py", *(ROOT / "component").rglob("*.py")]:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        used |= set(_KEY.findall(text))
        for pair in _KEY2.findall(text):
            used |= set(pair)
    return used


def test_locales_are_shipped():
    assert i18n.app_available_locales() == ["en", "es-ES"]


def test_catalogs_have_identical_keys():
    assert _keys("en") == _keys("es-ES")


def test_every_key_used_in_code_exists():
    missing = _used_keys() - _keys("en")
    assert not missing, f"keys used in code but missing from the catalogs: {sorted(missing)}"


def test_t_formats_and_degrades_to_key():
    assert i18n.t("grid.success", level=17, cells="330", file="g.gpkg") == "r17 grid ready: 330 cells → g.gpkg"
    assert i18n.t("does.not.exist") == "does.not.exist"
