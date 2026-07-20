# -*- coding: utf-8 -*-
# flake8: noqa: E501
# pylint: disable=line-too-long,protected-access,too-many-branches
# pylint: disable=too-many-return-statements,too-many-statements
# pylint: disable=wrong-import-order
"""External-root model configuration and explicit provider connection probes."""

from __future__ import annotations

import io
import json
import os
import time
import wave
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, Body, Header, Request, Response, status

from domain.errors import ConflictError, StorageIntegrityError, ValidationError
from models import config as model_config
from schemas.models import (
    AsrConfig,
    ExecutionAuthorizationConfig,
    LlmConfig,
    ModelConfigData,
    ModelConfigItem,
    ModelConnectionTestRequest,
    ConnectionTestResponse,
    OssConfig,
    VlmConfig,
)
from services.runtime_files.atomic_store import (
    atomic_replace_bytes,
    canonical_json_bytes,
)
from services.runtime_files.errors import (
    IdempotencyConflictError,
    IdempotencyStateConflictError,
)
from services.runtime_files.idempotency_store import IdempotencyRecordStore
from services.runtime_files.locking import CrossProcessFileLock
from services.runtime_files.models import IdempotencyStatus
from services.file_agent_runtime import get_creator_agent_runtime
from services.storage_root import require_creator_data_root

from .dependencies import (
    CreatorErrorRoute,
    resolve_idempotency_key,
)

from utils.logger import setup_logger

logger = setup_logger("model_routes")

router = APIRouter(
    prefix="/models",
    tags=["models"],
    route_class=CreatorErrorRoute,
)


def _probe_wav() -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(b"\x00\x00" * 1600)
    return output.getvalue()


_SECTIONS = ("llm", "vlm", "asr", "image", "video", "oss")
_ENV_MAPPING: dict[str, dict[str, tuple[str, ...]]] = {
    "llm": {
        "base_url": ("TEXT_BASE_URL",),
        "api_key": ("TEXT_API_KEY",),
        "model_name": ("TEXT_MODEL_NAME",),
    },
    "vlm": {
        "base_url": ("VLM_BASE_URL", "TEXT_BASE_URL"),
        "api_key": ("VLM_API_KEY", "TEXT_API_KEY"),
        "model_name": ("VLM_MODEL_NAME", "TEXT_MODEL_NAME"),
    },
    "asr": {
        "base_url": ("ASR_BASE_URL",),
        "api_key": ("ASR_API_KEY",),
        "model_name": ("ASR_MODEL_NAME",),
    },
    "image": {
        "base_url": (
            "DASHSCOPE_IMAGE_BASE_URL",
            "OPENAI_IMAGE_BASE_URL",
            "IMAGE_BASE_URL",
        ),
        "api_key": (
            "DASHSCOPE_IMAGE_API_KEY",
            "OPENAI_IMAGE_API_KEY",
            "IMAGE_API_KEY",
        ),
        "model_name": (
            "DASHSCOPE_IMAGE_MODEL_NAME",
            "OPENAI_IMAGE_MODEL_NAME",
            "IMAGE_MODEL_NAME",
        ),
    },
    "video": {
        "base_url": ("VIDEO_BASE_URL",),
        "api_key": ("VIDEO_API_KEY",),
        "model_name": ("VIDEO_MODEL_NAME",),
    },
}


def _config_paths() -> Path:
    configured = os.environ.get("CREATOR_MODEL_CONFIG_PATH", "").strip()
    config_path = (
        Path(configured).expanduser().resolve(strict=False)
        if configured
        else require_creator_data_root() / "config" / "model_config.json"
    )
    root = require_creator_data_root().resolve()
    if not config_path.is_absolute() or not config_path.resolve(
        strict=False,
    ).is_relative_to(root):
        raise ValidationError(
            "CREATOR_MODEL_CONFIG_PATH 必须位于 CREATOR_DATA_ROOT 内",
        )
    return config_path


def _defaults() -> ModelConfigData:
    """Return an unconfigured form instead of pretending providers are loaded."""

    return ModelConfigData(
        llm=LlmConfig(
            enabled=True,
            protocol="OpenAI 协议",
            multimodal=False,
        ),
        vlm=VlmConfig(
            enabled=False,
            protocol="OpenAI 协议",
            use_llm=False,
            multimodal=False,
        ),
        asr=AsrConfig(
            enabled=False,
            provider="fun-asr",
            model_name="fun-asr",
            base_url="https://dashscope.aliyuncs.com/api/v1",
            protocol="DashScope Fun-ASR",
            reuse_llm_key=True,
        ),
        image=ModelConfigItem(
            enabled=False,
            protocol="OpenAI 协议",
        ),
        video=ModelConfigItem(
            enabled=False,
            protocol="Volcano Engine（火山引擎）",
        ),
        oss=OssConfig(),
        execution_authorization=ExecutionAuthorizationConfig(mode="required"),
    )


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"模型配置文件不可解析: {path.name}") from exc
    if not isinstance(value, dict):
        raise ValidationError(f"模型配置文件必须是 JSON object: {path.name}")
    return value


