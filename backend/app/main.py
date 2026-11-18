from contextlib import asynccontextmanager
import asyncio
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.config import get_settings
from app.database import engine
from app.models import Base  # noqa: F401 — ensures all models are imported/registered
from app.resilience import DatabaseUnavailable, is_transient

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s: %(message)s")

logger = logging.getLogger("pulse.main")

ENUM_DDL = [
    "CREATE TYPE userrole AS ENUM ('admin', 'engineer', 'support')",
    "CREATE TYPE checkstatus AS ENUM ('up', 'degraded', 'down')",
    "CREATE TYPE incidentstate AS ENUM ('investigating', 'identified', 'monitoring', 'resolved')",
    "CREATE TYPE incidentseverity AS ENUM ('outage', 'degradation')",
    "CREATE TYPE actorkind AS ENUM ('system', 'user')",
    "CREATE TYPE timelineeventkind AS ENUM ('opened', 'auto_detected', 'acked', 'status_changed', 'note', 'resolved')",
    "CREATE TYPE notificationstatus AS ENUM ('pending', 'sent', 'failed')",
    "CREATE TYPE notificationchannel AS ENUM ('webhook', 'email', 'sms')",
    "CREATE TYPE servicestate AS ENUM ('pending', 'healthy', 'degraded', 'down')",
]

# Idempotent column additions for databases created before these fields existed.
COLUMN_MIGRATIONS = [
    "ALTER TABLE services ADD COLUMN IF NOT EXISTS state servicestate NOT NULL DEFAULT 'pending'",
    "ALTER TABLE services ADD COLUMN IF NOT EXISTS recovery_threshold INTEGER NOT NULL DEFAULT 2",
    "ALTER TABLE services ADD COLUMN IF NOT EXISTS consecutive_failures INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE services ADD COLUMN IF NOT EXISTS consecutive_successes INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE services ADD COLUMN IF NOT EXISTS sla_target DOUBLE PRECISION NOT NULL DEFAULT 99.9",
    "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS event VARCHAR(50)",
]


async def create_all_with_enums() -> None:
    """Dev bootstrap: create enums (if missing) then all tables."""
    async with engine.begin() as conn:
        for ddl in ENUM_DDL:
            await conn.execute(text(f"""DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = '{ddl.split(' ')[2]}') THEN
                    {ddl};
                END IF;
            END $$;"""))
        await conn.run_sync(Base.metadata.create_all)
        for ddl in COLUMN_MIGRATIONS:
            await conn.execute(text(ddl))


async def bootstrap_with_retry(max_attempts: int = 5, backoff: float = 1.0) -> bool:
    settings = get_settings()
    if not settings.database_url.startswith("postgresql"):
        return True
    for attempt in range(1, max_attempts + 1):
        try:
            await create_all_with_enums()
            return True
        except Exception as exc:
            if not is_transient(exc) or attempt == max_attempts:
                logger.error("DB bootstrap failed permanently: %s", exc)
                return False
            logger.warning("DB bootstrap attempt %d/%d failed (%s) — retrying", attempt, max_attempts, exc)
            await asyncio.sleep(backoff * attempt)
    return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    ready = await bootstrap_with_retry()
    if ready:
        await ensure_default_admin()
    scheduler = None
    try:
        from app.engines.scheduler import MonitoringScheduler

        scheduler = MonitoringScheduler(concurrency=get_settings().check_concurrency)
        await scheduler.start()
    except Exception as exc:  # engine must never block API startup
        logger.error("Scheduler failed to start: %s", exc)
    yield
    if scheduler is not None:
        await scheduler.stop()
    await engine.dispose()


async def ensure_default_admin() -> None:
    """Dev bootstrap: a default admin so login works out of the box."""
    from sqlalchemy import select

    from app.database import AsyncSessionLocal
    from app.deps import hash_password
    from app.models import User, UserRole

    async with AsyncSessionLocal() as db:
        has_user = (await db.execute(select(User).limit(1))).scalar_one_or_none()
        if has_user is None:
            db.add(
                User(
                    email="admin@pulse.dev",
                    name="Ritesh Swain",
                    role=UserRole.ADMIN,
                    password_hash=hash_password("pulse123"),
                )
            )
            await db.commit()
            logger.info("Seeded default admin: admin@pulse.dev / pulse123")


def create_app() -> FastAPI:
    app = FastAPI(title=get_settings().app_name, version="0.2.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(DatabaseUnavailable)
    async def db_unavailable_handler(request: Request, exc: DatabaseUnavailable):
        return JSONResponse(status_code=503, content={"detail": "database temporarily unavailable"})

    @app.exception_handler(Exception)
    async def unhandled_handler(request: Request, exc: Exception):
        from fastapi import HTTPException

        if isinstance(exc, HTTPException):
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
        if is_transient(exc):
            return JSONResponse(status_code=503, content={"detail": "database temporarily unavailable"})
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": "internal server error"})

    from app.routers import auth, incidents, metrics, ops, public, services

    app.include_router(ops.router)
    from app.routers import channels

    app.include_router(channels.router)
    app.include_router(auth.router)
    app.include_router(services.router)
    app.include_router(incidents.router)
    app.include_router(metrics.router)
    app.include_router(public.router)
    return app


app = create_app()
