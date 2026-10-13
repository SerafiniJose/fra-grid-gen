import ipyvuetify as v
import reacton
from shapely.geometry import box

from component.model.state_manager import AppState
from component.scripts.aoi_prep import AoiError
from component.tile import aoi_tile


class _Result:
    method = "DRAW"


def test_resolve_publishes_info_for_the_current_result(chaco_aoi):
    state, result = AppState(), _Result()
    state.aoi_result.set(result)
    aoi_tile.resolve_aoi_into(state, result, resolve=lambda r: chaco_aoi)
    assert state.aoi_info.value is chaco_aoi
    assert state.aoi_error.value is None and state.aoi_resolving.value is False


def test_stale_result_is_dropped(chaco_aoi):
    state, old, new = AppState(), _Result(), _Result()
    state.aoi_result.set(new)
    state.aoi_resolving.set(True)
    aoi_tile.resolve_aoi_into(state, old, resolve=lambda r: chaco_aoi)
    assert state.aoi_info.value is None
    assert state.aoi_resolving.value is True  # the newer resolution still owns the flag


def test_aoi_errors_become_keys():
    state, result = AppState(), _Result()
    state.aoi_result.set(result)

    def boom(r):
        raise AoiError("antimeridian")

    aoi_tile.resolve_aoi_into(state, result, resolve=boom)
    assert state.aoi_error.value == ("antimeridian", "")
    assert state.aoi_info.value is None


def test_unexpected_errors_become_fetch():
    state, result = AppState(), _Result()
    state.aoi_result.set(result)

    def boom(r):
        raise RuntimeError("EE timeout")

    aoi_tile.resolve_aoi_into(state, result, resolve=boom)
    assert state.aoi_error.value == ("fetch", "EE timeout")


def test_summary_card_shows_estimate_and_continue_sits_below_it(chaco_aoi):
    went = []
    box_, rc = reacton.render(aoi_tile.AoiReady(info=chaco_aoi, on_continue=lambda: went.append(1)),
                              handle_error=False)
    try:
        assert rc.find(v.Html, children=["331"]).widgets  # r17 Steiner estimate for the Chaco box
        assert not rc.find(v.Card).find(v.Btn).widgets  # the button is outside the card
        rc.find(v.Btn, children=["Continue to Grid →"]).widget.click()
        assert went == [1]
    finally:
        rc.close()
