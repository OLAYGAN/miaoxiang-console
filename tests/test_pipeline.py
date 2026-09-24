from pathlib import Path
import json

import pytest

from backend.events import EventBus
from backend.models import AccountConfig, LyricData, LyricTemplateConfig
from backend.pipeline import PipelineEngine
from backend.models import PipelineSongState, PipelineSnapshot
from backend.storage import PipelineStateRepository


def make_account(tmp_path: Path | None = None) -> AccountConfig:
    root = tmp_path or Path()
    return AccountConfig(
        account_name="账号01",
        chrome_profile_dir=root / "chrome" / "account",
        chrome_debug_port=9222,
        lyric_dir=root / "lyrics",
        output_dir=root / "output",
        download_dir=root / "downloads",
    )


def make_refresh_account(tmp_path: Path) -> AccountConfig:
    return make_account(tmp_path).model_copy(update={"id": "account-1"})


def make_template(count: int = 2) -> LyricTemplateConfig:
    return LyricTemplateConfig(
        account_id="account-1",
        name="模板01",
        lyric_tone="温暖叙事，有具体画面",
        song_style="pop rock",
        themes=["成长"],
        generation_count=count,
    )


async def callback_assert_not_called(*args, **kwargs):
    raise AssertionError("刷新状态不应执行流水线回调")


def make_pipeline_snapshot() -> PipelineSnapshot:
    return PipelineSnapshot(
        account_id="account-1",
        account_name="账号01",
        template_id="template-1",
        template_name="模板01",
        day="2026-09-19",
        pause_before_upload=True,
        songs=[
            PipelineSongState(
                song_name="第一首",
                lyric_file="01_第一首.md",
                lyrics_status="completed",
                generation_status="completed",
                output_path="output/第一首.mp3",
                upload_status="pending",
            )
        ],
    )


def test_pipeline_repository_round_trips_latest_snapshot(tmp_path: Path) -> None:
    repository = PipelineStateRepository(tmp_path / "pipeline_state.json")
    snapshot = make_pipeline_snapshot()

    repository.save(snapshot)
    restored = repository.get()

    assert restored == snapshot


def test_pipeline_engine_restores_waiting_run_and_marks_restarted_run_stopped(tmp_path: Path) -> None:
    from backend.events import EventBus

    path = tmp_path / "pipeline_state.json"
    repository = PipelineStateRepository(path)
    waiting = make_pipeline_snapshot().model_copy(update={"status": "waiting_user"})
    repository.save(waiting)

    async def callback(*args, **kwargs):
        raise AssertionError("不应执行回调")

    engine = PipelineEngine(
        state_repository=repository,
        event_bus=EventBus(),
        lyric_generator=callback,
        lyric_saver=callback,
        generation_runner=callback,
        upload_runner=callback,
    )
    assert engine.current == waiting

    running = waiting.model_copy(update={"status": "running"})
    repository.save(running)
    restarted = PipelineEngine(
        state_repository=repository,
        event_bus=EventBus(),
        lyric_generator=callback,
        lyric_saver=callback,
        generation_runner=callback,
        upload_runner=callback,
    )
    assert restarted.current.status == "stopped"
    assert restarted.current.error == "服务重启，流水线已中断"


@pytest.mark.asyncio
async def test_pipeline_refresh_syncs_completed_single_stage_upload(tmp_path: Path) -> None:
    account = make_refresh_account(tmp_path)
    day = "2026-09-20"
    lyric_dir = Path(account.lyric_dir) / day
    output_dir = Path(account.output_dir) / day
    lyric_dir.mkdir(parents=True)
    output_dir.mkdir(parents=True)
    (lyric_dir / "01_第一首.md").write_text("lyric", encoding="utf-8")
    output = output_dir / "第一首.mp3"
    output.write_bytes(b"audio")
    (output_dir / ".uploaded.json").write_text(
        json.dumps([str(output.resolve())]),
        encoding="utf-8",
    )

    snapshot = make_pipeline_snapshot().model_copy(
        update={
            "day": day,
            "status": "failed",
            "stage": "report",
            "songs": [
                PipelineSongState(
                    song_name="第一首",
                    lyric_file="01_第一首.md",
                    lyrics_status="completed",
                    generation_status="completed",
                    output_path=str(output),
                    upload_status="failed",
                )
            ],
        }
    )
    repository = PipelineStateRepository(tmp_path / "pipeline_state.json")
    repository.save(snapshot)

    async def callback(*args, **kwargs):
        raise AssertionError("刷新状态不应执行流水线回调")

    engine = PipelineEngine(
        state_repository=repository,
        event_bus=EventBus(),
        lyric_generator=callback,
        lyric_saver=callback,
        generation_runner=callback,
        upload_runner=callback,
    )
    refreshed = engine.refresh(account)

    assert refreshed is not None
    assert refreshed.status == "completed"
    assert refreshed.stage == "report"
    assert refreshed.songs[0].generation_status == "completed"
    assert refreshed.songs[0].upload_status == "completed"
    assert repository.get() == refreshed


