"""Health-check execution and recording.

Separation of concerns:
    fetch_outcome   — I/O only (httpx). Returns raw outcome, classifies nothing.
    state.classify_response — PURE classification (unit-testable).
    record_check    — persistence + service state machine + incident detection.
"""
from __future__ import annotations

import logging
from collections import Counter

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    ActorKind,
    CheckResult,
    CheckStatus,
    Incident,
    IncidentSeverity,
    IncidentState,
    Notification,
    NotificationChannel,
    NotificationStatus,
    Service,
    TimelineEvent,
    TimelineEventKind,
)
from app.models import utcnow
from app.state import ServiceState, classify_response, next_service_state

logger = logging.getLogger("pulse.checker")

# Streak-boundary sentinel for "no up check ever recorded".
from datetime import datetime, timezone

EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)

_SEVERITY_ORDER = {CheckStatus.UP: 0, CheckStatus.DEGRADED: 1, CheckStatus.DOWN: 2}


def worst_status(statuses) -> CheckStatus | None:
    if not statuses:
        return None
    return max(statuses, key=lambda s: _SEVERITY_ORDER[s])


def worst_detail(service: Service, streak_statuses) -> str:
    counts = Counter(s.value for s in streak_statuses)
    parts = [f"{n}x {s}" for s, n in sorted(counts.items(), key=lambda kv: -_SEVERITY_ORDER[CheckStatus(kv[0])])]
    return f"{len(streak_statuses)} consecutive failing checks ({', '.join(parts)})"


async def fetch_outcome(service: Service) -> tuple[int | None, int | None, str | None]:
    """Perform the HTTP GET. Returns (status_code, latency_ms, error).

    Pure I/O — classification happens in state.classify_response.
    """
    url = service.url.rstrip("/") + service.health_path
    timeout_s = service.timeout_ms / 1000
    try:
        async with httpx.AsyncClient(timeout=timeout_s, follow_redirects=True) as client:
            resp = await client.get(url)
        latency = int(resp.elapsed.total_seconds() * 1000)
        return resp.status_code, latency, None
    except httpx.TimeoutException:
        return None, None, f"timeout after {service.timeout_ms}ms"
    except httpx.HTTPError as exc:
        return None, None, str(exc)


async def execute_http_check(service: Service) -> tuple[CheckStatus, int | None, int | None, str | None]:
    """Convenience for on-demand checks: fetch + classify. Returns (status, latency, code, error)."""
    code, latency, error = await fetch_outcome(service)
    status = classify_response(code, latency, service.degraded_latency_ms)
    return status, latency, code, error


async def record_check(
    db: AsyncSession, service: Service, status_code: int | None, latency_ms: int | None, error: str | None
) -> tuple[CheckResult, "ServiceState", bool]:
    """Classify, persist the CheckResult, advance the service state machine,
    auto-resolve incidents on sustained recovery, detect new failures.

    Returns (check_result, new_state, state_changed). Commit is left to the caller.
    """
    status = classify_response(status_code, latency_ms, service.degraded_latency_ms)
    detail = error or (f"latency {latency_ms}ms > {service.degraded_latency_ms}ms threshold"
                       if status == CheckStatus.DEGRADED else error)

    result = CheckResult(
        service_id=service.id,
        status=status,
        latency_ms=latency_ms,
        status_code=status_code,
        error=detail,
        checked_at=utcnow(),
    )
    db.add(result)

    transition = next_service_state(
        current=ServiceState(service.state.value),
        check=status,
        consecutive_failures=service.consecutive_failures,
        consecutive_successes=service.consecutive_successes,
        failure_threshold=service.failure_threshold,
        recovery_threshold=service.recovery_threshold,
    )
    service.state = transition.new_state
    service.consecutive_failures = transition.consecutive_failures
    service.consecutive_successes = transition.consecutive_successes
    await db.flush()

    if transition.changed:
        logger.info("state transition [%s]: %s", service.name, transition)

    if status == CheckStatus.UP and transition.new_state == ServiceState.HEALTHY:
        await auto_resolve_if_recovered(db, service, transition.consecutive_successes)
    else:
        await detect_incident(db, service, result)
    return result, transition.new_state, transition.changed


REOPEN_COOLDOWN_SEC = 15 * 60  # re-breaks within 15min reopen the incident, later ones are new


async def auto_resolve_if_recovered(db: AsyncSession, service: Service, successes: int) -> None:
    """Resolve the active incident when the service has recovered for good.

    Called once the state machine confirms HEALTHY (recovery_threshold consecutive ups).
    """
    from app.engines import notifier

    active = (
        await db.execute(
            select(Incident)
            .where(Incident.service_id == service.id, Incident.resolved_at.is_(None))
        )
    ).scalar_one_or_none()
    if active is None:
        return
    active.state = IncidentState.RESOLVED
    active.resolved_at = utcnow()
    db.add(
        TimelineEvent(
            incident_id=active.id,
            actor=ActorKind.SYSTEM,
            kind=TimelineEventKind.RESOLVED,
            message=(
                f"Sustained recovery observed ({successes} consecutive successful checks). "
                "Incident resolved automatically."
            ),
        )
    )
    await db.flush()
    logger.info("auto-resolved incident %s for [%s]", active.id, service.name)
    notifier.notify("incident.resolved", active.id, service.name, incident_payload_summary(active, service))


