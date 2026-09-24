import sys
from pathlib import Path

from backend.config import build_runtime_paths


def test_frozen_runtime_uses_exe_dir_for_data_and_bundle_for_resources(
    tmp_path: Path,
    monkeypatch,
) -> None:
    exe_dir = tmp_path / "MiaoxiangConsole"
    bundle_dir = tmp_path / "_internal"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle_dir), raising=False)
    monkeypatch.setattr(
        sys,
        "executable",
        str(exe_dir / "MiaoxiangConsole.exe"),
    )

    paths = build_runtime_paths()

    assert paths.project_root == exe_dir.resolve()
    assert paths.resource_root == bundle_dir.resolve()
    assert paths.data_dir == exe_dir / "data"
    assert paths.accounts_file == exe_dir / "data" / "accounts.json"
