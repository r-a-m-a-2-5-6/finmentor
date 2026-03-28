"""
finmentor — Orchestrator Guards
=================================
Behaviour guardrails applied by the Orchestrator before handing a
FinancialPlan to the CalculatorAgent.

Responsibilities:
  - Enforce emergency fund as the first task when no savings exist.
  - Inject risk-level warnings for conservative users.
  - Validate that the minimum viable profile is present before proceeding.
"""

from __future__ import annotations

from app.agents.shared.types import FinancialPlan, FinancialProfile, PlanTask


def apply_risk_guardrails(plan: FinancialPlan) -> FinancialPlan:
    """
    Override or augment the plan to enforce safe financial behaviour.

    Rules applied (in order):
      1. No savings detected → insert emergency_fund_calculator as step 0.
      2. Conservative risk profile → append equity-cap warning.

    Parameters
    ----------
    plan : FinancialPlan produced by PlannerAgent.

    Returns
    -------
    Mutated FinancialPlan with guardrails applied.
    """
    if not plan.profile.risk_profile:
        return plan

    level = plan.profile.risk_profile.level
    income = plan.profile.monthly_income or 0
    savings = plan.profile.current_savings or 0

    # Guard 1: no savings → emergency fund must come first
    if savings == 0 and plan.profile.existing_emergency_fund in (None, 0):
        has_ef = any(t.tool == "emergency_fund_calculator" for t in plan.tasks)

        if not has_ef and income > 0:
            ef_task = PlanTask(
                step=0,
                action="Build emergency fund first — no existing savings detected",
                tool="emergency_fund_calculator",
                priority="immediate",
                params={
                    "monthly_essential_expenses": (
                        plan.profile.monthly_expenses or income * 0.5
                    ),
                    "monthly_income": income,
                    "job_stability": "semi_stable",
                    "existing_emergency_fund": 0.0,
                },
            )
            plan.tasks.insert(0, ef_task)
            plan.warnings.append(
                "⚠️  No savings detected. "
                "Emergency fund MUST be built before any investment."
            )

    # Guard 2: conservative profile → cap equity exposure
    if level == "conservative":
        plan.warnings.append(
            "Conservative profile: equity exposure should not exceed 40%. "
            "Prefer PPF, FD, and balanced advantage funds."
        )

    return plan


def is_profile_complete(profile: FinancialProfile) -> bool:
    """
    Return True if the profile contains the minimum viable data needed
    to proceed to the CalculatorAgent.

    Minimum: monthly_income + monthly_expenses + at least one goal.
    """
    return bool(
        profile.monthly_income
        and profile.monthly_expenses
        and profile.goals
    )
