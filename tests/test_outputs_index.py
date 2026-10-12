import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from component.scripts import outputs_index as oi
from component.scripts.metadata import SCHEMA


def make_grid(root, name, generated_at="2026-10-12T10:00:00Z", level=17, cells=10):
    folder = root / name
    folder.mkdir(parents=True)
    record = {
        "schema": SCHEMA, "name": name, "generated_at": generated_at,
        "dggs": {"resolution": level}, "aoi": {"label": "Chaco"},
        "run": {"cell_count": cells, "formats": ["gpkg"]},
    }
    (folder / "metadata.json").write_text(json.dumps(record))
    (folder / f"{name}.gpkg").write_bytes(b"x" * 100)
    return folder


@pytest.mark.parametrize(
    "name,err",
    [("", "empty"), ("   ", "empty"), ("a/b", "invalid"), ("..", "invalid"), (".hidden", "invalid"),
     ("x" * 81, "too_long"), ("fra_isea3h_r17_chaco-1", None)],
)
def test_validate_grid_name(name, err):
    assert oi.validate_grid_name(name) == err


def test_list_outputs_newest_first_and_skips_non_grids(tmp_path):
    make_grid(tmp_path, "old", "2026-01-01T00:00:00Z")
    make_grid(tmp_path, "new", "2026-10-12T00:00:00Z", level=19, cells=99)
    (tmp_path / "no_metadata").mkdir()
    (tmp_path / ".new.part").mkdir()
    (tmp_path / "stray.txt").write_text("x")
    out = oi.list_outputs(tmp_path)
    assert [r.name for r in out] == ["new", "old"]
    assert out[0].level == 19 and out[0].cell_count == 99 and out[0].aoi_label == "Chaco"
    assert out[0].formats == ("gpkg",) and out[0].gpkg_path == tmp_path / "new" / "new.gpkg"
    assert out[0].size_bytes > 100


def test_name_status(tmp_path):
    make_grid(tmp_path, "g")
    (tmp_path / "other").mkdir()
    assert oi.name_status(tmp_path, "g") == "grid"
    assert oi.name_status(tmp_path, "other") == "taken"
    assert oi.name_status(tmp_path, "free_name") == "free"


def test_delete_removes_folder(tmp_path):
    make_grid(tmp_path, "g")
    oi.delete_output(tmp_path, "g")
    assert not (tmp_path / "g").exists()


@pytest.mark.parametrize("name", ["..", "", "no_metadata", "missing"])
def test_delete_refuses_non_grid_targets(tmp_path, name):
    (tmp_path / "no_metadata").mkdir()
    with pytest.raises(oi.DeleteRefused):
        oi.delete_output(tmp_path, name)
    assert tmp_path.exists() and (tmp_path / "no_metadata").exists()


