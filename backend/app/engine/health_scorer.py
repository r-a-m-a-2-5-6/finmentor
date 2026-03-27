"""
health_scorer.py
================
Financial health scoring utilities — Emergency Fund computation
for the Gaara AI Finance Engine.

Author : Gaara Platform – Financial Engine v1.0
Python : 3.9+
"""

from __future__ import annotations

import math

from app.engine.utils import _round2, _success, _error


# ---------------------------------------------------------------------------
# 3. Emergency Fund Calculator
# ---------------------------------------------------------------------------

def emergency_fund_calculator(
    monthly_essential_expenses: float,
    monthly_income: float,
    job_stability: str = "stable",
    dependents: int = 0,
    existing_emergency_fund: float = 0.0,
    existing_liquid_investments: float = 0.0,
    monthly_emi: float = 0.0,
    monthly_insurance_premium: float = 0.0,
) -> dict:
    """
    Calculate the recommended emergency fund size.

    Base rule (Gaara framework):
        - Stable job (govt/PSU): 3 months of essential expenses
        - Semi-stable (private, >2 yrs): 6 months
        - Unstable (freelance/startup/<1 yr): 9 months
        - Self-employed / business: 12 months

    Additions:
        + 1 month per dependent (capped at 3)
        + EMI and insurance premiums included in monthly essential.

    Monthly Essential = monthly_essential_expenses + monthly_emi
                      + monthly_insurance_premium

    Returns shortfall / surplus and recommended allocation instruments.
    """
    STABILITY_MONTHS = {
        "stable":        3,
        "semi_stable":   6,
        "unstable":      9,
        "self_employed": 12,
    }

    # ── Edge-case guards ──────────────────────────────────────────────────
    if monthly_essential_expenses < 0:
        return _error("INVALID_EXPENSES",
                      "monthly_essential_expenses must be >= 0.")
    if monthly_income < 0:
        return _error("INVALID_INCOME", "monthly_income must be >= 0.")
    if monthly_income == 0 and monthly_essential_expenses == 0:
        return _error("ZERO_INCOME_EXPENSES",
                      "Both income and expenses cannot be zero.")
    if job_stability not in STABILITY_MONTHS:
        return _error(
            "INVALID_STABILITY",
            f"job_stability must be one of {list(STABILITY_MONTHS.keys())}."
        )
    if dependents < 0:
        return _error("INVALID_DEPENDENTS", "dependents must be >= 0.")
    if existing_emergency_fund < 0 or existing_liquid_investments < 0:
        return _error("INVALID_EXISTING", "Existing fund values must be >= 0.")

    base_months = STABILITY_MONTHS[job_stability]
    dependent_months = min(dependents, 3)   # cap at 3 extra months
    total_months = base_months + dependent_months

    total_monthly_essential = (
        monthly_essential_expenses + monthly_emi + monthly_insurance_premium
    )

    target_fund = total_monthly_essential * total_months

    # Liquid assets available
    total_liquid = existing_emergency_fund + existing_liquid_investments
    shortfall = max(0.0, target_fund - total_liquid)
    surplus = max(0.0, total_liquid - target_fund)

    # Months of coverage currently available
    months_covered = (
        total_liquid / total_monthly_essential
        if total_monthly_essential > 0
        else 0
    )

    # Savings rate (for health check)
    savings_rate_pct = (
        (monthly_income - total_monthly_essential) / monthly_income * 100
        if monthly_income > 0 else 0
    )

    # Recommended build-up timeline (assuming 20% of monthly income)
    monthly_savings_for_ef = monthly_income * 0.20 if monthly_income > 0 else 0
    months_to_build = (
        math.ceil(shortfall / monthly_savings_for_ef)
        if monthly_savings_for_ef > 0 and shortfall > 0
        else 0
    )

    # Recommended instruments
    instruments = []
    if target_fund > 0:
        instruments = [
            {"instrument": "Savings Account / Sweep FD",
             "allocation_pct": 30,
             "rationale": "Instant liquidity for immediate needs"},
            {"instrument": "Liquid Mutual Fund",
             "allocation_pct": 50,
             "rationale": "T+1 redemption, better returns than savings"},
            {"instrument": "Short-term FD (3–6 month)",
             "allocation_pct": 20,
             "rationale": "Slightly higher yield with reasonable liquidity"},
        ]

    return _success({
        "inputs": {
            "monthly_essential_expenses": monthly_essential_expenses,
            "monthly_emi": monthly_emi,
            "monthly_insurance_premium": monthly_insurance_premium,
            "monthly_income": monthly_income,
            "job_stability": job_stability,
            "dependents": dependents,
        },
        "total_monthly_essential": _round2(total_monthly_essential),
        "recommended_months_cover": total_months,
        "target_emergency_fund": _round2(target_fund),
        "current_liquid_assets": _round2(total_liquid),
        "shortfall": _round2(shortfall),
        "surplus": _round2(surplus),
        "months_currently_covered": _round2(months_covered),
        "savings_rate_pct": _round2(savings_rate_pct),
        "months_to_build_at_20pct_savings": months_to_build,
        "status": (
            "ADEQUATE" if shortfall == 0
            else "BELOW_TARGET"
        ),
        "recommended_instruments": instruments,
    })