def load_model_config(*, include_environment: bool = True) -> ModelConfigData:
    """Load persisted configuration, optionally adding legacy environment fallback.

    Runtime callers keep supporting deployments configured through ``.env``.  The
    settings API passes ``include_environment=False`` so the UI reports only what
    the user has actually saved to ``model_config.json``.
    """

    config_path = _config_paths()
    base = _defaults().model_dump()
    with CrossProcessFileLock(config_path.parent / ".model-config.lock"):
        configs = _load_json(config_path)
    for section in _SECTIONS:
        config_section = configs.get(section)
        explicit: set[str] = set()
        if isinstance(config_section, dict):
            base[section].update(config_section)
            explicit.update(
                key
                for key, value in config_section.items()
                if value not in {None, ""}
            )
        if include_environment and section in _ENV_MAPPING:
            for field, env_names in _ENV_MAPPING[section].items():
                if field in explicit:
                    continue
                for name in env_names:
                    if os.environ.get(name):
                        base[section][field] = os.environ[name]
                        break
            if not isinstance(config_section, dict) and base[section].get(
                "model_name",
            ):
                base[section]["enabled"] = True
    authorization = configs.get("execution_authorization")
    if isinstance(authorization, dict):
        base["execution_authorization"].update(authorization)
    if base["vlm"].get("use_llm"):
        for field in ("base_url", "api_key", "model_name"):
            if not base["vlm"].get(field):
                base["vlm"][field] = base["llm"].get(field, "")
    return ModelConfigData.model_validate(base)


def save_model_config(data: ModelConfigData) -> None:
    config_path = _config_paths()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    payload = data.model_dump()
    with CrossProcessFileLock(config_path.parent / ".model-config.lock"):
        atomic_replace_bytes(
            config_path,
            canonical_json_bytes(payload) + b"\n",
        )
        os.chmod(config_path, 0o600)
    model_config._clear_user_config_cache()


def request_tool_configs() -> dict[str, dict[str, Any]]:
    data = load_model_config()
    configs: dict[str, dict[str, Any]] = {}
    mapping = {
        "llm": model_config.CREATOR_TEXT_CONFIG_TOOL,
        "vlm": model_config.CREATOR_VLM_CONFIG_TOOL,
        "asr": model_config.CREATOR_ASR_CONFIG_TOOL,
        "image": model_config.CREATOR_IMAGE_CONFIG_TOOL,
        "video": model_config.CREATOR_VIDEO_CONFIG_TOOL,
    }
    for section, tool_name in mapping.items():
        item = getattr(data, section)
        if not item.enabled or not item.model_name:
            continue
        tool_config: dict[str, Any] = {
            "api_key": item.api_key,
            "model": item.model_name,
            "base_url": item.base_url,
        }
        if section == "asr":
            tool_config.update(
                {
                    "provider": item.provider,
                    "language": item.language,
                    "reuse_llm_key": item.reuse_llm_key,
                },
            )
        if section == "image" and "dashscope" in item.protocol.casefold():
            tool_config["_image_backend"] = "DASHSCOPE"
        if section == "video":
            tool_config["_video_backend"] = (
                "seedance2"
                if "volcano" in item.protocol.casefold()
                or "火山" in item.protocol
                else "wan"
            )
        configs[tool_name] = tool_config
    return configs


def _qwenpaw_tool_configs(request: Request) -> dict[str, dict[str, Any]]:
    agent_id = request.headers.get("X-Agent-Id") or getattr(
        request.state,
        "agent_id",
        None,
    )
    if not agent_id:
        try:
            from qwenpaw.app.agent_context import get_current_agent_id

            agent_id = get_current_agent_id()
        except (ImportError, RuntimeError):
            return {}
    try:
        from qwenpaw.plugins.registry import PluginRegistry

        registry = PluginRegistry()
        return {
            name: value
            for name in model_config.CREATOR_CONFIG_TOOLS
            if (value := registry.get_tool_config(name, agent_id))
        }
    except (ImportError, AttributeError, RuntimeError):
        return {}


