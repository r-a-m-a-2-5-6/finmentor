"""
models/portfolio.py
===================
Portfolio, PortfolioHolding, and CashFlowEntry models.

One User → many Portfolios (e.g., "Retirement", "Child Education")
One Portfolio → many PortfolioHoldings (asset-level rows)
One Portfolio → many CashFlowEntry rows (for XIRR computation)

Author : 
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    CheckConstraint, Date, Enum, ForeignKey,
    Numeric, String, Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.user import User


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

AssetClassEnum = Enum(
    "equity", "debt", "gold", "real_estate", "cash", "crypto", "other",
    name="asset_class_enum",
)

CashFlowTypeEnum = Enum(
    "investment",   # negative (outflow)
    "redemption",   # positive (inflow)
    "dividend",     # positive (inflow)
    name="cash_flow_type_enum",
)


# ---------------------------------------------------------------------------
# Portfolio  (the envelope — one per goal)
# ---------------------------------------------------------------------------

class Portfolio(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Named goal-based portfolio container.

    Examples: "Retirement Corpus", "Emergency Fund",
              "Child's Higher Education", "House Down Payment".
    """
    __tablename__ = "portfolios"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Cached metrics — updated by background job or on-demand recalc
    current_value: Mapped[Decimal] = mapped_column(
        Numeric(16, 2), default=Decimal("0.00"), nullable=False
    )
    invested_value: Mapped[Decimal] = mapped_column(
        Numeric(16, 2), default=Decimal("0.00"), nullable=False
    )
    xirr_pct: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(6, 2), nullable=True
    )
    health_score: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 2), nullable=True
    )

    # ── Relationships ─────────────────────────────────────────────────────
    user: Mapped["User"] = relationship("User", back_populates="portfolios")
    holdings: Mapped[list["PortfolioHolding"]] = relationship(
        "PortfolioHolding", back_populates="portfolio",
        cascade="all, delete-orphan",
    )
    cash_flows: Mapped[list["CashFlowEntry"]] = relationship(
        "CashFlowEntry", back_populates="portfolio",
        cascade="all, delete-orphan",
        order_by="CashFlowEntry.transaction_date",
    )

    def __repr__(self) -> str:
        return f"<Portfolio id={self.id} name={self.name!r}>"


# ---------------------------------------------------------------------------
# PortfolioHolding  (asset-level detail)
# ---------------------------------------------------------------------------

class PortfolioHolding(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Individual holding line within a Portfolio.

    Stores both purchase and current values to compute unrealised gain/loss
    without a live price feed dependency.
    """
    __tablename__ = "portfolio_holdings"
    __table_args__ = (
        CheckConstraint("units >= 0", name="ck_units_non_negative"),
        CheckConstraint("purchase_nav > 0", name="ck_purchase_nav_positive"),
        CheckConstraint(
            "allocation_pct >= 0 AND allocation_pct <= 100",
            name="ck_allocation_pct_range",
        ),
    )

    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    # Instrument details
    instrument_name: Mapped[str] = mapped_column(String(200), nullable=False)
    isin: Mapped[Optional[str]] = mapped_column(
        String(12), nullable=True, index=True
    )
    asset_class: Mapped[str] = mapped_column(AssetClassEnum, nullable=False)
    folio_number: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)

    # Position
    units: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    purchase_nav: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    current_nav: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(12, 4), nullable=True
    )
    purchase_date: Mapped[Optional[Date]] = mapped_column(Date, nullable=True)

    # Computed / cached
    invested_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False
    )
    current_value: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 2), nullable=True
    )
    allocation_pct: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 2), nullable=True
    )

    # ── Relationship ──────────────────────────────────────────────────────
    portfolio: Mapped["Portfolio"] = relationship(
        "Portfolio", back_populates="holdings"
    )

    def __repr__(self) -> str:
        return (
            f"<PortfolioHolding {self.instrument_name!r} "
            f"units={self.units} nav={self.current_nav}>"
        )


# ---------------------------------------------------------------------------
# CashFlowEntry  (raw transaction log used by XIRR)
# ---------------------------------------------------------------------------

class CashFlowEntry(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Immutable transaction record for XIRR computation.

    Sign convention:
        investment  → stored as negative float (outflow)
        redemption  → stored as positive float (inflow)
        dividend    → stored as positive float (inflow)
    """
    __tablename__ = "cash_flow_entries"

    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    transaction_date: Mapped[Date] = mapped_column(Date, nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    flow_type: Mapped[str] = mapped_column(CashFlowTypeEnum, nullable=False)
    instrument_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ── Relationship ──────────────────────────────────────────────────────
    portfolio: Mapped["Portfolio"] = relationship(
        "Portfolio", back_populates="cash_flows"
    )

    def __repr__(self) -> str:
        return (
            f"<CashFlowEntry date={self.transaction_date} "
            f"amount={self.amount} type={self.flow_type}>"
        )