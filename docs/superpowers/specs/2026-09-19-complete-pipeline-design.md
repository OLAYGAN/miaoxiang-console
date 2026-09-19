# Complete Music Pipeline Design

## Goal

Add a resumable end-to-end pipeline that runs AI lyric generation, lyric saving, song generation/export/download, and album publishing in one operation. Existing single-stage features remain available and unchanged.

## Recommended Behavior

The pipeline defaults to automatic publishing after all selected songs are downloaded. It also provides a `pause_before_upload` option so the user can inspect generated songs before continuing.

## Architecture

Use a new pipeline orchestrator instead of rewriting the existing engines:

1. `PipelineEngine` owns one pipeline run and its stage states.
2. Existing AI lyric generation saves drafts through the current lyric API.
3. Existing `TaskEngine` handles generation, export, and download.
4. Existing upload flow handles publishing and external SMS verification.
5. A persisted pipeline state file records stage and per-song progress for recovery.

This keeps the existing AI作词, 任务管理, and 上传作品 workflows independently usable.

## Pipeline Stages

```text
lyrics
  -> generation
  -> pre_upload
  -> upload
  -> report
```

### Lyrics

- Read the selected lyric template.
- Generate the requested number of songs.
- Validate and save songs to `歌词根目录/当天日期/`.
- Save generated output paths and song names in pipeline state.
- If a generated song cannot be validated, mark that song `failed` and continue unless every song fails.

### Generation

- Pass saved lyric files to the existing generation task.
- Reuse existing completion detection so completed songs are skipped.
- Record generation/export/download output paths.
- If some songs fail, continue to upload only successfully downloaded songs.

### Pre-upload

- Read the account upload batch for the current day.
- Select every downloaded song, up to the configured upload batch limit.
- When `pause_before_upload` is enabled, enter `waiting_user` and wait for the user to click continue.
- When automatic upload is enabled, continue immediately.

### Upload

- Start the existing upload task with the selected files.
- Keep the external verification behavior: the user enters the SMS code in the platform popup.
- Poll upload status until it completes, fails, stops, or requires user action.
- Noncompliant songs are removed from the platform upload form by the existing upload flow; local MP3 files remain untouched.

### Report

Produce a compact run report:

- total songs
- lyric successes/failures
- generation successes/failures
- downloaded file paths
- uploaded paths
- removed-from-upload paths when available
- failed stage and error for each failed song

## State Model

Persist one current pipeline run in `data/pipeline_state.json`.

Run fields:

- `run_id`
- `account_id`
- `template_id`
- `day`
- `pause_before_upload`
- `status`: `running`, `waiting_user`, `completed`, `failed`, `stopped`
- `stage`: `lyrics`, `generation`, `pre_upload`, `upload`, `report`
- `song_states`
- `error`
- `created_at`
- `updated_at`

Song fields:

- `song_name`
- `lyric_file`
- `lyrics_status`
- `generation_status`
- `output_path`
- `upload_status`
- `upload_removed`
- `error`

## Resume Rules

- Existing valid lyric files with the same song name are reused.
- Songs with valid downloaded MP3 files skip generation.
- Generation retries only missing or failed outputs.
- Upload selects only current-day MP3 files that have not already been uploaded.
- A stop request finishes the current safe step and persists state.
- Resume continues from the first incomplete stage.

## API

Add pipeline endpoints without changing existing endpoints:

- `POST /api/pipeline/runs`
- `GET /api/pipeline/runs/current`
- `POST /api/pipeline/runs/resume`
- `POST /api/pipeline/runs/stop`

## UI

Add a pipeline panel to 任务管理:

- account selector
- lyric template selector
- generation count
- `生成完成后暂停确认` toggle
- start/resume/stop buttons
- stage progress
- per-song stage table
- final report summary

The existing stage tabs and single-stage buttons remain.

## Error Handling

- Missing account/template: fail before starting.
- API lyric failure: retry through existing AI retry settings, then mark failed songs.
- No downloadable songs: stop before upload with a clear report.
- Generation limit: keep successful outputs and stop before upload.
- Login required: set `waiting_user` and show the account login action.
- Upload failure: preserve local files and record the platform error.

## Compatibility

- No existing endpoint is removed.
- Existing task and upload state files remain unchanged.
- Pipeline state is additive.
- Existing single-stage UI controls continue to work.
- Full backend and frontend regression tests must pass before release.

## Testing

Add focused tests for:

1. Pipeline state transitions.
2. Lyric failure isolation.
3. Generation output reuse.
4. Pause before upload.
5. Automatic upload continuation.
6. Stop and resume.
7. Existing AI lyric endpoints unchanged.
8. Existing generation task behavior unchanged.
9. Existing upload task behavior unchanged.

