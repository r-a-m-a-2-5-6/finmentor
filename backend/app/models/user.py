"""
models/user.py
==============
User account + financial profile.

One user → one FinancialProfile (nullable until onboarding complete)
One user → many Portfolio rows
One user → many ChatSession rows

Author : FinMentor Platform
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean, CheckConstraint, Enum, ForeignKey,
    Integer, Numeric, String, Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from finmentor.backend.app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from finmentor.backend.app.models.portfolio import Portfolio
    from finmentor.backend.app.models.chat import ChatSession


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

RiskProfileEnum = Enum(
    "conservative", "moderate", "aggressive",
    name="risk_profile_enum",
)

JobStabilityEnum = Enum(
    "stable", "semi_stable", "unstable", "self_employed",
    name="job_stability_enum",
)


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------

class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Core authentication entity.

    Separates auth data (email, hashed_password) from financial profile
    so profile can be updated / deleted without touching credentials.
    """
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # ── Relationships ─────────────────────────────────────────────────────
    financial_profile: Mapped[Optional["FinancialProfile"]] = relationship(
        "FinancialProfile", back_populates="user",
        uselist=False, cascade="all, delete-orphan",
    )
    portfolios: Mapped[list["Portfolio"]] = relationship(
        "Portfolio", back_populates="user",
        cascade="all, delete-orphan",
    )
    chat_sessions: Mapped[list["ChatSession"]] = relationship(
        "ChatSession", back_populates="user",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email}>"


# ---------------------------------------------------------------------------
# FinancialProfile  (1-to-1 with User)
# ---------------------------------------------------------------------------

class FinancialProfile(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Stores the user's financial metadata used across all calculators.

    Nullable by design — created only after the onboarding PATCH call.
    Uses Numeric(precision, scale) for all monetary fields to avoid
    floating-point drift in tax / FIRE calculations.
    """
    __tablename__ = "financial_profiles"
    __table_args__ = (
        CheckConstraint("current_age >= 18 AND current_age <= 80",
                        name="ck_age_range"),
        CheckConstraint("target_retirement_age > current_age",
                        name="ck_retirement_age_gt_current"),
        CheckConstraint("monthly_income >= 0", name="ck_income_non_negative"),
        CheckConstraint("monthly_expenses >= 0", name="ck_expenses_non_negative"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True, nullable=False, index=True,
    )

    # ── Demographics ──────────────────────────────────────────────────────
    current_age: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    target_retirement_age: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    life_expectancy: Mapped[int] = mapped_column(Integer, default=85, nullable=False)

    # ── Income & Expenses ────────────────────────────────────────────────
    monthly_income: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 2), nullable=True
    )
    monthly_expenses: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 2), nullable=True
    )
    monthly_emi: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0.00"), nullable=False
    )
    monthly_insurance_premium: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0.00"), nullable=False
    )

    # ── Wealth ───────────────────────────────────────────────────────────
    current_corpus: Mapped[Decimal] = mapped_column(
        Numeric(16, 2), default=Decimal("0.00"), nullable=False
    )
    existing_emergency_fund: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0.00"), nullable=False
    )

    # ── Preferences ──────────────────────────────────────────────────────
    risk_profile: Mapped[Optional[str]] = mapped_column(
        RiskProfileEnum, nullable=True
    )
    job_stability: Mapped[str] = mapped_column(
        JobStabilityEnum, default="stable", nullable=False
    )
    dependents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    metro_city: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # ── Tax inputs ────────────────────────────────────────────────────────
    gross_annual_income: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(16, 2), nullable=True
    )
    preferred_tax_regime: Mapped[str] = mapped_column(
        Enum("old", "new", name="tax_regime_enum"),
        default="new", nullable=False,
    )

    # ── Relationship ──────────────────────────────────────────────────────
    user: Mapped["User"] = relationship("User", back_populates="financial_profile")

    def __repr__(self) -> str:
        return f"<FinancialProfile user_id={self.user_id} age={self.current_age}>"