"""Webhook channel configuration + delivery history (internal API)."""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Notification, WebhookChannel
from app.resilience import get_db

router = APIRouter(prefix="/api/channels", tags=["channels"])


class ChannelCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    url: str = Field(min_length=1, max_length=500)
    serviceId: Optional[str] = None
    isActive: bool = True


@router.get("")
async def list_channels(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(WebhookChannel).order_by(WebhookChannel.name))).scalars().all()
    return [
        {
            "id": str(c.id),
            "name": c.name,
            "url": c.url,
            "serviceId": str(c.service_id) if c.service_id else None,
            "isActive": c.is_active,
            "createdAt": int(c.created_at.timestamp() * 1000),
        }
        for c in rows
    ]


@router.post("", status_code=201)
async def create_channel(payload: ChannelCreate, db: AsyncSession = Depends(get_db)):
    exists = (
        await db.execute(select(WebhookChannel).where(WebhookChannel.name == payload.name))
    ).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=409, detail="channel name already exists")
    ch = WebhookChannel(
        name=payload.name,
        url=payload.url,
        service_id=uuid.UUID(payload.serviceId) if payload.serviceId else None,
        is_active=payload.isActive,
    )
    db.add(ch)
    await db.flush()
    return {"id": str(ch.id), "name": ch.name}


@router.delete("/{channel_id}", status_code=204)
async def delete_channel(channel_id: str, db: AsyncSession = Depends(get_db)):
    try:
        cid = uuid.UUID(channel_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="channel not found")
    ch = await db.get(WebhookChannel, cid)
    if ch is None:
        raise HTTPException(status_code=404, detail="channel not found")
    await db.delete(ch)


@router.get("/deliveries")
async def delivery_history(limit: int = 100, db: AsyncSession = Depends(get_db)):
    """Notification delivery history: one row per event per channel, with outcome."""
    rows = (
        await db.execute(
            select(Notification).order_by(Notification.at.desc()).limit(limit)
        )
    ).scalars().all()
    return [
        {
            "id": str(n.id),
            "incidentId": str(n.incident_id) if n.incident_id else None,
            "channel": n.channel.value if hasattr(n.channel, "value") else n.channel,
            "audience": n.audience,
            "event": n.event,
            "status": n.status.value,
            "detail": n.detail,
            "createdAt": int(n.at.timestamp() * 1000) if n.at else None,
        }
        for n in rows
    ]
