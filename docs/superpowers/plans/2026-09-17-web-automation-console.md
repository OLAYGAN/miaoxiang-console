# Web Automation Console Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a stable local web console that manages multiple accounts and runs the complete deterministic Miaoxiang generation, export, and download workflow one account at a time.

**Architecture:** A FastAPI backend serves the local control API and static frontend. A single background task engine serializes account runs as finite-state song workflows, emits logs over WebSocket, persists resumable state, and controls Chrome through Python Playwright. All browser waits use bounded timeouts and failures produce screenshots.

**Tech Stack:** Python 3.11+, FastAPI, Uvicorn, Playwright, Pydantic, pytest, pytest-asyncio, HTML/CSS/JavaScript static frontend.

---

## File Map

- `pyproject.toml`: Python dependencies and test configuration.
- `backend/__init__.py`: Backend package.
- `backend/config.py`: Runtime settings and filesystem paths.
- `backend/models.py`: Pydantic models for accounts, song records, logs, and task state.
- `backend/errors.py`: Typed application exceptions.
- `backend/lyrics.py`: Markdown lyric parsing.
- `backend/storage.py`: Atomic JSON persistence, account repository, run-state repository.
- `backend/events.py`: In-memory event bus and recent-log buffer.
- `backend/task_engine.py`: Song finite-state machine, retry/control semantics, and task runner.
- `backend/browser.py`: Chrome discovery/launch and Playwright session lifecycle.
- `backend/page_flow.py`: Deterministic Miaoxiang page operations.
- `backend/api.py`: FastAPI routes, WebSocket, static file serving, lifecycle shutdown.
- `backend/main.py`: Uvicorn entry point.
- `frontend/index.html`, `frontend/styles.css`, `frontend/app.js`: Local control console.
- `tests/test_lyrics.py`, `tests/test_storage.py`, `tests/test_task_engine.py`, `tests/test_browser.py`, `tests/test_api.py`: Unit and integration tests.

---

### Task 1: Python Project Foundation

**Files:**
- Create: `pyproject.toml`
- Create: `backend/__init__.py`
- Create: `backend/config.py`
- Create: `backend/models.py`
- Create: `backend/errors.py`
- Create: `tests/__init__.py`

- [x] Write `tests/test_models.py` asserting that `AccountConfig` applies defaults, rejects duplicate ports through the repository later, and converts paths to absolute normalized paths.
- [x] Run `pytest tests/test_models.py -q` and confirm the failure is caused by missing backend modules.
- [x] Add project metadata and dependencies: `fastapi`, `uvicorn[standard]`, `playwright`, `pydantic`, `pytest`, `pytest-asyncio`, `httpx`.
- [x] Implement runtime settings rooted in the project directory and create data/log/screenshot directories lazily.
- [x] Implement typed exceptions: `AppError`, `ValidationError`, `ConflictError`, `NotFoundError`, `TaskControlError`, `BrowserFlowError`, `GenerationLimitError`.
- [x] Run `pytest tests/test_models.py -q` and confirm pass.
- [ ] Commit `feat: add backend foundation`.

### Task 2: Lyric Parser

**Files:**
- Create: `backend/lyrics.py`
- Test: `tests/test_lyrics.py`

- [x] Write tests for:
  - Full-width colon song name.
  - Half-width colon song name.
  - Lyric extraction removing the repeated first title line.
  - Style extraction and whitespace trimming.
  - Missing section, short lyric, and short style failures.
- [x] Run `pytest tests/test_lyrics.py -q` and verify parser import failure.
- [x] Implement `parse_lyrics(text: str) -> LyricData` using regular expressions and explicit validation errors.
- [x] Implement `list_lyric_files(root: Path, account: str, day: str | None = None) -> list[Path]`.
- [x] Run `pytest tests/test_lyrics.py -q` and confirm pass.
- [ ] Commit `feat: add lyric parsing`.

### Task 3: Persistence and Event Bus

