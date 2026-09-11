# -*- coding: utf-8 -*-
"""Classify provider gateway errors by error code, not by wording.

The AgentScope model proxy (platform-pre) wraps upstream failures in its own
envelope and stamps ``retryable: true`` on errors that are demonstrably
deterministic. Measured samples (all of them returned in ~0.1s):

- missing required field in the body -> 502 ``ASP.UPSTREAM.ERROR``,
  ``retryable: true``, deterministic
- unresolvable reference-image host -> 502 ``ASP.UPSTREAM.ERROR``,
  ``retryable: true``, deterministic
- body over the gateway limit (8MB) -> 500 ``ASP.SYS.INTERNAL_ERROR``,
  ``retryable: true``, deterministic
- model not on the allowlist -> 400 ``ASP.BIZ.MODEL_NOT_ALLOWED``,
  ``retryable: false`` (correct)
- Credits exhausted -> 403 ``ASP.BIZ.CREDITS_INSUFFICIENT``,
  ``retryable: false`` (correct, but it reads like a permission failure)

Trusting the field means an unattended run re-sends requests that can never
succeed - each of which may still be billed upstream.  So classification here
keys on ``code`` alone and **fails closed**: an unknown code is treated as
non-retryable, because a wrong "retry" costs money while a wrong "don't retry"
only costs one user-visible failure.

Substring matching over message text is deliberately avoided: the same body
text appears for a broken configuration and for an exhausted balance, and the
403 Credits error reads like a permission failure.
"""

from __future__ import annotations

import re

# The envelope may be embedded in a larger message (callers append their own
# context and the raw provider body), so the code is extracted by pattern
# rather than by parsing the whole string as JSON.
_CODE_RE = re.compile(r'"code"\s*:\s*"(ASP\.[A-Z0-9_.]+)"')
_REQUEST_ID_RE = re.compile(r'"request_id"\s*:\s*"([0-9a-fA-F-]{8,})"')

# Only errors that are transient *because of the code itself* are retried.
GATEWAY_TRANSIENT_CODES = frozenset(
    {
        "ASP.UPSTREAM.UNAVAILABLE",
        "ASP.UPSTREAM.TIMEOUT",
        "ASP.UPSTREAM.CONNECTION_RESET",
        "ASP.COMM.RATE_LIMITED",
    },
)

# Configuration mistakes: retrying cannot fix them and the user must act.
GATEWAY_PERMANENT_CODES = frozenset(
    {
        "ASP.AUTH.UNAUTHORIZED",
        "ASP.PROXY.API_KEY_MISSING",
        "ASP.PROXY.API_KEY_INVALID",
        "ASP.BIZ.MODEL_NOT_ALLOWED",
        "ASP.COMM.NOT_FOUND",
    },
)

# Spending is stopped for the whole account, not for this request.
GATEWAY_QUOTA_CODES = frozenset({"ASP.BIZ.CREDITS_INSUFFICIENT"})

CLASS_TRANSIENT = "transient"
CLASS_PERMANENT = "permanent"
CLASS_QUOTA = "quota"
CLASS_UNKNOWN = "unknown"


def gateway_error_code(text: str) -> str:
    """The gateway error code embedded in *text*, or "" when there is none."""
    match = _CODE_RE.search(text or "")
    return match.group(1) if match else ""


def gateway_request_id(text: str) -> str:
    """The provider's request id, so a failure can be handed over."""
    match = _REQUEST_ID_RE.search(text or "")
    return match.group(1) if match else ""


def classify_gateway_error(text: str) -> str:
    """Classify by code: transient / permanent / quota / unknown / "".

    "" means the text carries no gateway envelope at all, so the caller keeps
    whatever judgement it applies to its own provider (DashScope, Ark, …).
    """
    code = gateway_error_code(text)
    if not code:
        return ""
    if code in GATEWAY_QUOTA_CODES:
        return CLASS_QUOTA
    if code in GATEWAY_TRANSIENT_CODES:
        return CLASS_TRANSIENT
    if code in GATEWAY_PERMANENT_CODES:
        return CLASS_PERMANENT
    # ASP.UPSTREAM.ERROR / ASP.SYS.INTERNAL_ERROR / anything unlisted: measured
    # samples show these carry deterministic client-side causes, so no retry.
    return CLASS_UNKNOWN


def is_gateway_quota_error(text: str) -> bool:
    """True when the provider refuses to spend more Credits."""
    return classify_gateway_error(text) == CLASS_QUOTA


def is_gateway_transient(text: str) -> bool:
    """True only for codes that are transient by their own nature."""
    return classify_gateway_error(text) == CLASS_TRANSIENT


def retryable_for_status(status_code: int, body: str = "") -> bool:
    """Retry decision for one HTTP failure, gateway code winning over status.

    Keeps the existing "5xx and 429 are transient" rule for providers that
    publish no envelope, while refusing to retry a gateway error that reports
    itself as retryable.
    """
    classified = classify_gateway_error(body)
    if classified:
        return classified == CLASS_TRANSIENT
    return status_code >= 500 or status_code == 429


__all__ = [
    "CLASS_PERMANENT",
    "CLASS_QUOTA",
    "CLASS_TRANSIENT",
    "CLASS_UNKNOWN",
    "GATEWAY_PERMANENT_CODES",
    "GATEWAY_QUOTA_CODES",
    "GATEWAY_TRANSIENT_CODES",
    "classify_gateway_error",
    "gateway_error_code",
    "gateway_request_id",
    "is_gateway_quota_error",
    "is_gateway_transient",
    "retryable_for_status",
]
