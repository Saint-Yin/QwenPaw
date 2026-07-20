# -*- coding: utf-8 -*-
"""Helpers for extracting structured JSON from model responses."""

from __future__ import annotations

import json
from typing import Any


def _strip_fenced_block(text: str) -> str | None:
    if "```json" in text:
        return text.split("```json", 1)[1].split("```", 1)[0].strip()
    if "```" in text:
        return text.split("```", 1)[1].split("```", 1)[0].strip()
    return None


def _find_balanced_json(text: str) -> str:
    start = next(
        (index for index, char in enumerate(text) if char in "[{"),
        -1,
    )
    if start < 0:
        raise json.JSONDecodeError("No JSON object or array found", text, 0)

    stack: list[str] = []
    in_string = False
    escaped = False
    pairs = {"{": "}", "[": "]"}

    for index in range(start, len(text)):
        char = text[index]

        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char in pairs:
            stack.append(pairs[char])
        elif stack and char == stack[-1]:
            stack.pop()
            if not stack:
                return text[start : index + 1]

    raise json.JSONDecodeError(
        "Unterminated JSON object or array",
        text,
        start,
    )


def extract_json_payload(response_text: str) -> Any:
    """Parse JSON from a plain, fenced, or lightly narrated model response.

    健壮性：围栏块内容非法时，回退到「平衡括号扫描」在整段文本里找第一个合法 JSON，
    避免因代码块里有轻微瑕疵而整轮解析失败（模型正文里其实常带合法 JSON）。
    """
    fenced = _strip_fenced_block(response_text)
    if fenced is not None:
        try:
            return json.loads(fenced)
        except json.JSONDecodeError:
            # 围栏内非法：先在围栏片段内做平衡扫描，再退回整段扫描
            try:
                return json.loads(_find_balanced_json(fenced))
            except json.JSONDecodeError:
                pass

    try:
        return json.loads(response_text.strip())
    except json.JSONDecodeError:
        return json.loads(_find_balanced_json(response_text))
