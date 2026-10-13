import struct
import threading

import geopandas as gpd
import pyogrio
import pytest
from shapely.geometry import box

from component.scripts import pmtiles_preview as pp

needs_tippecanoe = pytest.mark.skipif(pp.resolve_tippecanoe() is None, reason="tippecanoe not available")


def _gpkg(path, n=300):
    """n small squares (~0.002 deg) in a row, layer 'g'."""
    geoms = [box(-60 + i * 0.003, -22.3, -60 + i * 0.003 + 0.002, -22.298) for i in range(n)]
    frame = gpd.GeoDataFrame({"global_id": list(range(1, n + 1)), "level": [17] * n}, geometry=geoms, crs="EPSG:4326")
    pyogrio.write_dataframe(frame, path, layer="g", driver="GPKG")
    return path


def _header(path):
    raw = path.read_bytes()[:127]
    return raw[:7], raw[7], raw[100], raw[101], struct.unpack("<i", raw[102:106])[0] / 1e7


def test_feature_lines_carry_only_global_id():
    lines = pp.feature_lines([7, 8], ['{"type":"Point","coordinates":[1,2]}', '{"type":"Point","coordinates":[3,4]}'])
    assert lines.splitlines()[0] == (
        '{"type":"Feature","properties":{"global_id":7},"geometry":{"type":"Point","coordinates":[1,2]}}'
    )
    assert lines.endswith("\n") and len(lines.splitlines()) == 2


def test_parse_progress():
    assert pp.parse_progress('{"progress":46.0}') == 46.0
    assert pp.parse_progress("Warning: something") is None


def test_missing_binary_raises_typed_error(tmp_path, monkeypatch):
    monkeypatch.setattr(pp, "resolve_tippecanoe", lambda: None)
    with pytest.raises(pp.TippecanoeUnavailable):
        pp.build_preview(_gpkg(tmp_path / "g.gpkg"), "g", tmp_path / "o.pmtiles", minzoom=10, maxzoom=13,
                         tmp_dir=tmp_path)


def test_resolve_falls_back_to_interpreter_dir(tmp_path, monkeypatch):
    fake = tmp_path / "bin" / "tippecanoe"
    fake.parent.mkdir()
    fake.write_text("")
    monkeypatch.setattr(pp.shutil, "which", lambda name: None)
    monkeypatch.setattr(pp.sys, "executable", str(tmp_path / "bin" / "python"))
    assert pp.resolve_tippecanoe() == str(fake)
    fake.unlink()
    assert pp.resolve_tippecanoe() is None


@needs_tippecanoe
def test_builds_valid_pmtiles_with_the_zoom_range(tmp_path):
    out = tmp_path / "work" / ".preview.pmtiles"
    out.parent.mkdir()
    got = pp.build_preview(_gpkg(tmp_path / "g.gpkg"), "g", out, minzoom=10, maxzoom=13, tmp_dir=out.parent)
    assert got == out and out.stat().st_size > 0
    magic, version, minzoom, maxzoom, _ = _header(out)
    assert (magic, version, minzoom, maxzoom) == (b"PMTiles", 3, 10, 13)
    assert sorted(p.name for p in out.parent.iterdir()) == [".preview.pmtiles"]  # no temp files left


@needs_tippecanoe
def test_progress_milestones_are_sparse(tmp_path, caplog):
    out = tmp_path / "p.pmtiles"
    with caplog.at_level("INFO", logger="fra_grid"):
        pp.build_preview(_gpkg(tmp_path / "g.gpkg", n=2000), "g", out, minzoom=10, maxzoom=13, tmp_dir=tmp_path,
                         chunk=200)
    pcts = [r.getMessage() for r in caplog.records if r.getMessage().startswith("Map preview ")]
    assert pcts[:2] == ["Map preview 25%", "Map preview 50%"]  # feeding is the first half
    assert pcts[2:] in ([], ["Map preview 75%"])  # tippecanoe may finish before a poll sees 50 %


@needs_tippecanoe
def test_cancel_kills_tippecanoe_and_raises(tmp_path, monkeypatch):
    cancel = threading.Event()
    procs = []
    real_popen = pp.subprocess.Popen

    def popen(*a, **k):
        proc = real_popen(*a, **k)
        procs.append(proc)
        cancel.set()  # cancelled as soon as tippecanoe runs
        return proc

    monkeypatch.setattr(pp.subprocess, "Popen", popen)
    out = tmp_path / "c.pmtiles"
    with pytest.raises(pp.PreviewCancelled):
        pp.build_preview(_gpkg(tmp_path / "g.gpkg"), "g", out, minzoom=10, maxzoom=13, tmp_dir=tmp_path,
                         cancel=cancel)
    assert procs and procs[0].poll() is not None  # the subprocess is gone
    assert not out.exists()


@needs_tippecanoe
def test_tippecanoe_failure_raises_preview_failed(tmp_path):
    with pytest.raises(pp.PreviewFailed):
        pp.build_preview(_gpkg(tmp_path / "g.gpkg"), "g", tmp_path / "x.pmtiles", minzoom=13, maxzoom=10,
                         tmp_dir=tmp_path)


@needs_tippecanoe
def test_on_progress_reports_rising_percent_without_repeats(tmp_path):
    seen = []
    pp.build_preview(_gpkg(tmp_path / "g.gpkg", n=2000), "g", tmp_path / "p.pmtiles", minzoom=10, maxzoom=13,
                     tmp_dir=tmp_path, chunk=200, on_progress=seen.append)
    assert seen and seen == sorted(seen) and len(seen) == len(set(seen))
    assert 50.0 in seen  # feeding (first half) completes before tippecanoe's own progress
    assert all(0 < p <= 100 for p in seen)
