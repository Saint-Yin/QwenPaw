# -*- coding: utf-8 -*-
# flake8: noqa: E501
# pylint: disable=line-too-long,too-many-return-statements
import asyncio
import mimetypes
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlparse

import httpx

from models import config as model_config
from utils.paths import media_path_from_url


OSS_POLICY_URL = "https://dashscope.aliyuncs.com/api/v1/uploads"
DEFAULT_CREATOR_MEDIA_BUCKET = "creator-store"
WAN_MEDIA_PREFIX = "wan_media"
SD2_MEDIA_PREFIX = "sd2_media"
DASHSCOPE_TEMP_UPLOAD_MAX_BYTES = 1024 * 1024 * 1024
DASHSCOPE_TEMP_UPLOAD_CACHE_SECONDS = 47 * 60 * 60

_dashscope_temp_upload_cache: dict[
    tuple[str, int, int, str, str],
    tuple[str, float],
] = {}
_dashscope_temp_upload_locks: dict[
    tuple[str, int, int, str, str],
    asyncio.Lock,
] = {}
_dashscope_credential_tokens: dict[str, str] = {}


async def get_oss_policy(model: str = "wan2.7-r2v") -> dict:
    """Get OSS upload credentials."""
    api_key = model_config.get_oss_policy_api_key()
    if not api_key:
        raise RuntimeError(
            "creator_media_oss.policy_api_key or OSS_POLICY_API_KEY is required for OSS upload policy",
        )
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            OSS_POLICY_URL,
            params={"action": "getPolicy", "model": model},
            headers={"Authorization": f"Bearer {api_key}"},
        )
        resp.raise_for_status()
        return resp.json().get("data", resp.json())


async def upload_file_to_oss(
    file_content: bytes,
    filename: str,
    policy_data: dict,
) -> str:
    """Upload a file to OSS using the policy credentials. Returns oss:// URL."""
    upload_host = policy_data["upload_host"]
    upload_dir = policy_data["upload_dir"]
    key = f"{upload_dir}/{filename}"

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            upload_host,
            data={
                "OSSAccessKeyId": policy_data["oss_access_key_id"],
                "Signature": policy_data["signature"],
                "policy": policy_data["policy"],
                "x-oss-object-acl": policy_data.get(
                    "x_oss_object_acl",
                    "default",
                ),
                "x-oss-forbid-overwrite": policy_data.get(
                    "x_oss_forbid_overwrite",
                    "true",
                ),
                "key": key,
                "success_action_status": "200",
            },
            files={"file": (filename, file_content)},
        )
        resp.raise_for_status()

    return f"oss://{key}"


def _dashscope_transport_filename(path: Path, media_type: str) -> str:
    filename = path.name or "selected-media"
    if not Path(filename).suffix:
        extension = mimetypes.guess_extension(media_type) or ".bin"
        filename = f"{filename}{extension}"
    return _safe_filename(filename)


def _credential_cache_token(api_key: str) -> str:
    """Opaque per-process stand-in for *api_key* inside cache keys.

    The temp-upload cache is process-local, so a random token per
    credential keeps entries isolated without deriving cache material
    from the secret itself.
    """
    return _dashscope_credential_tokens.setdefault(api_key, uuid.uuid4().hex)


def _dashscope_temp_upload_cache_key(
    path: Path,
    *,
    api_key: str,
    model_name: str,
) -> tuple[str, int, int, str, str]:
    stat = path.stat()
    credential_fingerprint = _credential_cache_token(api_key)
    return (
        str(path.resolve()),
        int(stat.st_size),
        int(stat.st_mtime_ns),
        model_name,
        credential_fingerprint,
    )


