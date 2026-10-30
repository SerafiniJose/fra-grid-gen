"""Build a grid's PMTiles map preview with tippecanoe (Solara-free).

The GPKG layer is streamed to tippecanoe's stdin as GeoJSONSeq, one Arrow
batch at a time (only ``global_id`` and the outline), so memory stays flat up
to the 10M-cell cap and no intermediate GeoJSON lands on disk. tippecanoe's
temp files (``-t``) and the archive it assembles (``-o``) belong on local
disk: its PMTiles writer seeks constantly and SEPAL's NFS is ~60x slower
(measured in spatial_risk's pmtiles_convert).

Progress: feeding counts for the first half, tippecanoe's ``--json-progress``
for the second; INFO milestones at 25/50/75 % go out on the caller's thread
(the job thread, so notify_bridge turns them into task steps), and
``on_progress(pct)`` gets every rise of the percent, also on that thread.
``cancel`` is checked between batches and while tippecanoe runs; a set event
kills the subprocess and raises ``PreviewCancelled``.
"""

import logging
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path

import pyogrio
import shapely

from component.parameter import grid as g

logger = logging.getLogger(g.LOGGER_NAME)

CHUNK = 50_000
MILESTONES = (25, 50, 75)
_POLL_S = 0.1
_PROGRESS_RE = re.compile(r'"progress"\s*:\s*([0-9.]+)')


class TippecanoeUnavailable(RuntimeError):
    """No tippecanoe binary on PATH or next to the interpreter."""


class PreviewFailed(RuntimeError):
    """tippecanoe exited with an error."""


class PreviewCancelled(Exception):
    """The cancel event was set while the preview was building."""


def resolve_tippecanoe():
    """Absolute path to ``tippecanoe``, or None.

    PATH first, then next to ``sys.executable``: SEPAL kernels run the env's
    interpreter without its ``bin/`` on PATH.
    """
    found = shutil.which("tippecanoe")
    if found:
        return found
    sibling = Path(sys.executable).parent / "tippecanoe"
    return str(sibling) if sibling.exists() else None


def feature_lines(ids, geometries_json, layer=None, minzoom=None) -> str:
    """GeoJSONSeq text: one Feature per line, ``global_id`` as the only property.

    ``layer``/``minzoom`` put the features in another tile layer than ``-l``'s,
    from that zoom (tippecanoe's per-feature ``"tippecanoe"`` member).
    """
    tip = f',"tippecanoe":{{"layer":"{layer}","minzoom":{int(minzoom)}}}' if layer else ""
    return "".join(
        f'{{"type":"Feature","properties":{{"global_id":{int(i)}}},"geometry":{geom}{tip}}}\n'
        for i, geom in zip(ids, geometries_json)
    )


def parse_progress(line: str):
    match = _PROGRESS_RE.search(line)
    return float(match.group(1)) if match else None


class _Milestones:
    """Log each 25/50/75 % threshold once and report each rise, on the calling thread."""

    def __init__(self, on_progress=None):
        self._next = 0
        self._last = 0.0
        self._on_progress = on_progress

    def update(self, pct: float) -> None:
        if self._on_progress is not None and pct > self._last:
            self._last = pct
            self._on_progress(pct)
        while self._next < len(MILESTONES) and pct >= MILESTONES[self._next]:
            logger.info("Map preview %d%%", MILESTONES[self._next])
            self._next += 1


def _command(exe, out_path, tmp_dir, layer_name, minzoom, maxzoom) -> list:
    return [
        exe, "-o", str(out_path), "-t", str(tmp_dir), "-l", layer_name,
        "-Z", str(minzoom), "-z", str(maxzoom),
        "--no-feature-limit", "--no-tile-size-limit", "--force",
        "--json-progress", "--progress-interval=1",
    ]


def _kill(proc) -> None:
    if proc.poll() is None:
        proc.kill()
    proc.wait()


def build_preview(gpkg, layer, out_path, *, minzoom, maxzoom, tmp_dir, cancel=None, chunk=CHUNK,
                  on_progress=None, centroids_layer=None) -> Path:
    """Write ``out_path`` (a PMTiles archive of ``layer``'s cell outlines).

    ``centroids_layer`` (a GPKG layer of 1 ha centroid squares) goes into the same archive as
    the ``g.PREVIEW_CENTROIDS_LAYER`` source-layer, from ``g.PREVIEW_CENTROIDS_MINZOOM``.

    Raises ``TippecanoeUnavailable``, ``PreviewFailed`` or ``PreviewCancelled``;
    a partial archive is removed on any failure.
    """
    exe = resolve_tippecanoe()
    if exe is None:
        raise TippecanoeUnavailable("tippecanoe not found on PATH or next to the interpreter")
    gpkg, out_path, tmp_dir = Path(gpkg), Path(out_path), Path(tmp_dir).absolute()
    centroids_zoom = min(g.PREVIEW_CENTROIDS_MINZOOM, maxzoom)
    sources = [(layer, None, None)]
    if centroids_layer:
        sources.append((centroids_layer, g.PREVIEW_CENTROIDS_LAYER, centroids_zoom))
    total = max(sum(pyogrio.read_info(gpkg, layer=src)["features"] for src, _, _ in sources), 1)
    milestones = _Milestones(on_progress)
    tail = []  # last stderr lines, for the error message
    state = {"pct": 0.0}

    def drain(stream):
        for raw in stream:
            line = raw.decode("utf-8", "replace").strip()
            pct = parse_progress(line)
            if pct is not None:
                state["pct"] = pct
            elif line:
                tail[:] = (tail + [line])[-5:]

    proc = subprocess.Popen(
        _command(exe, out_path, tmp_dir, g.PREVIEW_LAYER, minzoom, maxzoom),
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )
    reader = threading.Thread(target=drain, args=(proc.stderr,), daemon=True)
    reader.start()
    try:
        fed = 0
        try:
            for src, tile_layer, tile_minzoom in sources:
                with pyogrio.open_arrow(gpkg, layer=src, columns=["global_id"], batch_size=chunk,
                                        use_pyarrow=True) as (meta, batches):
                    geom_col = meta["geometry_name"] or "wkb_geometry"
                    for batch in batches:
                        if cancel is not None and cancel.is_set():
                            raise PreviewCancelled()
                        geoms = shapely.from_wkb(batch.column(geom_col).to_numpy(zero_copy_only=False))
                        text = feature_lines(batch.column("global_id").to_numpy(), shapely.to_geojson(geoms),
                                             tile_layer, tile_minzoom)
                        proc.stdin.write(text.encode("utf-8"))
                        fed += batch.num_rows
                        milestones.update(50.0 * fed / total)
            proc.stdin.close()
        except BrokenPipeError:
            pass  # tippecanoe exited early: its return code says why
        while proc.poll() is None:
            if cancel is not None and cancel.is_set():
                raise PreviewCancelled()
            milestones.update(50.0 + state["pct"] / 2.0)
            try:
                proc.wait(timeout=_POLL_S)
            except subprocess.TimeoutExpired:
                pass
        reader.join(timeout=5)  # every stderr line read before the return code is judged
        if proc.returncode != 0:
            raise PreviewFailed(f"tippecanoe exited with {proc.returncode}: {' | '.join(tail)}")
    except BaseException:
        _kill(proc)
        out_path.unlink(missing_ok=True)
        raise
    finally:
        reader.join(timeout=5)  # never close stderr under the reader's feet
        for stream in (proc.stdin, proc.stderr):
            try:
                stream.close()
            except (OSError, ValueError):
                pass
    return out_path