@pytest.mark.asyncio
async def test_pipeline_upload_marks_only_platform_confirmed_songs(tmp_path: Path) -> None:
    first_output = tmp_path / "第一首.mp3"
    second_output = tmp_path / "第二首.mp3"

    async def run_upload(account, day, files, ai_created, real_name):
        return {
            "status": "completed",
            "uploaded_paths": [str(first_output.resolve())],
        }

    engine = PipelineEngine(
        state_repository=PipelineStateRepository(tmp_path / "pipeline_state.json"),
        event_bus=EventBus(),
        lyric_generator=lambda *args, **kwargs: None,
        lyric_saver=lambda *args, **kwargs: None,
        generation_runner=lambda *args, **kwargs: None,
        upload_runner=run_upload,
    )
    engine.current = PipelineSnapshot(
        account_id="account-1",
        account_name="账号01",
        template_id="template-1",
        template_name="模板01",
        day="2026-09-20",
        status="running",
        stage="upload",
        songs=[
            PipelineSongState(
                song_name="第一首",
                generation_status="completed",
                output_path=str(first_output),
            ),
            PipelineSongState(
                song_name="第二首",
                generation_status="completed",
                output_path=str(second_output),
            ),
        ],
    )

    await engine._execute_upload()

    assert engine.current.status == "completed"
    assert engine.current.songs[0].upload_status == "completed"
    assert engine.current.songs[0].upload_removed is False
    assert engine.current.songs[1].upload_removed is True


@pytest.mark.asyncio
async def test_pipeline_refresh_keeps_platform_removed_songs_completed(tmp_path: Path) -> None:
    account = make_refresh_account(tmp_path)
    day = "2026-09-20"
    lyric_dir = Path(account.lyric_dir) / day
    output_dir = Path(account.output_dir) / day
    lyric_dir.mkdir(parents=True)
    output_dir.mkdir(parents=True)
    songs = []
    for index, name in enumerate(["第一首", "第二首"], start=1):
        (lyric_dir / f"{index:02d}_{name}.md").write_text("lyric", encoding="utf-8")
        output = output_dir / f"{name}.mp3"
        output.write_bytes(b"audio")
        songs.append(PipelineSongState(
            song_name=name,
            lyric_file=f"{index:02d}_{name}.md",
            lyrics_status="completed",
            generation_status="completed",
            output_path=str(output),
            upload_status="completed" if index == 1 else "pending",
            upload_removed=index == 2,
        ))
    (output_dir / ".uploaded.json").write_text(
        json.dumps([str((output_dir / "第一首.mp3").resolve())]),
        encoding="utf-8",
    )
    repository = PipelineStateRepository(tmp_path / "pipeline_state.json")
    repository.save(PipelineSnapshot(
        account_id=account.id,
        account_name=account.account_name,
        template_id="template-1",
        template_name="模板01",
        day=day,
        status="completed",
        stage="report",
        songs=songs,
    ))
    engine = PipelineEngine(
        state_repository=repository,
        event_bus=EventBus(),
        lyric_generator=callback_assert_not_called,
        lyric_saver=callback_assert_not_called,
        generation_runner=callback_assert_not_called,
        upload_runner=callback_assert_not_called,
    )

    refreshed = engine.refresh(account)

    assert refreshed is not None
    assert refreshed.status == "completed"
    assert refreshed.songs[0].upload_status == "completed"
    assert refreshed.songs[1].upload_removed is True


