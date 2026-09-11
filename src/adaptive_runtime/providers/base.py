from __future__ import annotations

from typing import Protocol

from adaptive_runtime.contracts.provider import ModelRequest, ModelResult, ProviderErrorCode


class ProviderCallError(RuntimeError):
    def __init__(
        self,
        *,
        code: ProviderErrorCode,
        message: str,
        retryable: bool,
        http_status: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.http_status = http_status


class ProviderAdapter(Protocol):
    def complete(self, request: ModelRequest) -> ModelResult: ...
