from __future__ import annotations

import asyncio
import json

import pytest

from schemas.observability import ObservabilityConfigData
from services.observability import (
    load_observability_config,
    observability_config_path,
    read_trace_records,
    save_observability_config,
    trace_event,
    trace_span,
)


def test_trace_span_persists_parent_context_redaction_and_error(tmp_path, monkeypatch):
    monkeypatch.setenv("CREATOR_DATA_ROOT", str(tmp_path / "creator-runtime"))
    monkeypatch.setenv("CREATOR_TRACE_DIR", str(tmp_path / "traces"))
    monkeypatch.setenv("CREATOR_TRACING_ENABLED", "true")
    monkeypatch.setenv("CREATOR_TRACE_CAPTURE_CONTENT", "false")

    async def scenario() -> None:
        async with trace_span(
            "test.root",
            component="test",
            sessionId="session-1",
            attributes={"apiKey": "top-secret", "content": "private prompt"},
        ):
            async with trace_span(
                "test.child",
                component="test",
                runId="run-1",
            ):
                trace_event(
                    "test.task",
                    component="test",
                    taskId="task-1",
                    attributes={"authorization": "Bearer secret"},
                )
            with pytest.raises(RuntimeError, match="boom"):
                async with trace_span("test.failure", component="test"):
                    raise RuntimeError("boom")

    asyncio.run(scenario())
    records = read_trace_records(filters={"sessionId": "session-1"}, limit=100)

    assert [item["name"] for item in records] == [
        "test.root.started",
        "test.child.started",
        "test.task",
        "test.child.finished",
        "test.failure.started",
        "test.failure.finished",
        "test.root.finished",
    ]
    trace_ids = {item["traceId"] for item in records}
    assert len(trace_ids) == 1
    child = next(item for item in records if item["name"] == "test.child.started")
    root = records[0]
    assert child["parentSpanId"] == root["spanId"]
    assert child["runId"] == "run-1"
    task = next(item for item in records if item["name"] == "test.task")
    assert task["taskId"] == "task-1"
    assert task["attributes"]["authorization"] == "[REDACTED]"
    assert root["attributes"]["apiKey"] == "[REDACTED]"
    assert root["attributes"]["content"] == {"redacted": True, "chars": 14}
    failure = next(item for item in records if item["name"] == "test.failure.finished")
    assert failure["status"] == "error"
    assert failure["attributes"]["errorType"] == "RuntimeError"
    assert failure["attributes"]["durationMs"] >= 0


def test_trace_reader_filters_limits_and_emits_logger(tmp_path, monkeypatch, caplog):
    monkeypatch.setenv("CREATOR_DATA_ROOT", str(tmp_path / "creator-runtime"))
    monkeypatch.setenv("CREATOR_TRACE_DIR", str(tmp_path / "traces"))
    monkeypatch.setenv("CREATOR_TRACING_ENABLED", "true")
    caplog.set_level("INFO", logger="qwenpaw.creator.trace")
    for index in range(5):
        trace_event(
            "test.record",
            component="test",
            sessionId="wanted" if index % 2 == 0 else "other",
            attributes={"index": index},
        )

    records = read_trace_records(filters={"sessionId": "wanted"}, limit=2)
    assert [item["attributes"]["index"] for item in records] == [2, 4]
    assert any('"name":"test.record"' in item.message for item in caplog.records)

    with pytest.raises(ValueError, match="between 1 and 2000"):
        read_trace_records(limit=0)


def test_observability_config_migrates_legacy_env_once_then_file_is_authoritative(
    tmp_path, monkeypatch
):
    data_root = tmp_path / "creator-runtime"
    monkeypatch.setenv("CREATOR_DATA_ROOT", str(data_root))
    monkeypatch.setenv("CREATOR_TRACING_ENABLED", "false")
    monkeypatch.setenv("CREATOR_TRACE_DIR", str(tmp_path / "legacy-traces"))
    monkeypatch.setenv("CREATOR_TRACE_LOG_LEVEL", "WARNING")
    monkeypatch.setenv("CREATOR_TRACE_CAPTURE_CONTENT", "true")

    migrated = load_observability_config()
    path = observability_config_path()
    assert migrated == ObservabilityConfigData(
        enabled=False,
        traceDirectory=str(tmp_path / "legacy-traces"),
        logLevel="WARNING",
        captureContent=True,
    )
    assert path == data_root / "config" / "observability.json"
    assert path.stat().st_mode & 0o777 == 0o600
    assert json.loads(path.read_text(encoding="utf-8"))["captureContent"] is True

    monkeypatch.setenv("CREATOR_TRACING_ENABLED", "true")
    assert load_observability_config().enabled is False

    save_observability_config(
        ObservabilityConfigData(
            enabled=True,
            traceDirectory="diagnostics/traces",
            logLevel="INFO",
            captureContent=False,
        )
    )
    saved = load_observability_config()
    assert saved.enabled is True
    assert saved.trace_directory == "diagnostics/traces"


def test_tracing_never_breaks_runtime_without_a_data_workspace(monkeypatch):
    monkeypatch.delenv("CREATOR_DATA_ROOT", raising=False)
    trace_event("test.no-root", component="test")

    async def scenario() -> None:
        async with trace_span("test.no-root-span", component="test"):
            pass

    asyncio.run(scenario())
