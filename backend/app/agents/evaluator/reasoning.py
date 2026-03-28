"""
finmentor — Reasoning Layer
=============================
Performs deterministic financial reasoning *before* the ExplainerAgent
generates advice.  This grounds the advice in verified math rather than
letting the LLM hallucinate plausibility checks.

Three analysis modules
----------------------
  1. Income-vs-Expense  — cash-flow health, savings rate, surplus
  2. Risk Profile Check — compares declared vs inferred risk tolerance
  3. Time Horizon Eval  — feasibility of reaching the primary goal on time

All three feed into a ReasoningReport whose `advisor_notes` list is
injected verbatim into the ExplainerAgent's prompt.  This means the LLM
*sees* the reasoning and cannot contradict it without deliberately ignoring
explicit context — a much safer failure mode than silent hallucination.

Design contract
---------------
  • PURE FUNCTIONS — no LLM calls, no IO, fully unit-testable.
  • No mutation of inputs.
  • All monetary values in INR, all rates as decimals (0.12 = 12%).
"""

from __future__ import annotations

import math
from typing import Optional

from app.agents.shared.types import (
    FinancialPlan,
    FinancialProfile,
    IncomeExpenseAnalysis,
    ReasoningReport,
    RiskProfileCheck,
    TimeHorizonEval,
)

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

# Cash-flow thresholds
HEALTHY_EXPENSE_RATIO  = 0.60   # ≤60% expenses of income = healthy
TIGHT_EXPENSE_RATIO    = 0.75   # 60–75% = tight
DEFICIT_EXPENSE_RATIO  = 1.00   # ≥100% = deficit
HEALTHY_SAVINGS_RATE   = 0.20   # ≥20% savings = healthy

# Risk inference thresholds
AGGRESSIVE_AGE_CEILING = 35
CONSERVATIVE_AGE_FLOOR = 50
COMFORTABLE_SURPLUS    = 30_000   # ₹30k/month surplus = can afford aggression

# FIRE / SIP math assumptions (used for time-horizon projection only)
DEFAULT_PRE_RETIREMENT_RETURN  = 0.12   # 12% p.a. equity-heavy
DEFAULT_POST_RETIREMENT_RETURN = 0.07   # 7% p.a. debt-heavy
DEFAULT_INFLATION               = 0.06   # 6% p.a.
DEFAULT_LIFE_EXPECTANCY         = 85


# ─────────────────────────────────────────────────────────────────────────────
# Module 1 — Income vs Expense Analysis
# ─────────────────────────────────────────────────────────────────────────────