async def bind_creator_tool_config(request: Request):
    """Bind host config first, then fill only absent fields from external local config."""

    configs = _qwenpaw_tool_configs(request)
    for tool_name, local in request_tool_configs().items():
        merged = dict(local)
        merged.update(configs.get(tool_name) or {})
        configs[tool_name] = merged
    token = model_config.set_request_tool_configs(configs)
    try:
        yield
    finally:
        model_config.reset_request_tool_configs(token)


def _notify_agent_model_config_changed() -> None:
    runtime = get_creator_agent_runtime()
    if runtime is None:
        return
    for project in runtime.services.projects.list():
        runtime.notify(project.project_id)


async def _validate_model_connectivity(data: ModelConfigData) -> None:
    """Run connectivity probes for every enabled model with credentials. Raises ValidationError on failure."""

    failures: list[str] = []

    async with httpx.AsyncClient(timeout=30) as client:
        for section in ("llm", "vlm", "asr", "image", "video"):
            item = getattr(data, section)
            if not getattr(item, "enabled", False) or not item.model_name:
                continue
            api_key = item.api_key
            if (
                section == "asr"
                and getattr(item, "reuse_llm_key", False)
                and not api_key
            ):
                api_key = data.llm.api_key
            if not item.base_url or not api_key:
                failures.append(f"{section}: 缺少 Base URL 或 API Key")
                continue
            probe = ModelConnectionTestRequest(
                type=section,
                base_url=item.base_url,
                api_key=api_key,
                model_name=item.model_name,
                protocol=item.protocol,
                provider=getattr(item, "provider", None),
            )
            try:
                url, headers, payload = _probe_payload(probe)
                if payload.pop("_multipart_probe", False):
                    headers.pop("Content-Type", None)
                    resp = await client.post(
                        url,
                        headers=headers,
                        data={
                            "model": payload["model"],
                            "response_format": "json",
                        },
                        files={
                            "file": ("probe.wav", _probe_wav(), "audio/wav"),
                        },
                    )
                else:
                    resp = await client.post(
                        url,
                        headers=headers,
                        json=payload,
                    )
                if not resp.is_success:
                    try:
                        body = resp.json()
                        if isinstance(body, dict):
                            err_obj = body.get("error")
                            msg = (
                                err_obj.get("message")
                                if isinstance(err_obj, dict)
                                else body.get("message")
                                or body.get("error")
                                or str(body)
                            )
                        else:
                            msg = str(body)
                    except ValueError:
                        msg = resp.text[:200]
                    failures.append(
                        f"{section}: HTTP {resp.status_code}: {msg or '请求失败'}",
                    )
            except httpx.ConnectError:
                failures.append(f"{section}: 无法连接到服务，请检查 Base URL")
            except httpx.TimeoutException:
                failures.append(f"{section}: 连接超时，请检查网络或 Base URL")
            except (httpx.HTTPError, ValueError) as exc:
                failures.append(f"{section}: {exc}")

        oss = data.oss
        if (
            oss.enabled
            and oss.endpoint
            and oss.access_key_id
            and oss.access_key_secret
            and oss.bucket
        ):
            try:
                import oss2

                auth = oss2.Auth(oss.access_key_id, oss.access_key_secret)
                bucket = oss2.Bucket(auth, oss.endpoint, oss.bucket)
                bucket.get_bucket_info()
            except Exception as exc:
                exc_str = str(exc)
                if (
                    "InvalidAccessKeyId" in exc_str
                    or "AccessDenied" in exc_str
                ):
                    failures.append("OSS: Access Key 无效或权限不足")
                elif "NoSuchBucket" in exc_str:
                    failures.append("OSS: Bucket 不存在")
                elif (
                    "connect" in exc_str.lower()
                    or "timeout" in exc_str.lower()
                ):
                    failures.append("OSS: 无法连接到 OSS 服务")
                else:
                    failures.append(f"OSS: {exc_str}")

    if failures:
        raise ValidationError("以下模型连通性验证失败，请检查配置后重试：" + "；".join(failures))


@router.get("/config", response_model=ModelConfigData)
async def get_model_config() -> ModelConfigData:
    return load_model_config(include_environment=False)


