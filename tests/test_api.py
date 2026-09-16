from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.api import create_app
from backend.config import RuntimePaths
from backend.models import ConsoleSettings


class FakeFlow:
    def __init__(self, engine, stop_after: int | None = None) -> None:
        self.engine = engine
        self.stop_after = stop_after
        self.processed = 0

    async def process_song(self, lyric_data, on_step):
        self.processed += 1
        on_step("generate")
        if self.stop_after and self.processed >= self.stop_after:
            await self.engine.stop()
        return Path("output") / f"{lyric_data.song_name}.mp3"


class FakeBrowser:
    def __init__(self, flow: FakeFlow) -> None:
        self.flow = flow
        self.entered = 0
        self.exited = 0

    async def __aenter__(self):
        self.entered += 1
        return self.flow

    async def __aexit__(self, exc_type, exc, tb):
        self.exited += 1
        return False


def account_payload(tmp_path: Path, name: str = "账号01", port: int = 9222) -> dict:
    return {
        "account_name": name,
        "chrome_profile_dir": str(tmp_path / "chrome" / name),
        "chrome_debug_port": port,
        "lyric_dir": str(tmp_path / "lyrics"),
        "output_dir": str(tmp_path / "output"),
        "download_dir": str(tmp_path / "downloads"),
        "max_retries": 1,
        "song_interval_seconds": 0,
    }


def write_song(tmp_path: Path, name: str = "01_song") -> Path:
    directory = tmp_path / "lyrics" / "2026-09-17" / "账号01"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{name}.md"
    lyrics = "夜色像一台缓慢转动的引擎\n穿过城市也穿过我的呼吸\n" + "旧灯光写下未完成的旋律\n" * 20
    style = "男声摇滚，粗粝低音，鼓点密集，副歌开阔，带有都市夜行感和少量电子质感。整体情绪从压抑推进到明亮，尾奏保留城市噪声和模拟合成器余韵。"
    path.write_text(
        f"# 歌名：《{name}》\n\n## 歌词\n《{name}》\n{lyrics}\n[End]\n\n## 歌曲风格\n{style}\n",
        encoding="utf-8",
    )
    return path


def make_client(tmp_path: Path, stop_after: int | None = None):
    holder: dict = {}

    def factory(account, settings):
        flow = FakeFlow(holder["engine"], stop_after=stop_after)
        browser = FakeBrowser(flow)
        holder["browser"] = browser
        return browser

    paths = RuntimePaths(
        project_root=tmp_path,
        data_dir=tmp_path / "data",
        log_dir=tmp_path / "logs",
        screenshot_dir=tmp_path / "screenshots",
        accounts_file=tmp_path / "data" / "accounts.json",
        settings_file=tmp_path / "data" / "settings.json",
        run_state_file=tmp_path / "data" / "run_state.json",
    )
    app = create_app(runtime_paths=paths, browser_factory=factory, poll_interval=0.01)
    holder["engine"] = app.state.engine
    return app, holder


def test_health_and_account_crud(tmp_path: Path) -> None:
    app, _ = make_client(tmp_path)
    with TestClient(app) as client:
        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"

        created = client.post("/api/accounts", json=account_payload(tmp_path))
        assert created.status_code == 201
        account = created.json()

        conflict = client.post("/api/accounts", json=account_payload(tmp_path, port=9223))
        assert conflict.status_code == 409
        assert "名称" in conflict.json()["detail"]

        copied = client.post(f"/api/accounts/{account['id']}/copy", json={"account_name": "账号02"})
        assert copied.status_code == 200
        assert copied.json()["chrome_debug_port"] == 9223

        deleted = client.delete(f"/api/accounts/{account['id']}")
        assert deleted.status_code == 204
        assert client.get(f"/api/accounts/{account['id']}").status_code == 404


def test_song_listing_reports_parse_errors(tmp_path: Path) -> None:
    app, _ = make_client(tmp_path)
    with TestClient(app) as client:
        account = client.post("/api/accounts", json=account_payload(tmp_path)).json()
        good = write_song(tmp_path)
        bad = write_song(tmp_path, "00_bad")
        bad.write_text("# 歌名：《坏文件》\n", encoding="utf-8")

        response = client.get(f"/api/accounts/{account['id']}/songs?day=2026-09-17")
        assert response.status_code == 200
        songs = {item["file_name"]: item for item in response.json()}
        assert songs["00_bad.md"]["valid"] is False
        assert "歌名" not in songs["00_bad.md"]["error"]
        assert songs["01_song.md"]["valid"] is True
        assert songs["01_song.md"]["song_name"] == "01_song"
        assert Path(songs["01_song.md"]["path"]) == good


def test_start_requires_existing_account_and_songs(tmp_path: Path) -> None:
    app, _ = make_client(tmp_path)
    with TestClient(app) as client:
        missing = client.post("/api/runs", json={"account_id": "missing", "song_files": ["x.md"]})
        assert missing.status_code == 404

        account = client.post("/api/accounts", json=account_payload(tmp_path)).json()
        empty = client.post("/api/runs", json={"account_id": account["id"], "song_files": []})
        assert empty.status_code == 422


