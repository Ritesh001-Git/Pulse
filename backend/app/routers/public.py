import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Integer, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    CheckResult,
    CheckStatus,
    Incident,
    Service,
    Subscriber,
    utcnow,
)
from app.resilience import get_db
from app.schemas import SubscribeRequest
from app.serializers import incident_summary, service_summary, timeline_event
from sqlalchemy.orm import selectinload

router = APIRouter(prefix="/api/public", tags=["public"])


def _public_message(svc: Service, status: str) -> str | None:
    if status == "down":
        return (
            f"We are aware of an outage affecting {svc.name}. Our team is actively working "
            "on it — we will post updates here as we make progress."
        )
    if status == "degraded":
        return (
            f"{svc.name} is slower than normal. We have identified the cause and are working "
            "on a fix. No action is needed from you."
        )
    return None


@router.get("/status")
async def public_status(db: AsyncSession = Depends(get_db)):
    services = (await db.execute(select(Service).order_by(Service.name))).scalars().all()
    out_services = []
    counts = {"up": 0, "degraded": 0, "down": 0, "unknown": 0}
    for svc in services:
        latest = (
            await db.execute(
                select(CheckResult).where(CheckResult.service_id == svc.id).order_by(CheckResult.checked_at.desc()).limit(1)
            )
        ).scalar_one_or_none()
        status = latest.status.value if latest else "unknown"
        counts[status] = counts.get(status, 0) + 1
        avail = 100.0
        if latest:
            row = (
                await db.execute(
                    select(func.count(), func.sum(func.cast(CheckResult.status == CheckStatus.DOWN, Integer)))
                    .where(CheckResult.service_id == svc.id)
                )
            ).one()
            total, downs = row
            if total:
                avail = round(100 * (1 - (downs or 0) / total), 2)
        summary = service_summary(svc, latest, avail)
        summary["publicMessage"] = _public_message(svc, status)
        out_services.append(summary)

    incidents = (
        await db.execute(
            select(Incident)
            .options(selectinload(Incident.service), selectinload(Incident.acknowledged_by_user))
            .order_by(Incident.opened_at.desc())
            .limit(50)
        )
    ).scalars().all()
    overall = "up"
    if counts["down"] > 0:
        overall = "down"
    elif counts["degraded"] > 0:
        overall = "degraded"

    return {
        "overall": overall,
        "counts": {k: v for k, v in counts.items() if k != "unknown"},
        "services": out_services,
        "incidents": [incident_summary(i) for i in incidents],
    }


@router.get("/incidents")
async def public_incidents(limit: int = Query(default=20, ge=1, le=100), db: AsyncSession = Depends(get_db)):
    incidents = (
        await db.execute(
            select(Incident)
            .options(selectinload(Incident.service), selectinload(Incident.acknowledged_by_user))
            .order_by(Incident.opened_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    return [incident_summary(i) for i in incidents]


@router.get("/incidents/{incident_id}")
async def public_incident(incident_id: str, db: AsyncSession = Depends(get_db)):
    try:
        inc = await db.get(Incident, uuid.UUID(incident_id))
    except ValueError:
        inc = None
    if inc is None:
        raise HTTPException(status_code=404, detail="incident not found")
    if not inc.timeline:
        await db.refresh(inc, ["timeline"])
    data = incident_summary(inc)
    data["timeline"] = [timeline_event(ev) for ev in inc.timeline]
    return data


@router.get("/uptime")
async def public_uptime(window: str = Query(default="30d", pattern="^(24h|7d|30d|90d)$"), db: AsyncSession = Depends(get_db)):
    days = {"24h": 1, "7d": 7, "30d": 30, "90d": 90}.get(window, 30)
    since = utcnow() - timedelta(days=days)
    services = (await db.execute(select(Service).order_by(Service.name))).scalars().all()
    out = []
    for svc in services:
        row = (
            await db.execute(
                select(func.count(), func.sum(func.cast(CheckResult.status == CheckStatus.DOWN, __import__("sqlalchemy").Integer)))
                .where(CheckResult.service_id == svc.id, CheckResult.checked_at >= since)
            )
        ).one()
        total, downs = row
        total, downs = total or 0, downs or 0
        out.append(
            {
                "serviceId": str(svc.id),
                "serviceName": svc.name,
                "uptimePct": 100.0 if total == 0 else round(100 * (1 - downs / total), 3),
            }
        )
    return out


@router.post("/subscribe", status_code=201)
async def subscribe(payload: SubscribeRequest, db: AsyncSession = Depends(get_db)):
    if not payload.email and not payload.webhookUrl:
        raise HTTPException(status_code=422, detail="email or webhookUrl required")
    service_id = None
    if payload.serviceId:
        try:
            service_id = uuid.UUID(payload.serviceId)
        except ValueError:
            raise HTTPException(status_code=404, detail="service not found")
        svc = await db.get(Service, service_id)
        if svc is None:
            raise HTTPException(status_code=404, detail="service not found")
    sub = Subscriber(
        email=payload.email, webhook_url=payload.webhookUrl,
        service_id=service_id, unsubscribe_token=uuid.uuid4().hex,
    )
    db.add(sub)
    await db.flush()
    return {"status": "subscribed", "unsubscribeToken": sub.unsubscribe_token}


@router.post("/unsubscribe")
async def unsubscribe(token: str = Query(...), db: AsyncSession = Depends(get_db)):
    sub = (await db.execute(select(Subscriber).where(Subscriber.unsubscribe_token == token))).scalar_one_or_none()
    if sub is None:
        raise HTTPException(status_code=404, detail="subscription not found")
    await db.delete(sub)
    return {"status": "unsubscribed"}
