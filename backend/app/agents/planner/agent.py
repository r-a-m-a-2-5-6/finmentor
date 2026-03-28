"""
finmentor — Planner Agent
==========================
Extracts goals, builds a risk profile, identifies missing data,
and returns a FinancialPlan with an ordered task list for the CalculatorAgent.

Uses a single LLM call with JSON output — no tool-calling needed here.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.agents.planner.parser import parse_planner_output
from app.agents.planner.prompt import PLANNER_SYSTEM_PROMPT
from app.agents.shared.llm import get_llm
from app.agents.shared.types import FinancialPlan


def _format_profile_context(user_profile: Any) -> str:
    """
    Convert a SQLAlchemy FinancialProfile ORM object into a plain-text
    context block injected before the user message.

    The planner LLM is instructed to treat these values as ground truth
    and MUST NOT ask for them again.
    """
    lines = [
        "=== USER'S STORED FINANCIAL PROFILE ===",
        "IMPORTANT: The following data is already known. "
        "Do NOT ask the user for any of these values. "
        "Set is_complete=true and use these figures directly.\n",
    ]

    def _fmt(val) -> Optional[str]:
        """Return None if blank/zero-ish, else str."""
        if val is None:
            return None
        if isinstance(val, Decimal) and val == Decimal("0.00"):
            return None
        return str(val)

    field_map = [
        ("current_age",               "Age (years)"),
        ("target_retirement_age",     "Target retirement age"),
        ("life_expectancy",           "Life expectancy"),
        ("monthly_income",            "Monthly income (₹)"),
        ("monthly_expenses",          "Monthly expenses (₹)"),
        ("monthly_emi",               "Monthly EMI (₹)"),
        ("monthly_insurance_premium", "Monthly insurance premium (₹)"),
        ("current_corpus",            "Current corpus / savings (₹)"),
        ("existing_emergency_fund",   "Existing emergency fund (₹)"),
        ("risk_profile",              "Risk profile"),
        ("job_stability",             "Job stability"),
        ("dependents",                "Number of dependents"),
        ("metro_city",                "Lives in metro city"),
        ("gross_annual_income",       "Gross annual income (₹)"),
        ("preferred_tax_regime",      "Preferred tax regime"),
    ]

    has_any = False
    for attr, label in field_map:
        raw = getattr(user_profile, attr, None)
        val = _fmt(raw)
        if val is not None:
            lines.append(f"- {label}: {val}")
            has_any = True

    if not has_any:
        return ""   # No profile data — don't inject empty block

    lines.append("\n=== END OF PROFILE ===")
    return "\n".join(lines)


class PlannerAgent:
    """
    Parses user input and returns a structured FinancialPlan.

    Parameters
    ----------
    llm : Optional pre-configured LLM instance. Defaults to get_llm(temperature=0.1).
    """

    def __init__(self, llm=None):
        self.llm = llm or get_llm(temperature=0.1)

    def run(
        self,
        user_message: str,
        conversation_history: Optional[list[dict]] = None,
        user_profile: Any = None,               # ← NEW: ORM FinancialProfile or None
    ) -> FinancialPlan:
        """
        Parse user input and return a FinancialPlan.

        Parameters
        ----------
        user_message        : Latest user message.
        conversation_history: List of {"role": "user"|"assistant", "content": str}.
        user_profile        : Optional ORM FinancialProfile to pre-populate context.
        """
        messages = [SystemMessage(content=PLANNER_SYSTEM_PROMPT)]

        # ── Inject stored profile as a system-level context block ─────────
        if user_profile is not None:
            profile_context = _format_profile_context(user_profile)
            if profile_context:
                messages.append(SystemMessage(content=profile_context))

        # ── Inject prior conversation turns ───────────────────────────────
        for turn in (conversation_history or []):
            if turn["role"] == "user":
                messages.append(HumanMessage(content=turn["content"]))
            else:
                messages.append(AIMessage(content=turn["content"]))

        messages.append(HumanMessage(content=user_message))

        response = self.llm.invoke(messages)
        print("🧠 LLM RAW CONTENT:", response.content)
        return parse_planner_output(response.content.strip())