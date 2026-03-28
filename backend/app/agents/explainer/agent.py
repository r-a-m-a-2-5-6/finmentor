"""
finmentor — Explainer Agent
=============================
Converts raw calculation results + user profile + reasoning report into warm,
personalised, Indian-context financial advice.

The ReasoningReport from the reasoning layer is injected into the prompt so
the LLM advice is anchored to verified financial analysis.  The model cannot
silently contradict the deterministic reasoning without explicitly ignoring
context in its own window — a much safer failure mode.

Temperature is slightly elevated (0.4) to allow natural, friendly prose
while keeping financial claims grounded in the calculation data.
"""

from __future__ import annotations

import json
from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.explainer.prompt import EXPLAINER_SYSTEM_PROMPT
from app.agents.shared.llm import get_llm
from app.agents.shared.types import CalculationResult, FinancialProfile, ReasoningReport


class ExplainerAgent:
    """
    Generates human-friendly financial advice from calculation results.

    Parameters
    ----------
    llm : Optional pre-configured LLM instance.
          Defaults to get_llm(temperature=0.4) for natural prose.
    """

    def __init__(self, llm=None):
        self.llm = llm or get_llm(temperature=0.4)

    def run(
        self,
        profile: FinancialProfile,
        calculation_results: list[CalculationResult],
        original_query: str,
        reasoning_report: Optional[ReasoningReport] = None,
    ) -> str:
        """
        Generate personalised financial advice.

        Parameters
        ----------
        profile             : User's financial profile from PlannerAgent.
        calculation_results : Completed calculations from CalculatorAgent.
        original_query      : The user's original question (for context anchoring).
        reasoning_report    : Pre-advice analysis from the reasoning layer.
                              When provided, advisor_notes are injected so the LLM
                              cannot contradict the deterministic analysis.

        Returns
        -------
        Formatted advice string following the 5-section structure defined in
        EXPLAINER_SYSTEM_PROMPT.
        """
        context = {
            "user_profile": {
                "age": profile.age,
                "monthly_income": profile.monthly_income,
                "monthly_expenses": profile.monthly_expenses,
                "monthly_savings": profile.monthly_savings,
                "goals": profile.goals,
                "risk_level": (
                    profile.risk_profile.level if profile.risk_profile else "moderate"
                ),
                "city_type": profile.city_type,
            },
            "calculations": [
                {
                    "type": r.tool,
                    "success": r.success,
                    "data": r.result.get("data") if r.success else r.result,
                }
                for r in calculation_results
            ],
        }

        # Build the reasoning section — injected when available
        reasoning_section = ""
        if reasoning_report:
            notes_block = "\n".join(
                f"  • {note}" for note in reasoning_report.advisor_notes
            )
            reasoning_section = (
                f"\n\n### Pre-advice Analysis (MUST incorporate into advice)\n"
                f"Overall feasibility: {reasoning_report.overall_feasibility.upper()}\n"
                f"Income assessment : {reasoning_report.income_expense.assessment.upper()} "
                f"(expense ratio {reasoning_report.income_expense.expense_ratio:.0%})\n"
                f"Risk alignment    : "
                f"{'MISMATCH — ' + reasoning_report.risk_check.mismatch_direction if reasoning_report.risk_check.mismatch_detected else 'ALIGNED'}\n"
                f"Goal feasibility  : {reasoning_report.time_horizon.feasibility.upper()}"
                + (
                    f" (shortfall ₹{reasoning_report.time_horizon.shortfall:,.0f})"
                    if reasoning_report.time_horizon.shortfall else ""
                )
                + f"\n\nAdvisor notes to address in your advice:\n{notes_block}"
            )

        prompt = (
            f'User\'s original question: "{original_query}"\n\n'
            f"Financial profile and calculation results:\n"
            f"{json.dumps(context, indent=2)}"
            f"{reasoning_section}\n\n"
            "Please provide personalised financial advice following the structure "
            "in your system instructions. Your advice MUST be consistent with the "
            "pre-advice analysis above."
        )

        messages = [
            SystemMessage(content=EXPLAINER_SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ]

        response = self.llm.invoke(messages)
        return response.content