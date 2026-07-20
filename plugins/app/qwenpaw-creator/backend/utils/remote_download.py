"""Download remote files via curl with timeout and size limits."""

import os
from pathlib import Path
import subprocess
import tempfile
from urllib.parse import urlsplit, urlunsplit

logger = __import__("utils.logger", fromlist=["setup_logger"]).setup_logger(
    "utils.remote_download")

# 上限/超时均可经环境变量覆盖：默认 2 GiB，足够下载一场完整比赛视频。
# 原先硬编码 500 MiB，会把近 1 GiB 的高光素材卡在 curl 错误 63
# (Maximum file size exceeded)，导致剪辑拿不到本地文件而失败。
MAX_BYTES = int(os.environ.get("CREATOR_DOWNLOAD_MAX_BYTES", 2 * 1024 * 1024 * 1024))
TIMEOUT_SECONDS = int(os.environ.get("CREATOR_DOWNLOAD_TIMEOUT_SECONDS", 300))
CONNECT_TIMEOUT_SECONDS = int(os.environ.get("CREATOR_DOWNLOAD_CONNECT_TIMEOUT_SECONDS", 15))
LOW_SPEED_LIMIT = int(os.environ.get("CREATOR_DOWNLOAD_LOW_SPEED_LIMIT", 1024))
LOW_SPEED_TIME_SECONDS = int(os.environ.get("CREATOR_DOWNLOAD_LOW_SPEED_TIME_SECONDS", 60))


def download_remote_file(url: str, local_path: str) -> None:
    """Download a remote file to a local path via curl. Raises RuntimeError on failure."""
    target = Path(local_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".download", dir=target.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    parsed = urlsplit(url)
    redacted_url = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
    logger.info(
        "Downloading remote file | url=%s max_bytes=%d timeout=%ds",
        redacted_url[:100],
        MAX_BYTES, TIMEOUT_SECONDS,
    )
    cmd = [
        "curl",
        "--fail",
        "--location",
        "--silent",
        "--show-error",
        "--max-time", str(TIMEOUT_SECONDS),
        "--connect-timeout", str(CONNECT_TIMEOUT_SECONDS),
        "--speed-limit", str(LOW_SPEED_LIMIT),
        "--speed-time", str(LOW_SPEED_TIME_SECONDS),
        "--max-filesize", str(MAX_BYTES),
        "--user-agent", "creator-poc/1.0",
        "--output", str(temporary),
        url,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_SECONDS + 10)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "curl download failed").strip()
            # curl 退出码 63 = --max-filesize 超限，单独提示更直观
            hint = ""
            if result.returncode == 63:
                hint = (f" (文件超过下载上限 {MAX_BYTES / 1024 / 1024:.0f} MiB；"
                        f"可调大环境变量 CREATOR_DOWNLOAD_MAX_BYTES)")
            raise RuntimeError(f"Remote file download failed: {detail[:300]}{hint}")

        if temporary.stat().st_size <= 0:
            raise RuntimeError("Remote file downloaded empty")
        with temporary.open("rb") as handle:
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        directory_fd = os.open(target.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        size_mib = target.stat().st_size / 1024 / 1024
        logger.info(f"Downloaded remote file | path={target}, size_mib={size_mib:.1f}")
    finally:
        temporary.unlink(missing_ok=True)
