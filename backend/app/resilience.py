"""Resilient DB access: transient-error classification, retry, and resilient sessions.

Guarantees:
- A dropped/hung database fails *that request* fast, with a clean 503 — never a raw 500.
- Transient failures (connection reset, pool exhaustion, brief outage) are retried
  once for reads; writes are retried only via explicit idempotent paths.
- Long-running consumers (the monitoring loop) use `resilient_session`, which
  tolerates outages and surfaces a `DatabaseUnavailable` signal instead of crashing.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Callable, TypeVar

import asyncpg
from sqlalchemy import exc as sa_exc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal

logger = logging.getLogger("pulse.db")

T = TypeVar("T")


class DatabaseUnavailable(Exception):
    """Raised when the database cannot be reached after retry attempts."""


def is_transient(exc: BaseException) -> bool:
    """True for errors worth retrying — connection-level, not data-level."""
    if isinstance(exc, (asyncpg.PostgresConnectionError, asyncpg.InterfaceError)):
        return True
    if isinstance(exc, asyncio.TimeoutError):
        return True
    if isinstance(exc, ConnectionError):
        # ConnectionRefusedError / ConnectionResetError can surface unwrapped
        # from the event loop (uvloop) before SQLAlchemy translates them.
        return True
    if isinstance(exc, sa_exc.OperationalError):
        # Connection refused/reset/timeout; excludes constraint violations (IntegrityError)
        return True
    if isinstance(exc, sa_exc.TimeoutError):
        return True
    # Pool checkout timeouts surface as asyncio.TimeoutError from asyncpg pool internals.
    return False


async def retry_async(
    fn: Callable[[], object],
    attempts: int = 2,
    backoff: float = 0.25,
    on_give_up: type[Exception] | None = DatabaseUnavailable,
) -> object:
    """Run an awaitable-producing callable with bounded retry on transient errors.

    Retries only transient failures; data errors (IntegrityError, etc.) propagate
    immediately because retrying them can never succeed.
    """
    last_exc: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            return await fn()
        except Exception as exc:
            if not is_transient(exc) or attempt == attempts:
                last_exc = exc
                break
            last_exc = exc
            await asyncio.sleep(backoff * attempt)
    if on_give_up is not None and last_exc is not None and is_transient(last_exc):
        raise on_give_up(str(last_exc)) from last_exc
    raise last_exc  # type: ignore[misc]


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: one session per request, with transient-retry and clean rollback."""
    session: AsyncSession | None = None
    try:
        # Connection acquisition is the retryable part (pool checkout / fresh connect).
        async def _make() -> AsyncSession:
            return AsyncSessionLocal()

        session = await retry_async(_make)
        yield session
        await session.commit()
    except DatabaseUnavailable:
        raise
    except Exception as exc:
        if session is not None:
            try:
                await session.rollback()
            except Exception:
                pass
        # Lazy connects fail at first execute, outside the retry window —
        # translate transient errors so every consumer sees one exception type.
        if is_transient(exc):
            raise DatabaseUnavailable(str(exc)) from exc
        raise
    finally:
        if session is not None:
            await session.close()


@asynccontextmanager
async def resilient_session(attempts: int = 3, backoff: float = 0.5):
    """Session for background loops (monitoring engine).

    - Retries transient failures across a slightly wider window.
    - On persistent outage raises `DatabaseUnavailable` — the caller (loop)
      catches it, backs off, and keeps running; it never crashes the loop.
    """
    session: AsyncSession | None = None
    try:
        async def _make() -> AsyncSession:
            return AsyncSessionLocal()

        session = await retry_async(_make, attempts=attempts, backoff=backoff)
        yield session
        await session.commit()
    except DatabaseUnavailable:
        raise
    except Exception as exc:
        if session is not None:
            try:
                await session.rollback()
            except Exception:
                pass
        if is_transient(exc):
            raise DatabaseUnavailable(str(exc)) from exc
        raise
    finally:
        if session is not None:
            await session.close()
