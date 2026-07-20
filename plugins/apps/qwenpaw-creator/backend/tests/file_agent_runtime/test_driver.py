# -*- coding: utf-8 -*-
# flake8: noqa: E501
# pylint: disable=line-too-long,protected-access,too-many-statements
# pylint: disable=unused-argument
from __future__ import annotations

import asyncio
import json

import pytest

from api.file_asset_routes import _AssetInput, _ingest_many_sync
from schemas.assets import SourceMediaMetadata, SourceModelRunRef
from services.file_agent_runtime import (
    AgentModelConfigurationError,
    AgentModelTurn,
    AgentRunStatus,
    AgentToolCall,
    CallbackAgentChatClient,
    FileCreatorAgentRuntime,
)
from services.file_agent_runtime.prompts import render_creator_system_prompt
from services.project_files.facade import CreatorFileServices
from services.project_files.models import Project
from services.project_files.review import ReviewDecisionItem
from services.runtime_files.atomic_store import AtomicJsonRecordStore
from services.runtime_files.models import (
    CreatorMessageRecord,
    MessageChannel,
    MessageClassification,
    RuntimeProjectState,
)
from services.runtime_files.execution_models import (
    ExecutionAuthorizationStatus,
)
from services.source_analysis import (
    SourceAnalyzerOutput,
    SourceMediaAnalysisService,
)
from services.specialist_tools import SpecialistToolResult


pytestmark = pytest.mark.unit


PROJECT_ID = "project-1"
SESSION_ID = "session-1"
CONVERSATION_ID = "conversation-1"
GOAL_ID = "goal-1"


def test_message_text_includes_exact_project_json_selection_locator() -> None:
    from services.file_agent_runtime.driver import _message_text

    message = CreatorMessageRecord(
        message_id="message-selection",
        project_id=PROJECT_ID,
        creator_session_id=SESSION_ID,
        conversation_id=CONVERSATION_ID,
        message_seq=1,
        role="user",
        content_parts=[{"type": "text", "text": "修改这段描述"}],
        metadata={
            "context": {
                "panel": "workbench",
                "selection": {
                    "ref": "unit:unit-1",
                    "field": "unit:unit-1/editPlan/storyboard/panel:panel-1/description",
                    "path": "/production/units_by_id/unit-1/plan/storyboard/items/panel-1/description",
                    "label": "VLM 分镜 1 · 描述",
                    "text": "猫跳上桌面",
                    "start": 0,
                    "end": 5,
                },
            },
        },
    )

    rendered = _message_text(message)

    assert rendered.startswith("修改这段描述\n[Creator UI 结构化上下文")
    assert '"ref":"unit:unit-1"' in rendered
    assert (
        '"field":"unit:unit-1/editPlan/storyboard/panel:panel-1/description"'
        in rendered
    )
    assert (
        '"path":"/production/units_by_id/unit-1/plan/storyboard/items/panel-1/description"'
        in rendered
    )


def test_ai_edit_idempotency_can_be_scoped_to_one_model_tool_call() -> None:
    from services.file_agent_runtime.driver import (
        _specialist_tool_recovery,
        _specialist_tool_invocation_id,
    )

    arguments = {
        "projectId": PROJECT_ID,
        "targetRef": "unit:unit-1",
        "arguments": {"operation": "execute"},
    }
    first = _specialist_tool_invocation_id(
        "specialist-run-1",
        "ai_edit",
        arguments,
        call_id="tool-call-1",
    )
    replay = _specialist_tool_invocation_id(
        "specialist-run-1",
        "ai_edit",
        arguments,
        call_id="tool-call-1",
    )
    retry = _specialist_tool_invocation_id(
        "specialist-run-1",
        "ai_edit",
        arguments,
        call_id="tool-call-2",
    )
    image_first = _specialist_tool_invocation_id(
        "specialist-run-1",
        "image_generation",
        arguments,
        call_id="tool-call-1",
    )
    image_retry = _specialist_tool_invocation_id(
        "specialist-run-1",
        "image_generation",
        arguments,
        call_id="tool-call-2",
    )

    assert first == replay
    assert retry != first
    assert image_retry == image_first
    assert "file_id=null" in _specialist_tool_recovery("ai_edit")


def _create_project(tmp_path, *, initial_goal: str | None):
    services = CreatorFileServices.create(tmp_path.resolve())

    def initialize(staged_root) -> None:
        services.sessions.initialize_staged_project(
            staged_root,
            PROJECT_ID,
            session_id=SESSION_ID,
            conversation_id=CONVERSATION_ID,
            initial_goal=initial_goal,
            goal_id=GOAL_ID if initial_goal is not None else None,
            initial_message_id="message-initial"
            if initial_goal is not None
            else None,
            initial_client_message_id=(
                "client-initial" if initial_goal is not None else None
            ),
        )

    snapshot = services.projects.create(
        Project.new(project_id=PROJECT_ID, name="Initial"),
        initialize_staged_project=initialize,
    )
    services.poller.note_commit(snapshot)
    return services, snapshot


def _edit_client(*, description: str):
    turn = 0

    async def callback(messages, tools):
        nonlocal turn
        assert {item["function"]["name"] for item in tools} == {
            "read_project",
            "read_project_file",
            "jq_project",
            "delegate_to_agent",
        }
        # The role prompt and static Pydantic schema form one stable system prompt.
        assert messages[0]["content"] == render_creator_system_prompt(
            project_id=PROJECT_ID,
        )
        assert "# Workspace 基础 Schema" in messages[0]["content"]
        assert "PROJECT_JSON_SCHEMA=" in messages[0]["content"]
        turn += 1
        if turn == 1:
            return AgentModelTurn(
                tool_calls=(
                    AgentToolCall(
                        call_id="read-1",
                        name="read_project",
                        arguments={"projectId": PROJECT_ID},
                    ),
                ),
            )
        if turn == 2:
            observed = json.loads(messages[-1]["content"])
            return AgentModelTurn(
                tool_calls=(
                    AgentToolCall(
                        call_id="write-1",
                        name="jq_project",
                        arguments={
                            "projectId": PROJECT_ID,
                            "baseEtag": observed["etag"],
                            "program": ".description = $description",
                            "stringArgs": {"description": description},
                        },
                    ),
                ),
            )
        return AgentModelTurn(content="项目说明已更新。")

    return CallbackAgentChatClient(callback)


