# -*- coding: utf-8 -*-
# pylint: disable=use-implicit-booleaness-not-comparison,protected-access
from __future__ import annotations

import asyncio
import json
from pathlib import Path
import threading
import time

import httpx
from fastapi import FastAPI
import pytest

from api.dependencies import creator_error_handler
from api import model_routes
from domain.errors import CreatorError, ValidationError
from schemas.models import ModelConfigData


router = model_routes.router


def _config(model_name: str = "qwen-plus") -> dict:
    return {
        "llm": {
            "enabled": True,
            "model_name": model_name,
            "api_key": "secret",
            "base_url": "https://example.test/v1",
            "protocol": "OpenAI 协议",
            "custom_protocol": "",
            "multimodal": False,
        },
        "vlm": {
            "enabled": False,
            "model_name": "",
            "api_key": "",
            "base_url": "",
            "protocol": "OpenAI 协议",
            "custom_protocol": "",
            "use_llm": True,
            "multimodal": False,
        },
        "grounding": {
            "enabled": True,
            "model_name": "",
            "api_key": "",
            "base_url": "",
            "protocol": "OpenAI 协议",
            "custom_protocol": "",
            "reuse_llm": True,
            "tavily_api_key": "tvly-test",
        },
        "asr": {
            "enabled": False,
            "model_name": "fun-asr",
            "api_key": "",
            "base_url": "https://example.test/asr",
            "protocol": "DashScope Fun-ASR",
            "custom_protocol": "",
            "provider": "fun-asr",
            "language": "",
            "reuse_llm_key": True,
        },
        "image": {
            "enabled": False,
            "model_name": "",
            "api_key": "",
            "base_url": "",
            "protocol": "OpenAI 协议",
            "custom_protocol": "",
        },
        "video": {
            "enabled": False,
            "model_name": "",
            "api_key": "",
            "base_url": "",
            "protocol": "OpenAI 协议",
            "custom_protocol": "",
        },
        "oss": {
            "enabled": False,
            "access_key_id": "oss-access-id",
            "access_key_secret": "oss-access-secret",
            "endpoint": "oss-cn-hangzhou.aliyuncs.com",
            "bucket": "creator-media",
            "public_base_url": "https://media.example.test",
            "policy_api_key": "oss-policy-secret",
        },
        "executionAuthorization": {"mode": "required"},
    }


def test_enabled_grounding_requires_global_or_override_llm() -> None:
    missing = _config()
    missing["llm"]["api_key"] = ""
    with pytest.raises(ValidationError, match="Grounding 默认启用"):
        model_routes._ensure_grounding_model_configured(
            ModelConfigData.model_validate(missing),
        )

    override = _config()
    override["llm"]["api_key"] = ""
    override["grounding"].update(
        {
            "reuse_llm": False,
            "api_key": "grounding-key",
            "base_url": "https://grounding.example.test/v1",
            "model_name": "grounding-qwen",
        },
    )
    model_routes._ensure_grounding_model_configured(
        ModelConfigData.model_validate(override),
    )

    disabled = _config()
    disabled["llm"]["api_key"] = ""
    disabled["grounding"]["enabled"] = False
    model_routes._ensure_grounding_model_configured(
        ModelConfigData.model_validate(disabled),
    )


def test_grounding_accepts_generic_vlm_validation_with_tavily_search() -> None:
    payload = _config()
    payload["llm"].update(
        {
            "model_name": "generic-text-model",
            "base_url": "https://text.example.test/v1",
            "protocol": "OpenAI 协议",
        },
    )
    payload["vlm"].update(
        {
            "enabled": True,
            "use_llm": False,
            "model_name": "generic-vision-model",
            "api_key": "vision-key",
            "base_url": "https://vision.example.test/v1",
        },
    )
    payload["grounding"]["validation_source"] = "vlm"

    model_routes._ensure_grounding_model_configured(
        ModelConfigData.model_validate(payload),
    )


def test_grounding_rejects_non_search_llm_when_tavily_is_absent() -> None:
    payload = _config()
    payload["grounding"]["tavily_api_key"] = ""
    payload["llm"].update(
        {
            "model_name": "generic-text-model",
            "base_url": "https://text.example.test/v1",
            "protocol": "OpenAI 协议",
        },
    )

    with pytest.raises(ValidationError, match="不支持.*原生 web_search"):
        model_routes._ensure_grounding_model_configured(
            ModelConfigData.model_validate(payload),
        )


