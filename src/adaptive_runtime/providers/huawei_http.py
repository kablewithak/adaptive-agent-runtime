from __future__ import annotations

from adaptive_runtime.contracts.provider import ProviderErrorCode
from adaptive_runtime.providers.base import ProviderCallError


def classify_huawei_http_error(status_code: int) -> ProviderCallError:
    if status_code == 400:
        code = ProviderErrorCode.PROVIDER_REJECTED
        retryable = False
    elif status_code == 401:
        code = ProviderErrorCode.AUTHENTICATION_FAILED
        retryable = False
    elif status_code == 403:
        code = ProviderErrorCode.ENTITLEMENT_DENIED
        retryable = False
    elif status_code == 404:
        code = ProviderErrorCode.MODEL_UNAVAILABLE
        retryable = False
    elif status_code == 429:
        code = ProviderErrorCode.RATE_LIMITED
        retryable = True
    elif 500 <= status_code <= 599:
        code = ProviderErrorCode.PROVIDER_UNAVAILABLE
        retryable = True
    else:
        code = ProviderErrorCode.PROTOCOL_ERROR
        retryable = False

    return ProviderCallError(
        code=code,
        message=f"Huawei MaaS request failed with HTTP {status_code}",
        retryable=retryable,
        http_status=status_code,
    )
