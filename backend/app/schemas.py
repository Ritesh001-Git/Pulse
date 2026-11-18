"""Pydantic request models (camelCase wire format, matching the frontend contract)."""
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, HttpUrl


class LoginRequest(BaseModel):
    email: str
    password: str


class ServiceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: Optional[str] = None
    url: str = Field(min_length=1, max_length=500)
    healthPath: str = "/health"
    checkIntervalSec: int = Field(default=30, ge=5, le=3600)
    timeoutMs: int = Field(default=5000, ge=100, le=30000)
    degradedLatencyMs: int = Field(default=1000, ge=1)
    failureThreshold: int = Field(default=3, ge=1, le=20)
    recoveryThreshold: int = Field(default=2, ge=1, le=20)
    teamOwner: Optional[str] = None


class ServiceUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    description: Optional[str] = None
    url: Optional[str] = Field(default=None, min_length=1, max_length=500)
    healthPath: Optional[str] = None
    checkIntervalSec: Optional[int] = Field(default=None, ge=5, le=3600)
    timeoutMs: Optional[int] = Field(default=None, ge=100, le=30000)
    degradedLatencyMs: Optional[int] = Field(default=None, ge=1)
    failureThreshold: Optional[int] = Field(default=None, ge=1, le=20)
    recoveryThreshold: Optional[int] = Field(default=None, ge=1, le=20)
    teamOwner: Optional[str] = None
    isActive: Optional[bool] = None


class IncidentCreate(BaseModel):
    serviceId: str
    title: str = Field(min_length=1, max_length=300)
    severity: str = Field(default="outage", pattern="^(outage|degradation)$")


class AckRequest(BaseModel):
    pass  # actor comes from auth context


class NoteRequest(BaseModel):
    body: str = Field(min_length=1)


class StatusUpdateRequest(BaseModel):
    state: Optional[str] = Field(default=None, pattern="^(investigating|identified|monitoring|resolved)$")
    message: Optional[str] = None


class ResolveRequest(BaseModel):
    summary: Optional[str] = None


class SubscribeRequest(BaseModel):
    email: Optional[EmailStr] = None
    webhookUrl: Optional[str] = None
    serviceId: Optional[str] = None
