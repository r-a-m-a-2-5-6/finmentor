"""
finmentor — Planner Output Parser
===================================
Converts the raw JSON string produced by the PlannerAgent LLM call
into validated FinancialPlan / FinancialProfile / PlanTask objects.
"""

from __future__ import annotations

import json

from app.agents.shared.types import FinancialPlan, FinancialProfile, PlanTask, RiskProfile


def parse_planner_output(raw: str) -> FinancialPlan:
    """
    Parse raw LLM output into a FinancialPlan.

    Strips markdown fences if present, then deserialises JSON.
    Falls back to a minimal clarification-only plan on any error.

    Parameters
    ----------
    raw : Raw string content from the LLM response.

    Returns
    -------
    FinancialPlan
    """
    # Strip markdown code fences if the model wrapped the JSON
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    try:
        data = json.loads(raw)

        profile_data = data.get("profile", {})
        risk_data = profile_data.pop("risk_profile", None)
        if risk_data:
            profile_data["risk_profile"] = RiskProfile(**risk_data)

        profile = FinancialProfile(**profile_data)
        tasks = [PlanTask(**t) for t in data.get("tasks", [])]
        warnings = data.get("warnings", [])

        return FinancialPlan(profile=profile, tasks=tasks, warnings=warnings)

    except (json.JSONDecodeError, Exception) as exc:
        # Graceful degradation — ask the user for the minimum viable info
        return FinancialPlan(
            profile=FinancialProfile(
                is_complete=False,
                clarification_questions=[
                    "Could you share your monthly income, expenses, and main financial goal?"
                ],
                missing_fields=["monthly_income", "monthly_expenses", "goals"],
            ),
            tasks=[],
            warnings=[f"Profile parsing issue: {exc}"],
        )
