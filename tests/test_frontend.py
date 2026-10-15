from pathlib import Path
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
from contextlib import contextmanager
import json
import threading

import pytest
from playwright.async_api import async_playwright


@contextmanager
def serve_frontend():
    frontend_dir = Path(__file__).resolve().parent.parent / "frontend"

    class FrontendHandler(SimpleHTTPRequestHandler):
        def translate_path(self, path: str) -> str:
            parsed = urlsplit(path).path
            if parsed.startswith("/assets/"):
                path = "/" + parsed[len("/assets/"):]
            return super().translate_path(path)

    handler = lambda *args, **kwargs: FrontendHandler(*args, directory=frontend_dir, **kwargs)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/index.html"
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=5)


@pytest.mark.asyncio
async def test_editing_account_name_keeps_existing_directories() -> None:
    account = {
        "account_name": "艺",
        "chrome_profile_dir": r"F:\音乐\chrome\艺",
        "chrome_debug_port": 9224,
        "lyric_dir": r"F:\音乐\歌词\艺",
        "output_dir": r"F:\音乐\歌曲\艺",
        "download_dir": r"F:\音乐\下载\艺",
        "max_retries": 3,
        "generation_batch_size": 2,
        "upload_batch_size": 10,
        "upload_artist_name": "babycare",
        "upload_real_name": "",
        "song_interval_seconds": 5,
    }

    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(channel="chrome", headless=True)
            page = await browser.new_page()
            with serve_frontend() as base_url:
                await page.goto(base_url)
                await page.wait_for_selector("#account-form", state="attached")
                await page.evaluate(
                    """(account) => {
                    fillAccountForm(account);
                    state.accountEditorOpen = true;
                    state.view = "account";
                    renderView();
                    renderAccountEditor();
                    }""",
                    account,
                )
                await page.fill("#account-form [name='account_name']", "黄振艺")

                assert await page.input_value("#account-form [name='chrome_profile_dir']") == account["chrome_profile_dir"]
                assert await page.input_value("#account-form [name='lyric_dir']") == account["lyric_dir"]
                assert await page.input_value("#account-form [name='output_dir']") == account["output_dir"]
                assert await page.input_value("#account-form [name='download_dir']") == account["download_dir"]

            await browser.close()
    finally:
        pass


@pytest.mark.asyncio
async def test_partial_retry_keeps_previously_successful_song_states() -> None:
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(channel="chrome", headless=True)
            page = await browser.new_page()
            with serve_frontend() as base_url:
                await page.goto(base_url)
                await page.wait_for_selector("#song-table", state="attached")
                statuses = await page.evaluate(
                    """() => {
                    state.accountId = "account";
                    state.songs = ["one", "two", "three"].map((name) => ({
                        file_name: `${name}.md`,
                        valid: true,
                        song_name: name,
                        status: "pending",
                    }));
                    applyCurrentRun({
                        run_id: "first",
                        account_id: "account",
                        status: "failed",
                        songs: [
                            { file_name: "one.md", status: "success" },
                            { file_name: "two.md", status: "success" },
                            { file_name: "three.md", status: "failed" },
                        ],
                    }, { immediate: true });
                    applyCurrentRun({
                        run_id: "retry",
                        account_id: "account",
                        status: "running",
                        songs: [{ file_name: "three.md", status: "running" }],
                    });
                    return state.songs.map(songState);
                    }""",
                )

                assert statuses == ["success", "success", "running"]

            await browser.close()
    finally:
        pass


@pytest.mark.asyncio
async def test_clicking_song_row_toggles_selection() -> None:
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(channel="chrome", headless=True)
            page = await browser.new_page(viewport={"width": 1440, "height": 900})
            with serve_frontend() as base_url:
                await page.goto(base_url)
                await page.wait_for_selector("#song-table", state="attached")
                await page.evaluate(
                    """() => {
                    state.accountId = "account";
                    state.view = "task";
                    state.songs = [{
                        file_name: "pending.md",
                        valid: true,
                        song_name: "待处理歌曲",
                        status: "pending",
                    }];
                    state.selected = new Set();
                    renderView();
                    renderSongs();
                    }""",
                )

                row = page.locator(".song-row[data-file='pending.md']")
                await row.locator("span").first.click()
                selected = await page.evaluate(
                    "() => ({ checked: state.selected.has('pending.md'), className: document.querySelector('.song-row[data-file=\\'pending.md\\']').className })",
                )
                assert selected["checked"] is True
                assert "is-selected" in selected["className"]

                await row.locator("span").first.click()
                selected = await page.evaluate(
                    "() => ({ checked: state.selected.has('pending.md'), className: document.querySelector('.song-row[data-file=\\'pending.md\\']').className })",
                )
                assert selected["checked"] is False
                assert "is-selected" not in selected["className"]

            await browser.close()
    finally:
        pass


