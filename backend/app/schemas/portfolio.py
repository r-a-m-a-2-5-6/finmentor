"""
schemas/portfolio.py
====================
Pydantic v2 contracts for portfolio CRUD endpoints.

  POST   /portfolios                → CreatePortfolioRequest → PortfolioResponse
  GET    /portfolios                → list[PortfolioResponse]
  GET    /portfolios/{id}           → PortfolioResponse
  POST   /portfolios/{id}/holdings  → AddHoldingRequest → HoldingResponse
  POST   /portfolios/{id}/cashflows → AddCashFlowRequest → CashFlowResponse
  DELETE /portfolios/{id}           → 204 No Content

Author : FinMentor Platform
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Portfolio CRUD
# ---------------------------------------------------------------------------

class CreatePortfolioRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: Optional[str] = Field(default=None, max_length=500)


class PortfolioResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    description: Optional[str]
    current_value: Decimal
    invested_value: Decimal
    xirr_pct: Optional[Decimal]
    health_score: Optional[Decimal]
    holding_count: int = 0
    cash_flow_count: int = 0

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Holdings
# ---------------------------------------------------------------------------

class AddHoldingRequest(BaseModel):
    instrument_name: str = Field(min_length=1, max_length=200)
    isin: Optional[str] = Field(default=None, max_length=12)
    asset_class: Literal[
        "equity", "debt", "gold", "real_estate", "cash", "crypto", "other"
    ]
    folio_number: Optional[str] = Field(default=None, max_length=60)
    units: Decimal = Field(gt=0)
    purchase_nav: Decimal = Field(gt=0)
    current_nav: Optional[Decimal] = Field(default=None, gt=0)
    purchase_date: Optional[date] = None

    @field_validator("isin")
    @classmethod
    def isin_format(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and len(v) != 12:
            raise ValueError("ISIN must be exactly 12 characters.")
        return v


class HoldingResponse(BaseModel):
    id: uuid.UUID
    portfolio_id: uuid.UUID
    instrument_name: str
    isin: Optional[str]
    asset_class: str
    units: Decimal
    purchase_nav: Decimal
    current_nav: Optional[Decimal]
    purchase_date: Optional[date]
    invested_amount: Decimal
    current_value: Optional[Decimal]
    allocation_pct: Optional[Decimal]
    unrealised_gain: Optional[Decimal] = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Cash Flows
# ---------------------------------------------------------------------------

class AddCashFlowRequest(BaseModel):
    transaction_date: date
    amount: Decimal = Field(
        description="Negative = investment, Positive = redemption/dividend"
    )
    flow_type: Literal["investment", "redemption", "dividend"]
    instrument_name: Optional[str] = Field(default=None, max_length=200)
    notes: Optional[str] = Field(default=None, max_length=300)

    @field_validator("amount")
    @classmethod
    def validate_amount_sign(cls, v: Decimal, info) -> Decimal:
        # Validate sign convention consistency
        values = info.data
        flow_type = values.get("flow_type")
        if flow_type == "investment" and v > 0:
            raise ValueError("Investment cash flows must be negative (outflow).")
        if flow_type in ("redemption", "dividend") and v < 0:
            raise ValueError("Redemption/dividend cash flows must be positive (inflow).")
        return v


class CashFlowResponse(BaseModel):
    id: uuid.UUID
    portfolio_id: uuid.UUID
    transaction_date: date
    amount: Decimal
    flow_type: str
    instrument_name: Optional[str]
    notes: Optional[str]

    model_config = {"from_attributes": True}