def test_load_migrates_legacy_grounding_model_to_search_and_validation(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CREATOR_DATA_ROOT", str(tmp_path.resolve()))
    config_path = (tmp_path / "config" / "model_config.json").resolve()
    monkeypatch.setenv("CREATOR_MODEL_CONFIG_PATH", str(config_path))
    payload = _config()
    payload["grounding"].update(
        {
            "reuse_llm": False,
            "model_name": "legacy-qwen",
            "api_key": "legacy-key",
            "base_url": ("https://dashscope.aliyuncs.com/compatible-mode/v1"),
            "protocol": "DashScope（百炼）",
        },
    )
    config_path.parent.mkdir(parents=True)
    config_path.write_text(json.dumps(payload), encoding="utf-8")

    loaded = model_routes.load_model_config(include_environment=False)

    assert loaded.grounding.validation_source == "custom"
    assert loaded.grounding.search_reuse_llm is False
    assert loaded.grounding.search_model_name == "legacy-qwen"
    assert loaded.grounding.search_api_key == "legacy-key"


def test_model_config_is_single_file_native_and_idempotent(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CREATOR_DATA_ROOT", str(tmp_path.resolve()))
    monkeypatch.setenv(
        "CREATOR_MODEL_CONFIG_PATH",
        str((tmp_path / "config" / "model_config.json").resolve()),
    )

    app = FastAPI()
    app.add_exception_handler(CreatorError, creator_error_handler)
    app.include_router(router)

    async def scenario():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            first = await client.post(
                "/models/config",
                headers={"Idempotency-Key": "config-1"},
                json=_config(),
            )
            replay = await client.post(
                "/models/config",
                headers={"Idempotency-Key": "config-1"},
                json=_config(),
            )
            drift = await client.post(
                "/models/config",
                headers={"Idempotency-Key": "config-1"},
                json=_config("other-model"),
            )
            loaded = await client.get("/models/config")
        return first, replay, drift, loaded

    first, replay, drift, loaded = asyncio.run(scenario())
    assert first.status_code == 200
    assert replay.status_code == 200
    assert replay.headers["x-idempotent-replay"] == "true"
    assert drift.status_code == 409
    assert loaded.status_code == 200
    assert loaded.json()["llm"]["model_name"] == "qwen-plus"
    assert loaded.json()["llm"]["api_key"] == "secret"
    assert loaded.json()["grounding"] == {
        "enabled": True,
        "model_name": "",
        "api_key": "",
        "base_url": "",
        "protocol": "OpenAI 协议",
        "custom_protocol": "",
        "reuse_llm": True,
        "validation_source": "llm",
        "tavily_api_key": "tvly-test",
        "native_search_enabled": True,
        "search_provider": "dashscope_qwen",
        "search_reuse_llm": True,
        "search_model_name": "",
        "search_api_key": "",
        "search_base_url": "",
        "search_protocol": "DashScope（百炼）",
    }
    assert loaded.json()["oss"] == {
        "enabled": False,
        "access_key_id": "oss-access-id",
        "access_key_secret": "oss-access-secret",
        "endpoint": "oss-cn-hangzhou.aliyuncs.com",
        "bucket": "creator-media",
        "public_base_url": "https://media.example.test",
        "policy_api_key": "oss-policy-secret",
    }

    config_path = tmp_path / "config" / "model_config.json"
    secrets_path = tmp_path / "config" / "model_config.secrets.json"
    persisted = json.loads(config_path.read_text(encoding="utf-8"))
    assert persisted["llm"]["api_key"] == "secret"
    assert persisted["oss"] == {
        "enabled": False,
        "access_key_id": "oss-access-id",
        "access_key_secret": "oss-access-secret",
        "bucket": "creator-media",
        "endpoint": "oss-cn-hangzhou.aliyuncs.com",
        "policy_api_key": "oss-policy-secret",
        "public_base_url": "https://media.example.test",
    }
    assert config_path.stat().st_mode & 0o777 == 0o600
    assert not secrets_path.exists()
    assert list(
        (tmp_path / "config" / "runtime" / "idempotency").rglob("*.json"),
    )
    assert not any(
        path.suffix.casefold() in {".db", ".sqlite", ".sqlite3"}
        for path in tmp_path.rglob("*")
    )


def test_concurrent_single_file_save_is_atomic_and_last_writer_wins(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CREATOR_DATA_ROOT", str(tmp_path.resolve()))
    monkeypatch.setenv(
        "CREATOR_MODEL_CONFIG_PATH",
        str((tmp_path / "config" / "model_config.json").resolve()),
    )
    model_routes.save_model_config(ModelConfigData.model_validate(_config()))

    updater_payload = _config("secret-updater")
    updater_payload["oss"]["access_key_secret"] = "latest-secret"
    updater = ModelConfigData.model_validate(updater_payload)
    second_payload = _config("second-writer")
    second_payload["llm"]["api_key"] = "second-api-key"
    second_payload["oss"]["access_key_secret"] = "second-oss-secret"
    second_payload["oss"]["policy_api_key"] = "second-policy-secret"
    second_writer = ModelConfigData.model_validate(second_payload)

    updater_holds_lock = threading.Event()
    allow_updater_to_finish = threading.Event()
    original_atomic_replace = model_routes.atomic_replace_bytes

    def delayed_atomic_replace(target, payload, **kwargs):
        original_atomic_replace(target, payload, **kwargs)
        if (
            threading.current_thread().name == "secret-updater"
            and Path(target).name == "model_config.json"
        ):
            updater_holds_lock.set()
            assert allow_updater_to_finish.wait(timeout=3)

    monkeypatch.setattr(
        model_routes,
        "atomic_replace_bytes",
        delayed_atomic_replace,
    )
    failures: list[BaseException] = []

    def save(data: ModelConfigData) -> None:
        try:
            model_routes.save_model_config(data)
        except BaseException as error:  # pragma: no cover - asserted below
            failures.append(error)

    first = threading.Thread(
        target=save,
        args=(updater,),
        name="secret-updater",
    )
    second = threading.Thread(
        target=save,
        args=(second_writer,),
        name="second-writer",
    )
    first.start()
    assert updater_holds_lock.wait(timeout=3)
    second.start()
    time.sleep(0.05)
    allow_updater_to_finish.set()
    first.join(timeout=3)
    second.join(timeout=3)

    assert not first.is_alive()
    assert not second.is_alive()
    assert failures == []
    persisted = json.loads(
        (tmp_path / "config" / "model_config.json").read_text(
            encoding="utf-8",
        ),
    )
    assert persisted["llm"]["api_key"] == "second-api-key"
    assert persisted["oss"]["access_key_secret"] == "second-oss-secret"
    assert persisted["oss"]["policy_api_key"] == "second-policy-secret"
    assert model_routes.load_model_config().llm.model_name == "second-writer"