async def _wait_for(predicate, *, timeout: float = 5.0) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not predicate():
        if loop.time() >= deadline:
            raise TimeoutError("condition was not reached")
        await asyncio.sleep(0.01)


def test_initial_creation_runs_auto_fix_tool_loop_without_review(
    tmp_path,
) -> None:
    async def scenario():
        services, _snapshot = _create_project(tmp_path, initial_goal="请完善项目说明")
        driver = FileCreatorAgentRuntime(
            services,
            model_client=_edit_client(description="由初始任务生成"),
            poll_interval_seconds=0.01,
        )
        await driver.start()
        driver.notify(PROJECT_ID)
        await _wait_for(
            lambda: services.sessions.get_project_session(
                PROJECT_ID,
            ).last_consumed_message_seq
            == 1,
        )
        await driver.wait_until_idle(PROJECT_ID)
        project = services.projects.read(PROJECT_ID)
        session = services.sessions.get_project_session(PROJECT_ID)
        goal = services.sessions.get_goal(PROJECT_ID, GOAL_ID)
        runs = driver.runs.list(PROJECT_ID)
        review = services.reviews.active(PROJECT_ID)
        messages = services.sessions.list_messages(PROJECT_ID, SESSION_ID)
        events = services.sessions.list_events(PROJECT_ID, SESSION_ID)
        await driver.stop()
        return project, session, goal, runs, review, messages, events

    project, session, goal, runs, review, messages, events = asyncio.run(
        scenario(),
    )
    assert project.project.description == "由初始任务生成"
    assert project.generation == 1
    assert review is None
    assert session.status.value == "IDLE"
    assert session.error is None
    assert goal.status.value == "COMPLETED"
    assert len(runs) == 1
    assert runs[0].status is AgentRunStatus.SUCCEEDED
    assert runs[0].origin.value == "initial_creation"
    assert runs[0].review_policy.value == "auto_fix"
    assert runs[0].tool_call_count == 2
    assert {item.role for item in messages} >= {"user", "assistant", "tool"}
    event_types = {item.event_type for item in events}
    assert {
        "agent.message_delta",
        "agent.tool_delta",
        "message.completed",
        "agent.tool_started",
        "agent.tool_completed",
    } <= event_types
    assistant_turns = [item for item in messages if item.role == "assistant"]
    tool_results = [item for item in messages if item.role == "tool"]
    assert all(
        "准备调用工具" not in str(part.text or "")
        for item in assistant_turns
        for part in item.content_parts
    )
    assert assistant_turns[0].source == "creator_agent"
    assert assistant_turns[0].metadata["actionId"] == "read-1"
    assert assistant_turns[0].metadata["toolCall"] == {
        "id": "read-1",
        "name": "read_project",
        "arguments": {"projectId": PROJECT_ID},
    }
    assert all(item.source == "runtime_action_result" for item in tool_results)
    assert all(
        isinstance(json.loads(item.content_parts[0].text or ""), dict)
        for item in tool_results
    )


def test_stream_persistence_failure_is_not_reported_as_a_model_failure(
    tmp_path,
    monkeypatch,
) -> None:
    async def callback(_messages, _tools) -> AgentModelTurn:
        return AgentModelTurn(content="完整结果")

    async def scenario():
        services, _snapshot = _create_project(tmp_path, initial_goal="请生成结果")
        driver = FileCreatorAgentRuntime(
            services,
            model_client=CallbackAgentChatClient(callback),
            poll_interval_seconds=0.01,
        )
        original_append_event = driver.sessions.append_event

        def append_event(*args, **kwargs):
            if kwargs.get("event_type") == "agent.message_delta":
                raise OSError("runtime lock timeout")
            return original_append_event(*args, **kwargs)

        monkeypatch.setattr(driver.sessions, "append_event", append_event)
        await driver.start()
        driver.notify(PROJECT_ID)
        await _wait_for(
            lambda: services.sessions.get_project_session(
                PROJECT_ID,
            ).status.value
            == "ERROR",
        )
        await driver.wait_until_idle(PROJECT_ID)
        session = services.sessions.get_project_session(PROJECT_ID)
        events = services.sessions.list_events(PROJECT_ID, SESSION_ID)
        await driver.stop()
        return session, events

    session, events = asyncio.run(scenario())

    assert session.error is not None
    assert session.error["code"] == "STREAM_PERSISTENCE_FAILED"
    assert session.error["retryable"] is True
    failed = [
        event for event in events if event.event_type == "agent.run.failed"
    ]
    assert failed[-1].payload["error"]["code"] == "STREAM_PERSISTENCE_FAILED"


