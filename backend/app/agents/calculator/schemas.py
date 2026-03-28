"""
finmentor — Calculator Tool Input Schemas
==========================================
Pydantic models that define the typed input contract for each
LangChain StructuredTool in the CalculatorAgent.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SIPInput(BaseModel):
    monthly_investment: float = Field(..., description="Monthly SIP amount in INR")
    annual_rate_pct: float    = Field(..., description="Expected annual return % (e.g. 12)")
    years: int                = Field(..., description="Investment horizon in years")
    step_up_pct: float        = Field(0.0, description="Annual step-up % (default 0)")


class FIREInput(BaseModel):
    current_monthly_expense: float    = Field(..., description="Current monthly expenses INR")
    current_age: int                  = Field(..., description="Current age")
    target_retirement_age: int        = Field(..., description="Target retirement age")
    life_expectancy: int              = Field(85,  description="Life expectancy (default 85)")
    inflation_rate_pct: float         = Field(6.0, description="Inflation rate % (default 6)")
    post_retirement_return_pct: float = Field(7.0, description="Post-retirement return %")
    current_savings: float            = Field(0.0, description="Existing savings INR")
    monthly_savings: float            = Field(0.0, description="Monthly investment towards FIRE")
    pre_retirement_return_pct: float  = Field(12.0, description="Pre-retirement return %")


class EmergencyFundInput(BaseModel):
    monthly_essential_expenses: float  = Field(..., description="Monthly essential expenses INR")
    monthly_income: float              = Field(..., description="Monthly income INR")
    job_stability: str                 = Field(
        "stable",
        description="stable | semi_stable | unstable | self_employed",
    )
    dependents: int                    = Field(0,   description="Number of dependents")
    existing_emergency_fund: float     = Field(0.0, description="Existing emergency fund INR")
    existing_liquid_investments: float = Field(0.0, description="Other liquid investments INR")
    monthly_emi: float                 = Field(0.0, description="Monthly EMI obligations")
    monthly_insurance_premium: float   = Field(0.0, description="Monthly insurance premium")


class XIRRInput(BaseModel):
    cash_flows: list[float] = Field(
        ...,
        description="Cash flows (negative = investment, positive = return)",
    )
    dates: list[str]        = Field(..., description="Corresponding dates in YYYY-MM-DD format")
    guess: float            = Field(0.1, description="Initial guess for rate (default 0.10)")


class TaxInput(BaseModel):
    gross_annual_income: float  = Field(..., description="Gross annual income INR")
    section_80c: float          = Field(0.0,   description="80C investments (max 1,50,000)")
    section_80d_self: float     = Field(0.0,   description="Health insurance self (max 25,000)")
    section_80d_parents: float  = Field(0.0,   description="Health insurance parents (max 25,000)")
    parents_senior: bool        = Field(False,  description="Parents are senior citizens")
    self_senior: bool           = Field(False,  description="Self is senior citizen (age>=60)")
    hra_exemption: float        = Field(0.0,   description="Pre-computed HRA exemption")
    home_loan_interest: float   = Field(0.0,   description="Annual home loan interest (max 2,00,000)")
    new_regime: bool            = Field(False,  description="True = New Tax Regime")


class HRAInput(BaseModel):
    basic_salary_annual: float = Field(..., description="Annual basic salary INR")
    hra_received_annual: float = Field(..., description="Annual HRA received from employer INR")
    rent_paid_annual: float    = Field(..., description="Annual rent paid INR")
    metro_city: bool           = Field(False,  description="True for Delhi/Mumbai/Kolkata/Chennai")
