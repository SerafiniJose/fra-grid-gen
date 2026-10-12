"""Grid folders under the results root: naming, listing, atomic commit, delete.

A grid folder is a direct child of the root holding a readable
``metadata.json`` with this app's schema. Anything else is never listed,
replaced or deleted. Builds land in a staging ``.part`` folder and are renamed
into place; an overwrite parks the old folder as ``.<name>.old`` for the swap.

Every run stages in its own ``.<name>.<run id>.part`` holding an owner file
(pid, host, start time): on SEPAL every browser tab is its own kernel
process, so two sessions may build the same name, and a new kernel's startup
cleanup must not delete a part a live run is still writing.
"""

import json
import os
import re
import shutil
import socket
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from component.scripts.metadata import read_metadata_json
from component.scripts.writers import file_sizes

MAX_NAME_LEN = 80
OWNER_FILE = ".owner.json"
STALE_AGE_S = 24 * 3600  # a part older than this is abandoned, whoever owns it
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


class DeleteRefused(ValueError):
    def __init__(self, reason: str, name: str = ""):
        super().__init__(f"refused to delete {name!r}: {reason}")
        self.reason = reason


class NotAGridFolder(FileExistsError):
    """A path with the grid's name exists but is not a grid this app made."""


def validate_grid_name(name):
    if not name or not str(name).strip():
        return "empty"
    if len(name) > MAX_NAME_LEN:
        return "too_long"
    if not _NAME_RE.match(name):
        return "invalid"
    return None


def new_part_folder(root, name) -> Path:
    """Create this run's own staging folder, with an owner file in it."""
    part = Path(root) / f".{name}.{uuid.uuid4().hex[:8]}.part"
    part.mkdir(parents=True)
    owner = {"pid": os.getpid(), "host": socket.gethostname(), "started": time.time()}
    (part / OWNER_FILE).write_text(json.dumps(owner))
    return part


def old_folder(root, name) -> Path:
    return Path(root) / f".{name}.old"


def is_grid_folder(path) -> bool:
    path = Path(path)
    return path.is_dir() and not path.is_symlink() and read_metadata_json(path) is not None


def name_status(root, name) -> str:
    path = Path(root) / name
    if not path.exists() and not path.is_symlink():
        return "free"
    return "grid" if is_grid_folder(path) else "taken"


@dataclass(frozen=True)
class OutputRecord:
    name: str
    folder: Path
    metadata: dict
    files: tuple
    size_bytes: int

    @property
    def level(self) -> int:
        return int(self.metadata.get("dggs", {}).get("resolution", 0))

    @property
    def cell_count(self) -> int:
        return int(self.metadata.get("run", {}).get("cell_count", 0))

    @property
    def generated_at(self) -> str:
        return str(self.metadata.get("generated_at", ""))

    @property
    def aoi_label(self) -> str:
        return str(self.metadata.get("aoi", {}).get("label", ""))

    @property
    def formats(self) -> tuple:
        return tuple(self.metadata.get("run", {}).get("formats", ()))

    @property
    def gpkg_path(self):
        path = self.folder / f"{self.name}.gpkg"
        return path if path.exists() else None


def load_output(root, name):
    folder = Path(root) / name
    if validate_grid_name(name) is not None or folder.is_symlink() or not folder.is_dir():
        return None
    record = read_metadata_json(folder)
    if record is None:
        return None
    sizes = file_sizes(folder)
    # Hidden files (the PMTiles map preview) are not deliverables: not listed,
    # but counted in the size, which is what a delete frees.
    files = tuple((n, s) for n, s in sizes if not n.startswith("."))
    return OutputRecord(name=name, folder=folder, metadata=record, files=files, size_bytes=sum(s for _, s in sizes))


def list_outputs(root) -> list:
    root = Path(root)
    if not root.is_dir():
        return []
    records = [r for p in root.iterdir() if not p.name.startswith(".") and (r := load_output(root, p.name))]
    return sorted(records, key=lambda r: (r.generated_at, r.name), reverse=True)


def commit_part(root, name, part, *, overwrite: bool) -> Path:
    """Rename this run's ``part`` into ``<root>/<name>``.

    An existing grid is replaced only when ``overwrite``; anything else at the
    target is never touched. If the swap fails half-way the old grid is put back.
    """
    root, part = Path(root), Path(part)
    target, old = root / name, old_folder(root, name)
    if not part.is_dir():
        raise FileNotFoundError(str(part))
    if not (target.exists() or target.is_symlink()):
        (part / OWNER_FILE).unlink(missing_ok=True)
        part.rename(target)
        return target
    if not is_grid_folder(target):
        raise NotAGridFolder(str(target))
    if not overwrite:
        raise FileExistsError(str(target))
    (part / OWNER_FILE).unlink(missing_ok=True)
    shutil.rmtree(old, ignore_errors=True)
    target.rename(old)
    try:
        part.rename(target)
    except BaseException:
        old.rename(target)
        raise
    shutil.rmtree(old, ignore_errors=True)
    return target


def _guarded_folder(root, name) -> Path:
    if validate_grid_name(name) is not None:
        raise DeleteRefused("invalid_name", name)
    root = Path(root).resolve()
    folder = root / name
    if folder.is_symlink():
        raise DeleteRefused("symlink", name)
    resolved = folder.resolve()
    if resolved == root or resolved.parent != root:
        raise DeleteRefused("outside_root", name)
    if not is_grid_folder(resolved):
        raise DeleteRefused("not_a_grid", name)
    return resolved


def delete_output(root, name, *, busy=()) -> None:
    if name in set(busy):
        raise DeleteRefused("busy", name)
    shutil.rmtree(_guarded_folder(root, name))


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except (OSError, OverflowError, ValueError):
        return False
    return True


def _part_abandoned(part: Path, now: float) -> bool:
    """True unless a live run on this host may still be writing ``part``."""
    try:
        owner = json.loads((part / OWNER_FILE).read_text())
        pid, host, started = int(owner["pid"]), str(owner["host"]), float(owner["started"])
    except (OSError, ValueError, TypeError, KeyError):
        try:
            return now - part.stat().st_mtime > STALE_AGE_S
        except OSError:
            return False
    if now - started > STALE_AGE_S:
        return True
    return host == socket.gethostname() and not _pid_alive(pid)


def cleanup_stale(root) -> list:
    """Remove abandoned staging folders and put back an orphaned ``.old`` grid.

    Only dot-prefixed folders ending in ``.part`` / ``.old`` are considered;
    files, symlinks and other folders are never touched. A ``.part`` goes only
    when its owner run is gone (dead pid on this host) or it is older than
    ``STALE_AGE_S``. A ``.<name>.old`` grid whose ``<name>`` is missing (a swap
    that died half-way) is renamed back; otherwise it is removed.
    """
    removed = []
    root = Path(root)
    if not root.is_dir():
        return removed
    now = time.time()
    for path in root.iterdir():
        if not path.name.startswith(".") or not path.is_dir() or path.is_symlink():
            continue
        if path.name.endswith(".part"):
            if _part_abandoned(path, now):
                shutil.rmtree(path, ignore_errors=True)
                removed.append(path.name)
        elif path.name.endswith(".old"):
            target = root / path.name[1:-len(".old")]
            if target.exists() or target.is_symlink():
                shutil.rmtree(path, ignore_errors=True)
                removed.append(path.name)
            elif is_grid_folder(path) and validate_grid_name(target.name) is None:
                path.rename(target)
    return removed
