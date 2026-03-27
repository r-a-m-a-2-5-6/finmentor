"""
api/routes/portfolio.py
=======================
Portfolio CRUD + X-Ray + Health Score endpoints.

  POST   /portfolios                — create portfolio
  GET    /portfolios                — list user's portfolios
  GET    /portfolios/{id}           — get single portfolio
  DELETE /portfolios/{id}           — delete portfolio
  POST   /portfolios/{id}/holdings  — add holding
  POST   /portfolios/{id}/cashflows — add cash flow
  POST   /portfolio/xray            — XIRR + allocation drift
  GET    /portfolio/health-score    — 6-dimension score

Author : FinMentor Platform
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_db
from app.engine.portfolio_xray import xirr_calculator
from app.engine.health_scorer import emergency_fund_calculator
from app.models.portfolio import CashFlowEntry, Portfolio, PortfolioHolding
from app.models.user import FinancialProfile, User
from app.schemas.finance import (
    AllocationDrift, HealthDimension, HealthScoreResponse,
    PortfolioXRayRequest, PortfolioXRayResponse,
)
from app.schemas.portfolio import (
    AddCashFlowRequest, AddHoldingRequest,
    CashFlowResponse, CreatePortfolioRequest,
    HoldingResponse, PortfolioResponse,
)
from app.utils.auth import get_current_user

router = APIRouter(tags=["Portfolio"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_portfolio_or_404(
    portfolio_id: uuid.UUID,
    user: User,
    db: AsyncSession,
) -> Portfolio:
    result = await db.execute(
        select(Portfolio)
        .where(Portfolio.id == portfolio_id, Portfolio.user_id == user.id)
        .options(
            selectinload(Portfolio.holdings),
            selectinload(Portfolio.cash_flows),
        )
    )
    portfolio = result.scalar_one_or_none()
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found.")
    return portfolio


# ===========================================================================
# Portfolio CRUD
# ===========================================================================

@router.post(
    "/portfolios",
    response_model=PortfolioResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new goal-based portfolio",
)
async def create_portfolio(
    body: CreatePortfolioRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PortfolioResponse:
    portfolio = Portfolio(
        user_id=current_user.id,
        name=body.name,
        description=body.description,
    )
    db.add(portfolio)
    await db.commit()
    await db.refresh(portfolio)
    return PortfolioResponse(
        id=portfolio.id, user_id=portfolio.user_id,
        name=portfolio.name, description=portfolio.description,
        current_value=portfolio.current_value,
        invested_value=portfolio.invested_value,
        xirr_pct=portfolio.xirr_pct, health_score=portfolio.health_score,
    )


@router.get(
    "/portfolios",
    response_model=list[PortfolioResponse],
    summary="List all portfolios for the current user",
)
async def list_portfolios(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[PortfolioResponse]:
    result = await db.execute(
        select(Portfolio)
        .where(Portfolio.user_id == current_user.id)
        .options(
            selectinload(Portfolio.holdings),
            selectinload(Portfolio.cash_flows),
        )
        .order_by(Portfolio.created_at.desc())
    )
    portfolios = result.scalars().all()
    return [
        PortfolioResponse(
            id=p.id, user_id=p.user_id, name=p.name, description=p.description,
            current_value=p.current_value, invested_value=p.invested_value,
            xirr_pct=p.xirr_pct, health_score=p.health_score,
            holding_count=len(p.holdings), cash_flow_count=len(p.cash_flows),
        )
        for p in portfolios
    ]


@router.get(
    "/portfolios/{portfolio_id}",
    response_model=PortfolioResponse,
    summary="Get a single portfolio by ID",
)
async def get_portfolio(
    portfolio_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PortfolioResponse:
    p = await _get_portfolio_or_404(portfolio_id, current_user, db)
    return PortfolioResponse(
        id=p.id, user_id=p.user_id, name=p.name, description=p.description,
        current_value=p.current_value, invested_value=p.invested_value,
        xirr_pct=p.xirr_pct, health_score=p.health_score,
        holding_count=len(p.holdings), cash_flow_count=len(p.cash_flows),
    )


@router.delete(
    "/portfolios/{portfolio_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a portfolio and all its data",
)
async def delete_portfolio(
    portfolio_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    p = await _get_portfolio_or_404(portfolio_id, current_user, db)
    await db.delete(p)
    await db.commit()


# ===========================================================================
# Holdings
# ===========================================================================

@router.post(
    "/portfolios/{portfolio_id}/holdings",
    response_model=HoldingResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a holding to a portfolio",
)
async def add_holding(
    portfolio_id: uuid.UUID,
    body: AddHoldingRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> HoldingResponse:
    portfolio = await _get_portfolio_or_404(portfolio_id, current_user, db)

    invested_amount = body.units * body.purchase_nav
    current_value = (
        body.units * body.current_nav if body.current_nav else None
    )

    holding = PortfolioHolding(
        portfolio_id=portfolio.id,
        instrument_name=body.instrument_name,
        isin=body.isin,
        asset_class=body.asset_class,
        folio_number=body.folio_number,
        units=body.units,
        purchase_nav=body.purchase_nav,
        current_nav=body.current_nav,
        purchase_date=body.purchase_date,
        invested_amount=invested_amount,
        current_value=current_value,
    )
    db.add(holding)

    # Update portfolio aggregate
    portfolio.invested_value = Decimal(str(portfolio.invested_value)) + invested_amount
    if current_value:
        portfolio.current_value = (
            Decimal(str(portfolio.current_value)) + current_value
        )

    await db.commit()
    await db.refresh(holding)

    unrealised = (
        Decimal(str(current_value)) - invested_amount
        if current_value else None
    )
    return HoldingResponse(
        id=holding.id, portfolio_id=holding.portfolio_id,
        instrument_name=holding.instrument_name, isin=holding.isin,
        asset_class=holding.asset_class, units=holding.units,
        purchase_nav=holding.purchase_nav, current_nav=holding.current_nav,
        purchase_date=holding.purchase_date,
        invested_amount=holding.invested_amount,
        current_value=holding.current_value,
        allocation_pct=holding.allocation_pct,
        unrealised_gain=unrealised,
    )


# ===========================================================================
# Cash Flows
# ===========================================================================

@router.post(
    "/portfolios/{portfolio_id}/cashflows",
    response_model=CashFlowResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record a cash flow transaction for XIRR",
)
async def add_cash_flow(
    portfolio_id: uuid.UUID,
    body: AddCashFlowRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CashFlowEntry:
    portfolio = await _get_portfolio_or_404(portfolio_id, current_user, db)

    entry = CashFlowEntry(
        portfolio_id=portfolio.id,
        transaction_date=body.transaction_date,
        amount=body.amount,
        flow_type=body.flow_type,
        instrument_name=body.instrument_name,
        notes=body.notes,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return entry


# ===========================================================================
# Portfolio X-Ray  (XIRR + drift)
# ===========================================================================

@router.post(
    "/portfolio/xray",
    response_model=PortfolioXRayResponse,
    summary="Compute XIRR and allocation drift for a portfolio",
)
async def portfolio_xray(
    body: PortfolioXRayRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PortfolioXRayResponse:
    # Resolve cash flows
    if body.portfolio_id:
        pid = uuid.UUID(body.portfolio_id)
        portfolio = await _get_portfolio_or_404(pid, current_user, db)
        cash_flows = [float(cf.amount) for cf in portfolio.cash_flows]
        dates = [cf.transaction_date.isoformat() for cf in portfolio.cash_flows]
        holdings = portfolio.holdings
    else:
        if len(body.cash_flows) < 2:
            raise HTTPException(
                status_code=422,
                detail="Provide at least 2 cash flow entries.",
            )
        cash_flows = [cf.amount for cf in body.cash_flows]
        dates = [cf.date for cf in body.cash_flows]
        holdings = []

    # XIRR
    xirr_result = xirr_calculator(cash_flows, dates)
    xirr_data = xirr_result.get("data") if xirr_result["status"] == "success" else None

    # Allocation drift
    drift: list[AllocationDrift] = []
    health_flags: list[str] = []

    if holdings and body.target_allocation:
        total_val = sum(
            float(h.current_value or h.invested_amount) for h in holdings
        )
        if total_val > 0:
            actual: dict[str, float] = {}
            for h in holdings:
                ac = h.asset_class
                val = float(h.current_value or h.invested_amount)
                actual[ac] = actual.get(ac, 0) + (val / total_val * 100)

            for asset_class, target_pct in body.target_allocation.items():
                actual_pct = actual.get(asset_class, 0.0)
                d = actual_pct - target_pct
                action = "hold" if abs(d) < 2 else ("sell" if d > 0 else "buy")
                drift.append(AllocationDrift(
                    asset_class=asset_class,
                    target_pct=target_pct,
                    actual_pct=round(actual_pct, 2),
                    drift_pct=round(d, 2),
                    action=action,
                ))
                if abs(d) > 5:
                    direction = "over-weight" if d > 0 else "under-weight"
                    health_flags.append(
                        f"{asset_class.title()} is {direction} by {abs(d):.1f}%"
                    )

    total_invested = abs(sum(cf for cf in cash_flows if cf < 0))
    total_returned = sum(cf for cf in cash_flows if cf > 0)

    return PortfolioXRayResponse(
        xirr_pct=xirr_data["xirr_pct"] if xirr_data else None,
        total_invested=total_invested,
        total_current_value=total_returned,
        absolute_gain=total_returned - total_invested,
        absolute_return_pct=(
            (total_returned - total_invested) / total_invested * 100
            if total_invested > 0 else 0.0
        ),
        duration_years=xirr_data["duration_years"] if xirr_data else 0.0,
        allocation_drift=drift,
        health_flags=health_flags,
    )


# ===========================================================================
# Health Score
# ===========================================================================

@router.get(
    "/portfolio/health-score",
    response_model=HealthScoreResponse,
    summary="Get a 6-dimension financial health score",
)
async def health_score(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> HealthScoreResponse:
    # Fetch financial profile
    result = await db.execute(
        select(FinancialProfile).where(
            FinancialProfile.user_id == current_user.id
        )
    )
    profile = result.scalar_one_or_none()

    if not profile:
        raise HTTPException(
            status_code=404,
            detail="Complete your financial profile first (PATCH /auth/profile).",
        )

    income = float(profile.monthly_income or 0)
    expenses = float(profile.monthly_expenses or 0)
    emi = float(profile.monthly_emi or 0)
    insurance = float(profile.monthly_insurance_premium or 0)
    corpus = float(profile.current_corpus or 0)
    ef = float(profile.existing_emergency_fund or 0)

    # ── Dimension 1: Emergency Fund ─────────────────────────────────────
    ef_result = emergency_fund_calculator(
        monthly_essential_expenses=expenses,
        monthly_income=income,
        job_stability=profile.job_stability,
        dependents=profile.dependents,
        existing_emergency_fund=ef,
        monthly_emi=emi,
        monthly_insurance_premium=insurance,
    )
    ef_data = ef_result.get("data", {})
    ef_coverage = float(ef_data.get("months_currently_covered", 0))
    ef_score = min(10.0, ef_coverage / float(ef_data.get("recommended_months_cover", 6)) * 10)
    ef_insight = (
        "Emergency fund is fully funded."
        if ef_data.get("status") == "ADEQUATE"
        else f"Shortfall of ₹{ef_data.get('shortfall', 0):,.0f}. "
             f"Currently covers {ef_coverage:.1f} months."
    )

    # ── Dimension 2: Savings Rate ────────────────────────────────────────
    savings_rate = float(ef_data.get("savings_rate_pct", 0))
    sr_score = min(10.0, savings_rate / 30 * 10)   # 30% = perfect score
    sr_insight = (
        f"Savings rate is {savings_rate:.1f}%. "
        + ("Excellent — above 20%." if savings_rate >= 20 else "Aim for 20%+.")
    )

    # ── Dimension 3: Debt Load (EMI/Income ratio) ─────────────────────
    emi_ratio = (emi / income * 100) if income > 0 else 0
    debt_score = max(0.0, 10.0 - emi_ratio / 5)   # 50% ratio = 0 score
    debt_insight = (
        f"EMI-to-income ratio is {emi_ratio:.1f}%. "
        + ("Healthy — below 30%." if emi_ratio < 30 else "High — consider prepaying loans.")
    )

    # ── Dimension 4: Investment Consistency (profile completeness proxy) ─
    has_corpus = corpus > 0
    has_profile = profile.target_retirement_age is not None
    inv_score = 7.0 if (has_corpus and has_profile) else (5.0 if has_corpus else 2.0)
    inv_insight = (
        "Corpus and retirement goal set — investment consistency looks good."
        if (has_corpus and has_profile)
        else "Set a retirement target and start building corpus."
    )

    # ── Dimension 5: Insurance Coverage ──────────────────────────────────
    ins_score = 8.0 if insurance > 0 else 3.0
    ins_insight = (
        f"Insurance premium of ₹{insurance:,.0f}/month recorded."
        if insurance > 0
        else "No insurance premium found. Consider life + health coverage."
    )

    # ── Dimension 6: Retirement Readiness ───────────────────────────────
    rr_score = 5.0
    rr_insight = "Set a FIRE target via /fire/calculate for a detailed readiness score."
    if profile.current_age and profile.target_retirement_age:
        years_left = profile.target_retirement_age - profile.current_age
        if years_left <= 0:
            rr_score = 10.0
            rr_insight = "Already at or past retirement age."
        elif corpus > 0:
            # Simple heuristic: corpus / (annual_expense * 25) * 10
            annual_exp = expenses * 12
            if annual_exp > 0:
                readiness = corpus / (annual_exp * 25)
                rr_score = min(10.0, readiness * 10)
            rr_insight = f"Corpus covers {rr_score*10:.0f}% of 25x annual expense target."

    # ── Aggregate ────────────────────────────────────────────────────────
    weights = [0.20, 0.20, 0.15, 0.20, 0.10, 0.15]
    raw_scores = [ef_score, sr_score, debt_score, inv_score, ins_score, rr_score]
    names = [
        "Emergency Fund", "Savings Rate", "Debt Load",
        "Investment Consistency", "Insurance Coverage", "Retirement Readiness",
    ]
    insights = [ef_insight, sr_insight, debt_insight, inv_insight, ins_insight, rr_insight]

    overall = sum(s * w for s, w in zip(raw_scores, weights)) * 10  # out of 100

    grade_map = [(90, "A+"), (80, "A"), (65, "B"), (50, "C"), (35, "D")]
    grade = next((g for threshold, g in grade_map if overall >= threshold), "F")

    dimensions = [
        HealthDimension(
            name=n, score=round(s, 1), weight=w,
            weighted_score=round(s * w * 10, 1), insight=i,
        )
        for n, s, w, i in zip(names, raw_scores, weights, insights)
    ]

    # Top action = lowest weighted score dimension
    worst = min(dimensions, key=lambda d: d.weighted_score)
    top_action = f"Priority: Improve your {worst.name} — {worst.insight}"

    return HealthScoreResponse(
        overall_score=round(overall, 1),
        grade=grade,
        dimensions=dimensions,
        top_action=top_action,
        summary=(
            f"Your overall financial health score is {overall:.0f}/100 (Grade {grade}). "
            f"Strongest area: {max(dimensions, key=lambda d: d.weighted_score).name}."
        ),
    )