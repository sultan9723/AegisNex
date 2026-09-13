"""Input validation schemas for AegisNex API."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field, field_validator


class LoginRequest(BaseModel):
    """Login request schema."""

    username: str = Field(..., min_length=1, max_length=255, description="Username or email")
    password: str = Field(..., min_length=1, max_length=128, description="Password")

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        """Validate username format."""
        v = v.strip()
        if not v:
            raise ValueError("Username cannot be empty")
        if len(v) > 255:
            raise ValueError("Username too long")
        return v


class IncidentCreateRequest(BaseModel):
    """Incident creation request schema."""

    service_name: str = Field(..., min_length=1, max_length=255)
    description: str = Field(..., min_length=1, max_length=2000)
    severity: str = Field(default="medium", pattern=r"^(low|medium|high|critical)$")
    source: str = Field(default="manual", max_length=100)


class RemediationRequest(BaseModel):
    """Remediation execution request schema."""

    incident_id: str = Field(..., min_length=1, max_length=100)
    action: str = Field(..., min_length=1, max_length=100)
    approved_by: str = Field(default="system", max_length=255)


class NotificationConfig(BaseModel):
    """Notification configuration schema."""

    channel_type: str = Field(..., pattern=r"^(email|slack|discord|pagerduty|teams|webhook)$")
    enabled: bool = Field(default=True)
    config: dict[str, Any] = Field(default_factory=dict)


class MonitoringTargetCreate(BaseModel):
    """Monitoring target creation schema."""

    name: str = Field(..., min_length=1, max_length=255)
    type: str = Field(..., pattern=r"^(http|ssl|tcp|dns)$")
    target: str = Field(..., min_length=1, max_length=1000)
    interval_seconds: int = Field(default=60, ge=10, le=3600)
    timeout_seconds: int = Field(default=5, ge=1, le=60)
    enabled: bool = Field(default=True)


class UserCreateRequest(BaseModel):
    """User creation request schema."""

    email: str = Field(..., description="User email address")
    password: str = Field(..., min_length=8, max_length=128)
    role: str = Field(default="read_only", pattern=r"^(super_admin|administrator|soc_analyst|operator|read_only|auditor)$")

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        """Validate email format."""
        v = v.strip().lower()
        email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        if not re.match(email_pattern, v):
            raise ValueError("Invalid email format")
        return v


class PaginationParams(BaseModel):
    """Pagination parameters."""

    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=200)


class SearchRequest(BaseModel):
    """Search request schema."""

    query: str = Field(..., min_length=1, max_length=500)
    filters: dict[str, Any] = Field(default_factory=dict)
    pagination: PaginationParams = Field(default_factory=PaginationParams)
