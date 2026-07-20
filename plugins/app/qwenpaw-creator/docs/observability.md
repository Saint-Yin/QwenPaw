# Creator runtime observability

Creator writes one structured JSON object per line to:

```text
${CREATOR_DATA_ROOT}/observability/traces/creator-trace-YYYY-MM-DD.jsonl
```

The same records are emitted through the `qwenpaw.creator.trace` logger, so a
live terminal and the persisted trace show the same execution facts. This is
diagnostic telemetry; `project.json` plus scoped Runtime JSON/JSONL records
remain the business-state source of truth.

## Find one task path

Every record contains `traceId`, `spanId`, and (for nested work)
`parentSpanId`. Records also carry every available business correlation id:
`projectId`, `sessionId`, `goalId`, `transactionId`, `assistantMessageId`,
`actionId`, `runId`, `taskId`, and `modelRunId`.

Use the Creator-owned read-only API to inspect the newest records:

```http
GET /creator/observability/traces?sessionId=session-...&limit=500
GET /creator/observability/traces?runId=run-...
GET /creator/observability/traces?taskId=task-...
GET /creator/observability/traces?traceId=trace-...
```

Standalone development uses the `/api/creator` prefix instead. Every Creator
HTTP response includes `X-Creator-Trace-ID` and `X-Request-ID`, which can be
copied directly into the query above.

For a URL-backed video edit, the normal path is visible in order:

```text
creator.http.request
  -> creator.asset_ingest.enqueued
  -> creator.asset_ingest.download_started/completed
  -> creator.asset_ingest.probe_completed/blob_stored/completed
  -> creator.model.requested/completed
  -> creator.action.parsed/dispatched (or creator.action.rejected with reason)
  -> creator.specialist.accepted
  -> creator.scheduler.runs_claimed
  -> creator.specialist.execute
  -> creator.specialist.model_requested/completed
  -> creator.runtime_action.dispatch + requested/completed
  -> creator.task.registered
  -> creator.ai_edit.build_plan + plan_started/completed
  -> creator.ai_edit.execute
  -> creator.ai_edit.ffmpeg_started
  -> creator.ai_edit.clip_started/completed (or clip_failed with stage)
  -> creator.ai_edit.concat_completed/ffmpeg_completed
  -> creator.runtime.continuation
  -> creator.specialist.execution_boundary
  -> creator.final_video.section_completed
  -> creator.final_video.completed
```

Each finished span records `durationMs`. Failed spans additionally record the
exception type, message, and bounded stack. Scheduler batches expose claimed
run ids and per-run status; runtime action and continuation records bridge a
SpecialistRun to its durable Task.

Idle 250 ms runtime polls are intentionally not persisted. A missing matching
`completed`/`finished` record after a `started`/`requested` record therefore
means the named real operation is still running or the process stopped; it is
not hidden among repeated no-op scheduler cycles.

## Configuration and safety

The authoritative configuration lives in the Creator Data Workspace:

```text
${CREATOR_DATA_ROOT}/config/observability.json
```

```json
{
  "enabled": true,
  "traceDirectory": "observability/traces",
  "logLevel": "INFO",
  "captureContent": false
}
```

Read or update it through Creator-owned APIs:

```http
GET  /creator/observability/config
POST /creator/observability/config
Idempotency-Key: <stable-key>
```

Standalone development uses the `/api/creator` prefix. The four old
`CREATOR_TRACING_*` / `CREATOR_TRACE_*` environment variables are deprecated
compatibility fallbacks: when the JSON file does not exist, their effective
values are migrated into it once. After that, the file is authoritative.

- `captureContent=false` is the safe default. Prompts, model output, thinking,
  deltas, and content are represented by character counts.
- Keys matching API key, authorization, cookie, password, secret, or token are
  always redacted.
- Files are created with mode `0600` and values/collections are bounded to
  prevent an accidental unbounded trace record.

Set `enabled` to `false` only when a benchmark must exclude local diagnostic
I/O.