@router.post("/config")
async def update_model_config(
    data: ModelConfigData,
    response: Response,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
) -> dict[str, bool]:
    key = resolve_idempotency_key(idempotency_key)
    root = require_creator_data_root() / "config" / "runtime" / "idempotency"
    records = IdempotencyRecordStore(root)
    payload = data.model_dump(mode="json", by_alias=True)
    request_hash = records.request_hash(payload)
    try:
        with records.operation_lock(
            owner_id="creator-model-config",
            scope="HTTP:model-config-update",
            idempotency_key=key,
        ):
            reservation = records.reserve(
                owner_id="creator-model-config",
                scope="HTTP:model-config-update",
                idempotency_key=key,
                request_hash=request_hash,
            )
            if reservation.record.status is IdempotencyStatus.COMPLETED:
                response.headers["X-Idempotent-Replay"] = "true"
                _notify_agent_model_config_changed()
                return {"ok": True}
            if reservation.record.status is IdempotencyStatus.FAILED:
                raise StorageIntegrityError(
                    "上一次模型配置写入失败，请使用新的 Idempotency-Key 重试",
                )
            data.llm.enabled = True
            await _validate_model_connectivity(data)
            save_model_config(data)
            _notify_agent_model_config_changed()
            records.complete(
                owner_id="creator-model-config",
                scope="HTTP:model-config-update",
                idempotency_key=key,
                request_hash=request_hash,
                response={"ok": True},
                response_status=status.HTTP_200_OK,
            )
    except IdempotencyConflictError as error:
        raise ConflictError("Idempotency-Key 已用于不同的模型配置") from error
    except IdempotencyStateConflictError as error:
        raise ConflictError("模型配置写入状态冲突") from error
    response.headers["X-Idempotent-Replay"] = "false"
    return {"ok": True}


def _probe_payload(
    body: ModelConnectionTestRequest,
) -> tuple[str, dict[str, str], dict[str, Any]]:
    base = body.base_url.rstrip("/")
    headers = {
        "Authorization": f"Bearer {body.api_key}",
        "Content-Type": "application/json",
    }
    if body.type == "asr":
        provider = body.provider or (
            "whisper" if "whisper" in body.protocol.casefold() else "fun-asr"
        )
        if provider == "whisper":
            return (
                f"{base}/audio/transcriptions",
                headers,
                {"_multipart_probe": True, "model": body.model_name},
            )
        headers["X-DashScope-Async"] = "enable"
        return (
            f"{base}/services/audio/asr/transcription",
            headers,
            {
                "model": body.model_name,
                "input": {
                    "file_urls": [
                        "https://dashscope.oss-cn-beijing.aliyuncs.com/samples/audio/paraformer/hello_world_female2.wav",
                    ],
                },
                "parameters": {},
            },
        )
    if body.type in {"llm", "vlm"}:
        content: Any = "Reply with pong only."
        if body.type == "vlm":
            content = [
                {"type": "text", "text": "Reply with red only."},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAIAAACQkWg2AAAAFklEQVR4nGO4I2JDEmIY1TCqYfhqAAAeBCwQ8YdREQAAAABJRU5ErkJggg==",
                    },
                },
            ]
        return (
            f"{base}/chat/completions",
            headers,
            {
                "model": body.model_name,
                "messages": [{"role": "user", "content": content}],
                "max_tokens": 8,
            },
        )
    if body.type == "image":
        if "dashscope" in body.protocol.casefold() or "百炼" in body.protocol:
            return (
                base,
                headers,
                {
                    "model": body.model_name,
                    "input": {
                        "messages": [
                            {"role": "user", "content": [{"text": "一枚红色圆点"}]},
                        ],
                    },
                    "parameters": {"size": "1024*1024", "n": 1},
                },
            )
        return (
            f"{base}/images/generations",
            headers,
            {
                "model": body.model_name,
                "prompt": "a red dot",
                "n": 1,
                "size": "1024x1024",
            },
        )
    if "volcano" in body.protocol.casefold() or "火山" in body.protocol:
        return (
            f"{base}/api/v3/contents/generations/tasks",
            headers,
            {
                "model": body.model_name,
                "content": [{"type": "text", "text": "a static red circle"}],
                "duration": 4,
                "resolution": "720p",
                "ratio": "16:9",
            },
        )
    headers["X-DashScope-Async"] = "enable"
    return (
        f"{base}/services/aigc/video-generation/video-synthesis",
        headers,
        {
            "model": body.model_name,
            "input": {"prompt": "a static red circle"},
            "parameters": {"duration": 4},
        },
    )


