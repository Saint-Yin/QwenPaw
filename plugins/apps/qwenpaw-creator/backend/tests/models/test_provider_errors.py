# -*- coding: utf-8 -*-
# pylint: disable=protected-access
# flake8: noqa: E501
"""Error classification for the AgentScope model proxy.

Every envelope here is a measured sample, not a guessed shape: the proxy
answers a deterministic client fault with ``502`` + ``retryable: true``, and
an exhausted balance with a ``403`` that reads like a permission failure.
Classification has to key on ``code`` because both the status and the
provider's own retryable flag are wrong in opposite directions.
"""

from __future__ import annotations

import pytest

from models.provider_errors import (
    CLASS_PERMANENT,
    CLASS_QUOTA,
    CLASS_TRANSIENT,
    CLASS_UNKNOWN,
    classify_gateway_error,
    gateway_error_code,
    gateway_request_id,
    is_gateway_quota_error,
    retryable_for_status,
)
from services.file_agent_runtime.work_scheduler import (
    _is_transient_dispatch_error,
    _provider_error_suffix,
)
from services.media_files.transient_errors import (
    is_transient_error_message,
    is_transient_task_error,
)
from utils.exceptions import ModelError


# Wrapping matters: the raising layer appends its own context and the raw
# provider body, so the code is never the whole string.
UPSTREAM_ENVELOPE = (
    'Image generation failed with status 502: {"code": "ASP.UPSTREAM.ERROR", '
    '"message": "InvalidParameter: Failed to download the reference media", '
    '"retryable": true, "request_id": "d5507d1b-1059-9635-989e-e1f0c1b6b62e"}. '
    "Check creator_image_model configuration."
)

CREDITS_ENVELOPE = (
    'Chat completion failed with status 403: {"code": '
    '"ASP.BIZ.CREDITS_INSUFFICIENT", "message": "模型 Credits 不足，请先使用'
    '贡献值兑换", "retryable": false, "request_id": '
    '"bcc611fa-c5da-4190-8e3b-73aff40f4444"}'
)

SIZE_ENVELOPE = (
    '{"code": "ASP.SYS.INTERNAL_ERROR", "message": "internal error", '
    '"retryable": true}'
)

# Same refusal as CREDITS_ENVELOPE, but as an OpenAI-compatible client raises
# it on the Agent main loop: the body is re-serialised as a Python repr, so
# every quote is a single quote and ``False`` is capitalised. Captured from a
# run whose project session died in a retry loop.
CREDITS_REPR_ENVELOPE = (
    "Creator AgentScope model request failed: Error code: 403 - "
    "{'error': {'code': 'ASP.BIZ.CREDITS_INSUFFICIENT', "
    "'message': '模型 Credits 不足，请先使用贡献值兑换', "
    "'retryable': False, 'type': 'BUSINESS'}, 'request_id': "
    "'70491bf2-9f12-4e43-82c1-bab4a321f647'}"
)


def test_deterministic_upstream_error_is_not_transient() -> None:
    """A 0.1s rejection must not spend a retry slot on a billed render."""
    assert gateway_error_code(UPSTREAM_ENVELOPE) == "ASP.UPSTREAM.ERROR"
    assert classify_gateway_error(UPSTREAM_ENVELOPE) == CLASS_UNKNOWN
    # "status 502" is in the shared marker table and "status 5" is in the
    # scheduler's own; both would have called this transient.
    assert is_transient_error_message(UPSTREAM_ENVELOPE) is False
    assert _is_transient_dispatch_error(Exception(UPSTREAM_ENVELOPE)) is False


def test_oversized_body_is_not_transient() -> None:
    assert classify_gateway_error(SIZE_ENVELOPE) == CLASS_UNKNOWN
    assert retryable_for_status(500, SIZE_ENVELOPE) is False


def test_credits_refusal_is_its_own_class() -> None:
    assert classify_gateway_error(CREDITS_ENVELOPE) == CLASS_QUOTA
    assert is_gateway_quota_error(CREDITS_ENVELOPE) is True
    # Permanent for this request, but not a reason to wall the node: the fix
    # is a top-up, not an edit to the prompt.
    assert is_transient_error_message(CREDITS_ENVELOPE) is False


def test_a_repr_serialised_envelope_still_classifies() -> None:
    """The main loop hands over a repr, not JSON, and must not read as blank.

    A regex that only accepts double quotes finds no envelope here, so the
    caller falls back to its status rule and the provider's own
    ``retryable: False`` is discarded - which is how one Credits refusal
    turned into repeated failures inside two seconds.
    """
    assert gateway_error_code(CREDITS_REPR_ENVELOPE) == (
        "ASP.BIZ.CREDITS_INSUFFICIENT"
    )
    assert classify_gateway_error(CREDITS_REPR_ENVELOPE) == CLASS_QUOTA
    assert is_gateway_quota_error(CREDITS_REPR_ENVELOPE) is True
    assert gateway_request_id(CREDITS_REPR_ENVELOPE) == (
        "70491bf2-9f12-4e43-82c1-bab4a321f647"
    )
    assert retryable_for_status(403, CREDITS_REPR_ENVELOPE) is False


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("ASP.UPSTREAM.TIMEOUT", CLASS_TRANSIENT),
        ("ASP.COMM.RATE_LIMITED", CLASS_TRANSIENT),
        ("ASP.BIZ.MODEL_NOT_ALLOWED", CLASS_PERMANENT),
        ("ASP.PROXY.API_KEY_INVALID", CLASS_PERMANENT),
        ("ASP.BIZ.CREDITS_INSUFFICIENT", CLASS_QUOTA),
        ("ASP.SOMETHING.NEW", CLASS_UNKNOWN),
    ],
)
def test_classification_keys_on_the_code(code: str, expected: str) -> None:
    body = f'{{"code": "{code}", "retryable": true}}'
    assert classify_gateway_error(body) == expected
    # The provider's own flag never decides: it says retryable for all six.
    assert retryable_for_status(502, body) == (expected == CLASS_TRANSIENT)


