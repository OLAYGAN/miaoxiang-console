# Batch Generation Implementation Plan

**Goal:** Submit up to two lyric jobs together, validate every generated asset, select the newest matching version for each lyric, and export/download selected songs serially.

**Architecture:** `PageFlow.process_batch()` handles batch page orchestration. `TaskEngine` groups pending songs by account batch size, retries only lyrics with no matching generated asset, and never regenerates a lyric after generation succeeds but export fails.

**Tech Stack:** FastAPI, Python Playwright, Pydantic, pytest.

---

## Tasks

### 1. Models and settings

- Add `AccountConfig.generation_batch_size`, default `2`, range `1..2`.
- Add `GeneratedCandidate` and `BatchSongResult` models.
- Expose batch size in the account form and tooltip.

### 2. Page batch flow

- Add asset-card snapshot/state helpers.
- Add batch wait logic:
  - refresh asset tabs once after submitting the batch;
  - wait for new titled cards and stable non-loading state;
  - support 0, partial, or complete result sets.
- Add detail classification:
  - click every newly generated card;
  - read the detail section titled `歌词`;
  - normalize and match against each submitted lyric;
  - preserve asset-list order, newest first.
- Add `PageFlow.process_batch()`:
  - prepare page once;
  - submit each lyric without entering editor;
  - classify generated cards;
  - select first matching card per lyric;
  - export/download selected cards serially;
  - return success, generation-failed, or export-failed per lyric.

### 3. Task engine batching

- Group valid pending lyrics into batches of `generation_batch_size`.
- Call `flow.process_batch()` when available.
- Retry only lyrics reported as generation failures.
- Mark export failures final for that run, without regenerating.
- Preserve existing single-song flow for non-batch implementations and diagnostics.

### 4. UI and docs

- Add batch-size field.
- Show batch step names in existing progress UI.
- Document two-version selection: newest first matching version is exported.

### 5. Verification

- Unit tests for partial batch results and retry separation.
- Full pytest suite.
- Live smoke test with two lyrics only after implementation and user approval.
