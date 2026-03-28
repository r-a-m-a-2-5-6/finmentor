"""
finmentor — Input Validator
=============================
Checks the FinancialProfile produced by the PlannerAgent for:
  • Impossible values   (e.g. negative income, age > 120)
  • Unrealistic ratios  (e.g. SIP > disposable income, savings > income)
  • Internal contradictions (e.g. existing_emergency_fund > current_savings,
                              age >= target_retirement_age)
  • Regulatory breaches  (e.g. 80C investment > ₹1.5 L statutory cap)

Severity contract
-----------------
  "error"   → blocked=True, execution halts, user is asked to correct
  "warning"  → blocked=False, execution continues, issue surfaced in output
  "info"    → purely informational nudge, never blocks

Design notes
------------
  • All thresholds are named constants at the top of this file — easy to tune.
  • Each rule is a standalone private function (_check_*) returning
    0-or-more ValidationIssue objects.  Add new rules by adding functions
    and registering them in RULES at the bottom.
  • Auto-correction (e.g. capping 80C) is applied to a *copy* of the
    profile — the original is never mutated.
"""

from __future__ import annotations

import copy
from collections.abc import Callable

from app.agents.shared.types import (
    FinancialPlan,
    FinancialProfile,
    ValidationIssue,
    ValidationResult,
)

# ─────────────────────────────────────────────────────────────────────────────
# Thresholds (all monetary values in INR)
# ─────────────────────────────────────────────────────────────────────────────

MAX_80C                  = 150_000.0   # Section 80C statutory cap
MAX_80D_SELF             = 25_000.0    # Section 80D self + family cap
MAX_80D_PARENTS          = 25_000.0    # Section 80D parents cap (50k if senior)
MAX_HOME_LOAN_INTEREST   = 200_000.0   # Section 24(b) cap
MAX_AGE                  = 100
MIN_AGE                  = 1
MAX_RETIREMENT_AGE       = 75
MIN_RETIREMENT_GAP_YRS   = 1           # must retire at least 1 year from now

# Expense ratio thresholds
EXPENSE_RATIO_TIGHT      = 0.75        # expenses > 75% of income → warning
EXPENSE_RATIO_DEFICIT    = 1.00        # expenses >= 100% of income → error

# SIP / savings realism
MAX_SAVINGS_RATE         = 0.85        # savings > 85% of income is unrealistic
SAVINGS_VS_SURPLUS_SLACK = 1.05        # reported savings may exceed surplus by 5%

# ─────────────────────────────────────────────────────────────────────────────
# Individual rule functions
# Each accepts (profile, plan) and returns list[ValidationIssue]
# ─────────────────────────────────────────────────────────────────────────────