@pytest.mark.asyncio
async def test_download_failure_row_offers_lyrics_redownload() -> None:
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(channel="chrome", headless=True)
            page = await browser.new_page()
            captured: dict = {}

            async def handle_redownload(route) -> None:
                captured.update(route.request.post_data_json)
                await route.fulfill(
                    status=202,
                    content_type="application/json",
                    body=(
                        '{"run_id":"redownload","account_id":"account",'
                        '"account_name":"账号01","status":"running",'
                        '"current_step":"opening_browser",'
                        '"songs":[{"file_name":"failed.md","song_name":"失败歌曲",'
                        '"status":"running","current_step":"opening_browser",'
                        '"attempts":0}]}'
                    ),
                )

            await page.route("**/api/runs/redownload", handle_redownload)
            with serve_frontend() as base_url:
                await page.goto(base_url)
                await page.wait_for_selector("#song-table", state="attached")
                await page.evaluate("state.view = 'task'; renderView();")
                await page.evaluate(
                    """() => {
                    state.accountId = "account";
                    state.accounts = [{
                        id: "account",
                        account_name: "账号01",
                        lyric_dir: "E:\\\\music\\\\lyrics",
                    }];
                    document.getElementById("lyric-dir-input").value = "E:\\\\music\\\\lyrics";
                    state.songs = [
                        {
                            file_name: "failed.md",
                            valid: true,
                            song_name: "失败歌曲",
                            status: "下载失败",
                        },
                        {
                            file_name: "done.md",
                            valid: true,
                            song_name: "完成歌曲",
                            status: "success",
                        },
                        {
                            file_name: "export.md",
                            valid: true,
                            song_name: "导出失败歌曲",
                            status: "导出失败",
                        },
                    ];
                    renderSongs();
                    }""",
                )

                button = page.locator('[data-redownload="failed.md"]')
                assert await button.count() == 1
                assert await button.inner_text() == "重新下载"
                assert await page.locator('[data-redownload="done.md"]').count() == 0
                export_button = page.locator('[data-redownload="export.md"]')
                assert await export_button.count() == 1
                assert await export_button.inner_text() == "重新导出"
                await button.click()
                await page.wait_for_timeout(50)

                assert captured == {
                    "account_id": "account",
                    "file_name": "failed.md",
                    "day": await page.evaluate("todayValue()"),
                }

            await browser.close()
    finally:
        pass


@pytest.mark.asyncio
async def test_repair_all_button_sends_selected_accounts_serially() -> None:
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(channel="chrome", headless=True)
            page = await browser.new_page()
            captured: dict = {}

            async def handle_repair(route) -> None:
                captured.update(route.request.post_data_json)
                await route.fulfill(
                    status=202,
                    content_type="application/json",
                    body=(
                        '{"queue_id":"repair-queue","stage":"repair","day":"2026-10-15",'
                        '"status":"running","current_index":0,"concurrency":1,'
                        '"items":[{"account_id":"account","account_name":"账号01",'
                        '"status":"running","request":{},"result":null}]}'
                    ),
                )

            await page.route("**/api/multi-stage/repair/runs", handle_repair)
            with serve_frontend() as base_url:
                await page.goto(base_url)
                await page.wait_for_selector("#repair-run", state="attached")
                await page.evaluate("state.view = 'task'; renderView();")
                selected = await page.evaluate(
                    """() => {
                    state.accountId = "account";
                    state.accounts = [{
                        id: "account",
                        account_name: "账号01",
                        lyric_dir: "E:\\\\music\\\\lyrics",
                    }, {
                        id: "other",
                        account_name: "账号02",
                        lyric_dir: "E:\\\\music\\\\other",
                    }];
                    state.selectedTaskAccounts = new Set(["account", "other"]);
                    state.dashboardSongs = {
                        account: [
                            { file_name: "download.md", valid: true, song_name: "下载", status: "下载失败" },
                            { file_name: "export.md", valid: true, song_name: "导出", status: "导出失败" },
                            { file_name: "generate.md", valid: true, song_name: "生成", status: "生成失败" },
                        ],
                        other: [
                            { file_name: "success.md", valid: true, song_name: "成功", status: "success" },
                        ],
                    };
                    document.getElementById("lyric-dir-input").value = "E:\\\\music\\\\lyrics";
                    state.songs = [
                        { file_name: "download.md", valid: true, song_name: "下载", status: "下载失败" },
                        { file_name: "export.md", valid: true, song_name: "导出", status: "导出失败" },
                        { file_name: "generate.md", valid: true, song_name: "生成", status: "生成失败" },
                        { file_name: "manual.md", valid: true, song_name: "描述", status: "描述不符合" },
                        { file_name: "success.md", valid: true, song_name: "成功", status: "success" },
                    ];
                    renderSongs();
                    renderControls();
                    document.getElementById("select-failed").click();
                    return [...state.selected];
                    }""",
                )

                assert selected == ["download.md", "export.md", "generate.md", "manual.md"]
                assert await page.locator("#repair-run").is_enabled()
                await page.locator("#repair-run").click()
                await page.wait_for_timeout(50)

                assert captured == {
                    "items": [
                        {"account_id": "account"},
                        {"account_id": "other"},
                    ],
                    "day": await page.evaluate("todayValue()"),
                }

            await browser.close()
    finally:
        pass


@pytest.mark.asyncio
async def test_upload_table_expands_instead_of_scrolling_internally() -> None:
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(channel="chrome", headless=True)
            page = await browser.new_page(viewport={"width": 1280, "height": 600})
            with serve_frontend() as base_url:
                await page.goto(base_url)
                await page.wait_for_selector("#upload-table", state="attached")
                metrics = await page.evaluate(
                    """() => {
                    document.body.dataset.stage = "upload";
                    const table = document.getElementById("upload-table");
                    table.querySelectorAll(".upload-row:not(.upload-head)").forEach((node) => node.remove());
                    for (let index = 1; index <= 12; index += 1) {
                        const row = document.createElement("div");
                        row.className = "upload-row";
                        row.append(Object.assign(document.createElement("span"), { textContent: String(index) }));
                        row.append(Object.assign(document.createElement("span"), { textContent: `第 ${index} 首歌曲.mp3` }));
                        row.append(Object.assign(document.createElement("span"), { textContent: "4.2 MB" }));
                        row.append(Object.assign(document.createElement("span"), { textContent: "待发布" }));
                        table.append(row);
                    }
                    const style = getComputedStyle(table);
                    return {
                        maxHeight: style.maxHeight,
                        overflowY: style.overflowY,
                        clientHeight: table.clientHeight,
                        scrollHeight: table.scrollHeight,
                    };
                    }""",
                )

                assert metrics["maxHeight"] == "none"
                assert metrics["overflowY"] == "visible"
                assert metrics["clientHeight"] == metrics["scrollHeight"]

            await browser.close()
    finally:
        pass


