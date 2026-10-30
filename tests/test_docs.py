import inspect

import ipyvuetify as v
import pytest
import solara

from component import i18n
from component.parameter import grid as g
from component.scripts import docs
from component.scripts.levels import all_levels


@pytest.mark.parametrize("locale", ["en", "es-ES", "fr-FR", "pt-PT"])
@pytest.mark.parametrize("page", docs.PAGES)
def test_every_locale_ships_every_page(locale, page):
    assert docs.doc_path(page, locale) == docs.DOC_DIR / locale / f"{page}.md"


def test_doc_locales_match_the_message_catalogs():
    assert sorted(p.name for p in docs.DOC_DIR.iterdir() if p.is_dir()) == i18n.app_available_locales()


def test_locale_fallback():
    assert docs.doc_path("about", "es-AR") == docs.DOC_DIR / "es-ES" / "about.md"
    assert docs.doc_path("about", "fr") == docs.DOC_DIR / "fr-FR" / "about.md"
    assert docs.doc_path("about", "de") == docs.DOC_DIR / "en" / "about.md"
    assert docs.doc_path("about", "") == docs.DOC_DIR / "en" / "about.md"
    with pytest.raises(ValueError):
        docs.doc_path("missing", "en")


@pytest.mark.parametrize("locale, sep", [("en", ","), ("es-ES", "."), ("fr-FR", " "), ("pt-PT", " ")])
def test_level_table_matches_the_level_statistics(locale, sep):
    text = docs.doc_text("documentation", locale)
    for stats in all_levels():
        assert f"{stats.cells:,}".replace(",", sep) in text, (locale, stats.level)


@pytest.mark.parametrize("locale", ["en", "es-ES", "fr-FR", "pt-PT"])
def test_documentation_explains_finer_level_correction(locale):
    text = docs.doc_text("documentation", locale)
    assert "validated_at_levels" in text and "fra_r17_id" in text
    assert str(g.CALIB_C1).replace(".", "." if locale == "en" else ",") in text


def test_doc_page_renders_markdown():
    from component.widget.doc_page import DocPage

    _, rc = solara.render(DocPage(page="about"), handle_error=False)
    html = rc.find(v.VuetifyTemplate).widget.template
    assert "<h3" in html and "FRA Remote Sensing Survey" in html


def test_app_puts_about_and_documentation_in_the_drawer(results_root):
    import importlib

    app = importlib.import_module("app")
    source = inspect.getsource(app.Page)
    assert 'DocPage(page="about")' in source and 'DocPage(page="documentation")' in source
    assert "steps_data=steps_data" in source
