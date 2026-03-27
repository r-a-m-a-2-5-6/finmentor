"""
models/base.py
==============
SQLAlchemy async declarative base + shared mixin columns.
Every table inherits TimestampMixin for audit trails.

Author : FinMentor Platform
Python : 3.11+
Deps   : sqlalchemy[asyncio], asyncpg
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Project-wide declarative base."""
    pass


class TimestampMixin:
    """
    Adds created_at / updated_at to any model.
    Both columns are timezone-aware and server-side defaulted.
    """
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class UUIDPrimaryKeyMixin:
    """UUID v4 primary key — avoids sequential-ID enumeration attacks."""
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )