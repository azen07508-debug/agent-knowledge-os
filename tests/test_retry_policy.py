"""Phase 15：Retry Policy（分类 + 重试矩阵）。"""

from runtime.retry_policy import (
    INVALID_PARAM,
    NETWORK,
    RATE_LIMIT,
    SERVER_ERROR,
    TIMEOUT,
    UNKNOWN,
    classify,
    decide_retry,
)


def test_no_retry_classes():
    for code in ("400", "INVALID_PARAM", "401", "403", "AUTH_FAILED",
                 "POLICY_VIOLATION", "409", "DUPLICATE", "NOT_IMPLEMENTED", "BOGUS_CODE"):
        decision = decide_retry(code, "whatever")

        assert decision.retryable is False, code
        assert decision.delay_seconds == 0


def test_timeout_never_retries_and_says_reconcile():
    decision = decide_retry("TIMEOUT", "twitter post timed out after 15s")

    assert decision.retryable is False
    assert decision.error_class == TIMEOUT
    assert "reconcile" in decision.reason


def test_network_and_5xx_retry_with_delay():
    network = decide_retry("NETWORK", "connection refused", attempt_no=1, default_delay=60)
    server = decide_retry("502", "bad gateway", attempt_no=1, default_delay=60)

    assert network.retryable is True and network.delay_seconds == 60
    assert network.error_class == NETWORK
    assert server.retryable is True and server.error_class == SERVER_ERROR


def test_rate_limit_honors_retry_after():
    decision = decide_retry("RATE_LIMIT", "", retry_after=120, attempt_no=1)

    assert decision.retryable is True and decision.delay_seconds == 120
    assert "retry-after=120" in decision.reason


def test_rate_limit_without_retry_after_uses_platform_default():
    decision = decide_retry("429", "", attempt_no=1, default_delay=30)

    assert decision.retryable is True and decision.delay_seconds == 30


def test_attempts_exhausted_stops_retrying():
    decision = decide_retry("500", "boom", attempt_no=3, max_attempts=3)

    assert decision.retryable is False and "最大尝试次数" in decision.reason


def test_classify_aliases_and_message_fallbacks():
    assert classify("429") == RATE_LIMIT
    assert classify("") == UNKNOWN
    assert classify("WHATEVER", "Connection refused by peer") == NETWORK
    assert classify("WHATEVER", "read timeout waiting for response") == TIMEOUT
    assert classify("param_error") == INVALID_PARAM  # 别名归一（大小写不敏感）
