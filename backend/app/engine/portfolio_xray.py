"""
portfolio_xray.py
=================
Portfolio analytics — XIRR (Extended Internal Rate of Return) computation
for the Gaara AI Finance Engine.

Deps   : scipy (XIRR fallback only) — install via `pip install scipy`

Author : Gaara Platform – Financial Engine v1.0
Python : 3.9+
"""

from __future__ import annotations

from datetime import datetime

from app.engine.utils import _round2, _success, _error


# ---------------------------------------------------------------------------
# 4. XIRR Calculator
# ---------------------------------------------------------------------------

def xirr_calculator(
    cash_flows: list[float],
    dates: list[str],          # ISO format: "YYYY-MM-DD"
    guess: float = 0.1,
) -> dict:
    """
    Calculate Extended Internal Rate of Return (XIRR) for irregular cash flows.

    XIRR solves for rate r such that:
        Σ [ CF_i / (1 + r)^(d_i / 365) ] = 0
        where d_i = days from first cash flow date to date i.

    Negative cash flows = investments (outflows).
    Positive cash flows = redemptions / returns (inflows).

    Uses Newton-Raphson iteration (no scipy required for common cases),
    with a scipy.optimize.brentq fallback for convergence safety.

    Parameters
    ----------
    cash_flows : list[float]
        List of cash flow amounts. Must include at least one negative
        and one positive value.
    dates : list[str]
        Corresponding dates in "YYYY-MM-DD" format.
    guess : float
        Initial guess for IRR (default 0.10 = 10%).
    """
    # ── Edge-case guards ──────────────────────────────────────────────────
    if len(cash_flows) != len(dates):
        return _error("LENGTH_MISMATCH",
                      "cash_flows and dates must have the same length.")
    if len(cash_flows) < 2:
        return _error("INSUFFICIENT_DATA",
                      "At least 2 cash flow entries required.")
    if not any(cf < 0 for cf in cash_flows):
        return _error("NO_OUTFLOW",
                      "At least one negative cash flow (investment) is required.")
    if not any(cf > 0 for cf in cash_flows):
        return _error("NO_INFLOW",
                      "At least one positive cash flow (return) is required.")

    try:
        parsed_dates = [datetime.strptime(d, "%Y-%m-%d").date() for d in dates]
    except ValueError as exc:
        return _error("INVALID_DATE", f"Date parse error: {exc}")

    base_date = parsed_dates[0]
    day_offsets = [(d - base_date).days for d in parsed_dates]

    def npv(rate: float) -> float:
        if rate == -1.0:
            return float("inf")
        return sum(
            cf / (1 + rate) ** (days / 365.0)
            for cf, days in zip(cash_flows, day_offsets)
        )

    def npv_deriv(rate: float) -> float:
        if rate == -1.0:
            return float("inf")
        return sum(
            -cf * (days / 365.0) / (1 + rate) ** (days / 365.0 + 1)
            for cf, days in zip(cash_flows, day_offsets)
        )

    # Newton-Raphson
    rate = guess
    MAX_ITER = 1000
    TOL = 1e-8
    converged = False

    for _ in range(MAX_ITER):
        f_val = npv(rate)
        f_prime = npv_deriv(rate)
        if abs(f_prime) < 1e-12:
            break
        new_rate = rate - f_val / f_prime
        if abs(new_rate - rate) < TOL:
            rate = new_rate
            converged = True
            break
        rate = new_rate

    # Fallback: scipy brentq
    if not converged:
        try:
            from scipy.optimize import brentq  # type: ignore
            rate = brentq(npv, -0.999, 100.0, xtol=TOL, maxiter=500)
            converged = True
        except Exception:
            return _error("CONVERGENCE_FAILED",
                          "XIRR did not converge. Check cash flow signs.")

    # Sanity check
    if not (-1 < rate < 100):
        return _error("UNREALISTIC_RESULT",
                      f"Computed rate {rate:.4f} is outside realistic bounds.")

    xirr_pct = rate * 100
    total_invested = sum(-cf for cf in cash_flows if cf < 0)
    total_returned = sum(cf for cf in cash_flows if cf > 0)
    absolute_gain = total_returned - total_invested
    duration_years = day_offsets[-1] / 365.0

    return _success({
        "xirr_pct": _round2(xirr_pct),
        "xirr_decimal": round(rate, 6),
        "total_invested": _round2(total_invested),
        "total_returned": _round2(total_returned),
        "absolute_gain": _round2(absolute_gain),
        "absolute_return_pct": _round2(
            absolute_gain / total_invested * 100 if total_invested > 0 else 0
        ),
        "duration_years": _round2(duration_years),
        "num_transactions": len(cash_flows),
        "converged": converged,
    })