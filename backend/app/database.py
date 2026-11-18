from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    """Declarative base for all Pulse models."""


def _build_engine():
    settings = get_settings()
    # Timeouts so a *hanging* database degrades in seconds, not TCP-default minutes:
    #   timeout         — connection establishment (seconds)
    #   command_timeout — max seconds any single statement may run
    connect_args = {}
    if settings.database_url.startswith("postgresql"):
        connect_args = {"timeout": 5, "command_timeout": 10}
    return create_async_engine(
        settings.database_url,
        echo=settings.echo_sql,
        pool_pre_ping=True,  # discard stale pooled connections transparently
        pool_size=10,
        max_overflow=20,
        pool_recycle=1800,   # recycle connections before server idle limits bite
        connect_args=connect_args,
    )


engine = _build_engine()

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