@pytest.mark.asyncio
async def test_pipeline_runs_all_stages_automatically(tmp_path: Path) -> None:
    repository = PipelineStateRepository(tmp_path / "pipeline_state.json")
    calls: list[str] = []

    async def generate_lyrics(template, count):
        calls.append("lyrics")
        return [LyricData(song_name=f"第{index}首", lyrics="风 把 灯光 吹成 街", style="s" * 60) for index in range(count)]

    async def save_lyrics(account, day, songs):
        calls.append("save")
        return [
            {"song_name": song.song_name, "file_name": f"{index + 1:02d}_{song.song_name}.md", "path": str(tmp_path / f"{song.song_name}.md")}
            for index, song in enumerate(songs)
        ]

    async def run_generation(account, day, files):
        calls.append("generation")
        return {
            path.name: {"status": "成功", "output_path": str(tmp_path / f"{path.stem}.mp3")}
            for path in files
        }

    async def run_upload(account, day, files, ai_created, real_name):
        calls.append("upload")
        return {"status": "completed", "files": files}

    engine = PipelineEngine(
        state_repository=repository,
        event_bus=EventBus(),
        lyric_generator=generate_lyrics,
        lyric_saver=save_lyrics,
        generation_runner=run_generation,
        upload_runner=run_upload,
    )

    engine.start(make_account(), make_template(), day="2026-09-19")
    await engine._task

    assert calls == ["lyrics", "save", "generation", "upload"]
    assert engine.current.status == "completed"
    assert engine.current.stage == "report"
    assert [song.upload_status for song in engine.current.songs] == ["completed", "completed"]


@pytest.mark.asyncio
async def test_pipeline_can_pause_before_upload_and_resume(tmp_path: Path) -> None:
    repository = PipelineStateRepository(tmp_path / "pipeline_state.json")
    upload_count = 0

    async def generate_lyrics(template, count):
        return [LyricData(song_name="第一首", lyrics="风 把 灯光 吹成 街", style="s" * 60)]

    async def save_lyrics(account, day, songs):
        return [{"song_name": "第一首", "file_name": "01_第一首.md", "path": str(tmp_path / "01.md")}]

    async def run_generation(account, day, files):
        return {files[0].name: {"status": "成功", "output_path": str(tmp_path / "第一首.mp3")}}

    async def run_upload(account, day, files, ai_created, real_name):
        nonlocal upload_count
        upload_count += 1
        return {"status": "completed"}

    engine = PipelineEngine(
        state_repository=repository,
        event_bus=EventBus(),
        lyric_generator=generate_lyrics,
        lyric_saver=save_lyrics,
        generation_runner=run_generation,
        upload_runner=run_upload,
    )
    engine.start(make_account(), make_template(count=1), day="2026-09-19", pause_before_upload=True)
    await engine._task

    assert engine.current.status == "waiting_user"
    assert engine.current.stage == "pre_upload"
    assert upload_count == 0

    engine.resume()
    await engine._task

    assert upload_count == 1
    assert engine.current.status == "completed"


@pytest.mark.asyncio
async def test_pipeline_fails_when_no_downloadable_output(tmp_path: Path) -> None:
    repository = PipelineStateRepository(tmp_path / "pipeline_state.json")

    async def generate_lyrics(template, count):
        return [LyricData(song_name="第一首", lyrics="风 把 灯光 吹成 街", style="s" * 60)]

    async def save_lyrics(account, day, songs):
        return [{"song_name": "第一首", "file_name": "01_第一首.md", "path": str(tmp_path / "01.md")}]

    async def run_generation(account, day, files):
        return {files[0].name: {"status": "失败", "error": "生成失败"}}

    async def run_upload(account, day, files, ai_created, real_name):
        raise AssertionError("不应进入上传")

    engine = PipelineEngine(
        state_repository=repository,
        event_bus=EventBus(),
        lyric_generator=generate_lyrics,
        lyric_saver=save_lyrics,
        generation_runner=run_generation,
        upload_runner=run_upload,
    )
    engine.start(make_account(), make_template(count=1), day="2026-09-19")
    await engine._task

    assert engine.current.status == "failed"
    assert engine.current.stage == "report"
    assert engine.current.error == "没有可上传的成品歌曲"