def test_delete_refuses_symlink_out_of_root(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    outside = make_grid(tmp_path, "outside")
    (root / "evil").symlink_to(outside, target_is_directory=True)
    with pytest.raises(oi.DeleteRefused):
        oi.delete_output(root, "evil")
    assert (outside / "metadata.json").exists()


def test_delete_refuses_busy_name(tmp_path):
    make_grid(tmp_path, "g")
    with pytest.raises(oi.DeleteRefused) as err:
        oi.delete_output(tmp_path, "g", busy={"g"})
    assert err.value.reason == "busy" and (tmp_path / "g").exists()


def _part_with_metadata(root, name, v):
    part = oi.new_part_folder(root, name)
    (part / "metadata.json").write_text(json.dumps({"schema": SCHEMA, "v": v}))
    return part


def _dead_pid():
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    return proc.pid


def _age(path, seconds):
    old = time.time() - seconds
    os.utime(path, (old, old))


def test_new_part_folder_is_unique_dot_prefixed_and_owned(tmp_path):
    a, b = oi.new_part_folder(tmp_path, "g"), oi.new_part_folder(tmp_path, "g")
    assert a != b and a.is_dir() and b.is_dir()
    assert a.name.startswith(".g.") and a.name.endswith(".part")
    owner = json.loads((a / oi.OWNER_FILE).read_text())
    assert owner["pid"] == os.getpid() and owner["host"] == socket.gethostname()


def test_commit_part_fresh_and_overwrite(tmp_path):
    part = _part_with_metadata(tmp_path, "g", 1)
    assert oi.commit_part(tmp_path, "g", part, overwrite=False) == tmp_path / "g"
    assert not (tmp_path / "g" / oi.OWNER_FILE).exists()
    part = _part_with_metadata(tmp_path, "g", 2)
    oi.commit_part(tmp_path, "g", part, overwrite=True)
    assert json.loads((tmp_path / "g" / "metadata.json").read_text())["v"] == 2
    assert sorted(p.name for p in tmp_path.iterdir()) == ["g"]


def test_commit_part_refuses_existing_grid_without_overwrite(tmp_path):
    oi.commit_part(tmp_path, "g", _part_with_metadata(tmp_path, "g", 1), overwrite=False)
    part = _part_with_metadata(tmp_path, "g", 2)
    with pytest.raises(FileExistsError):
        oi.commit_part(tmp_path, "g", part, overwrite=False)
    assert json.loads((tmp_path / "g" / "metadata.json").read_text())["v"] == 1
    assert part.is_dir()


def test_commit_part_never_replaces_a_non_grid_folder(tmp_path):
    (tmp_path / "g").mkdir()
    (tmp_path / "g" / "precious.txt").write_text("keep")
    part = oi.new_part_folder(tmp_path, "g")
    with pytest.raises(oi.NotAGridFolder):
        oi.commit_part(tmp_path, "g", part, overwrite=True)
    assert (tmp_path / "g" / "precious.txt").read_text() == "keep"


def test_failed_swap_restores_the_old_grid(tmp_path, monkeypatch):
    oi.commit_part(tmp_path, "g", _part_with_metadata(tmp_path, "g", 1), overwrite=False)
    part = _part_with_metadata(tmp_path, "g", 2)
    real_rename = Path.rename

    def flaky_rename(self, target):
        if self == part:
            raise OSError("rename failed")
        return real_rename(self, target)

    monkeypatch.setattr(Path, "rename", flaky_rename)
    with pytest.raises(OSError, match="rename failed"):
        oi.commit_part(tmp_path, "g", part, overwrite=True)
    assert json.loads((tmp_path / "g" / "metadata.json").read_text())["v"] == 1
    assert not oi.old_folder(tmp_path, "g").exists()


def test_cleanup_stale_only_touches_dot_folders(tmp_path):
    (tmp_path / ".a.part").mkdir()
    _age(tmp_path / ".a.part", 2 * oi.STALE_AGE_S)
    make_grid(tmp_path, "b")
    (tmp_path / "b").rename(tmp_path / ".b.old")
    make_grid(tmp_path, "b")
    (tmp_path / ".config").mkdir()
    (tmp_path / "c.part").mkdir()
    _age(tmp_path / "c.part", 2 * oi.STALE_AGE_S)
    (tmp_path / ".d.part").write_text("file, not folder")
    make_grid(tmp_path, "g")
    assert sorted(oi.cleanup_stale(tmp_path)) == [".a.part", ".b.old"]
    assert sorted(p.name for p in tmp_path.iterdir()) == [".config", ".d.part", "b", "c.part", "g"]


def test_cleanup_stale_keeps_a_part_owned_by_a_live_run(tmp_path):
    live = oi.new_part_folder(tmp_path, "g")  # owner pid = this process
    fresh_unowned = tmp_path / ".h.0123abcd.part"
    fresh_unowned.mkdir()
    assert oi.cleanup_stale(tmp_path) == []
    assert live.is_dir() and fresh_unowned.is_dir()


def test_cleanup_stale_removes_dead_owner_and_old_parts(tmp_path):
    dead = oi.new_part_folder(tmp_path, "g")
    owner = json.loads((dead / oi.OWNER_FILE).read_text())
    (dead / oi.OWNER_FILE).write_text(json.dumps({**owner, "pid": _dead_pid()}))
    other_host = oi.new_part_folder(tmp_path, "h")
    (other_host / oi.OWNER_FILE).write_text(json.dumps({**owner, "host": "elsewhere", "started": 0}))
    unowned = tmp_path / ".k.0123abcd.part"
    unowned.mkdir()
    _age(unowned, 2 * oi.STALE_AGE_S)
    assert sorted(oi.cleanup_stale(tmp_path)) == sorted([dead.name, other_host.name, unowned.name])
    assert list(tmp_path.iterdir()) == []


def test_cleanup_stale_restores_an_orphan_old_grid(tmp_path):
    make_grid(tmp_path, "g")
    (tmp_path / "g").rename(oi.old_folder(tmp_path, "g"))
    oi.old_folder(tmp_path, "x").mkdir()  # not a grid: left alone, never renamed into place
    assert oi.cleanup_stale(tmp_path) == []
    assert oi.is_grid_folder(tmp_path / "g")
    assert sorted(p.name for p in tmp_path.iterdir()) == [".x.old", "g"]