def _check_negative_values(
    profile: FinancialProfile, _plan: FinancialPlan
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    numeric_fields = {
        "monthly_income": profile.monthly_income,
        "monthly_expenses": profile.monthly_expenses,
        "monthly_savings": profile.monthly_savings,
        "current_savings": profile.current_savings,
        "existing_emergency_fund": profile.existing_emergency_fund,
        "section_80c_investments": profile.section_80c_investments,
        "health_insurance_premium": profile.health_insurance_premium,
        "home_loan_interest_annual": profile.home_loan_interest_annual,
    }
    for field, value in numeric_fields.items():
        if value is not None and value < 0:
            issues.append(ValidationIssue(
                field=field,
                severity="error",
                code="NEGATIVE_VALUE",
                message=f"{field} cannot be negative (got ₹{value:,.0f}).",
                suggestion=f"Please provide a non-negative value for {field}.",
            ))
    return issues


def _check_zero_income_with_sip(
    profile: FinancialProfile, plan: FinancialPlan
) -> list[ValidationIssue]:
    """₹0 income but a SIP task exists → impossible."""
    issues: list[ValidationIssue] = []
    if (profile.monthly_income or 0) == 0:
        has_sip = any(t.tool == "sip_calculator" for t in plan.tasks)
        if has_sip:
            issues.append(ValidationIssue(
                field="monthly_income",
                severity="error",
                code="SIP_WITH_ZERO_INCOME",
                message="A SIP investment was requested but monthly income is ₹0.",
                suggestion=(
                    "Please provide your actual monthly income so we can "
                    "recommend a realistic SIP amount."
                ),
            ))
    return issues


def _check_expenses_vs_income(
    profile: FinancialProfile, _plan: FinancialPlan
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    income   = profile.monthly_income   or 0
    expenses = profile.monthly_expenses or 0

    if income <= 0:
        return issues   # already caught by negative-values rule

    ratio = expenses / income
    if ratio >= EXPENSE_RATIO_DEFICIT:
        issues.append(ValidationIssue(
            field="monthly_expenses",
            severity="error",
            code="EXPENSES_EXCEED_INCOME",
            message=(
                f"Monthly expenses (₹{expenses:,.0f}) meet or exceed "
                f"income (₹{income:,.0f}). There is no surplus to invest or save."
            ),
            suggestion=(
                "Review your expense figures. If accurate, we will focus on "
                "budgeting advice rather than investment planning."
            ),
        ))
    elif ratio >= EXPENSE_RATIO_TIGHT:
        issues.append(ValidationIssue(
            field="monthly_expenses",
            severity="warning",
            code="HIGH_EXPENSE_RATIO",
            message=(
                f"Expenses are {ratio:.0%} of income, leaving very little "
                f"surplus (₹{income - expenses:,.0f}/month)."
            ),
            suggestion=(
                "Consider whether any discretionary spending can be reduced "
                "before committing to a SIP."
            ),
        ))
    return issues


def _check_savings_vs_income(
    profile: FinancialProfile, _plan: FinancialPlan
) -> list[ValidationIssue]:
    """Reported monthly savings > MAX_SAVINGS_RATE × income is unrealistic."""
    issues: list[ValidationIssue] = []
    income  = profile.monthly_income  or 0
    savings = profile.monthly_savings or 0

    if income <= 0 or savings <= 0:
        return issues

    if savings / income > MAX_SAVINGS_RATE:
        issues.append(ValidationIssue(
            field="monthly_savings",
            severity="warning",
            code="SAVINGS_RATE_UNREALISTIC",
            message=(
                f"Reported savings (₹{savings:,.0f}) is "
                f"{savings / income:.0%} of income — unusually high."
            ),
            suggestion=(
                "Please double-check the figure. "
                "If correct, we will use it as-is but flag the high savings rate."
            ),
        ))
    return issues


def _check_savings_vs_surplus(
    profile: FinancialProfile, _plan: FinancialPlan
) -> list[ValidationIssue]:
    """Reported savings significantly exceed (income − expenses)."""
    issues: list[ValidationIssue] = []
    income   = profile.monthly_income   or 0
    expenses = profile.monthly_expenses or 0
    savings  = profile.monthly_savings  or 0

    if income <= 0 or savings <= 0:
        return issues

    surplus = income - expenses
    if surplus <= 0:
        return issues   # already flagged above

    if savings > surplus * SAVINGS_VS_SURPLUS_SLACK:
        issues.append(ValidationIssue(
            field="monthly_savings",
            severity="error",
            code="SAVINGS_EXCEED_SURPLUS",
            message=(
                f"Reported monthly savings (₹{savings:,.0f}) exceed the "
                f"calculated surplus of ₹{surplus:,.0f} "
                f"(income ₹{income:,.0f} − expenses ₹{expenses:,.0f})."
            ),
            suggestion=(
                "Your savings cannot exceed what is left after expenses. "
                "Please verify income, expense, or savings figures."
            ),
        ))
    return issues


def _check_age_vs_retirement(
    profile: FinancialProfile, _plan: FinancialPlan
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    age            = profile.age
    retirement_age = profile.target_retirement_age

    if age is None or retirement_age is None:
        return issues

    if age < MIN_AGE or age > MAX_AGE:
        issues.append(ValidationIssue(
            field="age",
            severity="error",
            code="INVALID_AGE",
            message=f"Age {age} is outside the plausible range ({MIN_AGE}–{MAX_AGE}).",
            suggestion="Please provide a valid age.",
        ))
        return issues

    if retirement_age <= age:
        issues.append(ValidationIssue(
            field="target_retirement_age",
            severity="error",
            code="RETIREMENT_AGE_PAST",
            message=(
                f"Target retirement age ({retirement_age}) must be greater "
                f"than current age ({age})."
            ),
            suggestion=(
                f"Set a retirement age at least {MIN_RETIREMENT_GAP_YRS} year "
                "beyond your current age."
            ),
        ))
    elif retirement_age > MAX_RETIREMENT_AGE:
        issues.append(ValidationIssue(
            field="target_retirement_age",
            severity="warning",
            code="RETIREMENT_AGE_HIGH",
            message=f"Retirement age {retirement_age} is unusually high.",
            suggestion=(
                f"Most FIRE calculators cap life expectancy at 85–90. "
                "Please confirm this is intentional."
            ),
        ))
    return issues


def _check_80c_cap(
    profile: FinancialProfile, _plan: FinancialPlan
) -> list[ValidationIssue]:
    """Section 80C investment > statutory cap is a data error; auto-correct."""
    issues: list[ValidationIssue] = []
    amount = profile.section_80c_investments

    if amount is None or amount <= 0:
        return issues

    if amount > MAX_80C:
        issues.append(ValidationIssue(
            field="section_80c_investments",
            severity="warning",
            code="80C_EXCEEDS_CAP",
            message=(
                f"Section 80C investment of ₹{amount:,.0f} exceeds the "
                f"statutory deduction cap of ₹{MAX_80C:,.0f}. "
                f"The excess ₹{amount - MAX_80C:,.0f} will not yield tax benefit."
            ),
            suggestion=(
                f"The deduction will be auto-capped at ₹{MAX_80C:,.0f} "
                "for tax calculation purposes."
            ),
        ))
    return issues


def _check_emergency_fund_vs_savings(
    profile: FinancialProfile, _plan: FinancialPlan
) -> list[ValidationIssue]:
    """Emergency fund cannot logically exceed total current savings."""
    issues: list[ValidationIssue] = []
    ef      = profile.existing_emergency_fund or 0
    savings = profile.current_savings         or 0

    if ef > 0 and savings > 0 and ef > savings:
        issues.append(ValidationIssue(
            field="existing_emergency_fund",
            severity="warning",
            code="EF_EXCEEDS_TOTAL_SAVINGS",
            message=(
                f"Emergency fund (₹{ef:,.0f}) exceeds total reported savings "
                f"(₹{savings:,.0f}). Emergency funds are a subset of savings."
            ),
            suggestion=(
                "Please verify both figures. "
                "Typically your emergency fund is part of your total savings."
            ),
        ))
    return issues


# ─────────────────────────────────────────────────────────────────────────────
# Auto-correction helpers
# ─────────────────────────────────────────────────────────────────────────────

def _apply_auto_corrections(
    profile: FinancialProfile,
    issues: list[ValidationIssue],
) -> FinancialProfile:
    """
    Return a *copy* of profile with safe auto-corrections applied.
    Currently corrects: 80C cap breach.
    """
    corrected = copy.deepcopy(profile)

    codes = {i.code for i in issues}

    if "80C_EXCEEDS_CAP" in codes and corrected.section_80c_investments:
        corrected.section_80c_investments = min(
            corrected.section_80c_investments, MAX_80C
        )

    return corrected


# ─────────────────────────────────────────────────────────────────────────────
# Rule registry — add new rules here, nothing else changes
# ─────────────────────────────────────────────────────────────────────────────

RuleFunction = Callable[[FinancialProfile, FinancialPlan], list[ValidationIssue]]

RULES: list[RuleFunction] = [
    _check_negative_values,
    _check_zero_income_with_sip,
    _check_expenses_vs_income,
    _check_savings_vs_income,
    _check_savings_vs_surplus,
    _check_age_vs_retirement,
    _check_80c_cap,
    _check_emergency_fund_vs_savings,
]


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def validate_profile(
    profile: FinancialProfile,
    plan: FinancialPlan,
) -> ValidationResult:
    """
    Run all registered validation rules over *profile* + *plan*.

    Parameters
    ----------
    profile : FinancialProfile extracted by PlannerAgent.
    plan    : FinancialPlan (needed by some rules to inspect task list).

    Returns
    -------
    ValidationResult
        • is_valid   — False if any "error" issue was found.
        • blocked    — True if any "error" issue was found (hard stop).
        • issues     — Full list of all issues, sorted severity-first.
        • corrected_profile — Auto-corrected copy, or None if no corrections made.
    """
    all_issues: list[ValidationIssue] = []
    for rule in RULES:
        all_issues.extend(rule(profile, plan))

    # Sort: error > warning > info
    _severity_order = {"error": 0, "warning": 1, "info": 2}
    all_issues.sort(key=lambda i: _severity_order.get(i.severity, 9))

    has_errors = any(i.severity == "error" for i in all_issues)

    corrected: FinancialProfile | None = None
    if all_issues:
        candidate = _apply_auto_corrections(profile, all_issues)
        # Only return a corrected profile if something actually changed
        if candidate.model_dump() != profile.model_dump():
            corrected = candidate

    return ValidationResult(
        is_valid=not has_errors,
        blocked=has_errors,
        issues=all_issues,
        corrected_profile=corrected,
    )