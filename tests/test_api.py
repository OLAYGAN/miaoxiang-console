from pathlib import Path
from datetime import date
import json
import shutil
import time

import pytest
from fastapi.testclient import TestClient

from backend.api import create_app
from backend.api import build_upload_lyrics
from backend.api import build_upload_items
from backend.config import RuntimePaths
from backend.lyrics import parse_lyrics
from backend.models import AccountConfig, ConsoleSettings, SongRecord
from tests.test_ai_lyrics import make_song


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
    directory = tmp_path / "lyrics" / "2026-09-17"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{name}.md"
    lyrics = "夜色像一台缓慢转动的引擎\n穿过城市也穿过我的呼吸\n" + "旧灯光写下未完成的旋律\n" * 20
    style = "男声摇滚，粗粝低音，鼓点密集，副歌开阔，带有都市夜行感和少量电子质感。整体情绪从压抑推进到明亮，尾奏保留城市噪声和模拟合成器余韵。"
    path.write_text(
        f"# 歌名：《{name}》\n\n## 歌词\n《{name}》\n{lyrics}\n[End]\n\n## 歌曲风格\n{style}\n",
        encoding="utf-8",
    )
    return path


def write_duration_mp3(path: Path, seconds: float) -> Path:
    frame = bytes([0xFF, 0xE3, 0x18, 0x00]) + b"\x00" * 68
    path.write_bytes(frame * round(seconds / 0.072))
    return path


def make_client(tmp_path: Path, stop_after: int | None = None):
    holder: dict = {"models": [], "singers": []}

    def factory(account, settings):
        holder["models"].append(account.model_name)
        holder["singers"].append(account.singer_name)
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
        lyric_templates_file=tmp_path / "data" / "lyric_templates.json",
        pipeline_state_file=tmp_path / "data" / "pipeline_state.json",
        pipeline_queue_state_file=tmp_path / "data" / "pipeline_queue_state.json",
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

        created = client.post("/api/accounts", json=account_payload(tmp_path, port=19222))
        assert created.status_code == 201
        account = created.json()

        conflict = client.post("/api/accounts", json=account_payload(tmp_path, port=19223))
        assert conflict.status_code == 409
        assert "名称" in conflict.json()["detail"]

        source_profile = Path(account["chrome_profile_dir"])
        source_profile.mkdir(parents=True, exist_ok=True)
        (source_profile / "Local State").write_text("{}", encoding="utf-8")
        (source_profile / "Default").mkdir()
        (source_profile / "Default" / "Preferences").write_text("{}", encoding="utf-8")

        copied = client.post(f"/api/accounts/{account['id']}/copy", json={"account_name": "账号02"})
        assert copied.status_code == 200
        assert copied.json()["chrome_debug_port"] != 19222
        assert Path(copied.json()["chrome_profile_dir"]) != source_profile
        assert (Path(copied.json()["chrome_profile_dir"]) / "Default" / "Preferences").is_file()

        deleted = client.delete(f"/api/accounts/{account['id']}")
        assert deleted.status_code == 204
        assert client.get(f"/api/accounts/{account['id']}").status_code == 404


def test_account_directories_are_created_automatically(tmp_path: Path) -> None:
    app, _ = make_client(tmp_path)
    with TestClient(app) as client:
        payload = account_payload(tmp_path)
        account = client.post("/api/accounts", json=payload).json()

        day = date.today().isoformat()
        expected = [
            Path(payload["lyric_dir"]) / day,
            Path(payload["output_dir"]) / day,
            Path(payload["download_dir"]) / day,
            Path(payload["chrome_profile_dir"]),
        ]
        assert all(path.is_dir() for path in expected)

        client.get(f"/api/accounts/{account['id']}/songs?day=2026-09-17")
        assert (Path(payload["lyric_dir"]) / "2026-09-17").is_dir()


def test_account_root_folder_picker_returns_absolute_path(tmp_path: Path, monkeypatch) -> None:
    app, _ = make_client(tmp_path)

    def fake_picker(initial_dir: str | None = None) -> str:
        assert initial_dir is not None
        return str(tmp_path / "音乐库")

    monkeypatch.setattr("backend.api.pick_account_root_folder", fake_picker)
    with TestClient(app) as client:
        response = client.post("/api/folders/pick-account-root")

        assert response.status_code == 200
        assert response.json() == {"path": str((tmp_path / "音乐库").resolve())}


def test_account_root_folder_picker_cancelled(tmp_path: Path, monkeypatch) -> None:
    app, _ = make_client(tmp_path)
    monkeypatch.setattr("backend.api.pick_account_root_folder", lambda initial_dir=None: "")

    with TestClient(app) as client:
        response = client.post("/api/folders/pick-account-root")

        assert response.status_code == 200
        assert response.json() == {"path": ""}


def test_new_account_gets_an_available_debug_port(tmp_path: Path) -> None:
    app, _ = make_client(tmp_path)
    with TestClient(app) as client:
        first = client.post("/api/accounts", json=account_payload(tmp_path, "账号01"))
        assert first.status_code == 201

        suggested = client.get("/api/available-port").json()
        assert 1024 <= suggested["chrome_debug_port"] <= 65535
        assert suggested["chrome_debug_port"] != 9222

        duplicate = account_payload(tmp_path, "账号02")
        duplicate["chrome_debug_port"] = 9222
        created = client.post("/api/accounts", json=duplicate).json()
        assert created["chrome_debug_port"] != 9222


def test_copy_account_requires_source_chrome_directory(tmp_path: Path) -> None:
    app, _ = make_client(tmp_path)
    with TestClient(app) as client:
        account = client.post("/api/accounts", json=account_payload(tmp_path)).json()
        shutil.rmtree(Path(account["chrome_profile_dir"]))

        response = client.post(f"/api/accounts/{account['id']}/copy", json={"account_name": "账号副本"})

        assert response.status_code == 422
        assert "Chrome 用户目录不存在" in response.json()["detail"]