@pytest.mark.asyncio
async def test_upload_page_shows_daily_quota_and_blocks_when_exhausted() -> None:
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(channel="chrome", headless=True)
            page = await browser.new_page(viewport={"width": 1280, "height": 600})
            with serve_frontend() as base_url:
                await page.goto(base_url)
                await page.wait_for_selector("#upload-table", state="attached")
                rendered = await page.evaluate(
                    """() => {
                    state.accountId = "account";
                    state.accounts = [{
                        id: "account",
                        account_name: "account",
                        output_dir: "D:\\\\music\\\\output",
                    }];
                    state.uploads = {
                        day: "2026-10-03",
                        batch_size: 10,
                        daily_limit: 10,
                        daily_used: 10,
                        remaining_uploads: 0,
                        files: [
                            { file_name: "pending.mp3", path: "D:\\\\music\\\\pending.mp3", size: 1024 },
                        ],
                        uploaded_files: [],
                    };
                    state.selectedUploads = new Set(["pending.mp3"]);
                    renderUploads();
                    renderUploadRun();
                    const checkbox = document.querySelector("[data-upload-file='pending.mp3']");
                    return {
                        caption: document.getElementById("upload-caption").textContent,
                        limit: document.getElementById("upload-limit").textContent,
                        checkboxDisabled: checkbox.disabled,
                        startDisabled: document.getElementById("start-upload").disabled,
                    };
                    }""",
                )

                assert "今日已发布 10/10" in rendered["caption"]
                assert "剩余 0" in rendered["caption"]
                assert rendered["limit"] == "0"
                assert rendered["checkboxDisabled"] is True
                assert rendered["startDisabled"] is True

            await browser.close()
    finally:
        pass


@pytest.mark.asyncio
async def test_pipeline_queue_shows_global_phase_and_account_stage_counts() -> None:
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(channel="chrome", headless=True)
            page = await browser.new_page(viewport={"width": 1440, "height": 900})
            with serve_frontend() as base_url:
                await page.goto(base_url)
                await page.wait_for_selector("#pipeline-phase-summary", state="attached")
                rendered = await page.evaluate(
                    """() => {
                    state.pipelineQueue = {
                        queue_id: "queue",
                        day: "2026-09-29",
                        status: "running",
                        phase: "generation",
                        current_index: 0,
                        items: [
                            {
                                account_name: "first",
                                template_name: "模板一",
                                status: "running",
                                stage: "generation",
                                pipeline_snapshot: {
                                    songs: [
                                        { lyrics_status: "completed", generation_status: "completed", upload_status: "pending" },
                                        { lyrics_status: "completed", generation_status: "running", upload_status: "pending" },
                                    ],
                                },
                            },
                            {
                                account_name: "second",
                                template_name: "模板二",
                                status: "pending",
                                stage: "generation",
                                pipeline_snapshot: {
                                    songs: [
                                        { lyrics_status: "completed", generation_status: "pending", upload_status: "pending" },
                                    ],
                                },
                            },
                        ],
                    };
                    renderPipelinePanel();
                    return {
                        summary: document.getElementById("pipeline-phase-summary").innerText,
                        table: document.getElementById("pipeline-queue-table").innerText,
                    };
                    }""",
                )

                assert "AI 作词" in rendered["summary"]
                assert "账号 2/2" in rendered["summary"]
                assert "生成下载" in rendered["summary"]
                assert "账号 0/2" in rendered["summary"]
                assert "作词" in rendered["table"]
                assert "生成" in rendered["table"]
                assert "上传" in rendered["table"]
                assert "2/2" in rendered["table"]
                assert "1/2" in rendered["table"]

            await browser.close()
    finally:
        pass


@pytest.mark.asyncio
async def test_generation_and_upload_pages_use_available_content_width() -> None:
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(channel="chrome", headless=True)
            page = await browser.new_page(viewport={"width": 1600, "height": 900})
            with serve_frontend() as base_url:
                await page.goto(base_url)
                await page.wait_for_selector(".task-layout", state="attached")
                widths = await page.evaluate(
                    """() => {
                    const layout = document.querySelector('.task-layout');
                    const result = {};
                    for (const stage of ['generation', 'upload']) {
                    state.view = 'task';
                    state.stage = stage;
                    renderView();
                        document.body.dataset.stage = stage;
                        result[stage] = layout.getBoundingClientRect().width;
                    }
                    return result;
                    }""",
                )

                assert widths["generation"] > 1200
                assert widths["upload"] > 1200

            await browser.close()
    finally:
        pass


@pytest.mark.asyncio
async def test_dashboard_keeps_completed_lyrics_when_retrying_another_account() -> None:
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(channel="chrome", headless=True)
            page = await browser.new_page(viewport={"width": 1440, "height": 900})
            with serve_frontend() as base_url:
                await page.goto(base_url)
                await page.wait_for_selector("#dashboard-account-table", state="attached")
                rendered = await page.evaluate(
                    """() => {
                    state.accounts = [
                        { id: "first", account_name: "已完成一", chrome_debug_port: 9222 },
                        { id: "second", account_name: "已完成二", chrome_debug_port: 9223 },
                        { id: "third", account_name: "重跑账号", chrome_debug_port: 9224 },
                    ];
                    state.accountId = "first";
                    state.dashboardSongs = {
                        first: [{ file_name: "01.md", song_name: "已保存一", valid: true }],
                        second: [{ file_name: "02.md", song_name: "已保存二", valid: true }],
                        third: [],
                    };
                    state.multiQueue = {
                        stage: "lyrics",
                        day: todayValue(),
                        status: "running",
                        items: [{ account_id: "third", status: "running", result: null }],
                    };
                    renderDashboard();
                    return {
                        lyricCount: document.getElementById("dashboard-lyric-count").textContent,
                        rows: [...document.querySelectorAll("#dashboard-account-table .dashboard-account-row:not(.dashboard-account-head)")]
                            .map((row) => row.innerText.replace(/\\s+/g, " | ")),
                    };
                    }""",
                )

                assert rendered["lyricCount"] == "2"
                assert rendered["rows"][0].startswith("已完成一 | 端口 | 9222 | 1 |")
                assert "已生成" in rendered["rows"][0]
                assert rendered["rows"][1].startswith("已完成二 | 端口 | 9223 | 1 |")
                assert "已生成" in rendered["rows"][1]
                assert rendered["rows"][2].startswith("重跑账号 | 端口 | 9224 | 0 |")
                assert "处理中" in rendered["rows"][2]

            await browser.close()
    finally:
        pass


