# Complete Music Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (recommended) or superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a resumable end-to-end pipeline that orchestrates AI lyrics, generation/download, and publishing without replacing the existing single-stage features.

**Architecture:** Add persisted Pydantic pipeline snapshots and a `PipelineEngine` background orchestrator. Inject existing lyric, generation, and upload operations as async callbacks so the pipeline does not duplicate platform logic. Extend the existing FastAPI app and task-management UI additively.

**Tech Stack:** FastAPI, Pydantic v2, asyncio, existing vanilla JavaScript frontend, pytest.

---

### Task 1: Pipeline Models And Persistence

**Files:**
- Modify: `backend/models.py`
- Modify: `backend/config.py`
- Modify: `backend/storage.py`
- Test: `tests/test_pipeline.py`

Add `PipelineSongState`, `PipelineSnapshot`, and `PipelineStateRepository`. Persist the latest run to `data/pipeline_state.json`.

### Task 2: Pipeline Engine

**Files:**
- Create: `backend/pipeline.py`
- Test: `tests/test_pipeline.py`

Implement a callback-based engine with stages `lyrics`, `generation`, `pre_upload`, `upload`, and `report`. Support automatic upload, optional pause before upload, stop/resume, per-song persistence, and partial failure continuation.

Injected operations:

- `lyric_generator(settings, template, count)`
- `lyric_saver(account, day, songs)`
- `generation_runner(account, day, lyric_files)`
- `upload_runner(account, day, output_files, request_options)`

### Task 3: API Integration

**Files:**
- Modify: `backend/api.py`
- Test: `tests/test_api.py`

Add:

- `POST /api/pipeline/runs`
- `GET /api/pipeline/runs/current`
- `POST /api/pipeline/runs/resume`
- `POST /api/pipeline/runs/stop`

Refactor the upload item construction only far enough to expose a reusable helper. Existing endpoints keep their paths and payload behavior.

### Task 4: Task Management UI

**Files:**
- Modify: `frontend/index.html`
- Modify: `frontend/app.js`
- Modify: `frontend/styles.css`

Add a compact pipeline panel above the generation queue:

- account/template selectors
- pause-before-upload toggle
- start/resume/stop controls
- stage strip and per-song status table
- WebSocket status updates

### Task 5: Regression Verification

Run:

```powershell
.\.venv\Scripts\python -m pytest -q
```

Then verify in the browser:

1. Existing AI lyric generation remains usable.
2. Existing generation start remains usable.
3. Existing upload start remains usable.
4. Pipeline can pause before upload and resume.

