"""Writable scratch locations (pattern from spatial_risk's gdal_env).

On SEPAL every user-visible path is NFS (including /tmp); only the container
overlay (/var/tmp) is local disk. SQLite/GPKG writes are ~10x slower on NFS,
so the GPKG and dggrid's temp files are built under ``local_scratch_dir()``
and moved into place afterwards. Nothing here may raise at import time.
"""

import os
import tempfile
from pathlib import Path


def _uid() -> str:
    return str(os.getuid()) if hasattr(os, "getuid") else "user"


def _usable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False
    return os.access(path, os.W_OK | os.X_OK)


def scratch_dir() -> Path:
    """Large temp files (GDAL). ``$FRA_GRID_SCRATCH`` or <tmp>/fra_grid_<uid>."""
    env = os.environ.get("FRA_GRID_SCRATCH")
    path = Path(env).expanduser().absolute() if env else Path(tempfile.gettempdir()) / f"fra_grid_{_uid()}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def local_scratch_dir() -> Path:
    """Seek-heavy writers (GPKG, dggrid temp files): local disk when available."""
    candidates = []
    env = os.environ.get("FRA_GRID_LOCAL_SCRATCH")
    if env:
        candidates.append(Path(env).expanduser().absolute())
    candidates.append(Path("/var/tmp") / f"fra_grid_{_uid()}")
    for path in candidates:
        if _usable(path):
            return path
    return scratch_dir()


def configure_gdal_tmpdir():
    """Point GDAL's temp files (CPL_TMPDIR) away from the read-only CWD.

    Sets the environment (inherited by the dggrid subprocess) and pyogrio's
    in-process GDAL config. Keeps an operator-provided CPL_TMPDIR. Never raises.
    """
    try:
        path = Path(os.environ.get("CPL_TMPDIR") or scratch_dir() / "gdal")
        path.mkdir(parents=True, exist_ok=True)
        os.environ["CPL_TMPDIR"] = str(path)
        try:
            import pyogrio

            pyogrio.set_gdal_config_options({"CPL_TMPDIR": str(path)})
        except Exception:
            pass
        return path
    except Exception:
        return None
