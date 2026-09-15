# -*- coding: utf-8 -*-
# flake8: noqa: E501
# pylint: disable=redefined-outer-name,unused-argument
# ``config_path`` is an environmental fixture: the test body never reads it,
# but without it these writes would land on the developer's real config.
"""Platform one-click configuration: the browser-fetched key lands on the
proxy-served sections only, and never on a section the proxy cannot serve."""

from __future__ import annotations

import asyncio
import json

import pytest

from api import model_routes
from domain.errors import ValidationError

_CHAT_URL = "https://platform-pre.agentscope.io/v1/chat/completions"
_PROXIED = ("llm", "vlm", "image", "video", "tts", "asr")


def _section(**overrides) -> dict:
    section = {
        "enabled": False,
        "model_name": "",
        "api_key": "",
        "base_url": "",
        "protocol": "OpenAI 协议",
        "custom_protocol": "",
    }
    section.update(overrides)
    return section


def _config() -> dict:
    """A fresh container: only the text lane has a model chosen."""
    return {
        "llm": _section(
            enabled=True,
            model_name="qwen3.8-flash",
            api_key="old",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        ),
        "vlm": _section(use_llm=True),
        "image": _section(),
        "video": _section(),
        "tts": _section(protocol="DashScope（百炼）"),
        "asr": _section(),
        "s2v": _section(
            protocol="DashScope（百炼）",
            base_url="https://dashscope.aliyuncs.com/api/v1",
            api_key="bailian-key",
        ),
        "embedding": _section(
            protocol="DashScope（百炼）",
            base_url="https://dashscope.aliyuncs.com/api/v1",
            api_key="bailian-key",
        ),
        "grounding": _section(reuse_llm=True, tavily_api_key="tvly"),
    }


@pytest.fixture()
def config_path(tmp_path, monkeypatch):
    monkeypatch.setenv("CREATOR_DATA_ROOT", str(tmp_path.resolve()))
    path = (tmp_path / "config" / "model_config.json").resolve()
    monkeypatch.setenv("CREATOR_MODEL_CONFIG_PATH", str(path))
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(_config()), encoding="utf-8")
    return path


def _apply(api_key: str = "sk-as-issued", chat_url: str = _CHAT_URL) -> dict:
    return asyncio.run(
        model_routes.platform_autoconfigure(
            {"api_key": api_key, "chat_completions_url": chat_url},
        ),
    )


def test_the_issued_key_reaches_every_proxied_section(config_path) -> None:
    _apply()

    loaded = model_routes.load_model_config(include_environment=False)
    for name in _PROXIED:
        item = getattr(loaded, name)
        assert item.protocol == "AgentScope Platform", name
        assert item.api_key == "sk-as-issued", name
        # The chat suffix is stripped: sections other than the text lane
        # address the proxy API root, not one endpoint inside it.
        assert item.base_url == "https://platform-pre.agentscope.io/v1", name

    persisted = json.loads(config_path.read_text(encoding="utf-8"))
    assert persisted["video"]["base_url"].endswith("/v1")


def test_only_a_section_with_a_model_is_switched_on(config_path) -> None:
    # Enabling a section with no model would turn a missing setting into a
    # failed generation task, so the report is what tells the operator.
    result = _apply()

    loaded = model_routes.load_model_config(include_environment=False)
    assert loaded.llm.enabled is True
    assert loaded.video.enabled is False

    by_section = {row["section"]: row for row in result["sections"]}
    assert by_section["llm"] == {
        "section": "llm",
        "model_name": "qwen3.8-flash",
        "ready": True,
    }
    assert by_section["tts"]["ready"] is False
    assert by_section["tts"]["model_name"] == ""


def test_sections_the_proxy_cannot_serve_keep_their_own_backend(
    config_path,
) -> None:
    _apply()

    loaded = model_routes.load_model_config(include_environment=False)
    for name in ("s2v", "embedding"):
        item = getattr(loaded, name)
        assert item.protocol == "DashScope（百炼）", name
        assert item.api_key == "bailian-key", name
    assert loaded.grounding.tavily_api_key == "tvly"


def test_a_foreign_endpoint_is_refused_before_it_lands(config_path) -> None:
    # This value selects the media transport and the retry verdict of every
    # section it is written into, so a lookalike URL must not pass.
    with pytest.raises(ValidationError):
        _apply(chat_url="https://evil.test/v1/chat/completions")

    loaded = model_routes.load_model_config(include_environment=False)
    assert loaded.llm.api_key == "old"


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"api_key": "", "chat_completions_url": _CHAT_URL}, "api_key"),
        ({"api_key": "sk-as-issued", "chat_completions_url": ""}, "chat"),
    ],
)
def test_an_incomplete_platform_response_writes_nothing(
    config_path,
    payload,
    expected,
) -> None:
    with pytest.raises(ValidationError) as excinfo:
        asyncio.run(model_routes.platform_autoconfigure(payload))

    assert expected in str(excinfo.value)
    loaded = model_routes.load_model_config(include_environment=False)
    assert loaded.llm.api_key == "old"
