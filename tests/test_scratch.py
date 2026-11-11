import os

import pytest

from component.scripts import scratch


def test_scratch_dirs_are_absolute_writable_and_env_overridable(tmp_path, monkeypatch):
    monkeypatch.setenv("FRA_GRID_SCRATCH", str(tmp_path / "nfs"))
    monkeypatch.setenv("FRA_GRID_LOCAL_SCRATCH", str(tmp_path / "local"))
    assert scratch.scratch_dir() == tmp_path / "nfs"
    assert scratch.local_scratch_dir() == tmp_path / "local"
    assert os.access(scratch.local_scratch_dir(), os.W_OK)


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores directory permissions")
def test_local_scratch_falls_back_when_override_unusable(tmp_path, monkeypatch):
    blocked = tmp_path / "ro"
    blocked.mkdir()
    blocked.chmod(0o555)
    monkeypatch.setenv("FRA_GRID_SCRATCH", str(tmp_path / "nfs"))
    monkeypatch.setenv("FRA_GRID_LOCAL_SCRATCH", str(blocked / "x"))
    try:
        got = scratch.local_scratch_dir()
        assert got.is_absolute() and os.access(got, os.W_OK)
        assert got != blocked / "x"
    finally:
        blocked.chmod(0o755)


def test_configure_gdal_tmpdir_sets_env(tmp_path, monkeypatch):
    monkeypatch.delenv("CPL_TMPDIR", raising=False)
    monkeypatch.setenv("FRA_GRID_SCRATCH", str(tmp_path / "nfs"))
    got = scratch.configure_gdal_tmpdir()
    assert got is not None and os.environ["CPL_TMPDIR"] == str(got)


def test_cleanup_local_scratch_removes_only_old_run_folders(tmp_path, monkeypatch):
    local = tmp_path / "local"
    monkeypatch.setenv("FRA_GRID_LOCAL_SCRATCH", str(local))
    for name in ("old-run", "new-run", "dggrid"):
        (local / name).mkdir(parents=True)
    (local / "old-file").write_text("x")
    for name in ("old-run", "dggrid", "old-file"):
        os.utime(local / name, (0, 0))
    assert scratch.cleanup_local_scratch(3600) == ["old-run"]
    assert sorted(p.name for p in local.iterdir()) == ["dggrid", "new-run", "old-file"]
