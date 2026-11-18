import uuid
from datetime import datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_user
from app.engines import checker
from app.models import (
    CheckResult,
    CheckStatus,
    Incident,
    IncidentSeverity,
    IncidentState,
    Service,
    TimelineEvent,
    TimelineEventKind,
    ActorKind,
    utcnow,
)
from app.resilience import get_db
from app.schemas import IncidentCreate, ServiceCreate, ServiceUpdate
from app.serializers import incident_summary, ms, service_summary
from sqlalchemy.orm import selectinload

router = APIRouter(prefix="/api/services", tags=["services"], dependencies=[Depends(get_current_user)])


async def _latest_check(db: AsyncSession, service_id) -> CheckResult | None:
    return (
        await db.execute(
            select(CheckResult).where(CheckResult.service_id == service_id).order_by(CheckResult.checked_at.desc()).limit(1)
        )
    ).scalar_one_or_none()


async def _availability_pct(db: AsyncSession, service_id, days: int = 30) -> float:
    """Uptime % over the window: 100 - (down checks / total * 100). No data → 100."""
    import datetime as dt

    since = utcnow() - dt.timedelta(days=days)
    row = (
        await db.execute(
            select(func.count(), func.sum(func.coalesce(func.cast(CheckResult.status == CheckStatus.DOWN, __import__("sqlalchemy").Integer), 0)))
            .where(CheckResult.service_id == service_id, CheckResult.checked_at >= since)
        )
    ).one()
    total, downs = row
    if not total:
        return 100.0
    return round(100.0 * (1 - (downs or 0) / total), 2)


@router.get("")
async def list_services(db: AsyncSession = Depends(get_db)):
    services = (await db.execute(select(Service).order_by(Service.name))).scalars().all()
    out = []
    for svc in services:
        latest = await _latest_check(db, svc.id)
        avail = await _availability_pct(db, svc.id)
        out.append(service_summary(svc, latest, avail))
    return out


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_service(payload: ServiceCreate, db: AsyncSession = Depends(get_db)):
    exists = (
        await db.execute(select(Service).where(Service.name == payload.name))
    ).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=409, detail=f"service '{payload.name}' already exists")
    svc = Service(
        name=payload.name,
        description=payload.description,
        url=payload.url,
        health_path=payload.healthPath,
        check_interval_sec=payload.checkIntervalSec,
        timeout_ms=payload.timeoutMs,
        degraded_latency_ms=payload.degradedLatencyMs,
        failure_threshold=payload.failureThreshold,
        recovery_threshold=payload.recoveryThreshold,
        team_owner=payload.teamOwner,
    )
    db.add(svc)
    await db.flush()
    return service_summary(svc, None, 100.0)


async def _get_service(db: AsyncSession, service_id: str) -> Service:
    try:
        sid = uuid.UUID(service_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="service not found")
    svc = await db.get(Service, sid)
    if svc is None:
        raise HTTPException(status_code=404, detail="service not found")
    return svc