def test_parent_authors_story_units_and_production_without_planning_specialists(
    tmp_path,
) -> None:
    turn = 0

    async def callback(messages, tools):
        nonlocal turn
        tool_names = {item["function"]["name"] for item in tools}
        assert tool_names == {
            "read_project",
            "read_project_file",
            "jq_project",
            "delegate_to_agent",
        }
        delegate = next(
            item
            for item in tools
            if item["function"]["name"] == "delegate_to_agent"
        )
        roles = delegate["function"]["parameters"]["properties"]["role"][
            "enum"
        ]
        assert "story_planning_agent" not in roles
        assert "unit_planning_routing_agent" not in roles

        turn += 1
        if turn == 1:
            return AgentModelTurn(
                tool_calls=(
                    AgentToolCall(
                        call_id="main-read",
                        name="read_project",
                        arguments={"projectId": PROJECT_ID},
                    ),
                ),
            )
        if turn == 2:
            observed = json.loads(messages[-1]["content"])
            story = {
                "title": "主 Agent 创建的项目",
                "outline": "理解任务后建立可执行结构",
                "narration": "",
                "sections": {
                    "items": {
                        "section-1": {
                            "section_id": "section-1",
                            "title": "主体",
                            "summary": "",
                            "narrative": "",
                            "script": "",
                            "voiceover": "",
                            "duration_budget_seconds": 15,
                            "pacing": "",
                            "constraints": [],
                            "transition": "",
                            "units": {
                                "items": {
                                    "unit-1": {
                                        "unit_id": "unit-1",
                                        "title": "剪辑单元",
                                        "route": "edit",
                                        "duration_seconds": 15,
                                        "narrative": "",
                                        "continuity": "",
                                        "source_refs": [],
                                        "character_refs": [],
                                        "scene_ref": None,
                                        "prop_refs": [],
                                        "shots": {"items": {}, "order": []},
                                    },
                                },
                                "order": ["unit-1"],
                            },
                        },
                    },
                    "order": ["section-1"],
                },
            }
            production = {
                "units_by_id": {
                    "unit-1": {
                        "route": "edit",
                        "intent": "",
                        "source_asset_version_ids": [],
                        "plan": None,
                        "storyboard_sheet_artifact_version_id": None,
                        "timeline_summary": "",
                        "subtitles_file_id": None,
                        "rendered_video_artifact_version_id": None,
                    },
                },
            }
            return AgentModelTurn(
                tool_calls=(
                    AgentToolCall(
                        call_id="main-write-structure",
                        name="jq_project",
                        arguments={
                            "projectId": PROJECT_ID,
                            "baseEtag": observed["etag"],
                            "program": ".story = $story | .production = $production",
                            "jsonArgs": {
                                "story": story,
                                "production": production,
                            },
                        },
                    ),
                ),
            )
        return AgentModelTurn(content="主 Agent 已建立 Story、Unit 与 Production。")

    async def scenario():
        services, _snapshot = _create_project(
            tmp_path,
            initial_goal="请创建一个剪辑项目结构",
        )
        driver = FileCreatorAgentRuntime(
            services,
            model_client=CallbackAgentChatClient(callback),
            poll_interval_seconds=0.01,
        )
        await driver.start()
        driver.notify(PROJECT_ID)
        await _wait_for(
            lambda: services.sessions.get_project_session(
                PROJECT_ID,
            ).last_consumed_message_seq
            == 1,
        )
        await driver.wait_until_idle(PROJECT_ID)
        project = services.projects.read(PROJECT_ID)
        specialist_runs = driver.executions.list_specialist_runs(PROJECT_ID)
        events = services.sessions.list_events(PROJECT_ID, SESSION_ID)
        await driver.stop()
        return project, specialist_runs, events

    project, specialist_runs, events = asyncio.run(scenario())
    assert project.project.story.title == "主 Agent 创建的项目"
    section = project.project.story.sections.items["section-1"]
    assert section.units.items["unit-1"].route.value == "edit"
    assert project.project.production.units_by_id["unit-1"].route == "edit"
    assert specialist_runs == []
    event_types = [item.event_type for item in events]
    assert "workspace.head_changed" in event_types
    assert not any(item.startswith("subagent.") for item in event_types)


def test_source_intelligence_receives_every_user_media_part_directly(
    tmp_path,
) -> None:
    parent_turn = 0
    observed_source_content: list[dict[str, object]] = []

    async def parent_callback(messages, tools):
        nonlocal parent_turn
        assert "delegate_to_agent" in {
            item["function"]["name"] for item in tools
        }
        parent_turn += 1
        if parent_turn == 1:
            return AgentModelTurn(
                tool_calls=(
                    AgentToolCall(
                        call_id="delegate-source",
                        name="delegate_to_agent",
                        arguments={
                            "role": "source_intelligence_agent",
                            "target_refs": ["asset:input-video"],
                            "task": "理解用户提交的全部素材。",
                        },
                    ),
                ),
            )
        return AgentModelTurn(content="素材理解 Agent 已收到原生素材。")

    async def source_callback(messages, tools):
        assert "analyze_source_media" in {
            item["function"]["name"] for item in tools
        }
        content = messages[1]["content"]
        assert isinstance(content, list)
        observed_source_content.extend(content)
        return AgentModelTurn(content="[SUCCESS]\n已直接观察全部用户素材。")

    async def scenario():
        services, _snapshot = _create_project(tmp_path, initial_goal=None)
        message = services.sessions.append_message(
            PROJECT_ID,
            SESSION_ID,
            CONVERSATION_ID,
            role="user",
            content_parts=[
                {"type": "text", "text": "请理解两个素材"},
                {
                    "type": "image_url",
                    "image_url": {"url": "https://cdn.example.com/input.png"},
                },
                {
                    "type": "video_url",
                    "video_url": {"url": "https://cdn.example.com/input.mp4"},
                },
            ],
            source="initial_creation",
            channel=MessageChannel.COMPOSER,
            classification=MessageClassification.MUTATION_INSTRUCTION,
        ).message
        services.sessions.create_goal(
            PROJECT_ID,
            SESSION_ID,
            CONVERSATION_ID,
            root_message_seq=message.message_seq,
            intent="请理解两个素材",
            goal_id=GOAL_ID,
        )
        driver = FileCreatorAgentRuntime(
            services,
            model_client=CallbackAgentChatClient(parent_callback),
            source_model_client=CallbackAgentChatClient(source_callback),
            poll_interval_seconds=0.01,
        )
        await driver.start()
        driver.notify(PROJECT_ID)
        await _wait_for(
            lambda: services.sessions.get_project_session(
                PROJECT_ID,
            ).last_consumed_message_seq
            == message.message_seq,
        )
        await driver.wait_until_idle(PROJECT_ID)
        specialist_runs = driver.executions.list_specialist_runs(PROJECT_ID)
        await driver.stop()
        return specialist_runs

    specialist_runs = asyncio.run(scenario())

    assert [item["type"] for item in observed_source_content] == [
        "text",
        "image_url",
        "video_url",
    ]
    assert observed_source_content[1]["image_url"] == {
        "url": "https://cdn.example.com/input.png",
    }
    assert observed_source_content[2]["video_url"] == {
        "url": "https://cdn.example.com/input.mp4",
    }
    assert len(specialist_runs) == 1
    assert specialist_runs[0].status.value == "FAILED"
    assert "current_intelligence_version_id" in (
        specialist_runs[0].final_summary_text or ""
    ) or "exactly one ProjectSource" in (
        specialist_runs[0].final_summary_text or ""
    )