**Files:**
- Create: `backend/storage.py`
- Create: `backend/events.py`
- Test: `tests/test_storage.py`

- [x] Write tests proving:
  - JSON writes are atomic.
  - Corrupt files are backed up before recreation.
  - Accounts can be created, updated, copied, and deleted.
  - Port and account-name conflicts are rejected.
  - Run state is isolated by date/account/song.
  - Event subscribers receive logs and state snapshots.
- [x] Run tests and confirm missing storage/event modules fail.
- [x] Implement `JsonStore` with `atomic_write`, timestamped backup, and UTF-8 JSON.
- [x] Implement `AccountRepository` and `RunStateRepository`.
- [x] Implement `EventBus` with bounded recent history and disconnect-safe publish.
- [x] Run `pytest tests/test_storage.py -q` and confirm pass.
- [ ] Commit `feat: add persistence and event bus`.

### Task 4: Task Engine Semantics

**Files:**
- Create: `backend/task_engine.py`
- Test: `tests/test_task_engine.py`

- [x] Write async tests with a fake page flow:
  - Successful song updates run state once.
  - Parse failure advances to next song without browser calls.
  - Retryable failure respects max retries.
  - Generation limit stops the whole run.
  - Stop request prevents new songs and marks stopping/stopped.
  - Pause blocks between state-machine steps and resume continues.
  - Completed songs are skipped unless `fresh_run` is true.
  - Unexpected exceptions emit error events and do not deadlock the engine.
- [x] Run tests and confirm task engine import failure.
- [x] Implement `ControlState`, `SongTask`, and `TaskEngine`.
- [x] Keep one active task at a time; use `asyncio.Lock`.
- [x] Implement bounded sleeps with an abort-aware event.
- [x] Implement event/status emission around every state transition.
- [x] Run `pytest tests/test_task_engine.py -q` and confirm pass.
- [ ] Commit `feat: add deterministic task engine`.

### Task 5: Chrome Session Manager

**Files:**
- Create: `backend/browser.py`
- Test: `tests/test_browser.py`

- [x] Write tests for:
  - Chrome path discovery from configured override and common Windows locations.
  - User-data directory isolation by account slug.
  - Profile path refusal for unsafe root-like paths.
  - Command line contains remote debugging port, profile, no-first-run, and no-default-browser-check.
  - CDP readiness uses bounded polling.
- [x] Run tests and confirm browser module import failure.
- [x] Implement `ChromeSession.start()`:
  1. Resolve executable.
  2. Ensure profile directory.
  3. Launch process with `CREATE_NO_WINDOW` on Windows.
  4. Poll `http://127.0.0.1:<port>/json/version`.
  5. Connect Playwright over CDP.
  6. Create or find a studio page.
- [x] Implement `ChromeSession.cleanup()` with browser disconnect, process termination, and bounded waits.
- [x] Implement async context manager semantics.
- [x] Run `pytest tests/test_browser.py -q` and confirm pass.
- [ ] Commit `feat: add chrome session manager`.

### Task 6: Deterministic Page Flow

**Files:**
- Create: `backend/page_flow.py`
- Test: `tests/test_page_flow.py`

- [x] Write fake-locator tests for:
  - Trusted mouse click sequence.
  - DOM click logging.
  - Segmented lyric input.
  - Generation-before/after title change.
  - Generation-limit text detection.
  - File archive and collision handling.
- [x] Run tests and confirm page flow import failure.
- [x] Implement helpers:
  - `trusted_click`
  - `dom_click`
  - `type_segmented`
  - `clear_and_type`
  - `screenshot_on_error`
  - `archive_download`
- [x] Implement `PageFlow` methods:
  - `ensure_create_page_ready`
  - `select_model`
  - `select_singer`
  - `fill_inputs`
  - `first_asset_title`
  - `generate`
  - `check_generation_limit`
  - `wait_for_generation`
  - `enter_editor`
  - `export_song`
  - `download_song`