@router.get("/{service_id}")
async def get_service(service_id: str, db: AsyncSession = Depends(get_db)):
    svc = await _get_service(db, service_id)
    latest = await _latest_check(db, svc.id)
    avail = await _availability_pct(db, svc.id)

    # 24h latency series, bucketed to ~30min points
    since = utcnow() - timedelta(hours=24)
    rows = (
        await db.execute(
            select(CheckResult.checked_at, CheckResult.latency_ms)
            .where(CheckResult.service_id == svc.id, CheckResult.checked_at >= since, CheckResult.latency_ms.is_not(None))
            .order_by(CheckResult.checked_at)
        )
    ).all()
    bucket_ms = 30 * 60 * 1000
    buckets: dict[int, list[int]] = {}
    for checked_at, latency in rows:
        key = int(ms(checked_at) // bucket_ms * bucket_ms)
        buckets.setdefault(key, []).append(latency)
    latency_series = [{"t": k, "ms": round(sum(v) / len(v))} for k, v in sorted(buckets.items())]

    # 90-day daily uptime buckets
    since90 = utcnow() - timedelta(days=90)
    day_rows = (
        await db.execute(
            select(CheckResult.checked_at, CheckResult.status)
            .where(CheckResult.service_id == svc.id, CheckResult.checked_at >= since90)
            .order_by(CheckResult.checked_at)
        )
    ).all()
    day_map: dict[str, dict[str, int]] = {}
    for checked_at, st in day_rows:
        day = checked_at.date().isoformat()
        d = day_map.setdefault(day, {"total": 0, "down": 0})
        d["total"] += 1
        if st == CheckStatus.DOWN:
            d["down"] += 1
    start_day = (utcnow() - timedelta(days=89)).date()
    uptime = []
    for i in range(90):
        day = start_day + timedelta(days=i)
        key = day.isoformat()
        agg = day_map.get(key)
        uptime.append(
            {
                "day": int(
                    datetime.combine(day, time.min, tzinfo=timezone.utc).timestamp() * 1000
                ),
                "uptime": 1.0 if agg is None else round(1 - agg["down"] / agg["total"], 4),
            }
        )

    incidents = (
        await db.execute(
            select(Incident)
            .options(selectinload(Incident.service), selectinload(Incident.acknowledged_by_user))
            .where(Incident.service_id == svc.id)
            .order_by(Incident.opened_at.desc())
            .limit(10)
        )
    ).scalars().all()

    data = service_summary(svc, latest, avail)
    data["latency"] = latency_series
    data["uptime"] = uptime
    data["incidents"] = [incident_summary(i) for i in incidents]
    return data


@router.patch("/{service_id}")
async def update_service(service_id: str, payload: ServiceUpdate, db: AsyncSession = Depends(get_db)):
    svc = await _get_service(db, service_id)
    updates = payload.model_dump(exclude_unset=True)
    mapping = {
        "healthPath": "health_path",
        "checkIntervalSec": "check_interval_sec",
        "timeoutMs": "timeout_ms",
        "degradedLatencyMs": "degraded_latency_ms",
        "failureThreshold": "failure_threshold",
        "recoveryThreshold": "recovery_threshold",
        "teamOwner": "team_owner",
        "isActive": "is_active",
    }
    for k, v in updates.items():
        setattr(svc, mapping.get(k, k), v)
    try:
        await db.flush()
    except IntegrityError:
        raise HTTPException(status_code=409, detail=f"service name '{updates.get('name')}' already exists")
    latest = await _latest_check(db, svc.id)
    return service_summary(svc, latest, await _availability_pct(db, svc.id))


@router.delete("/{service_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_service(service_id: str, db: AsyncSession = Depends(get_db)):
    svc = await _get_service(db, service_id)
    await db.delete(svc)


@router.get("/{service_id}/checks")
async def service_checks(
    service_id: str,
    since: int | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
):
    svc = await _get_service(db, service_id)
    q = select(CheckResult).where(CheckResult.service_id == svc.id)
    if since:
        q = q.where(CheckResult.checked_at >= utcnow() - timedelta(seconds=since))
    q = q.order_by(CheckResult.checked_at.desc()).limit(limit)
    rows = (await db.execute(q)).scalars().all()
    return [
        {
            "id": str(r.id),
            "checkedAt": ms(r.checked_at),
            "status": r.status.value,
            "latencyMs": r.latency_ms,
            "statusCode": r.status_code,
            "error": r.error,
        }
        for r in rows
    ]


@router.post("/{service_id}/check")
async def run_check_now(service_id: str, db: AsyncSession = Depends(get_db)):
    """On-demand health check: executes, classifies, persists, advances state, detects."""
    svc = await _get_service(db, service_id)
    code, latency, error = await checker.fetch_outcome(svc)
    result, new_state, changed = await checker.record_check(db, svc, code, latency, error)
    return {
        "check": {
            "serviceId": str(svc.id),
            "checkedAt": ms(result.checked_at),
            "status": result.status.value,
            "latencyMs": result.latency_ms,
            "statusCode": result.status_code,
            "error": result.error,
        },
        "serviceState": new_state.value,
        "stateChanged": changed,
    }
