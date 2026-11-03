"""Unit tests for CircuitBreaker state machine."""

import time
from unittest.mock import patch

from apps.gateway.execution.pipeline import CircuitBreaker, CircuitBreakerState


def _cb(threshold: int = 3, cooldown: float = 60.0) -> CircuitBreaker:
    return CircuitBreaker(failure_threshold=threshold, cooldown_seconds=cooldown)


class TestCircuitBreakerClosed:
    def test_starts_closed(self) -> None:
        assert _cb().state is CircuitBreakerState.CLOSED

    def test_allows_requests_when_closed(self) -> None:
        assert _cb().allow_request() is True

    def test_stays_closed_below_threshold(self) -> None:
        cb = _cb(threshold=3)
        cb.record_failure()
        cb.record_failure()
        assert cb.state is CircuitBreakerState.CLOSED

    def test_opens_at_threshold(self) -> None:
        cb = _cb(threshold=3)
        for _ in range(3):
            cb.record_failure()
        assert cb.state is CircuitBreakerState.OPEN

    def test_success_resets_failure_count(self) -> None:
        cb = _cb(threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        cb.record_failure()
        cb.record_failure()
        assert cb.state is CircuitBreakerState.CLOSED


class TestCircuitBreakerOpen:
    def test_rejects_requests_when_open(self) -> None:
        cb = _cb(threshold=1, cooldown=60.0)
        cb.record_failure()
        assert cb.state is CircuitBreakerState.OPEN
        assert cb.allow_request() is False

    def test_transitions_to_half_open_after_cooldown(self) -> None:
        cb = _cb(threshold=1, cooldown=0.05)
        cb.record_failure()
        time.sleep(0.1)
        assert cb.allow_request() is True
        assert cb.state is CircuitBreakerState.HALF_OPEN


class TestCircuitBreakerHalfOpen:
    def test_success_in_half_open_closes_circuit(self) -> None:
        cb = _cb(threshold=1, cooldown=0.05)
        cb.record_failure()
        time.sleep(0.1)
        cb.allow_request()  # transitions to HALF_OPEN
        cb.record_success()
        assert cb.state is CircuitBreakerState.CLOSED

    def test_failure_in_half_open_reopens_circuit(self) -> None:
        cb = _cb(threshold=1, cooldown=0.05)
        cb.record_failure()
        time.sleep(0.1)
        cb.allow_request()  # transitions to HALF_OPEN
        cb.record_failure()
        assert cb.state is CircuitBreakerState.OPEN
