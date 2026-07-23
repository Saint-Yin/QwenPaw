# -*- coding: utf-8 -*-
# flake8: noqa: E501
# pylint: disable=line-too-long,raise-missing-from,too-many-branches
# pylint: disable=too-many-statements,wrong-import-order
"""Video model wrapper for DashScope Bailian Wan2.7 video synthesis."""

import asyncio
import json
import mimetypes
from pathlib import Path
import tempfile
from urllib.parse import urlparse
import uuid
import httpx
from typing import Optional
from models.concurrency import model_slot
from models import config as model_config
from models.media_transport import (
    DASHSCOPE_TEMP_UPLOAD_MAX_BYTES,
    SEEDANCE_REFERENCE_IMAGE_MAX_BYTES,
    read_reference_media,
    reference_media_data_url,
    upload_local_file_to_dashscope_temp,
)
from services.runtime_files.safe_remote_download import safe_download_to_file
from utils.paths import media_path_from_url
from utils.logger import setup_logger
from utils.exceptions import ModelError

logger = setup_logger("model.video")

MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 15  # seconds
SEEDANCE_RESOLUTIONS = {"480p", "720p", "1080p"}
SEEDANCE_RATIOS = {"16:9", "9:16", "1:1", "4:3", "3:4", "21:9", "auto"}
VIDEO_REFERENCE_SUFFIXES = {".mp4", ".mov", ".m4v", ".webm", ".avi", ".mkv"}


def _reference_media_kind(filename: str) -> str:
    suffix = Path(filename or "").suffix.lower()
    return "video" if suffix in VIDEO_REFERENCE_SUFFIXES else "image"


def _uses_seedance_protocol() -> bool:
    return model_config.get_video_backend() == "seedance2"


async def _resolve_reference_media_url(
    url: str,
    backend: str,
) -> tuple[str, str]:
    """Transport reference media through the provider-bound channel.

    Returns ``(resolved_url, media_kind)`` where *media_kind* is ``image`` or
    ``video``.

    wan (Bailian): official model-bound temporary upload -> ``oss://`` URL
    (48h TTL, <=1GB) for any media kind; the submit request already carries
    ``X-DashScope-OssResourceResolve: enable``.
    seedance2 (Volcengine Ark): reference images may be inlined as Base64
    data URLs (<30MB per image), but the task API only accepts public URLs
    or ``asset://`` IDs for ``video_url`` parts, so public HTTP(S) media is
    passed through untouched and local reference videos are rejected with
    an actionable error.
    """
    model_name = model_config.get_video_model_name()
    if url.startswith("/generated/"):
        filename = (
            Path(urlparse(url).path).name
            or f"reference-{uuid.uuid4().hex}.bin"
        )
    elif url.startswith("file://"):
        parsed = urlparse(url)
        media_path = Path(parsed.path)
        filename = media_path.name or f"reference-{uuid.uuid4().hex}.bin"
    elif url.startswith(("http://", "https://")):
        filename = (
            Path(urlparse(url).path).name
            or f"reference-{uuid.uuid4().hex}.bin"
        )
    else:
        raise ModelError(
            f"Reference media must be /generated, file://, http://, or https:// before provider-bound transport: {url}",
            model_name=model_name,
        )

    try:
        if backend == "seedance2" and url.startswith(("http://", "https://")):
            # Public URLs are the officially supported form for both image
            # and video reference parts; pass them through untouched.
            kind = _reference_media_kind(filename)
            logger.info(
                f"Passing public reference media through | backend={backend}, "
                f"filename={filename}, kind={kind}",
            )
            return url, kind
        kind = _reference_media_kind(filename)
        if backend == "wan":
            media_type = (
                mimetypes.guess_type(filename)[0]
                or "application/octet-stream"
            )
            if url.startswith(("http://", "https://")):
                with tempfile.TemporaryDirectory(
                    prefix="creator-reference-",
                ) as temporary_directory:
                    media_path = Path(temporary_directory) / filename
                    _, downloaded_type, _ = await asyncio.to_thread(
                        safe_download_to_file,
                        url,
                        media_path,
                        max_bytes=DASHSCOPE_TEMP_UPLOAD_MAX_BYTES,
                        timeout=httpx.Timeout(
                            connect=30.0,
                            read=300.0,
                            write=300.0,
                            pool=30.0,
                        ),
                    )
                    resolved_url = await upload_local_file_to_dashscope_temp(
                        media_path,
                        api_key=model_config.get_video_api_key(),
                        model_name=model_name,
                        media_type=downloaded_type or media_type,
                    )
            else:
                media_path = (
                    media_path_from_url(url)
                    if url.startswith("/generated/")
                    else Path(urlparse(url).path)
                )
                resolved_url = await upload_local_file_to_dashscope_temp(
                    media_path,
                    api_key=model_config.get_video_api_key(),
                    model_name=model_name,
                    media_type=media_type,
                )
            logger.info(
                f"Uploaded reference media to DashScope temp storage | backend={backend}, "
                f"filename={filename}, url={resolved_url[:100]}",
            )
            return resolved_url, kind

        content, filename = await read_reference_media(
            url,
            max_bytes=SEEDANCE_REFERENCE_IMAGE_MAX_BYTES,
        )
        kind = _reference_media_kind(filename)
        if kind == "video":
            raise ModelError(
                "Seedance reference videos must be public HTTP(S) URLs: "
                "the Ark task API does not accept Base64-encoded video "
                f"and local uploads have no provider channel ({filename})",
                model_name=model_name,
            )
        resolved_url = reference_media_data_url(content, filename)
        logger.info(
            f"Inlined reference media as data URL | backend={backend}, "
            f"filename={filename}, bytes={len(content)}",
        )
        return resolved_url, kind
    except ModelError:
        raise
    except Exception as exc:
        raise ModelError(
            f"Reference media transport failed for {filename}: {exc}",
            model_name=model_name,
        ) from exc


