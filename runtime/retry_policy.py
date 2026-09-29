"""Phase 15：Retry Policy（错误分类 + 重试决策矩阵）。

矩阵（默认，平台 contract 可通过 retry_after 影响延迟）：

| 错误类            | 重试 | 说明 |
| ----------------- | ---- | ---- |
| AUTH              | 否   | 鉴权失败 |
| INVALID_PARAM     | 否   | 参数类 4xx |
| CONTENT_VIOLATION | 否   | 内容违规 |
| DUPLICATE         | 否   | 重复内容 |
| TIMEOUT           | 否   | **必须先 reconcile，禁止直接 retry** |
| NOT_IMPLEMENTED   | 否   | contract-only 平台，没有真实 API |
| NO_ADAPTER / BUILDER_ERROR / UNKNOWN | 否 | 配置/构建错误或不明确的失败，保守不重试 |
| NETWORK           | 是   | 明确网络连接失败 |
| SERVER_ERROR      | 是   | 5xx |
| RATE_LIMIT        | 是   | 依 retry-after / 平台 contract 定延迟 |

重试必须产生新的 PublishJobAttempt，不允许覆盖旧 attempt。
"""

from __future__ import annotations

from dataclasses import dataclass

AUTH = "AUTH"
INVALID_PARAM = "INVALID_PARAM"
CONTENT_VIOLATION = "CONTENT_VIOLATION"
DUPLICATE = "DUPLICATE"
TIMEOUT = "TIMEOUT"
NETWORK = "NETWORK"
SERVER_ERROR = "SERVER_ERROR"
RATE_LIMIT = "RATE_LIMIT"
NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
NO_ADAPTER = "NO_ADAPTER"
BUILDER_ERROR = "BUILDER_ERROR"
UNKNOWN = "UNKNOWN"

RETRYABLE = {NETWORK, SERVER_ERROR, RATE_LIMIT}

_CODE_ALIASES = {
    # 平台/适配器可能给出的码 → 归一到内部分类
    "400": INVALID_PARAM, "422": INVALID_PARAM, "BAD_REQUEST": INVALID_PARAM,
    "INVALID_PARAM": INVALID_PARAM, "PARAM_ERROR": INVALID_PARAM,
    "401": AUTH, "403": AUTH, "AUTH_FAILED": AUTH, "UNAUTHORIZED": AUTH,
    "POLICY_VIOLATION": CONTENT_VIOLATION, "CONTENT_VIOLATION": CONTENT_VIOLATION,
    "SENSITIVE": CONTENT_VIOLATION,
    "409": DUPLICATE, "DUPLICATE": DUPLICATE, "ALREADY_POSTED": DUPLICATE,
    "TIMEOUT": TIMEOUT, "GATEWAY_TIMEOUT": TIMEOUT,
    "429": RATE_LIMIT, "RATE_LIMIT": RATE_LIMIT, "RATE_LIMITED": RATE_LIMIT,
    "500": SERVER_ERROR, "502": SERVER_ERROR, "503": SERVER_ERROR,
    "SERVER_ERROR": SERVER_ERROR, "INTERNAL_ERROR": SERVER_ERROR,
    "NETWORK": NETWORK, "CONNECTION": NETWORK, "ECONNREFUSED": NETWORK,
    "ENOTFOUND": NETWORK, "DNS": NETWORK,
    "NOT_IMPLEMENTED": NOT_IMPLEMENTED, "CONTRACT_ONLY": NOT_IMPLEMENTED,
    "NO_ADAPTER": NO_ADAPTER, "BUILDER_ERROR": BUILDER_ERROR,
}

_NETWORK_WORDS = ("connection refused", "connection reset", "network is unreachable",
                  "name or service not known", "getaddrinfo", "econnrefused", "enotfound")


def classify(error_code: str, message: str = "") -> str:
    """把 (error_code, message) 归一成内部错误类；识别不了 → UNKNOWN。"""
    code = (error_code or "").strip().upper()
    if code in _CODE_ALIASES:
        return _CODE_ALIASES[code]
    if code.isdigit() and code in _CODE_ALIASES:
        return _CODE_ALIASES[code]
    lowered = (message or "").lower()
    if any(word in lowered for word in _NETWORK_WORDS):
        return NETWORK
    if "timeout" in lowered:
        return TIMEOUT
    return UNKNOWN


@dataclass(frozen=True)
class RetryDecision:
    error_class: str
    retryable: bool
    delay_seconds: int   # 下一次尝试的等待（进 job.scheduled_at）
    reason: str


def decide_retry(
    error_code: str,
    message: str = "",
    retry_after: int | None = None,
    attempt_no: int = 1,
    max_attempts: int = 3,
    default_delay: int = 60,
) -> RetryDecision:
    """按矩阵给出重试决策；TIMEOUT 永远不可重试，必须先 reconcile。"""
    error_class = classify(error_code, message)

    if error_class == TIMEOUT:
        return RetryDecision(error_class, False, 0, "TIMEOUT 必须先 reconcile，禁止直接重试。")
    if error_class not in RETRYABLE:
        return RetryDecision(error_class, False, 0, f"{error_class} 不重试。")
    if attempt_no >= max_attempts:
        return RetryDecision(error_class, False, 0, f"已达最大尝试次数 {max_attempts}。")
    if error_class == RATE_LIMIT:
        if retry_after is None:
            return RetryDecision(error_class, True, default_delay,
                                 f"rate limit 未给 retry-after，按平台默认 {default_delay}s。")
        return RetryDecision(error_class, True, int(retry_after), f"按 retry-after={retry_after}s。")
    return RetryDecision(error_class, True, default_delay, f"{error_class} 可重试。")
