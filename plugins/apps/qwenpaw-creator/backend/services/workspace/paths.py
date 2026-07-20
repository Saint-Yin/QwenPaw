# -*- coding: utf-8 -*-
# pylint: disable=too-many-boolean-expressions
"""Canonical paths for the Agent-facing Text Workspace.

The workspace is a virtual POSIX tree backed by immutable content hashes.  This
module deliberately contains no host-filesystem join helper: callers receive a
validated relative key and can only pass that key to :mod:`text_store`.
"""

from __future__ import annotations

from pathlib import PurePosixPath
import re

from domain.errors import ValidationError
from .mutations import safe_workspace_path


TEXT_WORKSPACE_SUFFIXES = frozenset({".md", ".txt", ".ref", ".vtt", ".ctm"})
SEARCHABLE_SUFFIXES = TEXT_WORKSPACE_SUFFIXES

_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:")
_PRIVATE_ROOTS = frozenset(
    {"runs", "runtime", "revisions", "blobs", "artifacts"},
)


def workspace_text_path(value: str) -> str:
    """Return a safe Folder-first text path.

    JSON/YAML and media files are intentionally excluded.  Media lives in the
    immutable Asset/Artifact Store and is referenced from ``.ref`` files.
    """

    normalized = safe_workspace_path(value)
    path = PurePosixPath(normalized)
    if path.parts[0].lower() in _PRIVATE_ROOTS or any(
        part.startswith(".") for part in path.parts
    ):
        raise ValidationError(
            "workspace path 指向系统私有命名空间",
            details={"path": value},
        )
    if path.suffix.lower() not in TEXT_WORKSPACE_SUFFIXES:
        raise ValidationError(
            "Text Workspace 只允许 Markdown/TXT/REF/VTT/CTM 文件",
            details={
                "path": value,
                "allowedSuffixes": sorted(TEXT_WORKSPACE_SUFFIXES),
            },
        )
    return normalized


def workspace_directory(value: str | None) -> str | None:
    """Validate an optional virtual directory/prefix.

    ``None`` denotes the workspace root.  Empty strings and ``.`` are rejected
    rather than normalized so traversal attempts remain visible to callers.
    """

    if value is None:
        return None
    normalized = safe_workspace_path(value)
    path = PurePosixPath(normalized)
    if path.parts[0].lower() in _PRIVATE_ROOTS or any(
        part.startswith(".") for part in path.parts
    ):
        raise ValidationError(
            "workspace prefix 指向系统私有命名空间",
            details={"path": value},
        )
    return normalized


def workspace_glob(value: str) -> str:
    """Validate a relative glob without resolving or touching the host FS."""

    if not isinstance(value, str):
        raise ValidationError("workspace glob 必须是字符串")
    raw = value
    if (
        not raw
        or raw != raw.strip()
        or raw.startswith(("/", "\\"))
        or "\\" in raw
        or "\x00" in raw
        or _WINDOWS_DRIVE_RE.match(raw)
    ):
        raise ValidationError("非法 workspace glob", details={"pattern": value})
    parts = raw.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValidationError("非法 workspace glob", details={"pattern": value})
    literal_root = parts[0].split("*", 1)[0].split("?", 1)[0]
    if literal_root.lower() in _PRIVATE_ROOTS or any(
        part.startswith(".") for part in parts
    ):
        raise ValidationError(
            "workspace glob 指向系统私有命名空间",
            details={"pattern": value},
        )
    return raw


def join_workspace_glob(prefix: str | None, pattern: str) -> str:
    safe_prefix = workspace_directory(prefix)
    safe_pattern = workspace_glob(pattern)
    return f"{safe_prefix}/{safe_pattern}" if safe_prefix else safe_pattern


def compile_workspace_glob(pattern: str) -> re.Pattern[str]:
    """Compile the small, deterministic glob grammar used by the tools.

    ``*`` and ``?`` never cross a directory separator; ``**`` may.  Character
    classes are treated literally so callers cannot smuggle arbitrary regex.
    """

    raw = workspace_glob(pattern)
    out: list[str] = []
    index = 0
    while index < len(raw):
        char = raw[index]
        if char == "*":
            if raw[index : index + 2] == "**":
                if raw[index + 2 : index + 3] == "/":
                    out.append("(?:.*/)?")
                    index += 3
                    continue
                out.append(".*")
                index += 2
                continue
            out.append("[^/]*")
        elif char == "?":
            out.append("[^/]")
        else:
            out.append(re.escape(char))
        index += 1
    return re.compile("^" + "".join(out) + "$")


def glob_matches(path: str, pattern: str) -> bool:
    return (
        compile_workspace_glob(pattern).fullmatch(workspace_text_path(path))
        is not None
    )


def scope_contains_path(scope: str, path: str) -> bool:
    """Return whether a canonical lease scope covers ``path``.

    Directory scopes must be explicit (``strategy/**``); an exact file scope
    covers exactly one file.  This avoids treating a filename as a directory by
    accident and makes hierarchical overlap checks deterministic.
    """

    candidate = workspace_text_path(path)
    if scope.endswith("/**"):
        root = workspace_directory(scope[:-3])
        assert root is not None
        return candidate.startswith(root + "/")
    return candidate == workspace_text_path(scope)


def scopes_overlap(left: str, right: str) -> bool:
    """Detect exact or hierarchical overlap between two lease scopes."""

    left_is_tree = left.endswith("/**")
    right_is_tree = right.endswith("/**")
    left_root = (
        workspace_directory(left[:-3])
        if left_is_tree
        else workspace_text_path(left)
    )
    right_root = (
        workspace_directory(right[:-3])
        if right_is_tree
        else workspace_text_path(right)
    )
    assert left_root is not None and right_root is not None
    if not left_is_tree and not right_is_tree:
        return left_root == right_root
    if left_is_tree and right_is_tree:
        return (
            left_root == right_root
            or left_root.startswith(right_root + "/")
            or right_root.startswith(left_root + "/")
        )
    if left_is_tree:
        return right_root.startswith(left_root + "/")
    return left_root.startswith(right_root + "/")


__all__ = [
    "SEARCHABLE_SUFFIXES",
    "TEXT_WORKSPACE_SUFFIXES",
    "compile_workspace_glob",
    "glob_matches",
    "join_workspace_glob",
    "scope_contains_path",
    "scopes_overlap",
    "workspace_directory",
    "workspace_glob",
    "workspace_text_path",
]