@pytest.mark.asyncio
async def test_pipeline_and_generation_share_one_model_choice() -> None:
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(channel="chrome", headless=True)
            page = await browser.new_page()
            with serve_frontend() as base_url:
                await page.goto(base_url)
                await page.wait_for_selector("#pipeline-model", state="attached")
                values = await page.evaluate(
                    """() => {
                    saveGenerationModel("Sway v5.5");
                    const fromGeneration = {
                        generation: document.getElementById("generation-model").value,
                        pipeline: document.getElementById("pipeline-model").value,
                        pipelineSingerVisible: !document.getElementById("pipeline-singer").closest(".singer-field").hidden,
                        pipelineSingerDisabled: document.getElementById("pipeline-singer").disabled,
                    };
                    saveGenerationModel("MiniMax v2.6");
                    const fromPipeline = {
                        generation: document.getElementById("generation-model").value,
                        pipeline: document.getElementById("pipeline-model").value,
                        pipelineSingerVisible: !document.getElementById("pipeline-singer").closest(".singer-field").hidden,
                        pipelineSingerDisabled: document.getElementById("pipeline-singer").disabled,
                    };
                    return { fromGeneration, fromPipeline };
                    }""",
                )

                assert values["fromGeneration"]["generation"] == "Sway v5.5"
                assert values["fromGeneration"]["pipeline"] == "Sway v5.5"
                assert values["fromGeneration"]["pipelineSingerVisible"] is True
                assert values["fromGeneration"]["pipelineSingerDisabled"] is False
                assert values["fromPipeline"]["generation"] == "MiniMax v2.6"
                assert values["fromPipeline"]["pipeline"] == "MiniMax v2.6"
                assert values["fromPipeline"]["pipelineSingerVisible"] is False
                assert values["fromPipeline"]["pipelineSingerDisabled"] is True

            await browser.close()
    finally:
        pass


@pytest.mark.asyncio
async def test_stage_account_lyrics_edit_opens_bound_template() -> None:
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(channel="chrome", headless=True)
            page = await browser.new_page(viewport={"width": 1440, "height": 900})

            async def handle_templates(route) -> None:
                await route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=(
                        '{"system_prompt":"通用规则",'
                        '"templates":[{"id":"template","account_id":"target",'
                        '"name":"账号模板","themes":["都市"],"generation_count":10,'
                        '"lyric_tone":"第一人称叙事","song_style":"都市流行"}]}'
                    ),
                )

            await page.route("**/api/accounts/target/lyric/templates", handle_templates)
            with serve_frontend() as base_url:
                await page.goto(base_url)
                await page.wait_for_timeout(300)
                await page.wait_for_selector("#stage-account-table", state="attached")
                await page.evaluate(
                    """() => {
                    state.accounts = [
                        { id: "other", account_name: "其它账号", chrome_debug_port: 9222, lyric_dir: "D:\\\\music\\\\other" },
                        { id: "target", account_name: "目标账号", chrome_debug_port: 9223, lyric_dir: "D:\\\\music\\\\target" },
                    ];
                    state.accountId = "other";
                    state.view = "lyrics";
                    state.stage = "lyrics";
                    state.selectedTaskAccounts = new Set(["target"]);
                    state.accountTemplates = {
                        other: [],
                        target: [{
                            id: "template",
                            account_id: "target",
                            name: "账号模板",
                            themes: ["都市"],
                            generation_count: 10,
                            lyric_tone: "第一人称叙事",
                            song_style: "都市流行",
                        }],
                    };
                    renderView();
                    renderTaskAccounts();
                    }""",
                )

                await page.locator("#stage-account-table [data-edit-stage-account='target']").click()
                await page.wait_for_timeout(500)
                await page.wait_for_selector("#lyric-template-form", state="visible")
                rendered = await page.evaluate(
                    """() => ({
                    currentAccount: state.accountId,
                    view: state.view,
                    settingsTab: state.settingsTab,
                    panelOwner: document.querySelector(".lyric-template-panel")?.closest(".view")?.id,
                    account: document.getElementById("template-account-select").value,
                    accountLocked: document.getElementById("template-account-select").disabled,
                    name: document.getElementById("template-name").value,
                    tone: document.getElementById("template-lyric-tone").value,
                    style: document.getElementById("template-song-style").value,
                    caption: document.getElementById("lyric-template-caption").textContent,
                    })""",
                )

                assert rendered["currentAccount"] == "target"
                assert rendered["view"] == "settings"
                assert rendered["settingsTab"] == "prompt"
                assert rendered["panelOwner"] == "view-settings"
                assert rendered["account"] == "target"
                assert rendered["accountLocked"] is True
                assert rendered["name"] == "账号模板"
                assert rendered["tone"] == "第一人称叙事"
                assert rendered["style"] == "都市流行"
                assert "目标账号" in rendered["caption"]

            await browser.close()
    finally:
        pass