def _normalize_seedance_resolution(resolution: str, model_name: str) -> str:
    value = (resolution or "720p").lower()
    if value not in SEEDANCE_RESOLUTIONS:
        raise ModelError(
            f"Seedance2 resolution must be one of {sorted(SEEDANCE_RESOLUTIONS)}",
            model_name=model_name,
        )
    return value


def _normalize_seedance_ratio(ratio: str, model_name: str) -> str:
    value = ratio or "16:9"
    if value not in SEEDANCE_RATIOS:
        raise ModelError(
            f"Seedance2 ratio must be one of {sorted(SEEDANCE_RATIOS)}",
            model_name=model_name,
        )
    return value


def _normalize_seedance_duration(duration: int, model_name: str) -> int:
    if duration < 4 or duration > 15:
        raise ModelError(
            "Seedance2 duration must be between 4 and 15 seconds",
            model_name=model_name,
        )
    return duration


async def submit_video_task(
    prompt: str,
    reference_image_url: Optional[str] = None,
    reference_image_url_list: Optional[list[str]] = None,
    ratio: str = "16:9",
    duration: int = 5,
    resolution: str = "720p",
    watermark: bool = True,
    generate_audio: bool = True,
) -> str:
    """Submit a Wan2.7 reference-to-video task. Returns task_id."""
    api_key = model_config.get_video_api_key()
    model_name = model_config.get_video_model_name()
    if not api_key:
        raise ModelError(
            "creator_video_model.api_key or VIDEO_API_KEY is required",
            model_name=model_name,
        )

    media = []
    all_images = []
    if reference_image_url:
        all_images.append(reference_image_url)
    if reference_image_url_list:
        all_images.extend(reference_image_url_list)
    uses_seedance = _uses_seedance_protocol()
    upload_backend = "seedance2" if uses_seedance else "wan"
    for img_url in dict.fromkeys(all_images):
        if img_url and img_url.strip():
            resolved_url, media_kind = await _resolve_reference_media_url(
                img_url.strip(),
                upload_backend,
            )
            media.append(
                {
                    "type": (
                        "reference_video"
                        if media_kind == "video"
                        else "reference_image"
                    ),
                    "url": resolved_url,
                },
            )

    url = model_config.get_video_submit_url()
    submit_timeout = model_config.get_video_submit_timeout()
    if uses_seedance:
        seedance_duration = _normalize_seedance_duration(duration, model_name)
        content = [{"type": "text", "text": prompt}]
        content.extend(
            (
                {
                    "type": "video_url",
                    "role": "reference_video",
                    "video_url": {"url": item["url"]},
                }
                if item["type"] == "reference_video"
                else {
                    "type": "image_url",
                    "role": "reference_image",
                    "image_url": {"url": item["url"]},
                }
            )
            for item in media
            if item.get("url")
        )
        body = {
            "duration": seedance_duration,
            "watermark": watermark,
            "model": model_name,
            "resolution": _normalize_seedance_resolution(
                resolution,
                model_name,
            ),
            "content": content,
            "ratio": _normalize_seedance_ratio(ratio, model_name),
            "audio": bool(generate_audio),
        }
    else:
        body = {
            "model": model_name,
            "input": {
                "prompt": prompt,
                "media": media,
            },
            "parameters": {
                "resolution": resolution.upper() if resolution else "720P",
                "ratio": ratio,
                "prompt_extend": False,
                "watermark": watermark,
                "duration": duration,
            },
        }
    logger.info(
        f"Submitting video task | model={model_name}, prompt_length={len(prompt)}, "
        f"ratio={ratio}, duration={duration}s, media={len(media)}, protocol={'seedance' if uses_seedance else 'wan'}",
    )

    try:
        async with httpx.AsyncClient(timeout=submit_timeout) as client:
            resp = None
            async with model_slot("video"):
                for attempt in range(MAX_RETRIES):
                    resp = await client.post(
                        url,
                        headers={
                            "Content-Type": "application/json",
                            "Authorization": f"Bearer {api_key}",
                            **(
                                {}
                                if uses_seedance
                                else {
                                    "X-DashScope-Async": "enable",
                                    "X-DashScope-OssResourceResolve": "enable",
                                }
                            ),
                        },
                        json=body,
                    )
                    if resp.status_code == 429:
                        wait = RETRY_BACKOFF_BASE * (attempt + 1)
                        logger.warning(
                            f"Video submit rate limited (429), retrying in {wait}s (attempt {attempt+1}/{MAX_RETRIES})",
                        )
                        await asyncio.sleep(wait)
                        continue
                    break
            resp.raise_for_status()
            data = resp.json()

        output = (
            data.get("output") if isinstance(data.get("output"), dict) else {}
        )
        task_id = (
            output.get("task_id") or data.get("task_id") or data.get("taskId")
        )
        task_id = task_id or data.get("id")
        if not task_id:
            raise ModelError(
                f"No task_id in response: {data}",
                model_name=model_name,
            )

        logger.info(f"Video task submitted successfully | task_id={task_id}")
        return task_id

    except httpx.TimeoutException as e:
        logger.error(f"Video task submission timed out: {e}")
        raise ModelError(
            f"Video task submission timed out after {submit_timeout}s",
            model_name=model_name,
        )
    except httpx.HTTPStatusError as e:
        logger.error(
            f"Video task submission HTTP error: {e.response.status_code} - {e.response.text[:500]}",
        )
        # 保留足够长的响应体：敏感审核等错误码出现在 ~200 字符之后，
        # 截得太短会让上层无法识别错误类型（端到端 Run 自愈依赖该标记）
        raise ModelError(
            f"Video task submission failed with status {e.response.status_code}: {e.response.text[:600]}",
            model_name=model_name,
        )
    except ModelError:
        raise
    except Exception as e:
        logger.error(f"Video task submission failed: {e}")
        raise ModelError(
            f"Video task submission failed: {str(e)}",
            model_name=model_name,
        )