- [x] Every locator has a bounded timeout and logs selector text.
- [x] Run `pytest tests/test_page_flow.py -q` and confirm pass.
- [ ] Commit `feat: add deterministic page flow`.

### Task 7: FastAPI Control Surface

**Files:**
- Create: `backend/api.py`
- Create: `backend/main.py`
- Test: `tests/test_api.py`

- [x] Write API tests for:
  - Health endpoint.
  - Account CRUD and conflict responses.
  - Lyric listing and parsing.
  - Start validation without an account.
  - One-active-task conflict.
  - Pause/resume/stop controls.
  - WebSocket receives log and status events.
  - Server shutdown calls engine cleanup.
- [x] Run tests and confirm API import failure.
- [x] Implement endpoints:
  - `GET /api/health`
  - `GET/POST /api/accounts`
  - `GET/PUT/DELETE /api/accounts/{id}`
  - `POST /api/accounts/{id}/copy`
  - `GET /api/accounts/{id}/songs`
  - `POST /api/runs`
  - `POST /api/runs/control`
  - `GET /api/runs/current`
  - `GET /api/logs/recent`
  - `GET /api/settings`
  - `PUT /api/settings`
  - `WS /ws`
- [x] Validate request bodies with Pydantic and map typed errors to JSON responses.
- [x] Mount static frontend from `frontend/`.
- [x] Run `pytest tests/test_api.py -q` and confirm pass.
- [ ] Commit `feat: add control api`.

### Task 8: Local Control Console UI

**Files:**
- Create: `frontend/index.html`
- Create: `frontend/styles.css`
- Create: `frontend/app.js`

- [x] Build a dense operational layout:
  - Left rail: account selector and account form.
  - Center: song queue and run controls.
  - Right: configuration and recent log stream.
- [x] Use stable controls: segmented tabs, checkboxes, numeric steppers, path inputs, and clear action buttons.
- [x] Implement WebSocket reconnect and polling fallback.
- [x] Disable destructive and config actions while a run is active.
- [x] Show per-song state, retry count, current step, screenshot path, and task summary.
- [x] Provide links/buttons to open log and screenshot folders through API-backed safe endpoints.
- [x] Keep all labels in Chinese and avoid decorative marketing content.
- [x] Verify manually in Chromium at 1440x900 and 390x844:
  - No blank screen.
  - No overlapping text.
  - Controls remain reachable.
  - WebSocket status is visible.
- [ ] Commit `feat: add local control console`.

### Task 9: End-to-End Verification

**Files:**
- Modify as needed based on failures.

- [ ] Live one-song test is deferred until the user logs into the generated Chrome profile manually.
- [x] Run `pytest -q`.
- [x] Run `python -m backend.main` and verify:
  - Console opens at `http://127.0.0.1:8787`.
  - Account can be created.
  - Lyric directory can be listed.
  - Dry-run parse works.
  - Stop endpoint releases the browser.
- [ ] Run a one-song live test only after the user logs into the generated Chrome profile manually.
- [ ] Verify generated MP3 reaches `output/YYYY-MM-DD/account/song.mp3`.
- [x] Verify interruption and restart skip completed songs.
- [x] Fix all failures, rerun tests, and commit `test: verify complete workflow`.

### Task 10: Documentation and Startup

**Files:**
- Create: `README.md`
- Create: `启动控制台.bat`
- Create: `.gitignore`

- [x] Document first-use Chrome login, account profile paths, lyric format, daily folder layout, run controls, screenshots, logs, state reset, and safe stop.
- [x] Add one-click Windows launcher that uses `.venv` and opens the console URL.
- [x] Add ignore rules for `.venv/`, caches, logs, screenshots, data, and downloaded files.
- [x] Run final `pytest -q`.
- [ ] Commit `docs: add console usage guide`.

---

## Verification Commands

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
.\.venv\Scripts\python -m pytest -q
.\.venv\Scripts\python -m playwright install chromium
.\.venv\Scripts\python -m backend.main
```

The server should expose:

```text
http://127.0.0.1:8787
```