def test_parent_reads_persisted_source_intelligence_and_links_project_structure(
    tmp_path,
    monkeypatch,
) -> None:
    class FakeAnalyzer:
        async def analyze(self, request):
            coverage = {
                "visual": {
                    "mode": "available",
                    "producer": "model_native",
                    "ratio": 1.0,
                },
                "asr": {
                    "mode": "unavailable",
                    "producer": None,
                    "ratio": None,
                },
                "ocr": {
                    "mode": "unavailable",
                    "producer": None,
                    "ratio": None,
                },
                "audio": {
                    "mode": "unavailable",
                    "producer": None,
                    "ratio": None,
                },
            }
            model_run = SourceModelRunRef(
                id="model-run-source-1",
                provider="fake",
                model="fake-vlm",
            )
            return SourceAnalyzerOutput(
                raw={
                    "summary": "海边日落中人物向镜头走来",
                    "coverage": coverage,
                    "shots": [],
                    "transcript": [],
                    "words": [],
                    "ocrSegments": [],
                    "audioEvents": [],
                    "entities": [],
                    "semanticEntries": [],
                },
                media=SourceMediaMetadata(
                    mediaKind="video",
                    mediaType="video/mp4",
                    durationMs=5000,
                    width=1920,
                    height=1080,
                ),
                model_runs=(model_run,),
                coverage_policy=coverage,
                provenance_refs=(request.evidence_ref,),
            )

    async def fake_model_upload(*_args, **_kwargs):
        return "https://model.example.com/source.mp4"

    monkeypatch.setattr(
        "services.file_agent_runtime.native_media.model_config.get_vlm_api_key",
        lambda: "configured",
    )
    monkeypatch.setattr(
        "services.file_agent_runtime.native_media.upload_local_file_to_dashscope_temp",
        fake_model_upload,
    )

    parent_turn = 0
    source_turn = 0
    asset_id = ""
    asset_version_id = ""
    source_id = ""
    read_intelligence = False

    async def parent_callback(messages, tools):
        nonlocal parent_turn, read_intelligence
        parent_turn += 1
        if parent_turn == 1:
            assert (
                f"asset-version:{asset_version_id}" in messages[-1]["content"]
            )
            return AgentModelTurn(
                tool_calls=(
                    AgentToolCall(
                        call_id="main-read-before-source",
                        name="read_project",
                        arguments={"projectId": PROJECT_ID},
                    ),
                ),
            )
        if parent_turn == 2:
            observed = json.loads(messages[-1]["content"])
            source = observed["project"]["sources"]["sources"]["items"][
                source_id
            ]
            assert source["selected_asset_version_id"] == asset_version_id
            return AgentModelTurn(
                tool_calls=(
                    AgentToolCall(
                        call_id="delegate-source-persisted",
                        name="delegate_to_agent",
                        arguments={
                            "role": "source_intelligence_agent",
                            "target_refs": [f"asset:{asset_id}"],
                            "task": "理解本轮上传素材并持久化 Source Intelligence。",
                        },
                    ),
                ),
            )
        if parent_turn == 3:
            delegated = json.loads(messages[-1]["content"])
            assert delegated["ok"] is True
            return AgentModelTurn(
                tool_calls=(
                    AgentToolCall(
                        call_id="main-reread-after-source",
                        name="read_project",
                        arguments={"projectId": PROJECT_ID},
                    ),
                ),
            )
        if parent_turn == 4:
            observed = json.loads(messages[-1]["content"])
            source = observed["project"]["sources"]["sources"]["items"][
                source_id
            ]
            intelligence_id = source["current_intelligence_version_id"]
            assert intelligence_id
            file_id = observed["project"]["assets"][
                "intelligence_versions_by_id"
            ][intelligence_id]["file_id"]
            return AgentModelTurn(
                tool_calls=(
                    AgentToolCall(
                        call_id="main-read-source-intelligence",
                        name="read_project_file",
                        arguments={
                            "projectId": PROJECT_ID,
                            "fileId": file_id,
                        },
                    ),
                ),
            )
        if parent_turn == 5:
            indexed = json.loads(messages[-1]["content"])
            assert "海边日落中人物向镜头走来" in indexed["content"]
            read_intelligence = True
            latest = next(
                json.loads(message["content"])
                for message in reversed(messages)
                if message.get("name") == "read_project"
            )
            story = {
                "title": "海边日落剪辑",
                "outline": "依据素材理解建立剪辑结构",
                "narration": "",
                "sections": {
                    "items": {
                        "section-source": {
                            "section_id": "section-source",
                            "title": "日落主体",
                            "summary": "海边日落中人物向镜头走来",
                            "narrative": "保留人物走向镜头的完整动作",
                            "script": "",
                            "voiceover": "",
                            "duration_budget_seconds": 5,
                            "pacing": "自然",
                            "constraints": [],
                            "transition": "",
                            "units": {
                                "items": {
                                    "unit-source": {
                                        "unit_id": "unit-source",
                                        "title": "素材剪辑",
                                        "route": "edit",
                                        "duration_seconds": 5,
                                        "narrative": "人物在日落海边走向镜头",
                                        "continuity": "",
                                        "source_refs": [source_id],
                                        "character_refs": [],
                                        "scene_ref": None,
                                        "prop_refs": [],
                                        "shots": {"items": {}, "order": []},
                                    },
                                },
                                "order": ["unit-source"],
                            },
                        },
                    },
                    "order": ["section-source"],
                },
            }
            production = {
                "units_by_id": {
                    "unit-source": {
                        "route": "edit",
                        "intent": "剪出人物在海边日落中走向镜头的段落",
                        "source_asset_version_ids": [asset_version_id],
                        "plan": None,
                        "storyboard_sheet_artifact_version_id": None,
                        "timeline_summary": "",
                        "subtitles_file_id": None,
                        "rendered_video_artifact_version_id": None,
                    },
                },
            }
            return AgentModelTurn(
                tool_calls=(
                    AgentToolCall(
                        call_id="main-link-source-structure",
                        name="jq_project",
                        arguments={
                            "projectId": PROJECT_ID,
                            "baseEtag": latest["etag"],
                            "program": ".story = $story | .production = $production",
                            "jsonArgs": {
                                "story": story,
                                "production": production,
                            },
                        },
                    ),
                ),
            )
        return AgentModelTurn(content="已根据素材理解建立剪辑项目结构。")

    async def source_callback(messages, tools):
        nonlocal source_turn
        source_turn += 1
        names = {item["function"]["name"] for item in tools}
        assert "analyze_source_media" in names
        if source_turn == 1:
            return AgentModelTurn(
                tool_calls=(
                    AgentToolCall(
                        call_id="analyze-source-persisted",
                        name="analyze_source_media",
                        arguments={
                            "projectId": PROJECT_ID,
                            "targetRef": f"asset:{asset_id}",
                            "arguments": {"force": False},
                        },
                    ),
                ),
            )
        if source_turn == 2:
            result = json.loads(messages[-1]["content"])
            assert result["status"] == "SUCCEEDED"
            return AgentModelTurn(
                tool_calls=(
                    AgentToolCall(
                        call_id="source-confirm-project",
                        name="read_project",
                        arguments={"projectId": PROJECT_ID},
                    ),
                ),
            )
        observed = json.loads(messages[-1]["content"])
        source = observed["project"]["sources"]["sources"]["items"][source_id]
        assert source["current_intelligence_version_id"]
        return AgentModelTurn(
            content="[SUCCESS]\n素材理解已持久化并关联 ProjectSource。",
        )

    async def scenario():
        nonlocal asset_id, asset_version_id, source_id
        services, _snapshot = _create_project(tmp_path, initial_goal=None)
        ingested, _ = _ingest_many_sync(
            services,
            project_id=PROJECT_ID,
            key="source-for-main-agent",
            inputs=[
                _AssetInput(
                    name="source.mp4",
                    content=b"verified-source",
                    media_type="video/mp4",
                ),
            ],
            attach_source=True,
            scope="main-agent-source-link-test",
        )
        asset_id = ingested["items"][0]["assetId"]
        asset_version_id = ingested["items"][0]["assetVersionId"]
        source_id = next(
            iter(
                services.projects.read(
                    PROJECT_ID,
                ).project.sources.sources.items,
            ),
        )
        analyzer_service = SourceMediaAnalysisService(
            services,
            analyzer=FakeAnalyzer(),
        )
        monkeypatch.setattr(
            "services.specialist_tools.source_analysis_service",
            lambda _services: analyzer_service,
        )
        message = services.sessions.append_message(
            PROJECT_ID,
            SESSION_ID,
            CONVERSATION_ID,
            role="user",
            content_parts=[{"type": "text", "text": "把上传素材剪成一个短视频"}],
            source="initial_creation",
            channel=MessageChannel.COMPOSER,
            classification=MessageClassification.MUTATION_INSTRUCTION,
            metadata={
                "assetVersionRefs": [f"asset-version:{asset_version_id}"],
            },
        ).message
        services.sessions.create_goal(
            PROJECT_ID,
            SESSION_ID,
            CONVERSATION_ID,
            root_message_seq=message.message_seq,
            intent="把上传素材剪成一个短视频",
            goal_id=GOAL_ID,
        )
        driver = FileCreatorAgentRuntime(
            services,
            model_client=CallbackAgentChatClient(parent_callback),
            source_model_client=CallbackAgentChatClient(source_callback),
            poll_interval_seconds=0.01,
        )
        await driver.start()
        driver.notify(PROJECT_ID)
        await _wait_for(
            lambda: services.sessions.get_project_session(
                PROJECT_ID,
            ).last_consumed_message_seq
            == message.message_seq,
        )
        await driver.wait_until_idle(PROJECT_ID)
        project = services.projects.read(PROJECT_ID).project
        specialist_runs = driver.executions.list_specialist_runs(PROJECT_ID)
        await driver.stop()
        return project, specialist_runs

    project, specialist_runs = asyncio.run(scenario())
    assert read_intelligence is True
    unit = project.story.sections.items["section-source"].units.items[
        "unit-source"
    ]
    assert unit.source_refs == [source_id]
    production = project.production.units_by_id["unit-source"]
    assert production.source_asset_version_ids == [asset_version_id]
    assert (
        project.sources.sources.items[
            source_id
        ].current_intelligence_version_id
        is not None
    )
    assert {item.role.value for item in specialist_runs} == {
        "source_intelligence_agent",
    }