def _extract_failed_task(data: object) -> dict | None:
    """从（可能是错误响应的）body 中挖出「任务已失败」的真实状态与错误。

    部分供应商（如 Seedance / routify）会把一次生成任务的失败包在 HTTP 4xx 响应体里，
    真实的 status=failed 与审核错误藏在嵌套字段（甚至是一段 JSON 字符串）中。
    这里递归扫描，找到含 status=="failed" 的节点并提取错误码/信息，
    以便调用方按 FAILED 精确上报，而不是当作可重试的传输错误反复轮询。
    """
    found: dict[str, str] = {}

    def visit(obj: object) -> bool:
        if isinstance(obj, dict):
            if str(obj.get("status", "")).lower() == "failed":
                error = obj.get("error")
                if isinstance(error, dict):
                    code = str(error.get("code") or "")
                    message = str(error.get("message") or error)
                else:
                    code = ""
                    message = (
                        str(error)
                        if error
                        else str(obj.get("message") or "Task failed")
                    )
                found["code"] = code
                found["message"] = f"{code}: {message}" if code else message
                return True
            return any(visit(v) for v in obj.values())
        if isinstance(obj, list):
            return any(visit(v) for v in obj)
        if isinstance(obj, str):
            stripped = obj.strip()
            if stripped.startswith("{") and stripped.endswith("}"):
                try:
                    return visit(json.loads(stripped))
                except (ValueError, TypeError):
                    return False
        return False

    return found if visit(data) else None