# Semantic diagnostic read: this performs no Creator/runtime/config mutation,
# so it is intentionally outside the mutating-route idempotency registry.
@router.post("/test", response_model=ConnectionTestResponse)
async def test_model_connection(
    body: ModelConnectionTestRequest = Body(...),
) -> ConnectionTestResponse:
    loaded = load_model_config()
    item = getattr(loaded, body.type)
    fallback_api_key = item.api_key
    if body.type == "asr" and item.reuse_llm_key and not fallback_api_key:
        fallback_api_key = loaded.llm.api_key
    selected = body.model_copy(
        update={
            "base_url": body.base_url or item.base_url,
            "api_key": body.api_key or fallback_api_key,
            "model_name": body.model_name or item.model_name,
            "protocol": body.protocol or item.protocol,
            "provider": body.provider or getattr(item, "provider", None),
        },
    )
    if (
        not selected.base_url
        or not selected.api_key
        or not selected.model_name
    ):
        return ConnectionTestResponse(
            ok=False,
            ms=0,
            error="配置不完整，请检查 Base URL、API Key 和模型名称",
        )
    start = time.monotonic()
    try:
        url, headers, payload = _probe_payload(selected)
        async with httpx.AsyncClient(timeout=30) as client:
            if payload.pop("_multipart_probe", False):
                headers.pop("Content-Type", None)
                response = await client.post(
                    url,
                    headers=headers,
                    data={
                        "model": payload["model"],
                        "response_format": "json",
                    },
                    files={"file": ("probe.wav", _probe_wav(), "audio/wav")},
                )
            else:
                response = await client.post(
                    url,
                    headers=headers,
                    json=payload,
                )
        elapsed = round((time.monotonic() - start) * 1000)
        if response.is_success:
            return ConnectionTestResponse(
                ok=True,
                ms=elapsed,
                detail="provider accepted the probe",
            )
        try:
            provider_body = response.json()
            if isinstance(provider_body, dict):
                err_obj = provider_body.get("error")
                if isinstance(err_obj, dict):
                    provider_error = (
                        err_obj.get("message")
                        or err_obj.get("type")
                        or str(err_obj)
                    )
                else:
                    provider_error = (
                        provider_body.get("message")
                        or provider_body.get("error")
                        or str(provider_body)
                    )
            else:
                provider_error = str(provider_body)
        except ValueError:
            provider_error = response.text[:300]
        return ConnectionTestResponse(
            ok=False,
            ms=elapsed,
            error=f"HTTP {response.status_code}: {provider_error or '请求失败'}",
        )
    except httpx.ConnectError:
        return ConnectionTestResponse(
            ok=False,
            ms=round((time.monotonic() - start) * 1000),
            error="无法连接到服务，请检查 Base URL 是否正确",
        )
    except httpx.TimeoutException:
        return ConnectionTestResponse(
            ok=False,
            ms=round((time.monotonic() - start) * 1000),
            error="连接超时，请检查网络或 Base URL",
        )
    except (httpx.HTTPError, ValueError) as exc:
        return ConnectionTestResponse(
            ok=False,
            ms=round((time.monotonic() - start) * 1000),
            error=str(exc),
        )


# Test the incoming config only. Not impacting the current backend config.
@router.post("/test-oss", response_model=ConnectionTestResponse)
async def test_oss_connection(
    body: OssConfig = Body(...),
) -> ConnectionTestResponse:
    if (
        not body.endpoint
        or not body.access_key_id
        or not body.access_key_secret
        or not body.bucket
    ):
        return ConnectionTestResponse(
            ok=False,
            ms=0,
            error="配置不完整，请检查 Endpoint、Access Key ID、Access Key Secret 和 Bucket",
        )
    try:
        import oss2

        auth = oss2.Auth(body.access_key_id, body.access_key_secret)
        bucket = oss2.Bucket(auth, body.endpoint, body.bucket)
        bucket.get_bucket_info()
        return ConnectionTestResponse(
            ok=True,
            detail="OSS bucket is reachable",
        )
    except Exception as exc:
        logger.warning("failed to test oss connection")
        exc_str = str(exc)
        if "InvalidAccessKeyId" in exc_str or "AccessDenied" in exc_str:
            return ConnectionTestResponse(
                ok=False,
                error="Access Key 无效或权限不足，请检查配置",
            )
        if "NoSuchBucket" in exc_str:
            return ConnectionTestResponse(
                ok=False,
                error="Bucket 不存在，请检查 Bucket 名称",
            )
        if "connect" in exc_str.lower() or "timeout" in exc_str.lower():
            return ConnectionTestResponse(
                ok=False,
                error="无法连接到 OSS 服务，请检查 Endpoint 和网络",
            )
        return ConnectionTestResponse(ok=False, error=exc_str)