def test_delete_account_can_remove_bound_chrome_profile(tmp_path: Path) -> None:
    app, _ = make_client(tmp_path)
    with TestClient(app) as client:
        payload = account_payload(tmp_path)
        account = client.post("/api/accounts", json=payload).json()
        profile = Path(payload["chrome_profile_dir"])
        profile.mkdir(parents=True, exist_ok=True)
        (profile / "Local State").write_text("{}", encoding="utf-8")
        (profile / "Default").mkdir()

        response = client.delete(f"/api/accounts/{account['id']}?delete_chrome=true")

        assert response.status_code == 204
        assert not profile.exists()
        assert client.get(f"/api/accounts/{account['id']}").status_code == 404


def test_delete_account_rejects_non_chrome_directory(tmp_path: Path) -> None:
    app, _ = make_client(tmp_path)
    with TestClient(app) as client:
        payload = account_payload(tmp_path)
        account = client.post("/api/accounts", json=payload).json()
        profile = Path(payload["chrome_profile_dir"])
        profile.mkdir(parents=True, exist_ok=True)
        (profile / "普通文件.txt").write_text("keep", encoding="utf-8")

        response = client.delete(f"/api/accounts/{account['id']}?delete_chrome=true")

        assert response.status_code == 422
        assert "不像 Chrome 用户数据目录" in response.json()["detail"]
        assert profile.exists()
        assert client.get(f"/api/accounts/{account['id']}").status_code == 200


def test_upload_batch_listing_reads_output_directory(tmp_path: Path) -> None:
    app, _ = make_client(tmp_path)
    with TestClient(app) as client:
        account = client.post("/api/accounts", json=account_payload(tmp_path)).json()
        output = tmp_path / "output" / "2026-09-18"
        output.mkdir(parents=True, exist_ok=True)
        for name in ("第一首.mp3", "第二首.mp3"):
            write_duration_mp3(output / name, 61.0)
        (output / "invalid.txt").write_text("not audio", encoding="utf-8")
        (output / ".uploaded.json").write_text(
            json.dumps([str((output / "第一首.mp3").resolve())]),
            encoding="utf-8",
        )

        response = client.get(f"/api/accounts/{account['id']}/uploads?day=2026-09-18")

        assert response.status_code == 200
        body = response.json()
        assert body["ready"] is True
        assert body["batch_size"] == 10
        assert [item["file_name"] for item in body["files"]] == ["第二首.mp3"]
        assert [item["file_name"] for item in body["uploaded_files"]] == ["第一首.mp3"]
        assert all(item["size"] > 0 for item in body["files"])


def test_upload_listing_and_items_skip_music_shorter_than_sixty_seconds(
    tmp_path: Path,
) -> None:
    app, _ = make_client(tmp_path)
    with TestClient(app) as client:
        account = client.post("/api/accounts", json=account_payload(tmp_path)).json()
        output = Path(account["output_dir"]) / "2026-09-18"
        output.mkdir(parents=True, exist_ok=True)
        write_duration_mp3(output / "短歌.mp3", 59.0)
        write_duration_mp3(output / "长歌.mp3", 61.0)

        listing = client.get(f"/api/accounts/{account['id']}/uploads?day=2026-09-18")

        assert listing.status_code == 200
        assert [item["file_name"] for item in listing.json()["files"]] == ["长歌.mp3"]

        lyric_day = Path(account["lyric_dir"]) / "2026-09-18"
        lyric_day.mkdir(parents=True, exist_ok=True)
        for title in ("短歌", "长歌"):
            lyric_file = write_song(tmp_path, title)
            lyric_file.replace(lyric_day / lyric_file.name)
        items = build_upload_items(AccountConfig.model_validate(account), "2026-09-18")

        assert [item["title"] for item in items] == ["长歌"]


def test_upload_reset_removes_only_selected_manifest_entries(tmp_path: Path) -> None:
    app, _ = make_client(tmp_path)
    with TestClient(app) as client:
        account = client.post("/api/accounts", json=account_payload(tmp_path)).json()
        output = tmp_path / "output" / "2026-09-18"
        output.mkdir(parents=True, exist_ok=True)
        first = output / "第一首.mp3"
        second = output / "第二首.mp3"
        first.write_bytes(b"audio")
        second.write_bytes(b"audio")
        manifest = output / ".uploaded.json"
        manifest.write_text(
            json.dumps([str(first.resolve()), str(second.resolve())]),
            encoding="utf-8",
        )

        response = client.post(
            f"/api/accounts/{account['id']}/uploads/reset?day=2026-09-18",
            json={"file_names": ["第一首.mp3"]},
        )

        assert response.status_code == 200
        assert response.json()["removed"] == ["第一首.mp3"]
        assert json.loads(manifest.read_text(encoding="utf-8")) == [str(second.resolve())]


def test_upload_lyrics_are_cleaned_to_plain_multiline_text() -> None:
    source = (
        "歌名：《新课本》\n\n"
        "[主歌1][成人独唱，木吉他，3 bars]\n"
        "油墨 还 没 散尽\n"
        "(轻声，带一点气声)\n"
        "[副歌1][鼓点，4 bars]\n"
        "新课本 新课本\n"
        "[End]"
    )

    result = build_upload_lyrics(source)

    assert result == "油墨还没散尽\n新课本新课本"


def test_start_upload_requires_account_query_parameter(tmp_path: Path) -> None:
    app, _ = make_client(tmp_path)
    with TestClient(app) as client:
        missing = client.post("/api/uploads/runs?day=2026-09-18")
        assert missing.status_code == 422

        missing_account = client.post("/api/uploads/runs?day=2026-09-18", json={})
        assert missing_account.status_code in {404, 422}


