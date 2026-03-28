"""
api/routes/finance.py
=====================
Financial calculation endpoints — pure compute, no DB writes.

  POST /fire/calculate   — FIRE corpus + milestones
  POST /sip/required     — Monthly SIP needed to reach a goal
  POST /sip/maturity     — What does ₹X/month grow to?
  POST /tax/compare      — Old vs New regime comparison

Author : FinMentor Platform
"""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status

from app.engine.fire_calculator import fire_corpus_calculator
from app.engine.sip_engine import sip_future_value
from app.engine.tax_optimizer import india_tax_calculator
from app.models.user import User
from app.schemas.finance import (
    FIREMilestone, FIRERequest, FIREResponse,
    SIPMaturityRequest, SIPMaturityResponse,
    SIPRequiredRequest, SIPRequiredResponse,
    TaxCompareRequest, TaxCompareResponse, TaxRegimeDetail,
)
from app.utils.auth import get_current_user

fire_router = APIRouter(prefix="/fire", tags=["FIRE Calculator"])
sip_router = APIRouter(prefix="/sip", tags=["SIP Calculator"])
tax_router = APIRouter(prefix="/tax", tags=["Tax Optimizer"])


# ---------------------------------------------------------------------------
# Helper: raise 422 from engine error response
# ---------------------------------------------------------------------------

def _unwrap(result: dict) -> dict:
    """Raise HTTPException if the engine returned an error."""
    if result["status"] == "error":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=result["error"]["message"],
        )
    return result["data"]


# ===========================================================================
# FIRE
# ===========================================================================

@fire_router.post(
    "/calculate",
    response_model=FIREResponse,
    summary="Compute FIRE corpus requirement with milestones",
)
async def fire_calculate(
    body: FIRERequest,
    _: User = Depends(get_current_user),
) -> FIREResponse:
    raw = fire_corpus_calculator(
        current_monthly_expense=float(body.monthly_expense_today),
        current_age=body.current_age,
        target_retirement_age=body.target_retirement_age,
        life_expectancy=body.life_expectancy,
        inflation_rate_pct=body.inflation_rate_pct,
        post_retirement_return_pct=body.post_retirement_return_pct,
        pre_retirement_return_pct=body.pre_retirement_return_pct,
        current_savings=float(body.current_corpus),
        monthly_savings=float(body.monthly_savings),
    )
    data = _unwrap(raw)

    # Build year-by-year milestone projections
    milestones = _build_fire_milestones(body, data)

    return FIREResponse(
        years_to_retire=data["years_to_retire"],
        post_retirement_years=data["post_retirement_years"],
        monthly_expense_at_retirement=Decimal(
            str(data["monthly_expense_at_retirement"])
        ),
        annual_expense_at_retirement=Decimal(
            str(data["annual_expense_at_retirement"])
        ),
        corpus_required=Decimal(str(data["corpus_required"])),
        corpus_required_4pct_rule=Decimal(str(data["corpus_required_4pct_rule"])),
        corpus_accumulated={
            k: Decimal(str(v))
            for k, v in data["corpus_accumulated"].items()
        },
        corpus_gap=Decimal(str(data["corpus_gap"])),
        monthly_sip_needed_to_close_gap=Decimal(
            str(data["monthly_sip_needed_to_close_gap"])
        ),
        fire_achievable_with_current_plan=data["fire_achievable_with_current_plan"],
        milestones=milestones,
    )


def _build_fire_milestones(
    body: FIRERequest,
    data: dict,
) -> list[FIREMilestone]:
    """
    Project corpus growth year-by-year using pre-retirement SIP growth.
    Returns a milestone for every 5th year plus the final year.
    """
    milestones: list[FIREMilestone] = []
    monthly_rate = body.pre_retirement_return_pct / 100 / 12
    monthly_sip = float(body.monthly_savings)
    years_to_retire = data["years_to_retire"]
    corpus_required = float(data["corpus_required"])

    accumulated = float(body.current_corpus)

    for year in range(1, years_to_retire + 1):
        # Grow existing corpus by 1 year
        accumulated = accumulated * (1 + body.pre_retirement_return_pct / 100)
        # Add SIP growth for the year
        if monthly_rate > 0:
            sip_fv = monthly_sip * (
                ((1 + monthly_rate) ** 12 - 1) / monthly_rate
            ) * (1 + monthly_rate)
        else:
            sip_fv = monthly_sip * 12
        accumulated += sip_fv

        # Milestone at every 5th year or the final year
        if year % 5 == 0 or year == years_to_retire:
            milestones.append(FIREMilestone(
                year=year,
                age=body.current_age + year,
                corpus_accumulated=Decimal(str(round(accumulated, 2))),
                corpus_required_at_this_point=Decimal(str(round(corpus_required, 2))),
                on_track=accumulated >= corpus_required * (year / years_to_retire),
            ))

    return milestones


# ===========================================================================
# SIP — Maturity
# ===========================================================================