def test_agentdock_boundary_is_carried_into_run_and_creates_review(
    tmp_path,
) -> None:
    async def scenario():
        services, snapshot = _create_project(tmp_path, initial_goal=None)
        root = services.root
        first = services.sessions.append_message(
            PROJECT_ID,
            SESSION_ID,
            CONVERSATION_ID,
            role="user",
            content_parts=[{"type": "text", "text": "初始目标"}],
            client_message_id="initial-client",
            source="initial_creation",
            channel=MessageChannel.COMPOSER,
            classification=MessageClassification.MUTATION_INSTRUCTION,
        ).message
        services.sessions.create_goal(
            PROJECT_ID,
            SESSION_ID,
            CONVERSATION_ID,
            root_message_seq=first.message_seq,
            intent="初始目标",
            goal_id=GOAL_ID,
        )
        services.sessions.mark_messages_consumed(
            PROJECT_ID,
            SESSION_ID,
            through_seq=first.message_seq,
            goal_id=GOAL_ID,
        )
        services.sessions.activate_run(
            PROJECT_ID,
            SESSION_ID,
            goal_id=GOAL_ID,
            run_id="old-run",
        )
        AtomicJsonRecordStore(
            root / PROJECT_ID / "runtime" / "state.json",
            RuntimeProjectState,
        ).write(
            RuntimeProjectState(
                project_id=PROJECT_ID,
                active_session_id=SESSION_ID,
                active_goal_id=GOAL_ID,
                last_project_generation=snapshot.generation,
                last_project_etag=snapshot.etag,
                accepted_generation=snapshot.generation,
                accepted_etag=snapshot.etag,
            ),
        )
        admitted = services.sessions.admit_user_request(
            PROJECT_ID,
            SESSION_ID,
            CONVERSATION_ID,
            request_id="interrupt-request",
            client_message_id="interrupt-message",
            content_parts=[{"type": "text", "text": "把说明改成审阅版本"}],
            channel=MessageChannel.AGENTDOCK,
            classification=MessageClassification.MUTATION_INSTRUCTION,
        )
        assert admitted.review_boundary is not None

        driver = FileCreatorAgentRuntime(
            services,
            model_client=_edit_client(description="等待用户审阅"),
            poll_interval_seconds=0.01,
        )
        await driver.start()
        driver.notify(PROJECT_ID)
        await _wait_for(
            lambda: services.sessions.get_project_session(
                PROJECT_ID,
            ).last_consumed_message_seq
            == admitted.message.message_seq,
        )
        await driver.wait_until_idle(PROJECT_ID)
        runs = driver.runs.list(PROJECT_ID)
        review = services.reviews.active(PROJECT_ID)
        pending_session = services.sessions.get_project_session(PROJECT_ID)
        assert review is not None
        resolved = services.reviews.decide(
            project_id=PROJECT_ID,
            review_id=review.review_id,
            decision_token=review.decision_token,
            decisions=[
                ReviewDecisionItem(
                    operation_id=operation.operation_id,
                    decision="ACCEPT",
                )
                for operation in review.operations
            ],
        )
        assert resolved.status.value == "RESOLVED"
        driver.notify(PROJECT_ID)
        await _wait_for(
            lambda: services.sessions.get_project_session(
                PROJECT_ID,
            ).status.value
            == "IDLE",
        )
        session = services.sessions.get_project_session(PROJECT_ID)
        goal = services.sessions.get_goal(PROJECT_ID, GOAL_ID)
        events = services.sessions.list_events(PROJECT_ID, SESSION_ID)
        await driver.stop()
        return admitted, runs, review, pending_session, session, goal, events

    (
        admitted,
        runs,
        review,
        pending_session,
        session,
        goal,
        events,
    ) = asyncio.run(
        scenario(),
    )
    run = runs[-1]
    assert run.origin.value == "agentdock_interrupt"
    assert run.review_policy.value == "require_review"
    assert run.review_boundary == admitted.review_boundary
    assert run.caused_by_request_id == admitted.review_boundary.request_id
    assert review is not None
    assert run.review_ids == [review.review_id]
    assert pending_session.status.value == "PENDING_REVIEW"
    assert session.status.value == "IDLE"
    assert goal.status.value == "COMPLETED"
    assert "agent.review.resolved" in {item.event_type for item in events}


