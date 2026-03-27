"""
sip_engine.py
=============
SIP (Systematic Investment Plan) future value computation
for the Gaara AI Finance Engine.

Author : Gaara Platform – Financial Engine v1.0
Python : 3.9+
"""

from __future__ import annotations

from app.engine.utils import _round2, _success, _error


# ---------------------------------------------------------------------------
# 1. SIP Future Value Calculator
# ---------------------------------------------------------------------------

def sip_future_value(
    monthly_investment: float,
    annual_rate_pct: float,
    years: int,
    step_up_pct: float = 0.0,
) -> dict:
    """
    Calculate the future value of a Systematic Investment Plan (SIP).

    Formula (flat SIP):
        FV = P × [((1 + r)^n - 1) / r] × (1 + r)
        where:
            P = monthly investment
            r = monthly rate = annual_rate / 12
            n = total months = years × 12

    Step-up SIP (annual increment):
        Each year the monthly investment increases by `step_up_pct`%.
        FV is the sum of FV of each year's annuity.

    Parameters
    ----------
    monthly_investment : float
        Monthly SIP amount in INR (must be > 0).
    annual_rate_pct : float
        Expected annual return in percent (e.g., 12 for 12%).
    years : int
        Investment horizon in years (1–50).
    step_up_pct : float, optional
        Annual step-up percentage (default 0 = flat SIP).

    Returns
    -------
    dict  JSON with invested_amount, estimated_returns, future_value,
          wealth_gained, absolute_return_pct, cagr_pct, yearly_breakdown.
    """
    # ── Edge-case guards ──────────────────────────────────────────────────
    if monthly_investment <= 0:
        return _error("INVALID_INVESTMENT", "monthly_investment must be > 0.")
    if annual_rate_pct < 0:
        return _error("INVALID_RATE", "annual_rate_pct must be >= 0.")
    if not (1 <= years <= 50):
        return _error("INVALID_YEARS", "years must be between 1 and 50.")
    if step_up_pct < 0:
        return _error("INVALID_STEPUP", "step_up_pct must be >= 0.")

    monthly_rate = annual_rate_pct / 100 / 12
    total_months = years * 12
    yearly_breakdown: list[dict] = []

    total_invested = 0.0
    total_fv = 0.0
    current_monthly = monthly_investment

    for year in range(1, years + 1):
        months_in_year = 12
        invested_this_year = current_monthly * months_in_year
        total_invested += invested_this_year

        # FV of this year's annuity-due contributions growing for remaining period
        months_remaining_after_year = (years - year) * 12

        if monthly_rate == 0:
            fv_this_year = current_monthly * months_in_year
        else:
            # FV of 12-month annuity-due at end of this year
            fv_annuity = current_monthly * (
                ((1 + monthly_rate) ** months_in_year - 1) / monthly_rate
            ) * (1 + monthly_rate)
            # Grow that lump sum for remaining months
            fv_this_year = fv_annuity * (1 + monthly_rate) ** months_remaining_after_year

        total_fv += fv_this_year

        yearly_breakdown.append({
            "year": year,
            "monthly_sip": _round2(current_monthly),
            "invested_cumulative": _round2(total_invested),
            "future_value_cumulative": _round2(total_fv),
        })

        # Apply step-up for next year
        current_monthly *= 1 + step_up_pct / 100

    wealth_gained = total_fv - total_invested
    abs_return_pct = (wealth_gained / total_invested * 100) if total_invested > 0 else 0

    # Approximate CAGR from invested (lump-sum equivalent at midpoint)
    cagr = ((total_fv / total_invested) ** (1 / years) - 1) * 100 if total_invested > 0 else 0

    return _success({
        "inputs": {
            "monthly_investment": monthly_investment,
            "annual_rate_pct": annual_rate_pct,
            "years": years,
            "step_up_pct": step_up_pct,
        },
        "invested_amount": _round2(total_invested),
        "estimated_returns": _round2(wealth_gained),
        "future_value": _round2(total_fv),
        "wealth_gained": _round2(wealth_gained),
        "absolute_return_pct": _round2(abs_return_pct),
        "cagr_pct": _round2(cagr),
        "yearly_breakdown": yearly_breakdown,
    })