from fastapi import APIRouter, Depends
from sqlalchemy import text

from app.deps import get_current_user
from app.resilience import get_db

router = APIRouter(tags=["ops"])


@router.get("/health")
async def health() -> dict:
    """Liveness: process is up (no DB round-trip)."""
    return {"status": "ok"}


@router.get("/health/db")
async def db_health(db=Depends(get_db)):
    from sqlalchemy import func, select

    from app.models import (
        CheckResult,
        Incident,
        MaintenanceWindow,
        Notification,
        Service,
        TimelineEvent,
        User,
    )

    try:
        await db.execute(text("SELECT 1"))
        counts = {}
        for model in (User, Service, CheckResult, Incident, TimelineEvent, Notification, MaintenanceWindow):
            counts[model.__tablename__] = (await db.execute(select(func.count()).select_from(model))).scalar_one()
        return {"status": "ok", "database": "connected", "tables": counts}
    except Exception as exc:
        from fastapi import HTTPException

        raise HTTPException(status_code=503, detail=f"database unhealthy: {exc}")