@pytest.mark.asyncio
async def test_generation_account_editor_only_shows_sway_singer() -> None:
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(channel="chrome", headless=True)
            page = await browser.new_page(viewport={"width": 1440, "height": 900})
            captured: list[dict] = []

            async def handle_save(route) -> None:
                captured.append(json.loads(route.request.post_data))
                payload = captured[-1]
                payload["model_name"] = "Sway v5.5"
                payload["singer_name"] = "老岩"
                await route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps(payload, ensure_ascii=False),
                )

            await page.route("**/api/accounts/target", handle_save)
            with serve_frontend() as base_url:
                await page.goto(base_url)
                await page.wait_for_selector("#generation-account-form", state="attached")
                await page.evaluate(
                    """() => {
                    state.accounts = [{
                        id: "target",
                        account_name: "目标账号",
                        chrome_debug_port: 9223,
                        model_name: "MiniMax v2.6",
                        singer_name: "老岩",
                    }];
                    state.stage = "generation";
                    state.view = "task";
                    state.selectedTaskAccounts = new Set(["target"]);
                    renderView();
                    renderTaskAccounts();
                    openGenerationAccountEditor("target");
                    }""",
                )

                singer_field = page.locator(".account-singer-field")
                assert await singer_field.is_hidden()
                assert await page.locator("#account-singer-select").is_disabled()
                assert await page.input_value("#account-singer-select") == ""

                await page.select_option("#account-model-select", "Sway v5.5")
                assert await singer_field.is_visible()
                await page.select_option("#account-singer-select", "老岩")
                await page.click("#generation-account-form button[type='submit']")
                await page.wait_for_timeout(200)

                assert captured
                assert captured[-1]["model_name"] == "Sway v5.5"
                assert captured[-1]["singer_name"] == "老岩"

            await browser.close()
    finally:
        pass


@pytest.mark.asyncio
async def test_generation_start_is_in_account_scope_and_view_switches_account() -> None:
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(channel="chrome", headless=True)
            page = await browser.new_page(viewport={"width": 1440, "height": 900})

            async def handle_second_songs(route) -> None:
                await route.fulfill(
                    status=200,
                    content_type="application/json",
                    body="[]",
                )

            await page.route("**/api/accounts/second/songs**", handle_second_songs)
            with serve_frontend() as base_url:
                await page.goto(base_url)
                await page.wait_for_selector("#stage-account-table", state="attached")
                await page.evaluate(
                    """() => {
                    state.accounts = [
                        { id: "first", account_name: "白日逐梦", chrome_debug_port: 9222, model_name: "自动", singer_name: "" },
                        { id: "second", account_name: "黄振艺", chrome_debug_port: 9223, model_name: "自动", singer_name: "" },
                    ];
                    state.accountId = "first";
                    state.selectedTaskAccounts = new Set(["first", "second"]);
                    state.view = "task";
                    state.stage = "generation";
                    renderAccounts();
                    renderView();
                    }""",
                )

                assert await page.evaluate(
                    "() => Boolean(document.getElementById('start-run').closest('.task-account-actions'))"
                )
                rows = page.locator("#stage-account-table .stage-account-row:not(.stage-account-head)")
                assert await rows.nth(0).locator("[data-focus-account='first']").is_disabled()
                await rows.nth(1).locator("[data-focus-account='second']").click()
                await page.wait_for_function(
                    "() => state.accountId === 'second' && document.getElementById('queue-caption').textContent.includes('黄振艺')"
                )
                assert await rows.nth(1).evaluate("node => node.classList.contains('is-viewing')")

            await browser.close()
    finally:
        pass


@pytest.mark.asyncio
async def test_generation_start_uses_real_checked_account_order() -> None:
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(channel="chrome", headless=True)
            page = await browser.new_page(viewport={"width": 1440, "height": 900})
            captured = {}

            async def handle_songs(route) -> None:
                account_id = route.request.url.split("/api/accounts/", 1)[1].split("/", 1)[0]
                song_name = {"first": "一", "second": "二", "third": "三"}[account_id]
                await route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps([
                        {"file_name": f"{account_id}.md", "valid": True, "song_name": song_name, "status": "pending"},
                    ], ensure_ascii=False),
                )

            async def handle_start(route) -> None:
                captured.update(route.request.post_data_json)
                payload = captured["items"]
                await route.fulfill(
                    status=202,
                    content_type="application/json",
                    body=json.dumps({
                        "queue_id": "generation-queue",
                        "stage": "generation",
                        "day": "2026-10-16",
                        "status": "running",
                        "current_index": 0,
                        "concurrency": 1,
                        "items": [
                            {
                                "account_id": item["account_id"],
                                "account_name": {"first": "白日逐梦", "second": "蹦儿波", "third": "黄振艺"}[item["account_id"]],
                                "status": "pending",
                            }
                            for item in payload
                        ],
                    }, ensure_ascii=False),
                )

            async def handle_accounts(route) -> None:
                await route.fulfill(status=200, content_type="application/json", body="[]")

            await page.route("**/api/accounts", handle_accounts)
            await page.route("**/api/accounts/*/songs**", handle_songs)
            await page.route("**/api/multi-stage/generation/runs", handle_start)
            with serve_frontend() as base_url:
                await page.goto(base_url)
                await page.wait_for_function("window.appReady === true")
                await page.wait_for_selector("#stage-account-table", state="attached")
                await page.evaluate(
                    """() => {
                    state.accounts = [
                        { id: "first", account_name: "白日逐梦", chrome_debug_port: 9222, model_name: "自动", singer_name: "", lyric_dir: "E:\\\\music\\\\first" },
                        { id: "second", account_name: "蹦儿波", chrome_debug_port: 9223, model_name: "自动", singer_name: "", lyric_dir: "E:\\\\music\\\\second" },
                        { id: "third", account_name: "黄振艺", chrome_debug_port: 9224, model_name: "自动", singer_name: "", lyric_dir: "E:\\\\music\\\\third" },
                    ];
                    state.accountId = "first";
                    state.selectedTaskAccounts = new Set();
                    state.view = "task";
                    state.stage = "generation";
                    document.getElementById("lyric-dir-input").value = "E:\\\\music\\\\first";
                    renderAccounts();
                    renderView();
                    }""",
                )

                checkboxes = page.locator("#stage-account-table [data-task-account]")
                await checkboxes.nth(0).check()
                await checkboxes.nth(1).check()
                await checkboxes.nth(2).check()
                assert "白日逐梦、蹦儿波、黄振艺" in await page.locator("#task-account-count").inner_text()
                await page.locator("#start-run").click()
                await page.wait_for_timeout(500)

                assert [item["account_id"] for item in captured["items"]] == ["first", "second", "third"]
                assert "白日逐梦 → 蹦儿波 → 黄振艺" in await page.locator("#toast").inner_text()

            await browser.close()
    finally:
        pass