def test_run_stop_releases_browser_and_reports_state(tmp_path: Path) -> None:
    app, holder = make_client(tmp_path, stop_after=1)
    write_song(tmp_path, "01_first")
    write_song(tmp_path, "02_second")
    with TestClient(app) as client:
        account = client.post("/api/accounts", json=account_payload(tmp_path)).json()
        started = client.post(
            "/api/runs",
            json={
                "account_id": account["id"],
                "song_files": ["01_first.md", "02_second.md"],
                "day": "2026-09-17",
                "fresh_run": True,
            },
        )
        assert started.status_code == 202
        assert started.json()["status"] in {"running", "stopping"}

        for _ in range(100):
            current = client.get("/api/runs/current").json()
            if current["status"] == "stopped":
                break
            client.post("/api/runs/control", json={"action": "stop"})

        assert current["status"] == "stopped"
        assert current["success_count"] == 1
        assert holder["browser"].exited >= 1


def test_pause_resume_and_conflict(tmp_path: Path) -> None:
    app, _ = make_client(tmp_path)
    write_song(tmp_path, "01_first")
    write_song(tmp_path, "02_second")
    with TestClient(app) as client:
        account = client.post("/api/accounts", json=account_payload(tmp_path)).json()
        client.post(
            "/api/runs",
            json={
                "account_id": account["id"],
                "song_files": ["01_first.md", "02_second.md"],
                "day": "2026-09-17",
                "fresh_run": True,
            },
        )
        pause = client.post("/api/runs/control", json={"action": "pause"})
        assert pause.status_code == 202
        current = client.get("/api/runs/current").json()
        assert current["status"] in {"paused", "running", "stopping", "completed"}
        client.post("/api/runs/control", json={"action": "resume"})
        client.post("/api/runs/control", json={"action": "stop"})


def test_settings_update(tmp_path: Path) -> None:
    app, _ = make_client(tmp_path)
    with TestClient(app) as client:
        original = client.get("/api/settings").json()
        assert original["generation_timeout_seconds"] == 300

        updated = client.put(
            "/api/settings",
            json={"generation_timeout_seconds": 301, "download_timeout_seconds": 31},
        )
        assert updated.status_code == 200
        assert updated.json()["generation_timeout_seconds"] == 301
        assert updated.json()["download_timeout_seconds"] == 31
        assert app.state.engine.settings.generation_timeout_seconds == 301
        assert app.state.engine.settings.download_timeout_seconds == 31


def test_open_folder_accepts_only_safe_builtin_folders(tmp_path: Path, monkeypatch) -> None:
    opened: list[Path] = []

    def fake_startfile(path) -> None:
        opened.append(Path(path))

    monkeypatch.setattr("backend.api.open_folder_on_windows", fake_startfile)
    app, _ = make_client(tmp_path)
    with TestClient(app) as client:
        allowed = client.post("/api/folders/open", json={"kind": "logs"})
        assert allowed.status_code == 204
        assert opened == [tmp_path / "logs"]

        rejected = client.post("/api/folders/open", json={"kind": "F:/音乐"})
        assert rejected.status_code == 422


def test_login_browser_open_status_and_close(tmp_path: Path, monkeypatch) -> None:
    class FakeSession:
        def __init__(self) -> None:
            self.started = 0
            self.cleaned = 0

        async def start(self):
            self.started += 1
            return self

        async def cleanup(self):
            self.cleaned += 1

    session = FakeSession()
    app, _ = make_client(tmp_path)
    monkeypatch.setattr(app.state.login_browser, "_session_factory", lambda account, settings: session)

    with TestClient(app) as client:
        account = client.post("/api/accounts", json=account_payload(tmp_path)).json()
        opened = client.post(f"/api/accounts/{account['id']}/browser/open")
        reused = client.post(f"/api/accounts/{account['id']}/browser/open")
        current = client.get("/api/browser/current")

        assert opened.status_code == reused.status_code == 202
        assert current.json()["account_id"] == account["id"]
        assert session.started == 1

        closed = client.post("/api/browser/close")
        assert closed.status_code == 204
        assert session.cleaned == 1
        assert client.get("/api/browser/current").json() is None


def test_websocket_receives_recent_events(tmp_path: Path) -> None:
    app, _ = make_client(tmp_path, stop_after=1)
    write_song(tmp_path, "01_first")
    with TestClient(app) as client:
        account = client.post("/api/accounts", json=account_payload(tmp_path)).json()
        with client.websocket_connect("/ws") as websocket:
            initial = websocket.receive_json()
            assert initial["type"] == "ready"
            client.post(
                "/api/runs",
                json={
                    "account_id": account["id"],
                    "song_files": ["01_first.md"],
                    "day": "2026-09-17",
                    "fresh_run": True,
                },
            )
            types = []
            for _ in range(30):
                event = websocket.receive_json()
                types.append(event["type"])
                if event["type"] == "status" and event["data"]["status"] in {"stopped", "completed", "failed"}:
                    break
            assert "log" in types
            assert "status" in types
