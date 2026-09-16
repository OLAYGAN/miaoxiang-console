"""Runtime paths and defaults for the local console."""

from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel


class RuntimePaths(BaseModel):
    project_root: Path
    data_dir: Path
    log_dir: Path
    screenshot_dir: Path
    accounts_file: Path
    settings_file: Path
    run_state_file: Path


def build_runtime_paths(project_root: Path | None = None) -> RuntimePaths:
    root = (project_root or Path(__file__).resolve().parent.parent).resolve()
    data_dir = root / "data"
    log_dir = root / "logs"
    screenshot_dir = root / "screenshots"
    return RuntimePaths(
        project_root=root,
        data_dir=data_dir,
        log_dir=log_dir,
        screenshot_dir=screenshot_dir,
        accounts_file=data_dir / "accounts.json",
        settings_file=data_dir / "settings.json",
        run_state_file=data_dir / "run_state.json",
    )


def ensure_runtime_directories(paths: RuntimePaths) -> None:
    paths.data_dir.mkdir(parents=True, exist_ok=True)
    paths.log_dir.mkdir(parents=True, exist_ok=True)
    paths.screenshot_dir.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_runtime_paths() -> RuntimePaths:
    paths = build_runtime_paths()
    ensure_runtime_directories(paths)
    return paths
