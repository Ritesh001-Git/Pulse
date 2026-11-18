"""Serializers: ORM rows → camelCase JSON matching the frontend contract.

Timestamps are epoch milliseconds (frontend convention).
"""
from __future__ import annotations

from typing import Any

from app.models import (
    CheckResult,
    Incident,
    IncidentSeverity,
    IncidentState,
    Service,
    TimelineEvent,
    User,
)

STATE_TO_STATUS = {"healthy": "up", "degraded": "degraded", "down": "down", "pending": "unknown"}


def ms(dt) -> int | None:
    return None if dt is None else int(dt.timestamp() * 1000)


def service_summary(service: Service, latest: CheckResult | None, availability: float) -> dict[str, Any]:
    # Stable state machine state (not the flickering latest check)
    status = STATE_TO_STATUS.get(service.state.value, "unknown")
    response_time = latest.latency_ms if latest else None
    return {
        "id": str(service.id),
        "name": service.name,
        "description": service.description,
        "url": service.url,
        "healthPath": service.health_path,
        "owner": service.team_owner,
        "status": status,
        "serviceState": service.state.value,
        "responseTimeMs": response_time,
        "availability": availability,
        "slaTarget": service.sla_target,
        "checkIntervalSec": service.check_interval_sec,
        "timeoutMs": service.timeout_ms,
        "degradedLatencyMs": service.degraded_latency_ms,
        "failureThreshold": service.failure_threshold,
        "recoveryThreshold": service.recovery_threshold,
        "consecutiveFailures": service.consecutive_failures,
        "isActive": service.is_active,
        "lastCheckedAt": ms(latest.checked_at) if latest else None,
    }


def incident_summary(inc: Incident) -> dict[str, Any]:
    return {
        "id": str(inc.id),
        "serviceId": str(inc.service_id),
        "serviceName": inc.service.name if inc.service else None,
        "title": inc.title,
        "severity": inc.severity.value,
        "state": inc.state.value,
        "acknowledged": inc.acknowledged,
        "ackedBy": inc.acknowledged_by_user.name if inc.acknowledged_by_user else None,
        "ackedAt": ms(inc.acknowledged_at),
        "openedAt": ms(inc.opened_at),
        "resolvedAt": ms(inc.resolved_at),
        "reopenedCount": inc.reopened_count,
    }


def timeline_event(ev: TimelineEvent) -> dict[str, Any]:
    return {
        "at": ms(ev.at),
        "actor": ev.actor.value,
        "who": ev.actor_user.name if ev.actor_user else None,
        "kind": ev.kind.value,
        "message": ev.message,
    }


def user_public(user: User) -> dict[str, Any]:
    return {"id": str(user.id), "email": user.email, "name": user.name, "role": user.role.value}
