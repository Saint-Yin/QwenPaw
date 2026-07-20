"""Resolve plugins shipped beside the current QwenPaw installation."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlsplit

LOCAL_PLUGIN_SOURCE_SCHEME = "qwenpaw-source"
QWENPAW_PACKAGE_DIR = Path(__file__).resolve().parents[1]
SOURCE_TREE_PLUGIN_SOURCES_DIR = QWENPAW_PACKAGE_DIR.parents[1] / "plugins"
BUNDLED_PLUGIN_SOURCES_DIR = QWENPAW_PACKAGE_DIR / "_bundled_plugins"
_SAFE_SEGMENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")


def _validate_segment(value: str, label: str) -> str:
    if not _SAFE_SEGMENT.fullmatch(value):
        raise ValueError(f"Invalid local plugin {label}: {value!r}")
    return value


def find_local_plugin_source(kind: str, plugin_id: str) -> Path | None:
    """Find a plugin in the source tree or installed QwenPaw package."""
    safe_kind = _validate_segment(kind, "kind")
    safe_plugin_id = _validate_segment(plugin_id, "id")
    for candidate_root in (
        SOURCE_TREE_PLUGIN_SOURCES_DIR,
        BUNDLED_PLUGIN_SOURCES_DIR,
    ):
        source_root = candidate_root.resolve()
        source_path = (source_root / safe_kind / safe_plugin_id).resolve()
        if not source_path.is_relative_to(source_root):
            continue
        if (source_path / "plugin.json").is_file():
            return source_path
    return None


def local_plugin_source_uri(kind: str, plugin_id: str) -> str:
    """Build the opaque source URI used by the Console install request."""
    safe_kind = _validate_segment(kind, "kind")
    safe_plugin_id = _validate_segment(plugin_id, "id")
    return f"{LOCAL_PLUGIN_SOURCE_SCHEME}://{safe_kind}/{safe_plugin_id}"


def resolve_local_plugin_source(source: str) -> Path | None:
    """Resolve a local-source URI, or return ``None`` for another source."""
    parsed = urlsplit(source)
    if parsed.scheme != LOCAL_PLUGIN_SOURCE_SCHEME:
        return None
    if parsed.query or parsed.fragment:
        raise ValueError(
            "Local plugin source URI cannot contain query or fragment",
        )

    kind = _validate_segment(parsed.netloc, "kind")
    path_parts = [part for part in parsed.path.split("/") if part]
    if len(path_parts) != 1:
        raise ValueError(
            "Local plugin source URI must identify exactly one plugin",
        )
    plugin_id = _validate_segment(path_parts[0], "id")
    source_path = find_local_plugin_source(kind, plugin_id)
    if source_path is None:
        raise FileNotFoundError(
            f"Plugin bundled with QwenPaw was not found: {kind}/{plugin_id}",
        )
    return source_path