@pytest.mark.asyncio
async def test_generation_view_and_progress_stay_available_while_queue_runs() -> None:
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(channel="chrome", headless=True)
            page = await browser.new_page(viewport={"width": 1440, "height": 900})

            async def handle_second_songs(route) -> None:
                await route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps([
                        {"file_name": "a.txt", "valid": True, "song_name": "A", "status": "pending"},
                        {"file_name": "b.txt", "valid": True, "song_name": "B", "status": "pending"},
                        {"file_name": "c.txt", "valid": True, "song_name": "C", "status": "pending"},
                    ], ensure_ascii=False),
                )

            async def handle_current(route) -> None:
                if "account_id=second" not in route.request.url:
                    await route.fulfill(status=200, content_type="application/json", body="null")
                    return
                run = {
                    "run_id": "running-run",
                    "account_id": "second",
                    "account_name": "黄振艺",
                    "status": "running",
                    "current_step": "download_song",
                    "songs": [
                        {"file_name": "a.txt", "song_name": "A", "status": "成功", "current_step": "done"},
                        {"file_name": "b.txt", "song_name": "B", "status": "成功", "current_step": "done"},
                        {"file_name": "c.txt", "song_name": "C", "status": "running", "current_step": "download_song"},
                    ],
                }
                await route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps(run, ensure_ascii=False),
                )

            await page.route("**/api/accounts/second/songs**", handle_second_songs)
            await page.route("**/api/runs/current**", handle_current)
            with serve_frontend() as base_url:
                await page.goto(base_url)
                await page.wait_for_selector("#stage-account-table", state="attached")
                await page.evaluate(
                    """() => {
                    state.accounts = [
                        { id: "first", account_name: "白日逐梦", chrome_debug_port: 9222, model_name: "自动" },
                        { id: "second", account_name: "黄振艺", chrome_debug_port: 9223, model_name: "自动" },
                    ];
                    state.accountId = "first";
                    state.selectedTaskAccounts = new Set(["first", "second"]);
                    state.view = "task";
                    state.stage = "generation";
                    state.multiQueue = {
                        stage: "generation",
                        status: "running",
                        items: [
                            { account_id: "first", status: "completed" },
                            { account_id: "second", status: "running" },
                        ],
                    };
                    state.generationRuns = {
                        second: {
                            account_id: "second",
                            status: "running",
                            current_step: "download_song",
                            songs: [
                                { file_name: "a.txt", status: "成功" },
                                { file_name: "b.txt", status: "成功" },
                                { file_name: "c.txt", status: "running", current_step: "download_song" },
                            ],
                        },
                    };
                    renderAccounts();
                    renderView();
                    }""",
                )

                rows = page.locator("#stage-account-table .stage-account-row:not(.stage-account-head)")
                second_view = rows.nth(1).locator("[data-focus-account='second']")
                second_edit = rows.nth(1).locator("[data-edit-stage-account='second']")
                assert await second_view.is_enabled()
                assert await second_edit.is_disabled()
                assert "2 / 3" in await rows.nth(1).inner_text()

                await second_view.click()
                await page.wait_for_function(
                    "() => state.accountId === 'second' && state.current?.account_id === 'second'",
                )
                assert await page.evaluate("() => multiStageRunning()")
                assert "2 / 3" in await rows.nth(1).inner_text()

            await browser.close()
    finally:
        pass


@pytest.mark.asyncio
async def test_upload_start_is_in_account_scope() -> None:
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(channel="chrome", headless=True)
            page = await browser.new_page(viewport={"width": 1440, "height": 900})
            with serve_frontend() as base_url:
                await page.goto(base_url)
                await page.wait_for_selector("#stage-account-table", state="attached")
                await page.evaluate(
                    """() => {
                    state.view = "task";
                    state.stage = "upload";
                    renderView();
                    }""",
                )

                assert await page.evaluate(
                    "() => Boolean(document.getElementById('start-upload').closest('.task-account-actions'))",
                )
                assert await page.locator("#start-upload").is_visible()
                assert await page.locator("#start-run").is_hidden()
                assert await page.locator("#multi-lyrics-start").is_hidden()

            await browser.close()
    finally:
        pass