def test_interrupt_revokes_stale_run_before_late_tool_commit(tmp_path) -> None:
    async def scenario():
        services, snapshot = _create_project(tmp_path, initial_goal="请修改项目")
        started = asyncio.Event()

        async def stubborn_model(_messages, _tools):
            started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                # Simulate a provider adapter that swallows cancellation and
                # returns a late mutation. The run epoch must still reject it.
                return AgentModelTurn(
                    tool_calls=(
                        AgentToolCall(
                            call_id="late-write",
                            name="jq_project",
                            arguments={
                                "projectId": PROJECT_ID,
                                "baseEtag": snapshot.etag,
                                "program": '.description = "must-not-commit"',
                            },
                        ),
                    ),
                )

        driver = FileCreatorAgentRuntime(
            services,
            model_client=CallbackAgentChatClient(stubborn_model),
            poll_interval_seconds=0.01,
        )
        await driver.start()
        driver.notify(PROJECT_ID)
        await asyncio.wait_for(started.wait(), timeout=2.0)
        interrupted = await driver.interrupt(PROJECT_ID, reason="test-stop")
        await driver.wait_until_idle(PROJECT_ID)
        project = services.projects.read(PROJECT_ID)
        session = services.sessions.get_project_session(PROJECT_ID)
        run = driver.runs.list(PROJECT_ID)[0]
        await driver.stop()
        return interrupted, project, session, run

    interrupted, project, session, run = asyncio.run(scenario())
    assert interrupted is True
    assert project.generation == 0
    assert project.project.description == ""
    assert run.status is AgentRunStatus.CANCELLED
    assert session.status.value == "CANCELLED"
    assert session.last_consumed_message_seq == 1


def test_interrupt_returns_before_slow_task_cleanup_finishes(tmp_path) -> None:
    async def scenario():
        services, _snapshot = _create_project(tmp_path, initial_goal="请修改项目")
        started = asyncio.Event()
        cleanup_started = asyncio.Event()
        release_cleanup = asyncio.Event()

        async def slow_cancel_model(_messages, _tools):
            started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cleanup_started.set()
                await release_cleanup.wait()
                raise

        driver = FileCreatorAgentRuntime(
            services,
            model_client=CallbackAgentChatClient(slow_cancel_model),
            poll_interval_seconds=0.01,
        )
        await driver.start()
        driver.notify(PROJECT_ID)
        await asyncio.wait_for(started.wait(), timeout=2.0)

        interrupted = await asyncio.wait_for(
            driver.interrupt(PROJECT_ID, reason="test-stop"),
            timeout=0.2,
        )
        await asyncio.wait_for(cleanup_started.wait(), timeout=2.0)
        still_active = PROJECT_ID in driver._active
        release_cleanup.set()
        await driver.wait_until_idle(PROJECT_ID)
        session = services.sessions.get_project_session(PROJECT_ID)
        await driver.stop()
        return interrupted, still_active, session

    interrupted, still_active, session = asyncio.run(scenario())
    assert interrupted is True
    assert still_active is True
    assert session.status.value == "CANCELLED"