def test_providers_without_an_envelope_keep_the_status_rule() -> None:
    """Bailian/Ark publish no envelope, so 5xx and 429 stay retryable."""
    assert classify_gateway_error("upstream connect error") == ""
    assert retryable_for_status(503, "upstream connect error") is True
    assert retryable_for_status(429, "too many requests") is True
    assert retryable_for_status(400, "bad request") is False
    assert is_transient_error_message("status 503: upstream busy") is True


def test_persisted_retryable_flag_does_not_outrank_the_envelope() -> None:
    """The stored flag is what the raising layer believed, not the truth."""
    assert (
        is_transient_task_error(
            {"message": UPSTREAM_ENVELOPE, "retryable": True},
        )
        is False
    )
    # Without an envelope the flag still speaks, so existing providers keep
    # the behaviour their executors were written against.
    assert (
        is_transient_task_error(
            {"message": "socket hang up", "retryable": True},
        )
        is True
    )
    assert is_transient_task_error({"message": "", "retryable": True}) is True


def test_request_id_is_lifted_out_for_handover() -> None:
    assert (
        gateway_request_id(UPSTREAM_ENVELOPE)
        == "d5507d1b-1059-9635-989e-e1f0c1b6b62e"
    )
    suffix = _provider_error_suffix(Exception(UPSTREAM_ENVELOPE))
    assert "provider_code=ASP.UPSTREAM.ERROR" in suffix
    assert "provider_request_id=d5507d1b-1059-9635-989e-e1f0c1b6b62e" in suffix
    # A provider that publishes nothing adds no noise to the user's message.
    assert _provider_error_suffix(Exception("socket hang up")) == ""


def test_model_error_from_a_gateway_4xx_is_marked_permanent() -> None:
    """The raising layers must not default a client fault to retryable."""
    error = ModelError(
        f"Video task submission failed with status 400: {UPSTREAM_ENVELOPE}",
        retryable=retryable_for_status(400, UPSTREAM_ENVELOPE),
    )
    assert error.retryable is False
    transient = ModelError(
        "Video task submission failed with status 503: upstream busy",
        retryable=retryable_for_status(503, "upstream busy"),
    )
    assert transient.retryable is True


# Measured on 2026-09-17: the proxy invented a name for an old condition.
# Concurrency throttling arrives as a 429 whose text says "please retry
# later", while the envelope reports retryable:false. No table can hold a
# code that did not exist when the table was written, so an unlisted code
# defers to the status the proxy now passes through.
CONCURRENCY_ENVELOPE = (
    "Text model 请求失败 [protocol=OpenAI-compatible "
    "model=qwen3.8-flash] HTTP 429: "
    '{"error":{"code":"ASP.BIZ.TOO_MANY_CONCURRENT_REQUESTS",'
    '"message":"并发计费任务过多，请稍后重试","retryable":false,'
    '"type":"BUSINESS"},'
    '"request_id":"96eebdd1-76fd-4b94-b668-3ac889244b83"}'
)


def test_an_unlisted_code_defers_to_the_passed_through_status() -> None:
    assert classify_gateway_error(CONCURRENCY_ENVELOPE) == CLASS_TRANSIENT
    assert is_transient_error_message(CONCURRENCY_ENVELOPE) is True
    assert retryable_for_status(429, CONCURRENCY_ENVELOPE) is True


def test_a_4xx_status_still_walls_an_unlisted_code() -> None:
    # Only the status changes: a 4xx for an unknown code stays a wall, so
    # deferring to the status does not turn into "retry everything".
    assert (
        classify_gateway_error(
            CONCURRENCY_ENVELOPE.replace("HTTP 429", "HTTP 400"),
        )
        == CLASS_UNKNOWN
    )


def test_a_measured_wrapper_keeps_walling_even_at_502() -> None:
    # Both the status and the provider's flag say retry; measured behaviour
    # says the request can never succeed, so the code still wins.
    assert classify_gateway_error(UPSTREAM_ENVELOPE) == CLASS_UNKNOWN
    assert is_transient_error_message(UPSTREAM_ENVELOPE) is False


def test_a_severed_stream_is_transient_without_any_envelope() -> None:
    # An httpx transport error carries no body: nothing was billed because the
    # response never completed, which is what makes the retry safe.
    assert (
        is_transient_error_message(
            "Text model request failed [protocol=AgentScope Platform] "
            "RemoteProtocolError: peer closed connection without sending "
            "complete message body (incomplete chunked read)",
        )
        is True
    )