def _upload_local_file_to_dashscope_temp_sync(
    path: Path,
    *,
    api_key: str,
    model_name: str,
    media_type: str,
) -> str:
    """Stream one local file to DashScope's model-bound temporary OSS."""

    size = path.stat().st_size
    if size > DASHSCOPE_TEMP_UPLOAD_MAX_BYTES:
        raise RuntimeError(
            "DashScope temporary upload rejects files larger than 1GB; "
            "provide a safe public nativeModelUrl/publicSourceUrl instead",
        )
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    timeout = httpx.Timeout(connect=30.0, read=300.0, write=3600.0, pool=30.0)
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        policy_response = client.get(
            OSS_POLICY_URL,
            params={"action": "getPolicy", "model": model_name},
            headers=headers,
        )
        policy_response.raise_for_status()
        payload = policy_response.json()
        policy = payload.get("data", payload)
        try:
            max_policy_bytes = int(
                float(policy["max_file_size_mb"]) * 1024 * 1024,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError(
                "DashScope upload policy missing max_file_size_mb",
            ) from exc
        if size > max_policy_bytes:
            raise RuntimeError(
                "selected local media exceeds the current model-bound DashScope upload "
                f"policy ({size} bytes > {max_policy_bytes} bytes); provide a safe "
                "public nativeModelUrl/publicSourceUrl",
            )
        filename = _dashscope_transport_filename(path, media_type)
        upload_dir = str(policy["upload_dir"]).rstrip("/")
        key = f"{upload_dir}/{uuid.uuid4().hex}-{filename}"
        form = {
            "OSSAccessKeyId": str(policy["oss_access_key_id"]),
            "Signature": str(policy["signature"]),
            "policy": str(policy["policy"]),
            "x-oss-object-acl": str(policy.get("x_oss_object_acl", "private")),
            "x-oss-forbid-overwrite": str(
                policy.get("x_oss_forbid_overwrite", "true"),
            ),
            "key": key,
            "success_action_status": "200",
        }
        with path.open("rb") as file_handle:
            upload_response = client.post(
                str(policy["upload_host"]),
                data=form,
                files={"file": (filename, file_handle, media_type)},
            )
        upload_response.raise_for_status()
    return f"oss://{key}"


async def upload_local_file_to_dashscope_temp(
    path: Path,
    *,
    api_key: str,
    model_name: str,
    media_type: str,
) -> str:
    """Return a cached 48-hour provider URL without reading the file into memory."""

    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(
            f"selected local media does not exist: {resolved}",
        )
    if not api_key.strip() or not model_name.strip():
        raise RuntimeError(
            "DashScope temporary upload requires API key and model name",
        )
    cache_key = _dashscope_temp_upload_cache_key(
        resolved,
        api_key=api_key,
        model_name=model_name,
    )
    now = time.monotonic()
    cached = _dashscope_temp_upload_cache.get(cache_key)
    if cached is not None and cached[1] > now:
        return cached[0]
    lock = _dashscope_temp_upload_locks.setdefault(cache_key, asyncio.Lock())
    async with lock:
        now = time.monotonic()
        cached = _dashscope_temp_upload_cache.get(cache_key)
        if cached is not None and cached[1] > now:
            return cached[0]
        url = await asyncio.to_thread(
            _upload_local_file_to_dashscope_temp_sync,
            resolved,
            api_key=api_key,
            model_name=model_name,
            media_type=media_type,
        )
        _dashscope_temp_upload_cache[cache_key] = (
            url,
            now + DASHSCOPE_TEMP_UPLOAD_CACHE_SECONDS,
        )
        return url


def _creator_media_bucket() -> str:
    return model_config.get_oss_bucket(DEFAULT_CREATOR_MEDIA_BUCKET)


def _creator_media_public_base_url() -> str:
    return model_config.get_oss_public_base_url()


def creator_oss_readiness() -> dict:
    """Return configuration readiness for creator-store public uploads."""
    access_key_id = model_config.get_oss_access_key_id()
    access_key_secret = model_config.get_oss_access_key_secret()
    endpoint = model_config.get_oss_endpoint()
    blockers = []
    if not access_key_id:
        blockers.append(
            "creator_media_oss.access_key_id or OSS_ACCESS_KEY_ID is required",
        )
    if not access_key_secret:
        blockers.append(
            "creator_media_oss.access_key_secret or OSS_ACCESS_KEY_SECRET is required",
        )
    if not endpoint:
        blockers.append(
            "creator_media_oss.endpoint or OSS_ENDPOINT is required",
        )
    return {
        "status": "ready" if not blockers else "blocked",
        "bucket": _creator_media_bucket(),
        "endpoint_set": bool(endpoint),
        "access_key_set": bool(access_key_id and access_key_secret),
        "public_base_url_set": bool(_creator_media_public_base_url()),
        "blockers": blockers,
    }


def _safe_filename(filename: str) -> str:
    stem = Path(filename or "reference").stem or "reference"
    suffix = Path(filename or "").suffix.lower()
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip("-._") or "reference"
    if not suffix or not re.fullmatch(r"\.[A-Za-z0-9]{1,10}", suffix):
        suffix = ".bin"
    return f"{stem}{suffix}"


def _object_key(filename: str, backend: str) -> str:
    prefix = SD2_MEDIA_PREFIX if backend == "seedance2" else WAN_MEDIA_PREFIX
    date = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"{prefix}/{date}/{uuid.uuid4().hex}-{_safe_filename(filename)}"


def _public_url(endpoint: str, bucket: str, key: str) -> str:
    quoted_key = quote(key)
    public_base_url = _creator_media_public_base_url()
    if public_base_url:
        return f"{public_base_url.rstrip('/')}/{quoted_key}"
    endpoint_host = (
        endpoint.replace("https://", "").replace("http://", "").rstrip("/")
    )
    return f"https://{bucket}.{endpoint_host}/{quoted_key}"


def _upload_with_oss2(file_content: bytes, filename: str, backend: str) -> str:
    try:
        import oss2  # type: ignore
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "oss2 package is required for creator-media uploads",
        ) from exc

    access_key_id = model_config.get_oss_access_key_id()
    access_key_secret = model_config.get_oss_access_key_secret()
    endpoint = model_config.get_oss_endpoint()
    if not access_key_id or not access_key_secret or not endpoint:
        readiness = creator_oss_readiness()
        raise RuntimeError("; ".join(readiness["blockers"]))

    bucket_name = _creator_media_bucket()
    key = _object_key(filename, backend)
    content_type = (
        mimetypes.guess_type(filename)[0] or "application/octet-stream"
    )
    auth = oss2.Auth(access_key_id, access_key_secret)
    bucket = oss2.Bucket(auth, endpoint, bucket_name)
    headers = {
        "Content-Type": content_type,
        "x-oss-object-acl": "public-read",
    }
    bucket.put_object(key, file_content, headers=headers)
    return _public_url(endpoint, bucket_name, key)


