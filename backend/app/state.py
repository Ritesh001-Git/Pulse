"""Service state machine — PURE logic, no I/O. Fully unit-testable.

Three service states (plus 'pending' for never-checked services):
    healthy / degraded / down

Inputs per check:
    - HTTP outcome: status_code, latency_ms, error (from httpx)
    - service thresholds: degraded_latency_ms, failure_threshold, recovery_threshold
    - persisted consecutive counters (so streaks survive restarts)

Transition rules
----------------
Classification of a single check (classify_response):
    error/timeout          -> down
    non-2xx/3xx status     -> down
    2xx/3xx + high latency -> degraded
    2xx/3xx + low latency  -> up

State transitions (next_service_state), with F = failure_threshold, R = recovery_threshold:
    up check:
        pending                -> healthy            (first evidence of life)
        healthy                -> healthy
        degraded/down          -> healthy ONLY after R consecutive ups (no single-check recovery)
    degraded check:
        down                   -> down               (never downgrade an outage)
        healthy/pending        -> degraded after F consecutive failures, else unchanged
    down check:
        any state              -> down after F consecutive failures, else unchanged
        (degraded failures count toward the same streak, so dg,dg,down => down)
"""
from __future__ import annotations

import enum
from dataclasses import dataclass

from app.models import CheckStatus


class ServiceState(str, enum.Enum):
    PENDING = "pending"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DOWN = "down"


@dataclass
class StateTransition:
    old_state: ServiceState
    new_state: ServiceState
    consecutive_failures: int
    consecutive_successes: int
    changed: bool

    def __str__(self) -> str:  # pragma: no cover
        arrow = "->" if self.changed else "=="
        return f"{self.old_state.value} {arrow} {self.new_state.value}"


def classify_response(
    status_code: int | None,
    latency_ms: int | None,
    degraded_latency_ms: int,
) -> CheckStatus:
    """Classify ONE HTTP outcome. Pure function."""
    if status_code is None:
        # timeout or connection error — no response at all
        return CheckStatus.DOWN
    if not (200 <= status_code < 400):
        return CheckStatus.DOWN
    if latency_ms is not None and latency_ms > degraded_latency_ms:
        return CheckStatus.DEGRADED
    return CheckStatus.UP


def next_service_state(
    current: ServiceState,
    check: CheckStatus,
    consecutive_failures: int,
    consecutive_successes: int,
    failure_threshold: int,
    recovery_threshold: int,
) -> StateTransition:
    """Advance the service state machine by one check. Pure function."""
    if check == CheckStatus.UP:
        failures = 0
        successes = consecutive_successes + 1
        if current == ServiceState.PENDING:
            new = ServiceState.HEALTHY  # first successful check after registration
        elif current in (ServiceState.DEGRADED, ServiceState.DOWN):
            new = ServiceState.HEALTHY if successes >= recovery_threshold else current
        else:
            new = current
    elif check == CheckStatus.DEGRADED:
        failures = consecutive_failures + 1
        successes = 0
        if current == ServiceState.DOWN:
            new = ServiceState.DOWN  # never downgrade an outage
        elif failures >= failure_threshold:
            new = ServiceState.DEGRADED
        else:
            new = current
    else:  # DOWN
        failures = consecutive_failures + 1
        successes = 0
        if failures >= failure_threshold:
            new = ServiceState.DOWN
        else:
            new = current

    return StateTransition(
        old_state=current,
        new_state=new,
        consecutive_failures=failures,
        consecutive_successes=successes,
        changed=new != current,
    )