def test_redundant_supersede_preserves_pending_replacement_message(
    tmp_path,
) -> None:
    async def scenario():
        services, snapshot = _create_project(
            tmp_path,
            initial_goal="先完成原始任务",
        )
        services.sessions.mark_messages_consumed(
            PROJECT_ID,
            SESSION_ID,
            through_seq=1,
            goal_id=GOAL_ID,
        )
        services.sessions.activate_run(
            PROJECT_ID,
            SESSION_ID,
            goal_id=GOAL_ID,
            run_id="old-run",
        )
        AtomicJsonRecordStore(
            services.root / PROJECT_ID / "runtime" / "state.json",
            RuntimeProjectState,
        ).write(
            RuntimeProjectState(
                project_id=PROJECT_ID,
                active_session_id=SESSION_ID,
                active_goal_id=GOAL_ID,
                last_project_generation=snapshot.generation,
                last_project_etag=snapshot.etag,
                accepted_generation=snapshot.generation,
                accepted_etag=snapshot.etag,
            ),
        )
        admitted = services.sessions.admit_user_request(
            PROJECT_ID,
            SESSION_ID,
            CONVERSATION_ID,
            request_id="replacement-request",
            client_message_id="replacement-message",
            content_parts=[{"type": "text", "text": "把片段缩短两秒"}],
            channel=MessageChannel.AGENTDOCK,
            classification=MessageClassification.MUTATION_INSTRUCTION,
        )
        assert admitted.review_boundary is not None
        services.sessions.clear_active_run(
            PROJECT_ID,
            SESSION_ID,
            expected_run_id="old-run",
            status="RESUMING",
        )

        async def replacement_model(_messages, _tools):
            return AgentModelTurn(content="替代请求已完成。")

        driver = FileCreatorAgentRuntime(
            services,
            model_client=CallbackAgentChatClient(replacement_model),
            poll_interval_seconds=0.01,
        )
        interrupted = await driver.interrupt(
            PROJECT_ID,
            superseded=True,
            reason="agentdock_interrupt",
        )
        pending = services.sessions.get_project_session(PROJECT_ID)
        events_before_start = services.sessions.list_events(
            PROJECT_ID,
            SESSION_ID,
        )

        await driver.start()
        driver.notify(PROJECT_ID)
        await _wait_for(
            lambda: services.sessions.get_project_session(
                PROJECT_ID,
            ).last_consumed_message_seq
            == admitted.message.message_seq,
        )
        await driver.wait_until_idle(PROJECT_ID)
        session = services.sessions.get_project_session(PROJECT_ID)
        runs = driver.runs.list(PROJECT_ID)
        events = services.sessions.list_events(PROJECT_ID, SESSION_ID)
        await driver.stop()
        return (
            interrupted,
            admitted,
            pending,
            session,
            runs,
            events_before_start,
            events,
        )

    (
        interrupted,
        admitted,
        pending,
        session,
        runs,
        events_before_start,
        events,
    ) = asyncio.run(scenario())

    assert interrupted is False
    assert pending.status.value == "RESUMING"
    assert pending.last_consumed_message_seq == 1
    assert pending.last_message_seq == admitted.message.message_seq == 2
    assert "agent.interrupt.idle" not in {
        item.event_type for item in events_before_start
    }
    assert session.status.value == "IDLE"
    assert session.last_consumed_message_seq == admitted.message.message_seq
    assert len(runs) == 1
    assert runs[0].status is AgentRunStatus.SUCCEEDED
    assert runs[0].origin.value == "agentdock_interrupt"
    assert runs[0].caused_by_message_seq == admitted.message.message_seq
    assert "agent.interrupt.idle" not in {item.event_type for item in events}


def test_agentdock_message_after_interrupt_reuses_goal_and_conversation_context(
    tmp_path,
) -> None:
    async def scenario():
        services, _snapshot = _create_project(
            tmp_path,
            initial_goal="先完成猫咪短片的素材整理",
        )
        first_started = asyncio.Event()
        observed_user_contexts: list[str] = []

        async def model(messages, _tools):
            user_context = str(messages[1]["content"])
            observed_user_contexts.append(user_context)
            if len(observed_user_contexts) == 1:
                first_started.set()
                await asyncio.Event().wait()
            return AgentModelTurn(content="已继承原任务并继续完成剪辑。")

        driver = FileCreatorAgentRuntime(
            services,
            model_client=CallbackAgentChatClient(model),
            poll_interval_seconds=0.01,
        )
        await driver.start()
        driver.notify(PROJECT_ID)
        await asyncio.wait_for(first_started.wait(), timeout=2.0)
        await driver.interrupt(PROJECT_ID, reason="user-stop")
        await driver.wait_until_idle(PROJECT_ID)

        stopped = services.sessions.get_project_session(PROJECT_ID)
        stopped_goal = services.sessions.get_goal(PROJECT_ID, GOAL_ID)
        admitted = services.sessions.admit_user_request(
            PROJECT_ID,
            SESSION_ID,
            CONVERSATION_ID,
            request_id="continue-request",
            client_message_id="continue-message",
            content_parts=[{"type": "text", "text": "继续刚才的任务，开始剪辑。"}],
            channel=MessageChannel.AGENTDOCK,
            classification=MessageClassification.MUTATION_INSTRUCTION,
        )
        driver.notify(PROJECT_ID)
        await _wait_for(
            lambda: services.sessions.get_project_session(
                PROJECT_ID,
            ).last_consumed_message_seq
            == admitted.message.message_seq,
        )
        await driver.wait_until_idle(PROJECT_ID)

        resumed = services.sessions.get_project_session(PROJECT_ID)
        resumed_goal = services.sessions.get_goal(PROJECT_ID, GOAL_ID)
        runs = driver.runs.list(PROJECT_ID)
        messages = services.sessions.list_messages(PROJECT_ID, SESSION_ID)
        await driver.stop()
        return (
            stopped,
            stopped_goal,
            admitted,
            resumed,
            resumed_goal,
            runs,
            messages,
            observed_user_contexts,
        )

    (
        stopped,
        stopped_goal,
        admitted,
        resumed,
        resumed_goal,
        runs,
        messages,
        observed_user_contexts,
    ) = asyncio.run(scenario())

    assert stopped.status.value == "CANCELLED"
    assert stopped.active_goal_id == GOAL_ID
    assert stopped_goal.status.value == "CANCELLED"
    assert admitted.message.conversation_id == CONVERSATION_ID
    assert resumed.status.value == "IDLE"
    assert resumed.active_goal_id == GOAL_ID
    assert resumed_goal.status.value == "COMPLETED"
    assert [item.goal_id for item in runs] == [GOAL_ID, GOAL_ID]
    assert [item.status for item in runs] == [
        AgentRunStatus.CANCELLED,
        AgentRunStatus.SUCCEEDED,
    ]
    assert len(observed_user_contexts) == 2
    continuation_context = observed_user_contexts[1]
    assert "CONVERSATION_HISTORY_JSON=" in continuation_context
    assert "先完成猫咪短片的素材整理" in continuation_context
    assert "CURRENT_USER_REQUEST=\n继续刚才的任务，开始剪辑。" in continuation_context
    assert [item.conversation_id for item in messages] == [
        CONVERSATION_ID,
        CONVERSATION_ID,
        CONVERSATION_ID,
    ]


