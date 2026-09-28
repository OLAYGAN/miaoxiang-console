from pathlib import Path
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
from contextlib import contextmanager
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
