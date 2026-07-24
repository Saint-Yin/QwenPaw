# -*- coding: utf-8 -*-
"""Provider configuration and retry policy."""

from __future__ import annotations

import os

import httpx

from models import config as model_config

DEFAULT_VISUAL_SEARCH_PROVIDERS = ("tavily", "dashscope_web_search_image")
DEFAULT_VISUAL_SEARCH_MIN_RESULTS_FOR_FALLBACK = 2


def tavily_api_key() -> str:
    return model_config.get_web_grounding_tavily_api_key()


def dashscope_api_key() -> str:
    try:
        return model_config.get_web_grounding_model_api_key() or os.environ.get(
            "DASHSCOPE_API_KEY",
            "",
        )
    except Exception:
        return os.environ.get("DASHSCOPE_API_KEY", "")


def dashscope_base_url() -> str:
    try:
        return model_config.get_web_grounding_model_base_url()
    except Exception:
        return "https://dashscope.aliyuncs.com/compatible-mode/v1"


def dashscope_model() -> str:
    try:
        return model_config.get_web_grounding_model_name() or "qwen3.7-plus"
    except Exception:
        return "qwen3.7-plus"


def dashscope_web_search_api_key() -> str:
    """Text web search shares Creator's configured text-model credential."""
    return dashscope_api_key()


def dashscope_web_search_base_url() -> str:
    """Text web search shares Creator's configured text-model endpoint."""
    return dashscope_base_url()


def dashscope_web_search_model() -> str:
    """Text web search shares Creator's configured text model."""
    return dashscope_model()


def responses_url_from_base(base_url: str) -> str:
    base = str(base_url or "").strip().rstrip("/")
    if not base:
        base = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    if base.endswith("/responses"):
        return base
    if base.endswith("/chat/completions"):
        base = base[: -len("/chat/completions")]
    return f"{base}/responses"


def visual_search_provider_order() -> tuple[str, ...]:
    """Return the fixed product provider chain, filtered by availability."""

    available = {
        "tavily": bool(tavily_api_key()),
        "dashscope_web_search_image": bool(dashscope_api_key()),
    }
    providers = tuple(
        provider
        for provider in DEFAULT_VISUAL_SEARCH_PROVIDERS
        if available[provider]
    )
    return providers or DEFAULT_VISUAL_SEARCH_PROVIDERS


def visual_search_min_results_for_fallback() -> int:
    return DEFAULT_VISUAL_SEARCH_MIN_RESULTS_FOR_FALLBACK


def is_retryable_visual_search_error(exc: BaseException) -> bool:
    if isinstance(exc, (httpx.TimeoutException, httpx.TransportError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return (
            exc.response.status_code >= 500 or exc.response.status_code == 429
        )
    return False