@sip_router.post(
    "/maturity",
    response_model=SIPMaturityResponse,
    summary="Project future value of a monthly SIP",
)
async def sip_maturity(
    body: SIPMaturityRequest,
    _: User = Depends(get_current_user),
) -> SIPMaturityResponse:
    raw = sip_future_value(
        monthly_investment=float(body.monthly_investment),
        annual_rate_pct=body.annual_rate_pct,
        years=body.years,
        step_up_pct=body.step_up_pct,
    )
    data = _unwrap(raw)
    return SIPMaturityResponse(
        invested_amount=Decimal(str(data["invested_amount"])),
        estimated_returns=Decimal(str(data["estimated_returns"])),
        future_value=Decimal(str(data["future_value"])),
        wealth_gained=Decimal(str(data["wealth_gained"])),
        absolute_return_pct=Decimal(str(data["absolute_return_pct"])),
        cagr_pct=Decimal(str(data["cagr_pct"])),
        yearly_breakdown=data["yearly_breakdown"],
    )


# ===========================================================================
# SIP — Required
# ===========================================================================

@sip_router.post(
    "/required",
    response_model=SIPRequiredResponse,
    summary="Calculate monthly SIP needed to reach a corpus target",
)
async def sip_required(
    body: SIPRequiredRequest,
    _: User = Depends(get_current_user),
) -> SIPRequiredResponse:
    monthly_rate = body.annual_rate_pct / 100 / 12
    n_months = body.years * 12
    pre_return = body.pre_retirement_return_pct if hasattr(body, 'pre_retirement_return_pct') else body.annual_rate_pct

    # FV of existing corpus
    fv_existing = float(body.existing_corpus) * (
        1 + body.annual_rate_pct / 100
    ) ** body.years

    remaining = max(0.0, float(body.target_corpus) - fv_existing)

    # Inverse SIP formula: P = FV × r / [((1+r)^n - 1) × (1+r)]
    if monthly_rate == 0 or n_months == 0:
        monthly_sip = remaining / n_months if n_months > 0 else 0.0
    else:
        annuity_factor = (
            ((1 + monthly_rate) ** n_months - 1) / monthly_rate
        ) * (1 + monthly_rate)
        monthly_sip = remaining / annuity_factor if annuity_factor > 0 else 0.0

    note = None
    if body.step_up_pct > 0:
        note = (
            f"With a {body.step_up_pct}% annual step-up, your initial SIP "
            f"would be lower. Shown figure is for flat SIP. "
            f"Use /sip/maturity to model step-up scenarios."
        )

    return SIPRequiredResponse(
        target_corpus=body.target_corpus,
        years=body.years,
        annual_rate_pct=body.annual_rate_pct,
        existing_corpus=body.existing_corpus,
        fv_of_existing_corpus=Decimal(str(round(fv_existing, 2))),
        remaining_corpus_needed=Decimal(str(round(remaining, 2))),
        monthly_sip_required=Decimal(str(round(monthly_sip, 2))),
        with_step_up_pct=body.step_up_pct,
        note=note,
    )


# ===========================================================================
# Tax — Compare regimes
# ===========================================================================

@tax_router.post(
    "/compare",
    response_model=TaxCompareResponse,
    summary="Compare Old vs New tax regime for FY 2024-25",
)
async def tax_compare(
    body: TaxCompareRequest,
    _: User = Depends(get_current_user),
) -> TaxCompareResponse:
    common_kwargs = dict(
        gross_annual_income=float(body.gross_annual_income),
        section_80c=float(body.section_80c),
        section_80d_self=float(body.section_80d_self),
        section_80d_parents=float(body.section_80d_parents),
        parents_senior=body.parents_senior,
        self_senior=body.self_senior,
        hra_exemption=float(body.hra_exemption),
        other_deductions_80c_cap=float(body.other_deductions_80c_cap),
        home_loan_interest=float(body.home_loan_interest),
        basic_salary=float(body.basic_salary),
        actual_hra_received=float(body.actual_hra_received),
        actual_rent_paid=float(body.actual_rent_paid),
        metro_city=body.metro_city,
    )

    old_raw = _unwrap(india_tax_calculator(**common_kwargs, new_regime=False))
    new_raw = _unwrap(india_tax_calculator(**common_kwargs, new_regime=True))

    def _to_detail(d: dict, regime: str) -> TaxRegimeDetail:
        return TaxRegimeDetail(
            regime=regime,
            taxable_income=Decimal(str(d["taxable_income"])),
            total_tax_payable=Decimal(str(d["total_tax_payable"])),
            effective_tax_rate_pct=Decimal(str(d["effective_tax_rate_pct"])),
            monthly_in_hand_approx=Decimal(str(d["monthly_in_hand_approx"])),
            deductions=d.get("deductions", {}),
            tax_breakdown=d["tax_breakdown"],
        )

    old_detail = _to_detail(old_raw, "old")
    new_detail = _to_detail(new_raw, "new")

    # Recommend regime with lower total tax
    if old_detail.total_tax_payable <= new_detail.total_tax_payable:
        recommended = "old"
        saving = new_detail.total_tax_payable - old_detail.total_tax_payable
    else:
        recommended = "new"
        saving = old_detail.total_tax_payable - new_detail.total_tax_payable

    return TaxCompareResponse(
        gross_annual_income=body.gross_annual_income,
        old_regime=old_detail,
        new_regime=new_detail,
        recommended_regime=recommended,
        tax_saving_with_recommended=saving,
    )