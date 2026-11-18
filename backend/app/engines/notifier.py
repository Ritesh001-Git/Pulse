"""Notification engine — webhook delivery with retries and persisted history.

Flow:
    notify(event, incident, service_name) →
        creates one pending Notification row per matching channel (delivery history)
        → schedules a background delivery task per row
        → each delivery: POST JSON payload, up to MAX_ATTEMPTS with backoff
        → row updated to sent / failed with detail (HTTP status or error text)

Delivery is fire-and-forget: a dead webhook endpoint never blocks or crashes
the API or the scheduler. History rows persist even when the endpoint is down,
so failures are auditable.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone

import httpx
from sqlalchemy import select

from app.models import (
    Notification,
    NotificationStatus,
    WebhookChannel,
)
from app.resilience import resilient_session

logger = logging.getLogger("pulse.notifier")

MAX_ATTEMPTS = 3
BACKOFF_S = [0.5, 1.5, 4.0]
DELIVERY_TIMEOUT_S = 5.0


def build_payload(event: str, incident_id: str, service_name: str, summary: dict) -> dict:
    """Canonical webhook payload shape."""
    return {
        "event": event,
        "at": int(datetime.now(timezone.utc).timestamp() * 1000),
        "service": service_name,
        "incident": {"id": incident_id, **summary},
    }


def notify(event: str, incident_id: str | uuid.UUID, service_name: str, summary: dict) -> None:
    """Sync fire-and-forget entry point: schedules delivery in the background.

    Never awaits at call sites, so the incident lifecycle path is never blocked
    by notification queuing.
    """
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_notify(event, str(incident_id), service_name, summary))
    except RuntimeError:
        logger.warning("notify(%s) skipped: no running event loop", event)


async def _notify(event: str, incident_id: str, service_name: str, summary: dict) -> int:
    """Queue webhook deliveries for an incident lifecycle event. Returns count queued."""
    incident_id = str(incident_id)
    payload = build_payload(event, incident_id, service_name, summary)
    queued = 0
    try:
        async with resilient_session() as db:
            channels = (
                await db.execute(select(WebhookChannel).where(WebhookChannel.is_active.is_(True)))
            ).scalars().all()
            for ch in channels:
                # service-scoped channels only receive their service's events
                summary_service_id = summary.get("_service_id")
                if ch.service_id is not None and str(ch.service_id) != str(summary_service_id):
                    continue
                row = Notification(
                    incident_id=uuid.UUID(incident_id),
                    channel="webhook",
                    audience=ch.name,
                    event=event,
                    status=NotificationStatus.PENDING,
                    detail=f"queued → {ch.url}",
                )
                db.add(row)
                await db.flush()
                queued += 1
                asyncio.create_task(_deliver(row.id, ch.url, payload))
    except Exception:
        # Notifications must never break the incident lifecycle path.
        logger.exception("notify(%s) failed to queue — incident flow unaffected", event)
    return queued


async def _deliver(notification_id: uuid.UUID, url: str, payload: dict) -> None:
    """Deliver with retries. Updates the history row; never raises."""
    last_detail = ""
    for attempt in range(MAX_ATTEMPTS):
        try:
            async with httpx.AsyncClient(timeout=DELIVERY_TIMEOUT_S) as client:
                resp = await client.post(url, json=payload)
            if 200 <= resp.status_code < 300:
                await _update_row(notification_id, NotificationStatus.SENT, f"{resp.status_code} on attempt {attempt + 1}")
                return
            last_detail = f"HTTP {resp.status_code} on attempt {attempt + 1}"
        except httpx.HTTPError as exc:
            last_detail = f"{type(exc).__name__} on attempt {attempt + 1}: {exc}"
        if attempt < MAX_ATTEMPTS - 1:
            await asyncio.sleep(BACKOFF_S[attempt])
    await _update_row(notification_id, NotificationStatus.FAILED, last_detail)
    logger.warning("webhook delivery FAILED after %d attempts (%s): %s", MAX_ATTEMPTS, url, last_detail)


async def _update_row(notification_id: uuid.UUID, status: NotificationStatus, detail: str) -> None:
    try:
        async with resilient_session() as db:
            row = await db.get(Notification, notification_id)
            if row is not None:
                row.status = status
                row.detail = detail
    except Exception:
        logger.exception("failed to record delivery outcome for %s", notification_id)