async def upload_reference_media_to_creator_oss(
    file_content: bytes,
    filename: str,
    backend: str,
) -> str:
    """Upload reference media to creator-media and return a public HTTPS URL."""
    if backend not in {"wan", "seedance2"}:
        raise ValueError(
            f"Unsupported video backend for OSS upload: {backend}",
        )
    return await asyncio.to_thread(
        _upload_with_oss2,
        file_content,
        filename,
        backend,
    )


async def read_reference_media(url: str) -> tuple[bytes, str]:
    """Read a local, localhost, or remote reference media URL into bytes."""
    if url.startswith("file://"):
        parsed = urlparse(url)
        media_path = Path(parsed.path)
        content = media_path.read_bytes()
        filename = media_path.name or f"reference-{uuid.uuid4().hex}"
        if not Path(filename).suffix:
            filename += _suffix_from_magic(content)
        return content, filename
    if url.startswith("/generated/"):
        media_path = media_path_from_url(url)
        return (
            media_path.read_bytes(),
            media_path.name or f"reference-{uuid.uuid4().hex}.bin",
        )
    if url.startswith(("http://", "https://")):
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.get(url)
            response.raise_for_status()
            filename = (
                Path(urlparse(url).path).name
                or f"reference-{uuid.uuid4().hex}.bin"
            )
            return response.content, filename
    raise ValueError(f"Unsupported reference media URL: {url}")


def _suffix_from_magic(content: bytes) -> str:
    """Recover a transport filename for suffix-free content-addressed blobs."""

    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if content.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if content.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    if content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return ".webp"
    if len(content) >= 12 and content[4:8] == b"ftyp":
        return ".mp4"
    if content.startswith(b"\x1aE\xdf\xa3"):
        return ".webm"
    return ".bin"
