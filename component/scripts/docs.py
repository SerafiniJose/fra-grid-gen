"""In-app About and Documentation pages: Markdown under ``component/doc/<locale>/``.

A locale without its own page (or a region variant such as es-AR) falls back
like the message catalogs: exact code, then the language, then English.
"""

from pathlib import Path

DOC_DIR = Path(__file__).resolve().parents[1] / "doc"
PAGES = ("about", "documentation")


def doc_path(page: str, locale: str) -> Path:
    if page not in PAGES:
        raise ValueError(f"page must be one of {PAGES}, got {page!r}")
    locale = locale or "en"
    candidates = [DOC_DIR / locale]
    candidates += sorted(p for p in DOC_DIR.glob(f"{locale[:2]}*") if p.is_dir())
    candidates.append(DOC_DIR / "en")
    for folder in candidates:
        path = folder / f"{page}.md"
        if path.is_file():
            return path
    raise FileNotFoundError(f"no {page}.md under {DOC_DIR}")


def doc_text(page: str, locale: str) -> str:
    return doc_path(page, locale).read_text(encoding="utf-8")
