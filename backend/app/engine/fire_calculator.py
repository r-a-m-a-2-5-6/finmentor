"""
fire_calculator.py
==================
FIRE (Financial Independence, Retire Early) corpus computation
for the Gaara AI Finance Engine.

Author : Gaara Platform – Financial Engine v1.0
Python : 3.9+
"""

from __future__ import annotations

from app.engine.utils import _round2, _success, _error


# ---------------------------------------------------------------------------
# 2. FIRE Corpus Calculator (with Inflation)
# ---------------------------------------------------------------------------

def fire_corpus_calculator(
    current_monthly_expense: float,
    current_age: int,
    target_retirement_age: int,
    life_expectancy: int = 85,
    inflation_rate_pct: float = 6.0,
    post_retirement_return_pct: float = 7.0,
    current_savings: float = 0.0,
    monthly_savings: float = 0.0,
    pre_retirement_return_pct: float = 12.0,
) -> dict:
    """
    Calculate the corpus needed for Financial Independence, Retire Early (FIRE).

    Step 1 – Inflation-adjusted expense at retirement:
        Expense_retirement = Expense_now × (1 + inflation)^years_to_retire

    Step 2 – Corpus using Present Value of Annuity (inflation-adjusted):
        Real return r_real = (1 + return) / (1 + inflation) - 1
        Corpus = Expense_annual × [1 - (1 + r_real)^(-n)] / r_real
        where n = post-retirement years = life_expectancy - retirement_age

    Step 3 – FV of existing savings & monthly SIP at retirement.

    Step 4 – Additional corpus needed = Corpus_required - Corpus_accumulated.

    Parameters
    ----------
    current_monthly_expense : float  Monthly expenses today in INR.
    current_age              : int   Current age in years.
    target_retirement_age    : int   Desired retirement age.
    life_expectancy          : int   Assumed lifespan (default 85).
    inflation_rate_pct       : float Annual inflation % (default 6).
    post_retirement_return_pct: float Return on retirement corpus % (default 7).
    current_savings          : float Existing invested savings in INR.
    monthly_savings          : float Monthly investment towards FIRE goal.
    pre_retirement_return_pct: float Expected pre-retirement return % (default 12).
    """
    # ── Edge-case guards ──────────────────────────────────────────────────
    if current_monthly_expense <= 0:
        return _error("INVALID_EXPENSE", "current_monthly_expense must be > 0.")
    if not (18 <= current_age <= 80):
        return _error("INVALID_AGE", "current_age must be between 18 and 80.")
    if target_retirement_age <= current_age:
        return _error("INVALID_RETIREMENT_AGE",
                      "target_retirement_age must be > current_age.")
    if life_expectancy <= target_retirement_age:
        return _error("INVALID_LIFE_EXPECTANCY",
                      "life_expectancy must be > target_retirement_age.")
    if inflation_rate_pct < 0 or inflation_rate_pct > 20:
        return _error("INVALID_INFLATION",
                      "inflation_rate_pct must be between 0 and 20.")
    if current_savings < 0:
        return _error("INVALID_SAVINGS", "current_savings must be >= 0.")

    years_to_retire = target_retirement_age - current_age
    post_retirement_years = life_expectancy - target_retirement_age

    inf = inflation_rate_pct / 100
    r_post = post_retirement_return_pct / 100
    r_pre = pre_retirement_return_pct / 100

    # Step 1 – Inflation-adjusted annual expense at retirement
    monthly_expense_at_retirement = current_monthly_expense * (1 + inf) ** years_to_retire
    annual_expense_at_retirement = monthly_expense_at_retirement * 12

    # Step 2 – Corpus via real-return annuity
    r_real = (1 + r_post) / (1 + inf) - 1
    if abs(r_real) < 1e-9:
        # Edge: real return ~ 0 → simple sum
        corpus_required = annual_expense_at_retirement * post_retirement_years
    else:
        corpus_required = annual_expense_at_retirement * (
            1 - (1 + r_real) ** (-post_retirement_years)
        ) / r_real

    # Step 3 – Corpus accumulated via existing savings + monthly SIP
    fv_current_savings = current_savings * (1 + r_pre) ** years_to_retire

    monthly_rate_pre = r_pre / 12
    n_months = years_to_retire * 12
    if monthly_rate_pre == 0:
        fv_monthly_sip = monthly_savings * n_months
    else:
        fv_monthly_sip = monthly_savings * (
            ((1 + monthly_rate_pre) ** n_months - 1) / monthly_rate_pre
        ) * (1 + monthly_rate_pre)

    total_corpus_accumulated = fv_current_savings + fv_monthly_sip
    corpus_gap = max(0.0, corpus_required - total_corpus_accumulated)

    # Monthly SIP required to fill the gap
    if corpus_gap > 0 and monthly_rate_pre > 0 and n_months > 0:
        monthly_sip_needed = corpus_gap / (
            ((1 + monthly_rate_pre) ** n_months - 1) / monthly_rate_pre
            * (1 + monthly_rate_pre)
        )
    else:
        monthly_sip_needed = 0.0

    # 4% withdrawal rule cross-check
    four_pct_corpus = annual_expense_at_retirement * 25

    return _success({
        "inputs": {
            "current_monthly_expense": current_monthly_expense,
            "current_age": current_age,
            "target_retirement_age": target_retirement_age,
            "life_expectancy": life_expectancy,
            "inflation_rate_pct": inflation_rate_pct,
            "post_retirement_return_pct": post_retirement_return_pct,
        },
        "years_to_retire": years_to_retire,
        "post_retirement_years": post_retirement_years,
        "monthly_expense_at_retirement": _round2(monthly_expense_at_retirement),
        "annual_expense_at_retirement": _round2(annual_expense_at_retirement),
        "corpus_required": _round2(corpus_required),
        "corpus_required_4pct_rule": _round2(four_pct_corpus),
        "corpus_accumulated": {
            "from_existing_savings": _round2(fv_current_savings),
            "from_monthly_sip": _round2(fv_monthly_sip),
            "total": _round2(total_corpus_accumulated),
        },
        "corpus_gap": _round2(corpus_gap),
        "monthly_sip_needed_to_close_gap": _round2(monthly_sip_needed),
        "fire_achievable_with_current_plan": corpus_gap == 0,
    })