@pytest.mark.asyncio
async def test_lyrics_stage_accounts_render_compact_responsive_cards() -> None:
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(channel="chrome", headless=True)
            page = await browser.new_page(viewport={"width": 1440, "height": 900})
            with serve_frontend() as base_url:
                await page.goto(base_url)
                await page.wait_for_selector("#stage-account-table", state="attached")
                await page.evaluate(
                    """() => {
                    const accounts = Array.from({ length: 8 }, (_, index) => ({
                        id: `account-${index}`,
                        account_name: `账号${String(index + 1).padStart(2, "0")}`,
                        chrome_debug_port: 9222 + index,
                        lyric_dir: `D:\\\\music\\\\account-${index}`,
                    }));
                    state.accounts = accounts;
                    state.accountId = accounts[0].id;
                    state.view = "lyrics";
                    state.stage = "lyrics";
                    state.selectedTaskAccounts = new Set(accounts.map((account) => account.id));
                    state.accountTemplates = Object.fromEntries(accounts.map((account, index) => [account.id, [{
                        id: `template-${index}`,
                        account_id: account.id,
                        name: `模板${index + 1}`,
                        generation_count: 5,
                    }]]));
                    state.dashboardSongs = {
                        "account-0": [
                            { file_name: "01.md", song_name: "晚风来信" },
                            { file_name: "02.md", song_name: "海面日出" },
                        ],
                        "account-2": [{ file_name: "03.md", song_name: "旧城列车" }],
                    };
                    state.multiQueue = {
                        stage: "lyrics",
                        day: todayValue(),
                        status: "running",
                        items: [
                            {
                                account_id: "account-0",
                                status: "completed",
                                result: {
                                    saved_count: 2,
                                    saved: [
                                        { song_name: "晚风来信" },
                                        { song_name: "海面日出" },
                                    ],
                                },
                            },
                            { account_id: "account-1", status: "running", result: null },
                            { account_id: "account-2", status: "failed", result: null },
                            { account_id: "account-3", status: "pending", result: null },
                        ],
                    };
                    renderView();
                    renderTaskAccounts();
                    }""",
                )

                wide = await page.evaluate(
                    """() => {
                    const grid = document.getElementById("stage-account-table");
                    const summary = document.getElementById("lyric-summary-list");
                    const columns = getComputedStyle(grid).gridTemplateColumns.split(" ").filter(Boolean).length;
                    return {
                        columns,
                        cards: grid.querySelectorAll(".lyric-account-card").length,
                        visibleSections: document.querySelectorAll("#view-lyrics .lyric-layout > section:not([hidden])").length,
                        startVisible: document.getElementById("multi-lyrics-start").checkVisibility(),
                        accountCards: grid.innerText,
                        completed: summary.querySelector("[data-lyric-summary-account='account-0']").innerText,
                        running: summary.querySelector("[data-lyric-summary-account='account-1']").innerText,
                        failed: summary.querySelector("[data-lyric-summary-account='account-2']").innerText,
                        overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
                    };
                    }""",
                )
                await page.set_viewport_size({"width": 1200, "height": 900})
                narrow = await page.evaluate(
                    """() => getComputedStyle(document.getElementById("stage-account-table")).gridTemplateColumns
                        .split(" ")
                        .filter(Boolean).length""",
                )

                assert 6 <= wide["columns"] <= 7
                assert wide["cards"] == 8
                assert wide["visibleSections"] == 1
                assert wide["startVisible"] is True
                assert "晚风来信" not in wide["accountCards"]
                assert "海面日出" not in wide["accountCards"]
                assert "已完成" in wide["completed"]
                assert "晚风来信" in wide["completed"]
                assert "海面日出" in wide["completed"]
                assert "正在生成" in wide["running"]
                assert "生成完成后显示歌名" in wide["running"]
                assert "生成失败" in wide["failed"]
                assert "旧城列车" in wide["failed"]
                assert wide["overflow"] <= 0
                assert narrow < wide["columns"]

            await browser.close()
    finally:
        pass


@pytest.mark.asyncio
async def test_ai_lyrics_provider_can_switch_between_configured_apis() -> None:
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(channel="chrome", headless=True)
            page = await browser.new_page(viewport={"width": 1440, "height": 900})
            captured: dict = {}
            configs = [
                {
                    "id": "first",
                    "name": "接口一",
                    "api_base_url": "https://api-one.example.com/v1",
                    "api_key": "key-one",
                    "model": "model-one",
                    "max_retries": 1,
                },
                {
                    "id": "second",
                    "name": "接口二",
                    "api_base_url": "https://api-two.example.com/v1",
                    "api_key": "key-two",
                    "model": "model-two",
                    "max_retries": 2,
                },
            ]

            async def handle_settings(route) -> None:
                if route.request.method == "PUT":
                    captured.update(route.request.post_data_json)
                    await route.fulfill(
                        status=200,
                        content_type="application/json",
                        body=(
                            '{"page_load_timeout_seconds":30,'
                            '"generation_timeout_seconds":300,'
                            '"editor_import_wait_seconds":8,'
                            '"export_timeout_seconds":60,'
                            '"download_timeout_seconds":30,'
                            '"log_history_limit":1000,'
                            '"ai_api_base_url":"https://api-two.example.com/v1",'
                            '"ai_api_key":"key-two",'
                            '"ai_model":"model-two",'
                            '"ai_max_retries":2,'
                            '"ai_api_configs":' + json.dumps(configs) + ","
                            '"active_ai_api_config_id":"second",'
                            '"ai_system_prompt":"' + ("X" * 150) + '"}'
                        ),
                    )
                    return
                await route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=(
                        '{"page_load_timeout_seconds":30,'
                        '"generation_timeout_seconds":300,'
                        '"editor_import_wait_seconds":8,'
                        '"export_timeout_seconds":60,'
                        '"download_timeout_seconds":30,'
                        '"log_history_limit":1000,'
                        '"ai_api_base_url":"https://api-one.example.com/v1",'
                        '"ai_api_key":"key-one",'
                        '"ai_model":"model-one",'
                        '"ai_max_retries":1,'
                        '"ai_api_configs":' + json.dumps(configs) + ","
                        '"active_ai_api_config_id":"first",'
                        '"ai_system_prompt":"' + ("X" * 150) + '"}'
                    ),
                )

            await page.route("**/api/settings", handle_settings)
            with serve_frontend() as base_url:
                await page.goto(base_url)
                await page.wait_for_selector("#ai-provider-select", state="attached")
                await page.evaluate(
                    """() => {
                    state.view = "settings";
                    state.settingsTab = "ai";
                    renderView();
                    state.view = "lyrics";
                    state.stage = "lyrics";
                    state.selectedTaskAccounts = new Set(["first"]);
                    state.accountId = "first";
                    state.selectedLyricTemplateId = "template";
                    renderView();
                    renderControls();
                    }""",
                )

                select = page.locator("#ai-provider-select")
                assert await select.input_value() == "first"
                assert await page.locator("[data-use-ai-config='second']").count() == 1
                await select.select_option("second")
                await page.wait_for_timeout(200)

                assert captured == {"active_ai_api_config_id": "second"}
                assert await select.input_value() == "second"
                assert "model-two" in await select.inner_text()
                assert await page.locator("#multi-lyrics-start").is_enabled()

            await browser.close()
    finally:
        pass


