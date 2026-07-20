# -*- coding: utf-8 -*-
# flake8: noqa: E501
"""Hash-verified Project Workspace prompt templates."""

from __future__ import annotations

import hashlib
from pathlib import Path


_PROMPT_PATH = Path(__file__).resolve().parent / "workspace_schema.system.txt"
_PROMPT_SHA256 = (
    "e5eda872c0e2d21805f5198c8f9e52605338969e745d69e23926c6ec352509b9"
)
_SCHEMA_PLACEHOLDER = "{{project_json_schema}}"


def render_workspace_schema_prompt(*, project_json_schema: str) -> str:
    data = _PROMPT_PATH.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != _PROMPT_SHA256:
        raise RuntimeError("Prompt hash mismatch: workspace_schema.system")
    text = data.decode("utf-8").strip()
    if text.count(_SCHEMA_PLACEHOLDER) != 1:
        raise RuntimeError(
            "Prompt placeholder mismatch: workspace_schema.system requires project_json_schema",
        )
    return text.replace(_SCHEMA_PLACEHOLDER, project_json_schema)


__all__ = ["render_workspace_schema_prompt"]
