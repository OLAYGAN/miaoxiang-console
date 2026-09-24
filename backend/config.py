"""Runtime paths and defaults for the local console."""

from functools import lru_cache
from pathlib import Path
import sys

from pydantic import BaseModel


class RuntimePaths(BaseModel):
    project_root: Path
    resource_root: Path | None = None
    data_dir: Path
    log_dir: Path
    screenshot_dir: Path
    accounts_file: Path
    settings_file: Path
    run_state_file: Path
    lyric_templates_file: Path
    pipeline_state_file: Path
    pipeline_queue_state_file: Path


def _frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def build_runtime_paths(
    project_root: Path | None = None,
    resource_root: Path | None = None,
) -> RuntimePaths:
    if project_root is not None:
        root = Path(project_root).resolve()
    elif _frozen():
        root = Path(sys.executable).resolve().parent
    else:
        root = Path(__file__).resolve().parent.parent
    if resource_root is not None:
        resources = Path(resource_root).resolve()
    elif _frozen():
        resources = Path(getattr(sys, "_MEIPASS", root)).resolve()
    else:
        resources = root
    data_dir = root / "data"
    log_dir = root / "logs"
    screenshot_dir = root / "screenshots"
    return RuntimePaths(
        project_root=root,
        resource_root=resources,
        data_dir=data_dir,
        log_dir=log_dir,
        screenshot_dir=screenshot_dir,
        accounts_file=data_dir / "accounts.json",
        settings_file=data_dir / "settings.json",
        run_state_file=data_dir / "run_state.json",
        lyric_templates_file=data_dir / "lyric_templates.json",
        pipeline_state_file=data_dir / "pipeline_state.json",
        pipeline_queue_state_file=data_dir / "pipeline_queue_state.json",
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