def test_start_upload_filters_selected_tracks(tmp_path: Path, monkeypatch) -> None:
    app, _ = make_client(tmp_path)
    captured = {}

    def fake_start(account, items, day):
        captured.update({"account": account, "items": items, "day": day})
        return {
            "status": "running", "step": "starting", "day": day,
            "account_id": account.id, "account_name": account.account_name,
            "total": len(items), "processed": 0,
            "verification_requested": False, "error": None,
        }

    monkeypatch.setattr(app.state.engine, "start_upload", fake_start)
    with TestClient(app) as client:
        account = client.post("/api/accounts", json=account_payload(tmp_path)).json()
        selected_song = write_song(tmp_path, "01_selected")
        other_song = write_song(tmp_path, "02_other")
        output = tmp_path / "output" / "2026-09-17"
        output.mkdir(parents=True, exist_ok=True)
        for lyric_path in (selected_song, other_song):
            parsed = parse_lyrics(lyric_path.read_text(encoding="utf-8"))
            write_duration_mp3(output / f"{parsed.song_name}.mp3", 61.0)

        response = client.post(
            f"/api/uploads/runs?account_id={account['id']}&day=2026-09-17",
            json={"file_names": ["01_selected.mp3"], "real_name": "龙英"},
        )

        assert response.status_code == 202
        assert [item["title"] for item in captured["items"]] == ["01_selected"]
        assert all(item["ai_created"] is True for item in captured["items"])
        assert all(item["real_name"] == "龙英" for item in captured["items"])


def test_start_upload_can_disable_ai_creation(tmp_path: Path, monkeypatch) -> None:
    app, _ = make_client(tmp_path)
    captured = {}

    def fake_start(account, items, day):
        captured.update({"items": items, "day": day})
        return {
            "status": "running", "step": "starting", "day": day,
            "account_id": account.id, "account_name": account.account_name,
            "total": len(items), "processed": 0,
            "verification_requested": False, "error": None,
        }

    monkeypatch.setattr(app.state.engine, "start_upload", fake_start)
    with TestClient(app) as client:
        account = client.post("/api/accounts", json=account_payload(tmp_path)).json()
        song = write_song(tmp_path, "01_selected")
        output = tmp_path / "output" / "2026-09-17"
        output.mkdir(parents=True)
        parsed = parse_lyrics(song.read_text(encoding="utf-8"))
        write_duration_mp3(output / f"{parsed.song_name}.mp3", 61.0)

        response = client.post(
            f"/api/uploads/runs?account_id={account['id']}&day=2026-09-17",
            json={"file_names": ["01_selected.mp3"], "ai_created": False, "real_name": "李四"},
        )

        assert response.status_code == 202
        assert all(item["ai_created"] is False for item in captured["items"])