def test_durable_interrupt_stops_remote_owner_without_restarting_message(
    tmp_path,
) -> None:
    async def scenario():
        services, _snapshot = _create_project(tmp_path, initial_goal="请修改项目")
        started = asyncio.Event()
        cancelled = asyncio.Event()

        async def blocking_model(_messages, _tools):
            started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.set()
                raise

        owner = FileCreatorAgentRuntime(
            services,
            model_client=CallbackAgentChatClient(blocking_model),
            poll_interval_seconds=0.01,
        )
        await owner.start()
        owner.notify(PROJECT_ID)
        await asyncio.wait_for(started.wait(), timeout=2.0)

        # Simulate the stop request landing in another QwenPaw process.  The
        # durable Session status is the cross-process signal; this coordinator
        # deliberately has no local handle for the active run.
        services.sessions.set_session_status(
            PROJECT_ID,
            SESSION_ID,
            "INTERRUPT_REQUESTED",
        )
        non_owner = FileCreatorAgentRuntime(
            services,
            model_client=CallbackAgentChatClient(blocking_model),
            poll_interval_seconds=0.01,
        )
        await non_owner.start()
        interrupted_locally = await non_owner.interrupt(
            PROJECT_ID,
            reason="remote-stop",
        )
        assert interrupted_locally is False

        await asyncio.wait_for(cancelled.wait(), timeout=2.0)
        await owner.wait_until_idle(PROJECT_ID)
        await asyncio.sleep(0.05)
        session = services.sessions.get_project_session(PROJECT_ID)
        runs = owner.runs.list(PROJECT_ID)
        await non_owner.stop()
        await owner.stop()
        return session, runs

    session, runs = asyncio.run(scenario())
    assert session.status.value == "CANCELLED"
    assert session.active_run_id is None
    assert session.last_consumed_message_seq == session.last_message_seq == 1
    assert len(runs) == 1
    assert runs[0].status is AgentRunStatus.CANCELLED


def test_missing_model_configuration_persists_session_error(tmp_path) -> None:
    async def scenario():
        services, _snapshot = _create_project(tmp_path, initial_goal="请修改项目")

        async def missing(_messages, _tools):
            raise AgentModelConfigurationError(
                "Creator text model configuration is incomplete: api_key",
            )

        driver = FileCreatorAgentRuntime(
            services,
            model_client=CallbackAgentChatClient(missing),
            poll_interval_seconds=0.01,
        )
        await driver.start()
        driver.notify(PROJECT_ID)
        await _wait_for(
            lambda: services.sessions.get_project_session(
                PROJECT_ID,
            ).status.value
            == "ERROR",
        )
        session = services.sessions.get_project_session(PROJECT_ID)
        goal = services.sessions.get_goal(PROJECT_ID, GOAL_ID)
        run = driver.runs.list(PROJECT_ID)[0]
        await driver.stop()
        return session, goal, run

    session, goal, run = asyncio.run(scenario())
    assert session.error is not None
    assert session.error["code"] == "MODEL_CONFIG_MISSING"
    assert "api_key" in session.error["message"]
    assert goal.status.value == "FAILED"
    assert run.status is AgentRunStatus.FAILED


def test_costly_specialist_tool_waits_for_file_authorization(
    tmp_path,
    monkeypatch,
) -> None:
    import services.file_agent_runtime.driver as driver_module

    monkeypatch.setattr(
        driver_module,
        "get_execution_authorization_mode",
        lambda: "required",
    )
    parent_turn = 0
    specialist_turn = 0

    async def callback(_messages, tools):
        nonlocal parent_turn, specialist_turn
        names = {item["function"]["name"] for item in tools}
        if "image_generation" in names:
            specialist_turn += 1
            if specialist_turn == 1:
                return AgentModelTurn(
                    tool_calls=(
                        AgentToolCall(
                            call_id="generate-image-1",
                            name="image_generation",
                            arguments={
                                "projectId": PROJECT_ID,
                                "targetRef": "asset:hero",
                                "arguments": {"prompt": "hero portrait"},
                            },
                        ),
                    ),
                )
            return AgentModelTurn(content="[SUCCESS]\n角色图已生成。")
        parent_turn += 1
        if parent_turn == 1:
            return AgentModelTurn(
                tool_calls=(
                    AgentToolCall(
                        call_id="delegate-visual-1",
                        name="delegate_to_agent",
                        arguments={
                            "role": "visual_development_agent",
                            "target_refs": ["asset:hero"],
                            "task": "生成角色图",
                        },
                    ),
                ),
            )
        return AgentModelTurn(content="视觉 Specialist 已完成。")

    async def scenario():
        services, _snapshot = _create_project(tmp_path, initial_goal="生成角色图")
        driver = FileCreatorAgentRuntime(
            services,
            model_client=CallbackAgentChatClient(callback),
            poll_interval_seconds=0.01,
        )

        async def fake_invoke(**_kwargs):
            return SpecialistToolResult(
                payload={
                    "ok": True,
                    "status": "SUCCEEDED",
                    "artifactVersionId": "artifact-version-1",
                },
            )

        driver.specialist_tools.invoke = fake_invoke  # type: ignore[method-assign]
        await driver.start()
        driver.notify(PROJECT_ID)
        await _wait_for(
            lambda: bool(
                driver.executions.list_execution_authorizations(PROJECT_ID),
            ),
        )
        authorization = driver.executions.list_execution_authorizations(
            PROJECT_ID,
        )[0]
        await _wait_for(
            lambda: driver.executions.get_specialist_run(
                PROJECT_ID,
                authorization.run_id,
            ).status.value
            == "WAITING_AUTHORIZATION",
        )
        waiting_run = driver.executions.get_specialist_run(
            PROJECT_ID,
            authorization.run_id,
        )
        driver.executions.decide_execution_authorization(
            PROJECT_ID,
            authorization.authorization_id,
            authorization_token=authorization.authorization_token,
            status=ExecutionAuthorizationStatus.APPROVED,
            decision={
                "provider": authorization.requested_provider,
                "model": authorization.requested_model,
                "maxCost": 0,
                "maxCandidates": 1,
            },
        )
        await _wait_for(
            lambda: services.sessions.get_project_session(
                PROJECT_ID,
            ).last_consumed_message_seq
            == 1,
        )
        await driver.wait_until_idle(PROJECT_ID)
        completed_run = driver.executions.get_specialist_run(
            PROJECT_ID,
            authorization.run_id,
        )
        events = services.sessions.list_events(PROJECT_ID, SESSION_ID)
        await driver.stop()
        return authorization, waiting_run, completed_run, events

    authorization, waiting_run, completed_run, events = asyncio.run(scenario())
    assert waiting_run.status.value == "WAITING_AUTHORIZATION"
    assert completed_run.status.value == "SUCCEEDED"
    assert authorization.operation == "image_generation"
    event_types = {item.event_type for item in events}
    assert "execution.authorization_required" in event_types
    assert "execution.authorization_decided" in event_types
