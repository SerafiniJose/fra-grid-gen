"""Grid folders under the results root: naming, listing, atomic commit, delete.

A grid folder is a direct child of the root holding a readable
``metadata.json`` with this app's schema. Anything else is never listed,
replaced or deleted. Builds land in ``.<name>.part`` and are renamed into
place; an overwrite parks the old folder as ``.<name>.old`` for the swap.
"""

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from component.scripts.metadata import read_metadata_json
from component.scripts.writers import file_sizes

MAX_NAME_LEN = 80
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


def part_folder(root, name) -> Path:
    return Path(root) / f".{name}.part"


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
    files = tuple(file_sizes(folder))
    return OutputRecord(name=name, folder=folder, metadata=record, files=files, size_bytes=sum(s for _, s in files))


def list_outputs(root) -> list:
    root = Path(root)
    if not root.is_dir():
        return []
    records = [r for p in root.iterdir() if not p.name.startswith(".") and (r := load_output(root, p.name))]
    return sorted(records, key=lambda r: (r.generated_at, r.name), reverse=True)


def commit_part(root, name) -> Path:
    root = Path(root)
    part, target, old = part_folder(root, name), root / name, old_folder(root, name)
    if not part.is_dir():
        raise FileNotFoundError(str(part))
    if target.exists() or target.is_symlink():
        if not is_grid_folder(target):
            raise NotAGridFolder(str(target))
        shutil.rmtree(old, ignore_errors=True)
        target.rename(old)
    part.rename(target)
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


def cleanup_stale(root) -> list:
    removed = []
    root = Path(root)
    if not root.is_dir():
        return removed
    for path in root.iterdir():
        stale = path.name.startswith(".") and path.name.endswith((".part", ".old"))
        if stale and path.is_dir() and not path.is_symlink():
            shutil.rmtree(path, ignore_errors=True)
            removed.append(path.name)
    return removed
