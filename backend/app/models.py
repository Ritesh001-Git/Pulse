"""Pulse domain models (SQLAlchemy 2.0 style, PostgreSQL).

Design notes
------------
- Primary keys are UUIDv4 strings (portable, non-guessable in APIs).
- Every table carries `created_at`; hot-path tables also carry explicit
  timestamp indexes for the range queries the metrics engine will run.
- Enum values are stored as native PostgreSQL enums (created once via
  `CHECKFIRST`-safe DDL in app/main.py at startup) with a *python-side*
  validation fallback so the model layer never writes an invalid value.
- Partial unique index on `incidents (service_id) WHERE resolved_at IS NULL`
  enforces "one active incident per service" while still allowing an
  unbounded history of resolved incidents.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_uuid() -> uuid.UUID:
    return uuid.uuid4()


def _pg_enum(enum_cls, name: str):
    """Native PG enum column that stores the member *value* (asyncpg requirement)."""
    return Enum(enum_cls, name=name, native_enum=True, values_callable=lambda e: [m.value for m in e])


# ---------------------------------------------------------------- Enums


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    ENGINEER = "engineer"
    SUPPORT = "support"


class CheckStatus(str, enum.Enum):
    UP = "up"
    DEGRADED = "degraded"
    DOWN = "down"


class IncidentState(str, enum.Enum):
    INVESTIGATING = "investigating"
    IDENTIFIED = "identified"
    MONITORING = "monitoring"
    RESOLVED = "resolved"


class ActorKind(str, enum.Enum):
    SYSTEM = "system"
    USER = "user"


class TimelineEventKind(str, enum.Enum):
    OPENED = "opened"
    AUTO_DETECTED = "auto_detected"
    ACKED = "acked"
    STATUS_CHANGED = "status_changed"
    NOTE = "note"
    RESOLVED = "resolved"


class NotificationStatus(str, enum.Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


class IncidentSeverity(str, enum.Enum):
    OUTAGE = "outage"
    DEGRADATION = "degradation"


class ServiceState(str, enum.Enum):
    PENDING = "pending"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DOWN = "down"


class NotificationChannel(str, enum.Enum):
    WEBHOOK = "webhook"
    EMAIL = "email"
    SMS = "sms"


# ---------------------------------------------------------------- Users


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        _pg_enum(UserRole, "userrole"), nullable=False, default=UserRole.ENGINEER
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    timeline_events: Mapped[list["TimelineEvent"]] = relationship(back_populates="actor_user")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User {self.email} ({self.role})>"


# ---------------------------------------------------------------- Services


class Service(Base):
    __tablename__ = "services"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    health_path: Mapped[str] = mapped_column(String(255), nullable=False, default="/health")
    check_interval_sec: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    timeout_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=5000)
    degraded_latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=1000)
    failure_threshold: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    recovery_threshold: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    sla_target: Mapped[float] = mapped_column(nullable=False, default=99.9)  # SLO %
    team_owner: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    # Live state machine (persisted so streaks/states survive restarts)
    state: Mapped[ServiceState] = mapped_column(
        _pg_enum(ServiceState, "servicestate"), nullable=False, default=ServiceState.PENDING
    )
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    consecutive_successes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    check_results: Mapped[list["CheckResult"]] = relationship(
        back_populates="service", cascade="all, delete-orphan", passive_deletes=True
    )
    incidents: Mapped[list["Incident"]] = relationship(
        back_populates="service", cascade="all, delete-orphan", passive_deletes=True
    )
    maintenance_windows: Mapped[list["MaintenanceWindow"]] = relationship(
        back_populates="service", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        CheckConstraint("check_interval_sec >= 5", name="ck_service_interval_min"),
        CheckConstraint("timeout_ms > 0 AND timeout_ms <= 30000", name="ck_service_timeout_range"),
        CheckConstraint("failure_threshold >= 1 AND failure_threshold <= 20", name="ck_service_threshold_range"),
        CheckConstraint("recovery_threshold >= 1 AND recovery_threshold <= 20", name="ck_service_recovery_range"),
        CheckConstraint("degraded_latency_ms > 0", name="ck_service_latency_positive"),
        Index("ix_services_is_active", "is_active"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Service {self.name} active={self.is_active}>"


# ---------------------------------------------------------------- Check results


class CheckResult(Base):
    __tablename__ = "check_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    service_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("services.id", ondelete="CASCADE"), nullable=False, index=True
    )
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    status: Mapped[CheckStatus] = mapped_column(
        _pg_enum(CheckStatus, "checkstatus"), nullable=False
    )
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # null on timeout/dial error
    status_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    service: Mapped[Service] = relationship(back_populates="check_results")

    __table_args__ = (
        # The monitoring engine's core time-series query: latest + windowed results per service.
        Index("ix_check_results_service_time", "service_id", "checked_at"),
        # Fast "find consecutive failures" scans.
        Index("ix_check_results_service_status", "service_id", "status", "checked_at"),
        CheckConstraint("latency_ms IS NULL OR latency_ms >= 0", name="ck_check_latency_nonneg"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<CheckResult {self.service_id} {self.status} @ {self.checked_at:%H:%M:%S}>"


# ---------------------------------------------------------------- Incidents


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    service_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("services.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    severity: Mapped[IncidentSeverity] = mapped_column(
        _pg_enum(IncidentSeverity, "incidentseverity"), nullable=False, default=IncidentSeverity.OUTAGE
    )
    state: Mapped[IncidentState] = mapped_column(
        _pg_enum(IncidentState, "incidentstate"), nullable=False, default=IncidentState.INVESTIGATING
    )
    acknowledged: Mapped[bool] = mapped_column(nullable=False, default=False)
    acknowledged_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    resolved_at: Mapped[Optional[datetime] | datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    reopened_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    service: Mapped[Service] = relationship(back_populates="incidents")
    acknowledged_by_user: Mapped[Optional[User]] = relationship(foreign_keys=[acknowledged_by])
    timeline: Mapped[list["TimelineEvent"]] = relationship(
        back_populates="incident",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="TimelineEvent.at",
    )

    __table_args__ = (
        # ONE active incident per service; resolved incidents (resolved_at set) are unrestricted,
        # so full incident history remains available for the same service.
        Index(
            "uq_incidents_service_active",
            "service_id",
            unique=True,
            postgresql_where=text("resolved_at IS NULL"),
        ),
        # Dashboard queries: active incidents first, then service history.
        Index("ix_incidents_resolved_at", "resolved_at"),
        Index("ix_incidents_service_opened", "service_id", "opened_at"),
        CheckConstraint(
            f"state IN ('{IncidentState.INVESTIGATING.value}', '{IncidentState.IDENTIFIED.value}', "
            f"'{IncidentState.MONITORING.value}', '{IncidentState.RESOLVED.value}')",
            name="ck_incident_state_valid",
        ),
        CheckConstraint("reopened_count >= 0", name="ck_incident_reopened_nonneg"),
        CheckConstraint(
            "resolved_at IS NULL OR resolved_at >= opened_at", name="ck_incident_resolution_order"
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Incident {self.service_id} {self.state.value} acked={self.acknowledged}>"


# ---------------------------------------------------------------- Timeline events


class TimelineEvent(Base):
    __tablename__ = "timeline_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    incident_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    actor: Mapped[ActorKind] = mapped_column(
        _pg_enum(ActorKind, "actorkind"), nullable=False, default=ActorKind.SYSTEM
    )
    actor_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    kind: Mapped[TimelineEventKind] = mapped_column(
        _pg_enum(TimelineEventKind, "timelineeventkind"),
        nullable=False,
        default=TimelineEventKind.STATUS_CHANGED,
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)

    incident: Mapped[Incident] = relationship(back_populates="timeline")
    actor_user: Mapped[Optional[User]] = relationship(back_populates="timeline_events")

    __table_args__ = (
        # Timeline fetch always ordered by incident + time.
        Index("ix_timeline_incident_at", "incident_id", "at"),
        CheckConstraint("NOT (actor = 'user' AND actor_user_id IS NULL)", name="ck_timeline_user_actor_needs_user"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<TimelineEvent {self.incident_id} {self.kind.value}>"


# ---------------------------------------------------------------- Notifications


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    channel: Mapped[NotificationChannel] = mapped_column(
        _pg_enum(NotificationChannel, "notificationchannel"), nullable=False
    )
    audience: Mapped[str] = mapped_column(String(120), nullable=False)  # e.g. "engineers", "support", "subscribers"
    incident_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    event: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # lifecycle event type
    status: Mapped[NotificationStatus] = mapped_column(
        _pg_enum(NotificationStatus, "notificationstatus"),
        nullable=False,
        default=NotificationStatus.PENDING,
    )
    detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # payload summary / delivery error

    incident: Mapped[Optional[Incident]] = relationship(foreign_keys=[incident_id])

    __table_args__ = (
        Index("ix_notifications_at", "at"),
        CheckConstraint(f"status IN ('{NotificationStatus.PENDING.value}', '{NotificationStatus.SENT.value}', '{NotificationStatus.FAILED.value}')", name="ck_notification_status_valid"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Notification {self.channel.value} -> {self.audience} ({self.status.value})>"


# ---------------------------------------------------------------- Webhook channels (config)


class WebhookChannel(Base):
    """Outgoing webhook configuration for incident notifications."""

    __tablename__ = "notification_channels"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    # Optional filter: channel only receives events for this service (null = all)
    service_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("services.id", ondelete="CASCADE"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    service: Mapped[Optional[Service]] = relationship()

    __table_args__ = (Index("ix_channels_service", "service_id"),)


# ---------------------------------------------------------------- Maintenance windows


class MaintenanceWindow(Base):
    __tablename__ = "maintenance_windows"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    service_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("services.id", ondelete="CASCADE"), nullable=False, index=True
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    service: Mapped[Service] = relationship(back_populates="maintenance_windows")

    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="ck_maintenance_window_order"),
        Index("ix_maintenance_service_window", "service_id", "starts_at", "ends_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<MaintenanceWindow {self.service_id} {self.starts_at} → {self.ends_at}>"


# ---------------------------------------------------------------- Subscribers (public status page)


class Subscriber(Base):
    __tablename__ = "subscribers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    webhook_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    service_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("services.id", ondelete="CASCADE"), nullable=True
    )
    unsubscribe_token: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    service: Mapped[Optional[Service]] = relationship()

    __table_args__ = (
        CheckConstraint("email IS NOT NULL OR webhook_url IS NOT NULL", name="ck_subscriber_has_target"),
        Index("ix_subscribers_service", "service_id"),
    )
