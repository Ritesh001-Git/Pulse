import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.deps import get_current_user
from app.models import (
    ActorKind,
    Incident,
    IncidentSeverity,
    IncidentState,
    Notification,
    NotificationChannel,
    NotificationStatus,
    Service,
    TimelineEvent,
    TimelineEventKind,
    utcnow,
)
from app.resilience import get_db
from app.schemas import AckRequest, IncidentCreate, NoteRequest, ResolveRequest, StatusUpdateRequest
from app.serializers import incident_summary, timeline_event
from app.engines import notifier

router = APIRouter(prefix="/api/incidents", tags=["incidents"], dependencies=[Depends(get_current_user)])


INCIDENT_LOADS = (
    selectinload(Incident.service).selectinload(Service.incidents),
    selectinload(Incident.acknowledged_by_user),
    selectinload(Incident.timeline).selectinload(TimelineEvent.actor_user),
)


async def _get_incident(db: AsyncSession, incident_id: str) -> Incident:
    try:
        iid = uuid.UUID(incident_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="incident not found")
    inc = (
        await db.execute(select(Incident).where(Incident.id == iid).options(*INCIDENT_LOADS))
    ).scalar_one_or_none()
    if inc is None:
        raise HTTPException(status_code=404, detail="incident not found")
    return inc


@router.get("")
async def list_incidents(
    state: str | None = Query(default=None, pattern="^(investigating|identified|monitoring|resolved)$"),
    service_id: str | None = None,
    active: bool | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    q = select(Incident).options(*INCIDENT_LOADS).order_by(Incident.opened_at.desc()).limit(limit)
    if state:
        q = q.where(Incident.state == IncidentState(state))
    if service_id:
        try:
            q = q.where(Incident.service_id == uuid.UUID(service_id))
        except ValueError:
            raise HTTPException(status_code=404, detail="service not found")
    if active is not None:
        q = q.where(Incident.resolved_at.is_(None) if active else Incident.resolved_at.is_not(None))
    incidents = (await db.execute(q)).scalars().all()
    return [incident_summary(i) for i in incidents]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_incident(payload: IncidentCreate, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    try:
        sid = uuid.UUID(payload.serviceId)
    except ValueError:
        raise HTTPException(status_code=404, detail="service not found")
    svc = await db.get(Service, sid)
    if svc is None:
        raise HTTPException(status_code=404, detail="service not found")

    active = (
        await db.execute(
            select(Incident).options(*INCIDENT_LOADS).where(Incident.service_id == sid, Incident.resolved_at.is_(None))
        )
    ).scalar_one_or_none()
    if active:
        raise HTTPException(status_code=409, detail="service already has an active incident")

    inc = Incident(
        service_id=sid,
        title=payload.title,
        severity=IncidentSeverity(payload.severity),
        state=IncidentState.INVESTIGATING,
    )
    db.add(inc)
    await db.flush()
    db.add_all(
        [
            TimelineEvent(
                incident_id=inc.id, actor=ActorKind.USER, actor_user_id=user.id,
                kind=TimelineEventKind.OPENED, message=f"Incident filed by {user.name}: {payload.title}",
            ),
            Notification(
                incident_id=inc.id, channel=NotificationChannel.WEBHOOK, audience="engineers",
                status=NotificationStatus.PENDING, detail=f"manual incident for {svc.name}",
            ),
        ]
    )
    summary = incident_summary(inc)
    summary["serviceName"] = svc.name  # fresh insert has no loaded relationship
    return summary


@router.get("/{incident_id}")
async def get_incident(incident_id: str, db: AsyncSession = Depends(get_db)):
    inc = await _get_incident(db, incident_id)
    data = incident_summary(inc)
    data["timeline"] = [timeline_event(ev) for ev in inc.timeline]
    data["notes"] = [
        {"at": timeline_event(ev)["at"], "author": ev.actor_user.name if ev.actor_user else "Unknown", "body": ev.message}
        for ev in inc.timeline
        if ev.kind == TimelineEventKind.NOTE
    ]
    return data


@router.post("/{incident_id}/ack")
async def ack_incident(incident_id: str, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    inc = await _get_incident(db, incident_id)
    if inc.acknowledged:
        return incident_summary(inc)  # idempotent
    inc.acknowledged = True
    inc.acknowledged_by = user.id
    inc.acknowledged_at = utcnow()
    db.add(
        TimelineEvent(
            incident_id=inc.id, actor=ActorKind.USER, actor_user_id=user.id,
            kind=TimelineEventKind.ACKED, message="Incident acknowledged.",
        )
    )
    await db.flush()
    summary = incident_summary(inc)
    summary["ackedBy"] = user.name  # freshly assigned relationship isn't loaded
    notifier.notify("incident.acknowledged", inc.id, inc.service.name, summary)
    return summary


@router.post("/{incident_id}/updates")
async def post_update(incident_id: str, payload: StatusUpdateRequest, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    inc = await _get_incident(db, incident_id)
    if inc.resolved_at is not None:
        raise HTTPException(status_code=409, detail="incident is resolved")
    if payload.state and payload.state != inc.state.value:
        inc.state = IncidentState(payload.state)
        message = payload.message or f"Status set to {inc.state.value.capitalize()}."
        db.add(
            TimelineEvent(
                incident_id=inc.id, actor=ActorKind.USER, actor_user_id=user.id,
                kind=TimelineEventKind.STATUS_CHANGED, message=message,
            )
        )
    elif payload.message:
        db.add(
            TimelineEvent(
                incident_id=inc.id, actor=ActorKind.USER, actor_user_id=user.id,
                kind=TimelineEventKind.NOTE, message=payload.message,
            )
        )
    else:
        raise HTTPException(status_code=422, detail="nothing to update: provide state and/or message")
    await db.flush()
    summary = incident_summary(inc)
    notifier.notify("incident.updated", inc.id, inc.service.name, summary)
    return summary


@router.post("/{incident_id}/notes")
async def add_note(incident_id: str, payload: NoteRequest, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    inc = await _get_incident(db, incident_id)
    db.add(
        TimelineEvent(
            incident_id=inc.id, actor=ActorKind.USER, actor_user_id=user.id,
            kind=TimelineEventKind.NOTE, message=payload.body,
        )
    )
    await db.flush()
    return incident_summary(inc)


@router.post("/{incident_id}/resolve")
async def resolve_incident(incident_id: str, payload: ResolveRequest, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    inc = await _get_incident(db, incident_id)
    if inc.resolved_at is not None:
        return incident_summary(inc)  # idempotent
    inc.state = IncidentState.RESOLVED
    inc.resolved_at = utcnow()
    db.add(
        TimelineEvent(
            incident_id=inc.id, actor=ActorKind.USER, actor_user_id=user.id,
            kind=TimelineEventKind.RESOLVED,
            message=payload.summary or "Incident resolved.",
        )
    )
    await db.flush()
    summary = incident_summary(inc)
    notifier.notify("incident.resolved", inc.id, inc.service.name, summary)
    return summary


@router.get("/{incident_id}/timeline")
async def get_timeline(incident_id: str, db: AsyncSession = Depends(get_db)):
    inc = await _get_incident(db, incident_id)
    return [timeline_event(ev) for ev in inc.timeline]