def _analyze_income_expense(profile: FinancialProfile) -> IncomeExpenseAnalysis:
    income   = profile.monthly_income   or 0.0
    expenses = profile.monthly_expenses or 0.0
    savings  = profile.monthly_savings  or 0.0

    surplus = income - expenses

    # Safe division guard
    expense_ratio       = (expenses / income) if income > 0 else 1.0
    actual_savings_rate = (savings  / income) if income > 0 else 0.0
    reported_savings_rate = (surplus / income) if income > 0 else 0.0
    savings_gap = reported_savings_rate - actual_savings_rate

    # Assessment
    if expense_ratio >= DEFICIT_EXPENSE_RATIO:
        assessment = "deficit"
    elif expense_ratio >= TIGHT_EXPENSE_RATIO:
        assessment = "tight"
    else:
        assessment = "healthy"

    flags: list[str] = []

    if assessment == "deficit":
        flags.append(
            "⚠️  Income does not cover expenses. Investment planning is not "
            "appropriate until the deficit is resolved."
        )
    elif assessment == "tight":
        flags.append(
            f"⚠️  Expense ratio is {expense_ratio:.0%}. Only "
            f"₹{surplus:,.0f}/month available. Consider a small emergency SIP first."
        )

    if savings_gap > 0.05:
        flags.append(
            f"📌 Reported savings (₹{savings:,.0f}) are higher than the "
            f"calculated surplus (₹{surplus:,.0f}). Verify expense or savings figures."
        )

    if actual_savings_rate < HEALTHY_SAVINGS_RATE and assessment != "deficit":
        flags.append(
            f"💡 Savings rate is {actual_savings_rate:.0%}, below the recommended "
            f"{HEALTHY_SAVINGS_RATE:.0%}. Aim to increase SIP contributions gradually."
        )

    return IncomeExpenseAnalysis(
        monthly_surplus=round(surplus, 2),
        expense_ratio=round(expense_ratio, 4),
        actual_savings_rate=round(actual_savings_rate, 4),
        reported_savings_rate=round(reported_savings_rate, 4),
        savings_gap=round(savings_gap, 4),
        assessment=assessment,
        flags=flags,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Module 2 — Risk Profile Check
# ─────────────────────────────────────────────────────────────────────────────

def _check_risk_profile(
    profile: FinancialProfile,
    income_analysis: IncomeExpenseAnalysis,
) -> RiskProfileCheck:
    declared = (
        profile.risk_profile.level if profile.risk_profile else "moderate"
    )

    # Infer behavioural risk from demographics + cash-flow
    age     = profile.age or 35
    surplus = income_analysis.monthly_surplus

    if age <= AGGRESSIVE_AGE_CEILING and surplus >= COMFORTABLE_SURPLUS:
        inferred = "aggressive"
    elif age >= CONSERVATIVE_AGE_FLOOR or income_analysis.assessment == "deficit":
        inferred = "conservative"
    else:
        inferred = "moderate"

    mismatch  = declared != inferred
    direction: Optional[str] = None
    flags: list[str] = []

    if mismatch:
        risk_order = {"conservative": 0, "moderate": 1, "aggressive": 2}
        if risk_order.get(declared, 1) > risk_order.get(inferred, 1):
            direction = "over_aggressive"
            flags.append(
                f"⚠️  You described yourself as '{declared}' but your profile "
                f"(age {age}, surplus ₹{surplus:,.0f}) suggests '{inferred}'. "
                "Investment allocations will be adjusted conservatively."
            )
        else:
            direction = "over_conservative"
            flags.append(
                f"💡 You described yourself as '{declared}' but your profile "
                f"(age {age}, surplus ₹{surplus:,.0f}) suggests room for '{inferred}' "
                "allocations. Review whether you're leaving returns on the table."
            )

    return RiskProfileCheck(
        declared_level=declared,
        inferred_level=inferred,
        mismatch_detected=mismatch,
        mismatch_direction=direction,
        flags=flags,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Module 3 — Time Horizon Evaluation
# ─────────────────────────────────────────────────────────────────────────────

def _fv_sip(monthly: float, annual_rate: float, years: int) -> float:
    """Future value of a monthly SIP at a constant annual rate."""
    if annual_rate == 0 or years == 0:
        return monthly * years * 12
    r = annual_rate / 12
    n = years * 12
    return monthly * (((1 + r) ** n - 1) / r) * (1 + r)


def _fv_lumpsum(amount: float, annual_rate: float, years: int) -> float:
    """Future value of a lump-sum amount at a constant annual rate."""
    return amount * ((1 + annual_rate) ** years)


def _retirement_corpus(
    monthly_expense_today: float,
    years_to_retirement: int,
    years_in_retirement: int,
    inflation: float,
    post_return: float,
) -> float:
    """
    Corpus needed at retirement to fund inflation-adjusted expenses for
    `years_in_retirement` years using the present-value-of-annuity formula.
    """
    future_monthly = monthly_expense_today * ((1 + inflation) ** years_to_retirement)
    future_annual  = future_monthly * 12
    real_rate      = (1 + post_return) / (1 + inflation) - 1

    if abs(real_rate) < 1e-9:
        return future_annual * years_in_retirement

    # PV of growing annuity (inflation-adjusted withdrawals)
    corpus = future_annual * (
        (1 - (1 + real_rate) ** -years_in_retirement) / real_rate
    )
    return corpus


def _evaluate_time_horizon(profile: FinancialProfile) -> TimeHorizonEval:
    age             = profile.age or 30
    retirement_age  = profile.target_retirement_age or 60
    years_to_goal   = max(retirement_age - age, 0)

    expenses  = profile.monthly_expenses  or 0.0
    savings   = profile.monthly_savings   or 0.0
    existing  = profile.current_savings   or 0.0

    flags: list[str] = []

    if years_to_goal <= 0:
        return TimeHorizonEval(
            years_to_goal=0,
            feasibility="infeasible",
            flags=["Retirement age is not in the future."],
        )

    # Corpus calculation
    years_in_retirement = DEFAULT_LIFE_EXPECTANCY - retirement_age
    corpus_required = _retirement_corpus(
        monthly_expense_today=expenses,
        years_to_retirement=years_to_goal,
        years_in_retirement=years_in_retirement,
        inflation=DEFAULT_INFLATION,
        post_return=DEFAULT_POST_RETIREMENT_RETURN,
    )

    # Projected corpus from current savings + monthly SIP
    fv_existing = _fv_lumpsum(existing, DEFAULT_PRE_RETIREMENT_RETURN, years_to_goal)
    fv_sip      = _fv_sip(savings,  DEFAULT_PRE_RETIREMENT_RETURN, years_to_goal)
    trajectory  = fv_existing + fv_sip
    shortfall   = max(corpus_required - trajectory, 0.0)

    # SIP needed to close shortfall (reverse engineer)
    required_sip: Optional[float] = None
    if shortfall > 0 and years_to_goal > 0:
        r = DEFAULT_PRE_RETIREMENT_RETURN / 12
        n = years_to_goal * 12
        if r > 0:
            required_sip = shortfall / (((1 + r) ** n - 1) / r * (1 + r))

    # Feasibility decision
    shortfall_ratio = shortfall / corpus_required if corpus_required > 0 else 0
    if shortfall_ratio < 0.10:
        feasibility = "achievable"
    elif shortfall_ratio < 0.35:
        feasibility = "aggressive"
    else:
        feasibility = "infeasible"

    # Flags
    if feasibility == "infeasible":
        flags.append(
            f"🚨 At current savings rate (₹{savings:,.0f}/month), you are on track "
            f"for only ₹{trajectory / 1e7:.1f} Cr against a required "
            f"₹{corpus_required / 1e7:.1f} Cr. "
            f"A monthly SIP of ₹{required_sip:,.0f} is needed to close the gap."
            if required_sip else
            f"🚨 Shortfall is very large relative to current contributions."
        )
    elif feasibility == "aggressive":
        flags.append(
            f"⚠️  Shortfall of ₹{shortfall / 1e5:.1f} lakh. "
            "Consider increasing SIP by 10–15% annually."
        )
    else:
        flags.append(
            f"✅ On track to reach the ₹{corpus_required / 1e7:.1f} Cr corpus "
            f"needed by age {retirement_age}."
        )

    return TimeHorizonEval(
        years_to_goal=years_to_goal,
        corpus_required=round(corpus_required, 2),
        current_trajectory_corpus=round(trajectory, 2),
        shortfall=round(shortfall, 2),
        feasibility=feasibility,
        required_monthly_sip=round(required_sip, 2) if required_sip else None,
        flags=flags,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Orchestrated reasoning — combines all three modules
# ─────────────────────────────────────────────────────────────────────────────

def _build_advisor_notes(
    ie: IncomeExpenseAnalysis,
    rc: RiskProfileCheck,
    th: TimeHorizonEval,
) -> list[str]:
    """Flatten all flags into a prioritised advisor-notes list."""
    notes: list[str] = []
    # Order: income > risk > time-horizon  (most immediate impact first)
    notes.extend(ie.flags)
    notes.extend(rc.flags)
    notes.extend(th.flags)
    return notes


def _overall_feasibility(
    ie: IncomeExpenseAnalysis,
    rc: RiskProfileCheck,
    th: TimeHorizonEval,
) -> str:
    if ie.assessment == "deficit":
        return "blocked"
    if th.feasibility == "infeasible" or rc.mismatch_direction == "over_aggressive":
        return "caution"
    return "proceed"


def run_reasoning(
    profile: FinancialProfile,
    plan: FinancialPlan,
) -> ReasoningReport:
    """
    Run the full three-module reasoning pass.

    Parameters
    ----------
    profile : FinancialProfile (possibly auto-corrected by the validator).
    plan    : FinancialPlan from PlannerAgent (used for context, not mutated).

    Returns
    -------
    ReasoningReport — injected into ExplainerAgent prompt as grounding context.
    """
    ie = _analyze_income_expense(profile)
    rc = _check_risk_profile(profile, ie)
    th = _evaluate_time_horizon(profile)

    return ReasoningReport(
        income_expense=ie,
        risk_check=rc,
        time_horizon=th,
        overall_feasibility=_overall_feasibility(ie, rc, th),
        advisor_notes=_build_advisor_notes(ie, rc, th),
    )