def test_start_upload_uses_account_real_name_when_request_omits_it(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app, _ = make_client(tmp_path)
    captured: dict = {}

    def fake_start(account, items, day):
        captured.update({"items": items})
        return {
            "status": "running", "step": "starting", "day": day,
            "account_id": account.id, "account_name": account.account_name,
            "total": len(items), "processed": 0,
            "verification_requested": False, "error": None,
        }

    monkeypatch.setattr(app.state.engine, "start_upload", fake_start)
    with TestClient(app) as client:
        payload = account_payload(tmp_path)
        payload["upload_real_name"] = "账号配置姓名"
        account = client.post("/api/accounts", json=payload).json()
        song = write_song(tmp_path, "01_selected")
        output = tmp_path / "output" / "2026-09-17"
        output.mkdir(parents=True)
        parsed = parse_lyrics(song.read_text(encoding="utf-8"))
        write_duration_mp3(output / f"{parsed.song_name}.mp3", 61.0)

        response = client.post(
            f"/api/uploads/runs?account_id={account['id']}&day=2026-09-17",
            json={"file_names": ["01_selected.mp3"]},
        )

        assert response.status_code == 202
        assert all(item["real_name"] == "账号配置姓名" for item in captured["items"])


def test_start_upload_allows_blank_real_name(tmp_path: Path, monkeypatch) -> None:
    app, _ = make_client(tmp_path)
    captured: dict = {}

    def fake_start(account, items, day):
        captured.update({"items": items, "day": day})
        return {
            "status": "running", "step": "starting", "day": day,
            "account_id": account.id, "account_name": account.account_name,
            "total": len(items), "processed": 0,
            "verification_requested": False, "error": None,
        }

    monkeypatch.setattr(app.state.engine, "start_upload", fake_start)
    with TestClient(app) as client:
        payload = account_payload(tmp_path)
        payload["upload_real_name"] = ""
        account = client.post("/api/accounts", json=payload).json()
        song = write_song(tmp_path, "01_selected")
        output = tmp_path / "output" / "2026-09-17"
        output.mkdir(parents=True)
        parsed = parse_lyrics(song.read_text(encoding="utf-8"))
        write_duration_mp3(output / f"{parsed.song_name}.mp3", 61.0)

        response = client.post(
            f"/api/uploads/runs?account_id={account['id']}&day=2026-09-17",
            json={"file_names": ["01_selected.mp3"], "real_name": ""},
        )

        assert response.status_code == 202
        assert all(item["real_name"] == "" for item in captured["items"])


def test_start_upload_can_enable_noncompliant_replacement(tmp_path: Path, monkeypatch) -> None:
    app, _ = make_client(tmp_path)
    captured: dict = {}

    def fake_start(account, items, day, **kwargs):
        captured.update({"items": items, "day": day, "kwargs": kwargs})
        return {
            "status": "running", "step": "starting", "day": day,
            "account_id": account.id, "account_name": account.account_name,
            "total": len(items), "processed": 0,
            "verification_requested": False, "error": None,
        }

    monkeypatch.setattr(app.state.engine, "start_upload", fake_start)
    with TestClient(app) as client:
        account = client.post("/api/accounts", json=account_payload(tmp_path)).json()
        song = write_song(tmp_path, "01_selected")
        output = tmp_path / "output" / "2026-09-17"
        output.mkdir(parents=True)
        parsed = parse_lyrics(song.read_text(encoding="utf-8"))
        write_duration_mp3(output / f"{parsed.song_name}.mp3", 61.0)

        response = client.post(
            f"/api/uploads/runs?account_id={account['id']}&day=2026-09-17",
            json={
                "file_names": ["01_selected.mp3"],
                "auto_replace_noncompliant": True,
            },
        )

        assert response.status_code == 202
        assert captured["kwargs"] == {"auto_replace_noncompliant": True}


def test_retry_rejected_upload_regenerates_pending_songs(tmp_path: Path, monkeypatch) -> None:
    app, _ = make_client(tmp_path)
    captured: dict = {}

    def fake_start(account, items, lyric_files, day, **kwargs):
        captured.update({
            "items": items,
            "lyric_files": lyric_files,
            "day": day,
            "kwargs": kwargs,
        })
        return {
            "status": "running", "step": "starting", "day": day,
            "account_id": account.id, "account_name": account.account_name,
            "total": len(items), "processed": 0,
            "verification_requested": False, "error": None,
        }

    monkeypatch.setattr(app.state.engine, "start_regeneration_upload", fake_start)
    with TestClient(app) as client:
        account = client.post("/api/accounts", json=account_payload(tmp_path)).json()
        song = write_song(tmp_path, "01_selected")
        parsed = parse_lyrics(song.read_text(encoding="utf-8"))
        output = tmp_path / "output" / "2026-09-17"
        output.mkdir(parents=True)
        output_path = output / f"{parsed.song_name}.mp3"
        write_duration_mp3(output_path, 61.0)
        listing = client.get(
            f"/api/accounts/{account['id']}/uploads?day=2026-09-17"
        ).json()
        response = client.post(
            f"/api/uploads/runs/retry-rejected?account_id={account['id']}&day=2026-09-17",
            json={
                "ai_created": True,
                "model_name": "Sway v5.5",
                "singer_name": "小岩",
            },
        )

        assert listing["files"][0]["file_name"] == output_path.name
        assert response.status_code == 202
        assert [item["title"] for item in captured["items"]] == [parsed.song_name]
        assert captured["lyric_files"] == [song]
        assert captured["kwargs"]["model_name"] == "Sway v5.5"
        assert captured["kwargs"]["singer_name"] == "小岩"


def test_lyric_template_can_move_between_accounts(tmp_path: Path) -> None:
    app, _ = make_client(tmp_path)
    with TestClient(app) as client:
        first = client.post("/api/accounts", json=account_payload(tmp_path, "账号01", 19222)).json()
        second_payload = account_payload(tmp_path, "账号02", 19223)
        second_payload["lyric_dir"] = str(tmp_path / "lyrics02")
        second_payload["output_dir"] = str(tmp_path / "output02")
        second_payload["download_dir"] = str(tmp_path / "downloads02")
        second = client.post("/api/accounts", json=second_payload).json()

        payload = {
            "name": "可迁移模板",
            "lyric_tone": "温暖叙事",
            "song_style": "pop rock",
            "themes": ["成长"],
            "generation_count": 2,
        }
        template = client.post(
            f"/api/accounts/{first['id']}/lyric/templates",
            json=payload,
        ).json()

        moved = client.put(
            f"/api/accounts/{second['id']}/lyric/templates/{template['id']}",
            json=payload,
        )

        assert moved.status_code == 200
        assert moved.json()["account_id"] == second["id"]
        assert [item["id"] for item in client.get(f"/api/accounts/{first['id']}/lyric/templates").json()["templates"]] == []
        assert [item["id"] for item in client.get(f"/api/accounts/{second['id']}/lyric/templates").json()["templates"]] == [template["id"]]


def test_pipeline_endpoints_use_existing_account_and_template(tmp_path: Path, monkeypatch) -> None:
    from backend.models import PipelineSnapshot

    app, _ = make_client(tmp_path)
    captured: dict = {}

    def fake_start(account, template, *, day, **kwargs):
        captured.update({
            "account": account,
            "template": template,
            "day": day,
            "pause": kwargs["pause_before_upload"],
            "ai_created": kwargs["ai_created"],
            "real_name": kwargs["real_name"],
            "model_name": kwargs["model_name"],
            "singer_name": kwargs["singer_name"],
        })
        snapshot = PipelineSnapshot(
            account_id=account.id,
            account_name=account.account_name,
            template_id=template.id,
            template_name=template.name,
            day=day,
            status="running",
            stage="lyrics",
        )
        app.state.pipeline_engine.current = snapshot
        return snapshot

    def fake_resume():
        snapshot = app.state.pipeline_engine.current
        assert snapshot is not None
        snapshot.status = "running"
        snapshot.stage = "upload"
        return snapshot

    async def fake_stop():
        snapshot = app.state.pipeline_engine.current
        assert snapshot is not None
        snapshot.status = "stopped"
        return snapshot

    monkeypatch.setattr(app.state.pipeline_engine, "start", fake_start)
    monkeypatch.setattr(app.state.pipeline_engine, "resume", fake_resume)
    monkeypatch.setattr(app.state.pipeline_engine, "stop", fake_stop)

    with TestClient(app) as client:
        account = client.post("/api/accounts", json=account_payload(tmp_path)).json()
        template = client.post(
            f"/api/accounts/{account['id']}/lyric/templates",
            json={
                "name": "流水线模板",
                "lyric_tone": "温暖叙事，有具体画面",
                "song_style": "pop rock",
                "themes": ["成长"],
                "generation_count": 2,
            },
        ).json()

        started = client.post(
            "/api/pipeline/runs",
            json={
                "account_id": account["id"],
                "template_id": template["id"],
                "day": "2026-09-19",
                "pause_before_upload": True,
                "ai_created": False,
                "real_name": "李四",
                "model_name": "Sway v5.5",
                "singer_name": "老岩",
            },
        )

        assert started.status_code == 202
        assert captured["day"] == "2026-09-19"
        assert captured["pause"] is True
        assert captured["ai_created"] is False
        assert captured["real_name"] == "李四"
        assert captured["model_name"] == "Sway v5.5"
        assert captured["singer_name"] == "老岩"
        assert client.get("/api/pipeline/runs/current").json()["status"] == "running"
        assert client.get("/api/pipeline/runs/current?day=2026-09-20").json() is None
        assert client.get(f"/api/pipeline/runs/current?account_id={account['id']}").json()["status"] == "running"
        assert client.get("/api/pipeline/runs/current?account_id=not-this-account").json() is None
        assert client.post("/api/pipeline/runs/resume").json()["stage"] == "upload"
        assert client.post("/api/pipeline/runs/stop").json()["status"] == "stopped"


def test_pipeline_queue_endpoint_runs_selected_accounts_in_order(tmp_path: Path, monkeypatch) -> None:
    from backend.models import PipelineSnapshot

    app, _ = make_client(tmp_path)
    started: list[str] = []
    captured_models: list[str] = []

    def fake_start(account, template, *, day, **kwargs):
        started.append(account.account_name)
        captured_models.append(kwargs["model_name"])
        snapshot = PipelineSnapshot(
            account_id=account.id,
            account_name=account.account_name,
            template_id=template.id,
            template_name=template.name,
            day=day,
            status="completed",
            stage="report",
            model_name=kwargs["model_name"],
        )
        app.state.pipeline_engine.current = snapshot
        return snapshot

    async def fake_wait():
        return app.state.pipeline_engine.current

    monkeypatch.setattr(app.state.pipeline_engine, "start", fake_start)
    monkeypatch.setattr(app.state.pipeline_engine, "wait", fake_wait)

    with TestClient(app) as client:
        first = client.post("/api/accounts", json=account_payload(tmp_path, "账号01", 9222)).json()
        second_payload = account_payload(tmp_path, "账号02", 9223)
        second_payload["chrome_profile_dir"] = str(tmp_path / "chrome" / "账号02")
        second_payload["lyric_dir"] = str(tmp_path / "lyrics02")
        second_payload["output_dir"] = str(tmp_path / "output02")
        second_payload["download_dir"] = str(tmp_path / "downloads02")
        second = client.post("/api/accounts", json=second_payload).json()
        first_template = client.post(
            f"/api/accounts/{first['id']}/lyric/templates",
            json={
                "name": "模板一",
                "lyric_tone": "温暖叙事",
                "song_style": "pop",
                "themes": ["成长"],
                "generation_count": 1,
            },
        ).json()
        second_template = client.post(
            f"/api/accounts/{second['id']}/lyric/templates",
            json={
                "name": "模板二",
                "lyric_tone": "温暖叙事",
                "song_style": "rock",
                "themes": ["成长"],
                "generation_count": 2,
            },
        ).json()

        options = client.get("/api/pipeline/queue/options").json()
        assert [item["account_name"] for item in options["accounts"]] == ["账号01", "账号02"]

        response = client.post(
            "/api/pipeline/queue/runs",
            json={
                "day": "2026-09-21",
                "items": [
                    {"account_id": first["id"], "template_id": first_template["id"]},
                    {"account_id": second["id"], "template_id": second_template["id"]},
                ],
                "real_name": "",
                "model_name": "TemPolor v4.1a",
            },
        )

        assert response.status_code == 202
        queue = response.json()
        assert [item["account_name"] for item in queue["items"]] == ["账号01", "账号02"]
        assert queue["model_name"] == "TemPolor v4.1a"

        finished = None
        for _ in range(30):
            finished = client.get("/api/pipeline/queue/runs/current?day=2026-09-21").json()
            if finished and finished["status"] in {"completed", "failed", "partial_failed", "stopped"}:
                break
            time.sleep(0.02)
        assert started == ["账号01", "账号02"]
        assert captured_models == ["TemPolor v4.1a", "TemPolor v4.1a"]
        assert finished is not None
        assert finished["status"] == "completed"
        assert [item["status"] for item in finished["items"]] == ["completed", "completed"]
        current = client.get("/api/pipeline/queue/runs/current?day=2026-09-21").json()
        assert current["status"] == "completed"


def test_pipeline_endpoint_runs_orchestrated_stages(tmp_path: Path, monkeypatch) -> None:
    app, _ = make_client(tmp_path)

    async def generate_lyrics(template, count):
        from backend.models import LyricData
        return [LyricData(song_name=f"第{index}首", lyrics="风 把 灯光 吹成 街", style="s" * 60) for index in range(count)]

    async def save_lyrics(account, day, songs):
        return [
            {"song_name": song.song_name, "file_name": f"{index + 1:02d}_{song.song_name}.md", "path": str(tmp_path / f"{index}.md")}
            for index, song in enumerate(songs)
        ]

    async def run_generation(account, day, files):
        return {
            path.name: {"status": "成功", "output_path": str(tmp_path / f"{path.stem}.mp3")}
            for path in files
        }

    async def run_upload(account, day, files, ai_created, real_name, auto_replace_noncompliant):
        return {"status": "completed", "files": files}

    monkeypatch.setattr(app.state.pipeline_engine, "_generate_lyrics", generate_lyrics)
    monkeypatch.setattr(app.state.pipeline_engine, "_save_lyrics", save_lyrics)
    monkeypatch.setattr(app.state.pipeline_engine, "_run_generation", run_generation)
    monkeypatch.setattr(app.state.pipeline_engine, "_run_upload", run_upload)

    with TestClient(app) as client:
        account = client.post("/api/accounts", json=account_payload(tmp_path)).json()
        template = client.post(
            f"/api/accounts/{account['id']}/lyric/templates",
            json={
                "name": "流水线集成模板",
                "lyric_tone": "温暖叙事，有具体画面",
                "song_style": "pop rock",
                "themes": ["成长"],
                "generation_count": 2,
            },
        ).json()
        response = client.post(
            "/api/pipeline/runs",
            json={
                "account_id": account["id"],
                "template_id": template["id"],
                "day": "2026-09-19",
                "auto_replace_noncompliant": True,
            },
        )

        assert response.status_code == 202
        assert app.state.pipeline_engine._task is not None
        for _ in range(30):
            client.get("/api/pipeline/runs/current")
            if app.state.pipeline_engine._task.done():
                break
            import time
            time.sleep(0.02)
        assert app.state.pipeline_engine._task.done()

        current = client.get("/api/pipeline/runs/current").json()
        assert current["status"] == "completed"
        assert current["auto_replace_noncompliant"] is True
        assert current["stage"] == "report"
        assert [song["upload_status"] for song in current["songs"]] == ["completed", "completed"]


def test_pipeline_generation_uses_two_retries_even_if_account_allows_more(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from backend.models import LyricData, TaskSnapshot

    app, _ = make_client(tmp_path)
    captured: list[int] = []

    async def generate_lyrics(template, count):
        return [
            LyricData(song_name=f"第{index}首", lyrics="风 把 灯光 吹成 街", style="s" * 60)
            for index in range(count)
        ]

    async def save_lyrics(account, day, songs):
        return [
            {"song_name": song.song_name, "file_name": f"{index + 1:02d}_{song.song_name}.md"}
            for index, song in enumerate(songs)
        ]

    def capture_generation_start(account, files, **kwargs):
        captured.append(account.max_retries)
        app.state.engine.current = TaskSnapshot(
            run_id="generation-run",
            account_id=account.id,
            account_name=account.account_name,
            status="completed",
            current_step="done",
        )
        return app.state.engine.current

    async def run_upload(account, day, files, ai_created, real_name, auto_replace_noncompliant):
        return {"status": "completed"}

    monkeypatch.setattr(app.state.pipeline_engine, "_generate_lyrics", generate_lyrics)
    monkeypatch.setattr(app.state.pipeline_engine, "_save_lyrics", save_lyrics)
    monkeypatch.setattr(app.state.pipeline_engine, "_run_upload", run_upload)
    monkeypatch.setattr(app.state.engine, "start", capture_generation_start)

    with TestClient(app) as client:
        payload = account_payload(tmp_path)
        payload["max_retries"] = 5
        account = client.post("/api/accounts", json=payload).json()
        template = client.post(
            f"/api/accounts/{account['id']}/lyric/templates",
            json={
                "name": "重试模板",
                "lyric_tone": "温暖叙事",
                "song_style": "pop",
                "themes": ["成长"],
                "generation_count": 1,
            },
        ).json()
        response = client.post(
            "/api/pipeline/runs",
            json={"account_id": account["id"], "template_id": template["id"], "day": "2026-09-29"},
        )
        assert response.status_code == 202

        for _ in range(30):
            current = client.get("/api/pipeline/runs/current").json()
            if current["status"] in {"completed", "failed", "stopped"}:
                break
            time.sleep(0.02)

        assert captured == [3]
        assert current["generation_max_retries"] == 2


def test_pipeline_generation_uses_selected_model(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from backend.models import LyricData, TaskSnapshot

    app, _ = make_client(tmp_path)
    captured: list[tuple[str, str]] = []

    async def generate_lyrics(template, count):
        return [
            LyricData(song_name=f"第{index}首", lyrics="风 把 灯光 吹成 街", style="s" * 60)
            for index in range(count)
        ]

    async def save_lyrics(account, day, songs):
        return [
            {"song_name": song.song_name, "file_name": f"{index + 1:02d}_{song.song_name}.md"}
            for index, song in enumerate(songs)
        ]

    def capture_generation_start(account, files, **kwargs):
        captured.append((kwargs.get("model_name"), kwargs.get("singer_name")))
        app.state.engine.current = TaskSnapshot(
            run_id="generation-run",
            account_id=account.id,
            account_name=account.account_name,
            status="completed",
            current_step="done",
        )
        return app.state.engine.current

    async def run_upload(account, day, files, ai_created, real_name, auto_replace_noncompliant):
        return {"status": "completed"}

    monkeypatch.setattr(app.state.pipeline_engine, "_generate_lyrics", generate_lyrics)
    monkeypatch.setattr(app.state.pipeline_engine, "_save_lyrics", save_lyrics)
    monkeypatch.setattr(app.state.pipeline_engine, "_run_upload", run_upload)
    monkeypatch.setattr(app.state.engine, "start", capture_generation_start)

    with TestClient(app) as client:
        account = client.post("/api/accounts", json=account_payload(tmp_path)).json()
        template = client.post(
            f"/api/accounts/{account['id']}/lyric/templates",
            json={
                "name": "模型模板",
                "lyric_tone": "温暖叙事",
                "song_style": "pop",
                "themes": ["成长"],
                "generation_count": 1,
            },
        ).json()
        response = client.post(
            "/api/pipeline/runs",
            json={
                "account_id": account["id"],
                "template_id": template["id"],
                "day": "2026-09-30",
                "model_name": "Sway v5.5",
                "singer_name": "老岩",
            },
        )
        assert response.status_code == 202

        current = None
        for _ in range(60):
            current = client.get("/api/pipeline/runs/current").json()
            if current["status"] in {"completed", "failed", "stopped"}:
                break
            time.sleep(0.02)

        assert captured == [("Sway v5.5", "老岩")]
        assert current["model_name"] == "Sway v5.5"


def test_pipeline_reuses_existing_lyrics_when_day_already_has_enough(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app, _ = make_client(tmp_path)

    async def reject_ai_generation(settings, *, template, count):
        raise AssertionError("当天歌词数量足够时不应再次调用 AI 作词")

    async def run_generation(account, day, files):
        return {
            path.name: {"status": "成功", "output_path": str(tmp_path / f"{path.stem}.mp3")}
            for path in files
        }

    async def run_upload(account, day, files, ai_created, real_name):
        return {"status": "completed", "files": files}

    monkeypatch.setattr("backend.api.generate_lyrics_with_ai", reject_ai_generation)
    monkeypatch.setattr(app.state.pipeline_engine, "_run_generation", run_generation)
    monkeypatch.setattr(app.state.pipeline_engine, "_run_upload", run_upload)

    with TestClient(app) as client:
        account = client.post("/api/accounts", json=account_payload(tmp_path)).json()
        write_song(tmp_path, "01_first")
        write_song(tmp_path, "02_second")
        template = client.post(
            f"/api/accounts/{account['id']}/lyric/templates",
            json={
                "name": "复用歌词模板",
                "lyric_tone": "温暖叙事",
                "song_style": "pop",
                "themes": ["成长"],
                "generation_count": 2,
            },
        ).json()

        response = client.post(
            "/api/pipeline/runs",
            json={"account_id": account["id"], "template_id": template["id"], "day": "2026-09-17"},
        )
        assert response.status_code == 202

        current = None
        for _ in range(30):
            current = client.get("/api/pipeline/runs/current").json()
            if current["status"] in {"completed", "failed", "stopped"}:
                break
            time.sleep(0.02)

        assert current["status"] == "completed"
        assert [song["lyric_file"] for song in current["songs"]] == [
            "01_first.md",
            "02_second.md",
        ]


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


def test_song_listing_detects_completion_from_output_files(tmp_path: Path) -> None:
    app, _ = make_client(tmp_path)
    with TestClient(app) as client:
        account = client.post("/api/accounts", json=account_payload(tmp_path)).json()
        write_song(tmp_path, "01_song")
        write_song(tmp_path, "02_song")
        write_song(tmp_path, "03_external")
        output = tmp_path / "output" / "2026-09-17"
        output.mkdir(parents=True, exist_ok=True)
        (output / "03_external.mp3").write_bytes(b"audio")

        app.state.run_state.mark(
            "2026-09-17",
            account["account_name"],
            SongRecord(
                file_name="01_song.md",
                status="成功",
                current_step="done",
                attempts=2,
                output_path=str(tmp_path / "output" / "2026-09-17" / "01_song.mp3"),
            ),
        )

        response = client.get(f"/api/accounts/{account['id']}/songs?day=2026-09-17")

        assert response.status_code == 200
        songs = {item["file_name"]: item for item in response.json()}
        assert songs["01_song.md"]["status"] == "pending"
        assert songs["02_song.md"]["status"] == "pending"
        assert songs["03_external.md"]["status"] == "success"
        assert songs["03_external.md"]["current_step"] == "done"
        assert songs["03_external.md"]["output_path"].endswith("03_external.mp3")


def test_start_requires_existing_account_and_songs(tmp_path: Path) -> None:
    app, _ = make_client(tmp_path)
    with TestClient(app) as client:
        missing = client.post("/api/runs", json={"account_id": "missing", "song_files": ["x.md"]})
        assert missing.status_code == 404

        account = client.post("/api/accounts", json=account_payload(tmp_path)).json()
        empty = client.post("/api/runs", json={"account_id": account["id"], "song_files": []})
        assert empty.status_code == 422


def test_start_uses_today_when_day_is_omitted(tmp_path: Path) -> None:
    app, holder = make_client(tmp_path, stop_after=1)
    write_song(tmp_path, "01_today")
    fixed_day = tmp_path / "lyrics" / "2026-09-17"
    today = tmp_path / "lyrics" / date.today().isoformat()
    if fixed_day != today and fixed_day.is_dir():
        fixed_day.rename(today)
    with TestClient(app) as client:
        account = client.post("/api/accounts", json=account_payload(tmp_path)).json()
        response = client.post(
            "/api/runs",
            json={
                "account_id": account["id"],
                "song_files": ["01_today.md"],
                "fresh_run": True,
            },
        )
        assert response.status_code == 202
        for _ in range(100):
            current = client.get("/api/runs/current").json()
            if current["status"] in {"stopped", "completed", "failed"}:
                break
            client.post("/api/runs/control", json={"action": "stop"})
        assert current["status"] == "stopped"
        assert holder["browser"].flow.processed == 1
        assert holder["models"] == ["自动"]


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
                "model_name": "Sway v5.5",
                "singer_name": "小岩",
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
        assert holder["models"] == ["Sway v5.5"]
        assert holder["singers"] == ["小岩"]


def test_run_allows_blank_sway_singer_choice(tmp_path: Path) -> None:
    app, holder = make_client(tmp_path, stop_after=1)
    write_song(tmp_path, "01_first")
    with TestClient(app) as client:
        account = client.post("/api/accounts", json=account_payload(tmp_path)).json()
        started = client.post(
            "/api/runs",
            json={
                "account_id": account["id"],
                "song_files": ["01_first.md"],
                "day": "2026-09-17",
                "fresh_run": True,
                "model_name": "Sway v5.5",
                "singer_name": "",
            },
        )

        assert started.status_code == 202
        for _ in range(100):
            current = client.get("/api/runs/current").json()
            if current["status"] == "stopped":
                break
            client.post("/api/runs/control", json={"action": "stop"})

        assert current["status"] == "stopped"
        assert holder["models"] == ["Sway v5.5"]
        assert holder["singers"] == [""]


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
            json={
                "generation_timeout_seconds": 301,
                "download_timeout_seconds": 31,
                "ai_api_base_url": "https://api.example.com/v1",
                "ai_api_key": "test-key",
                "ai_model": "lyric-model",
            },
        )
        assert updated.status_code == 200
        assert updated.json()["generation_timeout_seconds"] == 301
        assert updated.json()["download_timeout_seconds"] == 31
        assert app.state.engine.settings.generation_timeout_seconds == 301
        assert app.state.engine.settings.download_timeout_seconds == 31
        assert app.state.engine.settings.ai_api_base_url == "https://api.example.com/v1"
        assert app.state.engine.settings.ai_model == "lyric-model"
        assert app.state.engine.settings.ai_max_retries == 2

        prompt_updated = client.put(
            "/api/settings",
            json={"ai_system_prompt": "X" * 150},
        )
        assert prompt_updated.status_code == 200
        assert prompt_updated.json()["ai_system_prompt"] == "X" * 150


def test_ai_settings_connection(tmp_path: Path, monkeypatch) -> None:
    app, _ = make_client(tmp_path)

    async def fake_test(*, base_url, api_key, model):
        return {
            "ok": True,
            "model": model,
            "model_count": 3,
            "request": [base_url, api_key],
        }

    monkeypatch.setattr("backend.api.test_ai_api_connection", fake_test)
    with TestClient(app) as client:
        response = client.post(
            "/api/settings/ai/test",
            json={
                "ai_api_base_url": "https://api.example.com/v1",
                "ai_api_key": "test-key",
                "ai_model": "lyric-model",
            },
        )

        assert response.status_code == 200
        assert response.json()["model"] == "lyric-model"


def test_ai_lyric_templates_generate_and_save(tmp_path: Path, monkeypatch) -> None:
    app, _ = make_client(tmp_path)

    async def fake_generate(settings, *, template, count):
        assert template.name == "校园爱情"
        assert template.themes == ["爱情", "校园" * 20]
        assert count == 2
        return [make_song("没说出口"), make_song("最后一天")]

    async def fake_stream_generate(settings, *, template, count, on_progress):
        on_progress({
            "stage": "generating",
            "attempt": 1,
            "elapsed_seconds": 0.1,
            "expected_count": count,
            "content_chars": 128,
            "reasoning_chars": 32,
            "reasoning_available": True,
            "reasoning_excerpt": "Choosing campus imagery",
            "song_names": ["没说出口"],
            "message": "正在输出歌词",
        })
        return [make_song("没说出口"), make_song("最后一天")]

    monkeypatch.setattr("backend.api.generate_lyrics_with_ai", fake_generate)
    monkeypatch.setattr("backend.api.stream_lyrics_with_ai", fake_stream_generate)
    with TestClient(app) as client:
        client.put(
            "/api/settings",
            json={
                "ai_api_base_url": "https://api.example.com/v1",
                "ai_api_key": "test-key",
                "ai_model": "lyric-model",
            },
        )
        account = client.post("/api/accounts", json=account_payload(tmp_path)).json()

        template_payload = {
            "name": "校园爱情",
            "lyric_tone": "",
            "song_style": "短",
            "themes": ["爱情", "校园" * 20],
            "generation_count": 2,
        }
        created_template = client.post(
            f"/api/accounts/{account['id']}/lyric/templates",
            json=template_payload,
        )
        assert created_template.status_code == 201
        template_id = created_template.json()["id"]

        templates = client.get(f"/api/accounts/{account['id']}/lyric/templates").json()
        assert "songs" in templates["system_prompt"]
        assert [item["id"] for item in templates["templates"]] == [template_id]
        assert templates["templates"][0]["account_id"] == account["id"]

        generated = client.post(
            f"/api/accounts/{account['id']}/lyrics/generate",
            json={
                "template_id": template_id,
            },
        )
        assert generated.status_code == 200
        assert [song["song_name"] for song in generated.json()["songs"]] == ["没说出口", "最后一天"]

        streamed = client.post(
            f"/api/accounts/{account['id']}/lyrics/generate/stream",
            json={"template_id": template_id},
        )
        assert streamed.status_code == 200
        assert streamed.headers["content-type"].startswith("text/event-stream")
        assert "event: progress" in streamed.text
        assert "Choosing campus imagery" in streamed.text
        assert "event: done" in streamed.text
        assert "没说出口" in streamed.text

        other = client.post("/api/accounts", json=account_payload(tmp_path, "账号02", 9224)).json()
        wrong_account = client.post(
            f"/api/accounts/{other['id']}/lyrics/generate",
            json={"template_id": template_id},
        )
        assert wrong_account.status_code == 422
        assert "不属于该账号" in wrong_account.json()["detail"]

        saved = client.post(
            f"/api/accounts/{account['id']}/lyrics/save",
            json={"day": "2026-09-18", "songs": generated.json()["songs"]},
        )
        assert saved.status_code == 200
        saved_names = [item["file_name"] for item in saved.json()["saved"]]
        assert saved_names == ["01_没说出口.md", "02_最后一天.md"]
        for item in saved.json()["saved"]:
            parsed = parse_lyrics(Path(item["path"]).read_text(encoding="utf-8"))
            assert parsed.song_name in {"没说出口", "最后一天"}

        duplicate = client.post(
            f"/api/accounts/{account['id']}/lyrics/save",
            json={"day": "2026-09-18", "songs": generated.json()["songs"]},
        )
        assert duplicate.status_code == 422
        assert "歌名已存在" in duplicate.json()["detail"]


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
