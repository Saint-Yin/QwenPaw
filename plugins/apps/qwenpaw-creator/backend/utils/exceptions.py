# -*- coding: utf-8 -*-
# pylint: disable=redefined-builtin
"""Custom exception hierarchy for structured error handling."""


class AppError(Exception):
    """Base application exception with error code and HTTP status."""

    def __init__(
        self,
        message: str,
        code: str = "INTERNAL_ERROR",
        status_code: int = 500,
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


class AgentError(AppError):
    """Agent execution exception."""

    def __init__(self, message: str, agent_name: str = ""):
        super().__init__(message, code="AGENT_ERROR", status_code=500)
        self.agent_name = agent_name


class ModelError(AppError):
    """Model invocation exception (upstream API failure)."""

    def __init__(
        self,
        message: str,
        model_name: str = "",
        retryable: bool = True,
    ):
        super().__init__(message, code="MODEL_ERROR", status_code=502)
        self.model_name = model_name
        # 永久性错误（如上游 4xx 客户端错误）应标记为不可重试，
        # 供轮询等调用方快速失败，避免空等到超时。
        self.retryable = retryable


class ValidationError(AppError):
    """Request validation exception."""

    def __init__(self, message: str):
        super().__init__(message, code="VALIDATION_ERROR", status_code=422)


class TimeoutError(AppError):
    """Operation timeout exception."""

    def __init__(self, message: str, operation: str = ""):
        super().__init__(message, code="TIMEOUT_ERROR", status_code=504)
        self.operation = operation
