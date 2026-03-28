"""
finmentor — Calculator Tools
==============================
LangChain StructuredTool wrappers around the deterministic finance engine.

Each tool:
  - Declares a typed Pydantic input schema (from schemas.py).
  - Delegates to the pure-math engine (no LLM inside the tool itself).
  - Returns JSON so the CalculatorAgent can parse results reliably.
"""

from __future__ import annotations

import json

from langchain_core.tools import StructuredTool

# Pure-math engine — no LLM, fully deterministic
from app.engine import (
    emergency_fund_calculator,
    fire_corpus_calculator,
    hra_exemption_calculator,
    india_tax_calculator,
    sip_future_value,
    xirr_calculator,
)

# from app.engine.health_scorer import emergency_fund_calculator
# from app.engine.sip_engine import sip_future_value



from app.agents.calculator.schemas import (
    EmergencyFundInput,
    FIREInput,
    HRAInput,
    SIPInput,
    TaxInput,
    XIRRInput,
)


def build_tools() -> list[StructuredTool]:
    """Instantiate and return all calculator tools."""
    return [
        StructuredTool.from_function(
            func=lambda **kw: json.dumps(sip_future_value(**kw)),
            name="sip_calculator",
            description=(
                "Calculate SIP (Systematic Investment Plan) future value. "
                "Use when user wants to know how much their monthly mutual fund / SIP investment will grow."
            ),
            args_schema=SIPInput,
        ),
        StructuredTool.from_function(
            func=lambda **kw: json.dumps(fire_corpus_calculator(**kw)),
            name="fire_corpus_calculator",
            description=(
                "Calculate the corpus required for FIRE (Financial Independence, Retire Early). "
                "Accounts for inflation, existing savings, and monthly SIP towards the goal."
            ),
            args_schema=FIREInput,
        ),
        StructuredTool.from_function(
            func=lambda **kw: json.dumps(emergency_fund_calculator(**kw)),
            name="emergency_fund_calculator",
            description=(
                "Calculate the ideal emergency fund size based on job stability, dependents, "
                "monthly expenses, and existing liquid assets."
            ),
            args_schema=EmergencyFundInput,
        ),
        StructuredTool.from_function(
            func=lambda **kw: json.dumps(xirr_calculator(**kw)),
            name="xirr_calculator",
            description=(
                "Compute XIRR (Extended Internal Rate of Return) for irregular cash flows. "
                "Use when user wants to know the actual return on their investment portfolio."
            ),
            args_schema=XIRRInput,
        ),
        StructuredTool.from_function(
            func=lambda **kw: json.dumps(india_tax_calculator(**kw)),
            name="india_tax_calculator",
            description=(
                "Calculate India income tax (FY 2024-25) under Old or New regime. "
                "Applies 80C, 80D, HRA, Section 24(b), surcharge, cess, and 87A rebate."
            ),
            args_schema=TaxInput,
        ),
        StructuredTool.from_function(
            func=lambda **kw: json.dumps(hra_exemption_calculator(**kw)),
            name="hra_exemption_calculator",
            description=(
                "Calculate HRA (House Rent Allowance) exemption under Section 10(13A). "
                "Use before tax calculation when user pays rent and receives HRA."
            ),
            args_schema=HRAInput,
        ),
    ]


# Module-level singleton — imported by CalculatorAgent
TOOLS = build_tools()
