# -*- coding: utf-8 -*-
# flake8: noqa: E501
"""Strict marker plus free-form natural-language terminal protocol."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


class SpecialistResultProtocolError(ValueError):
    failure_kind = "RESULT_MARKER_MISSING"

    def __init__(self, raw_text: str) -> None:
        super().__init__(
            "Specialist result must start with [SUCCESS], [BLOCKED], or [FAILED]",
        )
        self.raw_text = raw_text


@dataclass(frozen=True, slots=True)
class ParsedSpecialistFinal:
    marker: Literal["SUCCESS", "BLOCKED", "FAILED"]
    summary_text: str


def parse_specialist_final(raw_text: str) -> ParsedSpecialistFinal:
    lines = raw_text.splitlines()
    first_index = next(
        (idx for idx, line in enumerate(lines) if line.strip()),
        None,
    )
    if first_index is None:
        raise SpecialistResultProtocolError(raw_text)
    marker_text = lines[first_index].strip()
    marker_map = {
        "[SUCCESS]": "SUCCESS",
        "[BLOCKED]": "BLOCKED",
        "[FAILED]": "FAILED",
    }
    marker = marker_map.get(marker_text)
    if marker is None:
        raise SpecialistResultProtocolError(raw_text)
    summary = "\n".join(lines[first_index + 1 :]).lstrip("\n")
    return ParsedSpecialistFinal(marker=marker, summary_text=summary)
