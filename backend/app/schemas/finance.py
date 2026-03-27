"""
schemas/finance.py
==================
Pydantic v2 request/response contracts for all financial calculation endpoints.

Endpoints covered:
  POST /fire/calculate
  POST /sip/required
  POST /sip/maturity
  POST /tax/compare
  POST /portfolio/xray
  GET  /portfolio/health-score

Author : FinMentor Platform
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, model_validator


# ===========================================================================
# Shared
# ===========================================================================

class EngineResult(BaseModel):
    """Wraps raw engine dict outputs for consistent API envelope."""
    status: Literal["success", "error"]
    data: Optional[dict[str, Any]] = None
    error: Optional[dict[str, str]] = None


# ===========================================================================
# FIRE  —  POST /fire/calculate
# ===========================================================================

class FIRERequest(BaseModel):
    """
    Minimum required: current_age, target_retirement_age, monthly_expense_today.
    All monetary values in INR.
    """
    current_age: int = Field(ge=18, le=80)
    target_retirement_age: int = Field(ge=19, le=90)
    monthly_expense_today: Decimal = Field(gt=0, description="Current monthly expenses in INR")

    life_expectancy: int = Field(default=85, ge=50, le=110)
    inflation_rate_pct: float = Field(default=6.0, ge=0.0, le=20.0)
    post_retirement_return_pct: float = Field(default=7.0, ge=0.0, le=30.0)
    pre_retirement_return_pct: float = Field(default=12.0, ge=0.0, le=40.0)

    current_corpus: Decimal = Field(default=Decimal("0"), ge=0)
    monthly_savings: Decimal = Field(default=Decimal("0"), ge=0)

    @model_validator(mode="after")
    def retirement_gt_current(self) -> "FIRERequest":
        if self.target_retirement_age <= self.current_age:
            raise ValueError("target_retirement_age must be > current_age.")
        return self


class FIREMilestone(BaseModel):
    year: int
    age: int
    corpus_accumulated: Decimal
    corpus_required_at_this_point: Decimal
    on_track: bool


class FIREResponse(BaseModel):
    years_to_retire: int
    post_retirement_years: int
    monthly_expense_at_retirement: Decimal
    annual_expense_at_retirement: Decimal
    corpus_required: Decimal
    corpus_required_4pct_rule: Decimal
    corpus_accumulated: dict[str, Decimal]
    corpus_gap: Decimal
    monthly_sip_needed_to_close_gap: Decimal
    fire_achievable_with_current_plan: bool
    milestones: list[FIREMilestone] = Field(default_factory=list)


# ===========================================================================
# SIP  —  POST /sip/required  &  POST /sip/maturity
# ===========================================================================

class SIPMaturityRequest(BaseModel):
    """
    What does ₹X/month grow to?
    Maps to sip_future_value().
    """
    monthly_investment: Decimal = Field(gt=0, description="Monthly SIP amount in INR")
    annual_rate_pct: float = Field(ge=0.0, le=50.0, description="Expected annual return %")
    years: int = Field(ge=1, le=50)
    step_up_pct: float = Field(default=0.0, ge=0.0, le=50.0,
                                description="Annual SIP step-up %")


class SIPMaturityResponse(BaseModel):
    invested_amount: Decimal
    estimated_returns: Decimal
    future_value: Decimal
    wealth_gained: Decimal
    absolute_return_pct: Decimal
    cagr_pct: Decimal
    yearly_breakdown: list[dict[str, Any]]


class SIPRequiredRequest(BaseModel):
    """
    How much do I need to invest monthly to reach ₹target?
    Inverse SIP calculation.
    """
    target_corpus: Decimal = Field(gt=0, description="Goal amount in INR")
    annual_rate_pct: float = Field(ge=0.0, le=50.0)
    years: int = Field(ge=1, le=50)
    step_up_pct: float = Field(default=0.0, ge=0.0, le=50.0)
    existing_corpus: Decimal = Field(default=Decimal("0"), ge=0,
                                      description="Already accumulated amount")


class SIPRequiredResponse(BaseModel):
    target_corpus: Decimal
    years: int
    annual_rate_pct: float
    existing_corpus: Decimal
    fv_of_existing_corpus: Decimal
    remaining_corpus_needed: Decimal
    monthly_sip_required: Decimal
    with_step_up_pct: float
    note: Optional[str] = None


# ===========================================================================
# Tax  —  POST /tax/compare
# ===========================================================================

class TaxCompareRequest(BaseModel):
    """
    Computes Old vs New regime and returns the better option.
    All deduction fields optional (0 if not provided).
    """
    gross_annual_income: Decimal = Field(gt=0)

    # Old-regime deductions
    section_80c: Decimal = Field(default=Decimal("0"), ge=0, le=150_000)
    section_80d_self: Decimal = Field(default=Decimal("0"), ge=0, le=50_000)
    section_80d_parents: Decimal = Field(default=Decimal("0"), ge=0, le=50_000)
    parents_senior: bool = False
    self_senior: bool = False
    hra_exemption: Decimal = Field(default=Decimal("0"), ge=0)
    other_deductions_80c_cap: Decimal = Field(
        default=Decimal("0"), ge=0, le=50_000,
        description="NPS 80CCD(1B) etc."
    )
    home_loan_interest: Decimal = Field(default=Decimal("0"), ge=0, le=200_000)

    # HRA auto-compute inputs
    basic_salary: Decimal = Field(default=Decimal("0"), ge=0)
    actual_hra_received: Decimal = Field(default=Decimal("0"), ge=0)
    actual_rent_paid: Decimal = Field(default=Decimal("0"), ge=0)
    metro_city: bool = False


class TaxRegimeDetail(BaseModel):
    regime: Literal["old", "new"]
    taxable_income: Decimal
    total_tax_payable: Decimal
    effective_tax_rate_pct: Decimal
    monthly_in_hand_approx: Decimal
    deductions: dict[str, Any]
    tax_breakdown: dict[str, Any]


class TaxCompareResponse(BaseModel):
    gross_annual_income: Decimal
    old_regime: TaxRegimeDetail
    new_regime: TaxRegimeDetail
    recommended_regime: Literal["old", "new"]
    tax_saving_with_recommended: Decimal
    fy: str = "2024-25"


# ===========================================================================
# Portfolio  —  POST /portfolio/xray  &  GET /portfolio/health-score
# ===========================================================================

class CashFlowInput(BaseModel):
    date: str = Field(description="ISO date YYYY-MM-DD")
    amount: float = Field(
        description="Negative = investment/outflow, Positive = redemption/inflow"
    )


class PortfolioXRayRequest(BaseModel):
    """
    Accepts raw cash flows for XIRR + optional holdings for allocation drift.
    portfolio_id is optional — if provided, DB holdings are used instead.
    """
    portfolio_id: Optional[str] = Field(
        default=None,
        description="UUID of existing portfolio; overrides cash_flows if provided",
    )
    cash_flows: list[CashFlowInput] = Field(
        default_factory=list,
        description="Manual cash flow list for ad-hoc XIRR (min 2 entries)",
    )
    target_allocation: Optional[dict[str, float]] = Field(
        default=None,
        description='e.g. {"equity": 60, "debt": 30, "gold": 10}',
        example={"equity": 60, "debt": 30, "gold": 10},
    )


class AllocationDrift(BaseModel):
    asset_class: str
    target_pct: float
    actual_pct: float
    drift_pct: float
    action: Literal["buy", "sell", "hold"]


class PortfolioXRayResponse(BaseModel):
    xirr_pct: Optional[float]
    total_invested: float
    total_current_value: float
    absolute_gain: float
    absolute_return_pct: float
    duration_years: float
    allocation_drift: list[AllocationDrift] = Field(default_factory=list)
    health_flags: list[str] = Field(
        default_factory=list,
        description="Human-readable warnings e.g. 'Equity over-weight by 15%'",
    )


class HealthDimension(BaseModel):
    name: str
    score: float = Field(ge=0.0, le=10.0)
    weight: float
    weighted_score: float
    insight: str


class HealthScoreResponse(BaseModel):
    overall_score: float = Field(ge=0.0, le=100.0)
    grade: Literal["A+", "A", "B", "C", "D", "F"]
    dimensions: list[HealthDimension]
    top_action: str = Field(description="Single highest-impact next step")
    summary: str