async def check_task_status(task_id: str) -> dict:
    """Check the status of a Wan2.7 video generation task."""
    api_key = model_config.get_video_api_key()
    model_name = model_config.get_video_model_name()
    if not api_key:
        raise ModelError(
            "creator_video_model.api_key or VIDEO_API_KEY is required",
            model_name=model_name,
        )
    url = model_config.get_video_task_url(task_id)
    status_timeout = model_config.get_video_status_timeout()

    logger.info(f"Checking task status | task_id={task_id}")

    try:
        async with httpx.AsyncClient(timeout=status_timeout) as client:
            resp = await client.get(
                url,
                headers={"Authorization": f"Bearer {api_key}"},
            )
            resp.raise_for_status()
            data = resp.json()

        payload = (
            data.get("output")
            if isinstance(data.get("output"), dict)
            else data
        )
        status_raw = str(
            payload.get("task_status") or payload.get("status") or "unknown",
        ).upper()

        # Normalize: succeeded → SUCCEEDED, running → RUNNING, failed → FAILED
        status_map = {
            "SUCCEEDED": "SUCCEEDED",
            "RUNNING": "RUNNING",
            "FAILED": "FAILED",
        }
        status = status_map.get(status_raw, status_raw)

        result = {"task_id": task_id, "status": status}

        if status == "SUCCEEDED":
            content = (
                payload.get("content")
                if isinstance(payload.get("content"), dict)
                else {}
            )
            video_url = (
                payload.get("video_url")
                or payload.get("videoUrl")
                or payload.get("url")
                or content.get("video_url")
                or content.get("videoUrl")
                or content.get("url")
                or ""
            )
            result["result_url"] = video_url
            logger.info(
                f"Video task succeeded | task_id={task_id}, url={video_url[:80] if video_url else ''}",
            )
        elif status == "FAILED":
            error_payload = payload.get("error") or {}
            error_msg = (
                error_payload.get("message")
                if isinstance(error_payload, dict)
                else str(error_payload)
            )
            error_msg = error_msg or payload.get("message") or "Task failed"
            result["error"] = error_msg
            logger.warning(
                f"Video task failed | task_id={task_id}: {error_msg}",
            )
        else:
            logger.info(f"Video task status: {status} | task_id={task_id}")

        return result

    except httpx.TimeoutException as e:
        logger.error(f"Task status check timed out | task_id={task_id}: {e}")
        raise ModelError("Task status check timed out", model_name=model_name)
    except httpx.HTTPStatusError as e:
        status_code = e.response.status_code
        # 供应商可能把「任务已失败」包在 4xx 响应体里（真实 status=failed 藏在 body），
        # 先尝试解析出来，按 FAILED 精确上报，避免上层把它当可重试错误空等到超时。
        try:
            body = e.response.json()
        except (ValueError, TypeError):
            body = None
        failure = _extract_failed_task(body)
        if failure is not None:
            logger.warning(
                f"Video task failed (reported via HTTP {status_code}) | "
                f"task_id={task_id}: {failure['message']}",
            )
            return {
                "task_id": task_id,
                "status": "FAILED",
                "error": failure["message"],
            }
        logger.error(
            f"Task status check HTTP error | task_id={task_id}: {status_code} - "
            f"{e.response.text[:500]}",
        )
        # 4xx 属客户端/永久错误 → 不可重试；5xx 与 429 视为瞬时错误可重试。
        raise ModelError(
            f"Task status check failed with status {status_code}",
            model_name=model_name,
            retryable=status_code >= 500 or status_code == 429,
        )
    except Exception as e:
        logger.error(f"Task status check failed | task_id={task_id}: {e}")
        raise ModelError(
            f"Task status check failed: {str(e)}",
            model_name=model_name,
        )