@pytest.mark.asyncio
async def test_settings_ai_page_can_add_another_provider() -> None:
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(channel="chrome", headless=True)
            page = await browser.new_page(viewport={"width": 1440, "height": 900})
            captured: dict = {}
            saved = False
            provider = {
                "id": "new-provider",
                "name": "新接口",
                "api_base_url": "https://api-new.example.com/v1",
                "api_key": "new-key",
                "model": "new-model",
                "max_retries": 2,
            }

            async def handle_settings(route) -> None:
                nonlocal saved
                if route.request.method == "PUT":
                    captured.update(route.request.post_data_json)
                    saved = True
                    await route.fulfill(
                        status=200,
                        content_type="application/json",
                        body=json.dumps({
                            "page_load_timeout_seconds": 30,
                            "generation_timeout_seconds": 300,
                            "editor_import_wait_seconds": 8,
                            "export_timeout_seconds": 60,
                            "download_timeout_seconds": 30,
                            "log_history_limit": 1000,
                            "ai_api_base_url": provider["api_base_url"],
                            "ai_api_key": provider["api_key"],
                            "ai_model": provider["model"],
                            "ai_max_retries": provider["max_retries"],
                            "ai_api_configs": [provider],
                            "active_ai_api_config_id": provider["id"],
                            "ai_system_prompt": "X" * 150,
                        }),
                    )
                    return
                if saved:
                    await route.fulfill(
                        status=200,
                        content_type="application/json",
                        body=json.dumps({
                            "page_load_timeout_seconds": 30,
                            "generation_timeout_seconds": 300,
                            "editor_import_wait_seconds": 8,
                            "export_timeout_seconds": 60,
                            "download_timeout_seconds": 30,
                            "log_history_limit": 1000,
                            "ai_api_base_url": provider["api_base_url"],
                            "ai_api_key": provider["api_key"],
                            "ai_model": provider["model"],
                            "ai_max_retries": provider["max_retries"],
                            "ai_api_configs": [provider],
                            "active_ai_api_config_id": provider["id"],
                            "ai_system_prompt": "X" * 150,
                        }),
                    )
                    return
                await route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps({
                        "page_load_timeout_seconds": 30,
                        "generation_timeout_seconds": 300,
                        "editor_import_wait_seconds": 8,
                        "export_timeout_seconds": 60,
                        "download_timeout_seconds": 30,
                        "log_history_limit": 1000,
                        "ai_api_base_url": "",
                        "ai_api_key": "",
                        "ai_model": "",
                        "ai_max_retries": 2,
                        "ai_api_configs": [],
                        "active_ai_api_config_id": "",
                        "ai_system_prompt": "X" * 150,
                    }),
                )

            await page.route("**/api/settings", handle_settings)
            with serve_frontend() as base_url:
                await page.goto(base_url)
                await page.wait_for_selector("#ai-settings-form", state="attached")
                await page.wait_for_timeout(300)
                await page.evaluate(
                    """() => {
                    state.view = "settings";
                    state.settingsTab = "ai";
                    renderView();
                    }""",
                )

                assert await page.locator("#ai-settings-form").is_visible()
                form = page.locator("#ai-settings-form")
                await form.locator("[name='ai_provider_name']").fill("新接口")
                await form.locator("[name='ai_api_base_url']").fill(provider["api_base_url"])
                await form.locator("[name='ai_api_key']").fill(provider["api_key"])
                await form.locator("[name='ai_model']").fill(provider["model"])
                await form.locator("[name='ai_max_retries']").fill("2")
                await page.locator("#save-settings").click()
                await page.wait_for_timeout(200)

                assert captured["active_ai_api_config_id"] == captured["ai_api_configs"][0]["id"]
                assert captured["ai_api_configs"][0]["name"] == provider["name"]
                assert captured["ai_api_configs"][0]["api_base_url"] == provider["api_base_url"]
                assert await page.locator("#ai-settings-form").is_hidden()
                assert "已配置 1 个 AI 接口" in await page.locator("#ai-config-cards").inner_text()

            await browser.close()
    finally:
        pass


@pytest.mark.asyncio
async def test_ai_api_card_can_run_single_connection_check() -> None:
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(channel="chrome", headless=True)
            page = await browser.new_page(viewport={"width": 1440, "height": 900})
            captured: list[dict] = []

            async def handle_test(route) -> None:
                captured.append(route.request.post_data_json)
                await route.fulfill(
                    status=200,
                    content_type="application/json",
                    body='{"ok":true,"model":"model-one","model_count":8}',
                )

            await page.route("**/api/settings/ai/test", handle_test)
            with serve_frontend() as base_url:
                await page.goto(base_url)
                await page.wait_for_selector("#ai-config-cards", state="attached")
                await page.wait_for_timeout(300)
                await page.evaluate(
                    """() => {
                    state.settings = {
                        ai_api_configs: [
                            { id: "first", name: "接口一", api_base_url: "https://api-one.example.com/v1", api_key: "key-one", model: "model-one", max_retries: 1 },
                            { id: "second", name: "接口二", api_base_url: "https://api-two.example.com/v1", api_key: "key-two", model: "model-two", max_retries: 1 },
                        ],
                        active_ai_api_config_id: "first",
                    };
                    state.view = "settings";
                    state.settingsTab = "ai";
                    renderView();
                    }""",
                )

                cards = page.locator("#ai-config-cards .settings-card")
                assert await cards.count() == 2
                await cards.nth(0).locator("[data-test-ai-config='first']").click()
                await page.wait_for_timeout(200)

                assert len(captured) == 1
                assert captured[0] == {
                    "ai_api_base_url": "https://api-one.example.com/v1",
                    "ai_api_key": "key-one",
                    "ai_model": "model-one",
                }
                assert "可用" in await cards.nth(0).inner_text()
                assert "未检测" in await cards.nth(1).inner_text()

            await browser.close()
    finally:
        pass
