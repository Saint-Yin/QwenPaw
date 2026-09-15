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
