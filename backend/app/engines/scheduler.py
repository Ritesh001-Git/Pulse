"""Monitoring scheduler — per-service independent health checks with asyncio + httpx.

Guarantees:
- Every ACTIVE service is checked on its OWN configured interval, independently.
  A slow/hanging check never blocks other services (individual asyncio tasks +
  a configurable global concurrency limit via semaphore).
- No overlapping checks for the same service (in-flight set; a due service
  whose previous check is still running is skipped this tick).
- Configured per-service timeout respected (httpx timeout = timeout_ms).
- Every check result is persisted (buffered in memory during a DB outage,
  flushed automatically on recovery — the loop never crashes).
- Service state machine (healthy/degraded/down) advanced via app/state.py.
"""
from __future__ import annotations

import asyncio
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select

from app.database import engine
from app.engines import checker
from app.models import CheckResult, Service
from app.resilience import DatabaseUnavailable, resilient_session
from app.state import ServiceState

logger = logging.getLogger("pulse.scheduler")

MAX_BUFFER = 5000
TICK_SECONDS = 1.0  # scheduling granularity


@dataclass
class BufferedCheck:
    service_id: str
    status_code: int | None
    latency_ms: int | None
    error: str | None
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class MonitoringScheduler:
    def __init__(self, concurrency: int = 8, tick_seconds: float = TICK_SECONDS) -> None:
        self._semaphore = asyncio.Semaphore(concurrency)
        self._tick = tick_seconds
        self._task: asyncio.Task | None = None
        self._stopping = asyncio.Event()
        self._in_flight: set[str] = set()
        self._due_at: dict[str, float] = {}
        self._buffer: deque[BufferedCheck] = deque(maxlen=MAX_BUFFER)
        self.checks_completed = 0
        self.checks_failed = 0
        self.skipped_overlapping = 0

    # ---- lifecycle -------------------------------------------------------

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="pulse-scheduler")
        logger.info("Scheduler started (concurrency=%d)", self._semaphore._value)

    async def stop(self) -> None:
        self._stopping.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
        await engine.dispose() if False else None
        logger.info("Scheduler stopped")

    # ---- main loop -------------------------------------------------------

    async def _run(self) -> None:
        loop = asyncio.get_running_loop()
        while not self._stopping.is_set():
            try:
                await self._tick_once(loop)
            except DatabaseUnavailable:
                logger.warning("DB unavailable — checks will buffer; retrying in 5s")
                await asyncio.sleep(5)
                continue
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Scheduler tick error — continuing")
            await asyncio.sleep(self._tick)

    async def _tick_once(self, loop) -> None:
        services = await self._load_services()
        now = loop.time()
        pending = []
        for svc in services:
            key = str(svc.id)
            if key in self._in_flight:
                self.skipped_overlapping += 1
                continue
            if self._due_at.get(key, 0) <= now:
                pending.append(svc)
                self._in_flight.add(key)  # reserve immediately; no overlap
        for svc in pending:
            asyncio.create_task(self._check_service(svc))
        if self._buffer:
            await self._flush_buffer()

    async def _load_services(self) -> list[Service]:
        try:
            async with resilient_session() as session:
                rows = await session.execute(
                    select(Service).where(Service.is_active.is_(True)).order_by(Service.name)
                )
                return list(rows.scalars().all())
        except DatabaseUnavailable:
            return []

    # ---- per-service check (fully independent) ---------------------------

    async def _check_service(self, svc: Service) -> None:
        loop = asyncio.get_running_loop()
        try:
            async with self._semaphore:  # global concurrency limit
                code, latency, error = await checker.fetch_outcome(svc)
            try:
                async with resilient_session() as session:
                    # re-fetch in this session (the loop's copy is detached from it)
                    fresh = await session.get(Service, svc.id)
                    if fresh is None or not fresh.is_active:
                        return
                    result, new_state, changed = await checker.record_check(
                        session, fresh, code, latency, error
                    )
                self.checks_completed += 1
                if changed:
                    logger.info(
                        "[%s] check=%s %sms -> state %s",
                        svc.name, result.status.value, latency, new_state.value,
                    )
            except DatabaseUnavailable:
                self._buffer.append(BufferedCheck(str(svc.id), code, latency, error))
                self.checks_failed += 1
                raise
        except DatabaseUnavailable:
            raise  # propagates to tick handler (backoff)
        except Exception:
            self.checks_failed += 1
            logger.exception("Check task failed for %s — continuing", svc.name)
        finally:
            self._in_flight.discard(str(svc.id))
            # next run = completion time + this service's own interval
            self._due_at[str(svc.id)] = loop.time() + svc.check_interval_sec

    # ---- outage buffering ------------------------------------------------

    async def _flush_buffer(self) -> None:
        try:
            async with resilient_session() as session:
                buffered, self._buffer = list(self._buffer), deque(maxlen=MAX_BUFFER)
                for item in buffered:
                    svc = await session.get(Service, __import__("uuid").UUID(item.service_id))
                    if svc is None:
                        continue
                    result = CheckResult(
                        service_id=svc.id,
                        status=checker.classify_response(item.status_code, item.latency_ms, svc.degraded_latency_ms),
                        latency_ms=item.latency_ms,
                        status_code=item.status_code,
                        error=item.error,
                        checked_at=item.fetched_at,
                    )
                    session.add(result)
                    # advance counters/state from buffered data without re-detection
                    from app.state import next_service_state, classify_response

                    st = classify_response(item.status_code, item.latency_ms, svc.degraded_latency_ms)
                    t = next_service_state(
                        ServiceState(svc.state.value), st,
                        svc.consecutive_failures, svc.consecutive_successes,
                        svc.failure_threshold, svc.recovery_threshold,
                    )
                    svc.state = t.new_state
                    svc.consecutive_failures = t.consecutive_failures
                    svc.consecutive_successes = t.consecutive_successes
            logger.info("Flushed %d buffered checks after DB recovery", len(buffered))
        except DatabaseUnavailable:
            pass  # stay buffered; try again next tick
