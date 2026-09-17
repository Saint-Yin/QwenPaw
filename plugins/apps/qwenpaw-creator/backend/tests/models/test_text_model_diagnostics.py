# -*- coding: utf-8 -*-
# pylint: disable=protected-access
# flake8: noqa: E501
"""The empty-reply diagnostics stay behind an opt-in switch.

A contentless reply used to be undecidable from the user's side: a reasoning
model that spent the whole budget on its thinking trace, a stream the gateway
ended without a closing frame, and a refusal all produced the same string. The
detail now exists, but only when ``CREATOR_MODEL_DIAGNOSTICS`` asks for it.
"""

from __future__ import annotations

import pytest

from models import text_model

REASONING_ONLY = {
    "choices": [{"message": {"content": ""}, "finish_reason": "length"}],
    "usage": {"prompt_tokens": 900, "completion_tokens": 4096},
    "_frame_count": 812,
    "_reasoning_content_dropped": True,
}

SEVERED_STREAM = {
    "choices": [{"message": {"content": ""}, "finish_reason": "stop"}],
    "_frame_count": 0,
    "_finish_reason_missing": True,
}


def test_the_detail_is_absent_unless_it_is_switched_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(text_model.DIAGNOSTICS_ENV, raising=False)
    assert text_model._empty_content_detail(REASONING_ONLY) == ""


@pytest.mark.parametrize("value", ["1", "true", "YES", "on"])
def test_any_affirmative_value_switches_it_on(
    monkeypatch: pytest.MonkeyPatch,
    value: str,
) -> None:
    monkeypatch.setenv(text_model.DIAGNOSTICS_ENV, value)
    assert text_model._empty_content_detail(REASONING_ONLY) != ""


def test_a_reasoning_only_reply_reads_as_an_exhausted_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(text_model.DIAGNOSTICS_ENV, "1")
    detail = text_model._empty_content_detail(REASONING_ONLY)
    assert "finish_reason=length" in detail
    assert "frames=812" in detail
    assert "reasoning_dropped=True" in detail
    assert "completion_tokens" in detail


def test_a_stream_without_a_closing_reason_is_not_read_as_a_clean_stop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # ``aggregate_stream_to_completion`` keeps the "stop" default so parsers
    # stay happy; the marker is what tells truncation from a finished reply.
    monkeypatch.setenv(text_model.DIAGNOSTICS_ENV, "1")
    detail = text_model._empty_content_detail(SEVERED_STREAM)
    assert "finish_reason=stop(never_reported)" in detail
    assert "reasoning_dropped=False" in detail
