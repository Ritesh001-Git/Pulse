import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Integer, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_user
from app.models import CheckResult, CheckStatus, Incident, IncidentState, Service, utcnow
from app.resilience import get_db

router = APIRouter(prefix="/api/metrics", tags=["metrics"], dependencies=[Depends(get_current_user)])

WINDOWS = {"24h": 1, "7d": 7, "30d": 30}


def _parse_window(window: str) -> int:
    return WINDOWS.get(window, 30)


@router.get("/uptime")
async def uptime(window: str = Query(default="30d", pattern="^(24h|7d|30d)$"), service_id: str | None = None, db: AsyncSession = Depends(get_db)):
    since = utcnow() - timedelta(days=_parse_window(window))
    q = select(Service)
    if service_id:
        try:
            q = q.where(Service.id == uuid.UUID(service_id))
        except ValueError:
            return []
    services = (await db.execute(q)).scalars().all()
    out = []
    for svc in services:
        row = (
            await db.execute(
                select(func.count(), func.sum(func.cast(CheckResult.status == CheckStatus.DOWN, Integer)))
                .where(CheckResult.service_id == svc.id, CheckResult.checked_at >= since)
            )
        ).one()
        total, downs = row
        total = total or 0
        downs = downs or 0
        out.append(
            {
                "serviceId": str(svc.id),
                "serviceName": svc.name,
                "window": window,
                "totalChecks": total,
                "downChecks": downs,
                "uptimePct": 100.0 if total == 0 else round(100 * (1 - downs / total), 3),
            }
        )
    return out


@router.get("/latency")
async def latency(window: str = Query(default="24h", pattern="^(24h|7d|30d)$"), service_id: str | None = None, db: AsyncSession = Depends(get_db)):
    since = utcnow() - timedelta(days=_parse_window(window))
    q = select(
        CheckResult.service_id,
        func.avg(CheckResult.latency_ms),
        func.percentile_cont(0.5).within_group(CheckResult.latency_ms),
        func.percentile_cont(0.95).within_group(CheckResult.latency_ms),
        func.count(),
    ).where(CheckResult.checked_at >= since, CheckResult.latency_ms.is_not(None))
    if service_id:
        try:
            q = q.where(CheckResult.service_id == uuid.UUID(service_id))
        except ValueError:
            return []
    q = q.group_by(CheckResult.service_id)
    rows = (await db.execute(q)).all()
    names = {str(s.id): s.name for s in (await db.execute(select(Service))).scalars().all()}
    return [
        {
            "serviceId": str(svc_id),
            "serviceName": names.get(str(svc_id)),
            "window": window,
            "samples": count,
            "avgMs": round(float(avg or 0), 1),
            "p50Ms": round(float(p50 or 0), 1),
            "p95Ms": round(float(p95 or 0), 1),
        }
        for svc_id, avg, p50, p95, count in rows
    ]


@router.get("/slo")
async def slo(window: str = Query(default="30d", pattern="^(24h|7d|30d)$"), db: AsyncSession = Depends(get_db)):
    """SLO compliance + error budget per service, computed from real check records.

    Error budget = allowed downtime = (1 - slaTarget/100) × window minutes.
    Consumed = observed downtime minutes (down checks × interval approximation:
    each down check represents one check-interval of outage)."""
    days = _parse_window(window)
    since = utcnow() - timedelta(days=days)
    window_minutes = days * 24 * 60
    services = (await db.execute(select(Service))).scalars().all()
    out = []
    for svc in services:
        row = (
            await db.execute(
                select(
                    func.count(),
                    func.sum(func.cast(CheckResult.status == CheckStatus.DOWN, Integer)),
                    func.sum(func.cast(CheckResult.status == CheckStatus.DEGRADED, Integer)),
                ).where(CheckResult.service_id == svc.id, CheckResult.checked_at >= since)
            )
        ).one()
        total, downs, degraded = row
        total, downs, degraded = total or 0, downs or 0, degraded or 0
        uptime_pct = 100.0 if total == 0 else round(100 * (1 - downs / total), 3)
        # degraded minutes count at half weight against the budget (SLO is full-outage based)
        interval_min = svc.check_interval_sec / 60
        outage_minutes = downs * interval_min
        degraded_minutes = degraded * interval_min * 0.5
        budget_minutes = (1 - svc.sla_target / 100) * window_minutes
        consumed = outage_minutes + degraded_minutes
        remaining = max(0.0, budget_minutes - consumed)
        out.append(
            {
                "serviceId": str(svc.id),
                "serviceName": svc.name,
                "window": window,
                "slaTarget": svc.sla_target,
                "uptimePct": uptime_pct,
                "compliant": uptime_pct >= svc.sla_target,
                "errorBudgetMinutes": round(budget_minutes, 1),
                "budgetConsumedMinutes": round(consumed, 1),
                "budgetRemainingMinutes": round(remaining, 1),
                "budgetRemainingPct": round(100 * remaining / budget_minutes, 1) if budget_minutes > 0 else None,
            }
        )
    return out


@router.get("/incidents")
async def incident_metrics(window: str = Query(default="30d", pattern="^(24h|7d|30d)$"), db: AsyncSession = Depends(get_db)):
    since = utcnow() - timedelta(days=_parse_window(window))
    incidents = (
        await db.execute(
            select(Incident).where(Incident.opened_at >= since).order_by(Incident.opened_at)
        )
    ).scalars().all()

    resolved_durations = [
        (i.resolved_at - i.opened_at).total_seconds() for i in incidents if i.resolved_at is not None
    ]
    mttr_min = round(sum(resolved_durations) / len(resolved_durations) / 60, 1) if resolved_durations else None

    per_service: dict[str, dict] = {}
    for i in incidents:
        key = str(i.service_id)
        entry = per_service.setdefault(key, {"serviceId": key, "count": 0, "outages": 0, "degradations": 0})
        entry["count"] += 1
        if i.severity.value == "outage":
            entry["outages"] += 1
        else:
            entry["degradations"] += 1
    names = {str(s.id): s.name for s in (await db.execute(select(Service))).scalars().all()}
    for entry in per_service.values():
        entry["serviceName"] = names.get(entry["serviceId"])

    return {
        "window": window,
        "totalIncidents": len(incidents),
        "activeIncidents": sum(1 for i in incidents if i.resolved_at is None),
        "mttrMinutes": mttr_min,
        "perService": list(per_service.values()),
    }