def incident_payload_summary(inc: Incident, service: Service) -> dict:
    return {
        "title": inc.title,
        "severity": inc.severity.value if hasattr(inc.severity, "value") else inc.severity,
        "state": inc.state.value if hasattr(inc.state, "value") else inc.state,
        "acknowledged": inc.acknowledged,
        "_service_id": str(service.id),
        "openedAt": int(inc.opened_at.timestamp() * 1000) if inc.opened_at else None,
        "resolvedAt": int(inc.resolved_at.timestamp() * 1000) if inc.resolved_at else None,
    }


async def detect_incident(db: AsyncSession, service: Service, result: CheckResult) -> Incident | None:
    """Streak-based failure detection with worst-in-streak severity.

    - Streak = all checks since the last `up` (never crosses a recovery boundary).
    - Trigger: streak length >= failure_threshold.
    - Severity: WORST status in the streak — any `down` => outage; a degraded
      check can never downgrade an outage-level streak.
    - Escalation: active degradation incident + a `down` => severity upgraded
      to outage + timeline event.
    """
    if result.status == CheckStatus.UP:
        return None

    active = (
        await db.execute(
            select(Incident)
            .where(Incident.service_id == service.id, Incident.resolved_at.is_(None))
        )
    ).scalar_one_or_none()

    last_up_at = (
        await db.execute(
            select(CheckResult.checked_at)
            .where(
                CheckResult.service_id == service.id,
                CheckResult.status == CheckStatus.UP,
                CheckResult.checked_at <= result.checked_at,
            )
            .order_by(CheckResult.checked_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    streak_statuses = (
        await db.execute(
            select(CheckResult.status)
            .where(
                CheckResult.service_id == service.id,
                CheckResult.checked_at > (last_up_at or EPOCH),
            )
            .order_by(CheckResult.checked_at)
        )
    ).scalars().all()

    streak_len = len(streak_statuses)
    worst = worst_status(streak_statuses)

    if active is not None:
        if active.severity == IncidentSeverity.DEGRADATION and worst == CheckStatus.DOWN:
            active.severity = IncidentSeverity.OUTAGE
            active.title = f"{service.name}: unreachable — {worst_detail(service, streak_statuses)}"
            db.add(
                TimelineEvent(
                    incident_id=active.id,
                    actor=ActorKind.SYSTEM,
                    kind=TimelineEventKind.STATUS_CHANGED,
                    message=(
                        f"Severity escalated to OUTAGE: a 'down' check occurred during the current "
                        f"failing streak (streak length {streak_len})."
                    ),
                )
            )
            await db.flush()
            from app.engines import notifier

            notifier.notify(
                "incident.escalated", active.id, service.name, incident_payload_summary(active, service)
            )
            return active
        return None

    if streak_len < service.failure_threshold:
        return None

    severity = IncidentSeverity.OUTAGE if worst == CheckStatus.DOWN else IncidentSeverity.DEGRADATION
    detail = worst_detail(service, streak_statuses)

    # Reopen vs new: a re-break shortly after an auto-resolve continues the
    # previous incident (same root cause likely); an older one starts fresh.
    previous = (
        await db.execute(
            select(Incident)
            .where(
                Incident.service_id == service.id,
                Incident.resolved_at.is_not(None),
                Incident.reopened_count >= 0,
            )
            .order_by(Incident.resolved_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    import time as _time

    recently_resolved = (
        previous is not None
        and (utcnow() - previous.resolved_at).total_seconds() <= REOPEN_COOLDOWN_SEC
        and previous.reopened_count < 3  # cap reopen cycles; beyond that create new
    )

    if recently_resolved:
        previous.resolved_at = None
        previous.reopened_count += 1
        previous.state = IncidentState.INVESTIGATING
        previous.title = f"{service.name}: {'unreachable' if severity == IncidentSeverity.OUTAGE else 'degraded'} — {detail}"
        db.add(
            TimelineEvent(
                incident_id=previous.id,
                actor=ActorKind.SYSTEM,
                kind=TimelineEventKind.AUTO_DETECTED,
                message=(
                    f"Incident REOPENED (#{previous.reopened_count}): failing again within the "
                    f"re-open window — {detail}."
                ),
            )
        )
        await db.flush()
        logger.info("reopened incident %s for [%s] (count=%d)", previous.id, service.name, previous.reopened_count)
        from app.engines import notifier

        notifier.notify("incident.reopened", previous.id, service.name, incident_payload_summary(previous, service))
        return previous

    inc = Incident(
        service_id=service.id,
        title=f"{service.name}: {'unreachable' if severity == IncidentSeverity.OUTAGE else 'degraded'} — {detail}",
        severity=severity,
        state=IncidentState.INVESTIGATING,
    )
    db.add(inc)
    await db.flush()
    db.add_all(
        [
            TimelineEvent(
                incident_id=inc.id,
                actor=ActorKind.SYSTEM,
                kind=TimelineEventKind.AUTO_DETECTED,
                message=f"{detail}. Incident opened automatically.",
            ),
            Notification(
                incident_id=inc.id,
                channel="webhook",
                audience="engineers",
                event="incident.created",
                status=NotificationStatus.PENDING,
                detail=f"incident {inc.id} opened for {service.name} ({severity.value})",
            ),
        ]
    )
    await db.flush()
    from app.engines import notifier

    notifier.notify("incident.created", inc.id, service.name, incident_payload_summary(inc, service))
    return inc
