"""
finmentor — Shared Pydantic Types
===================================
Typed contracts passed between PlannerAgent, CalculatorAgent,
ExplainerAgent, the Evaluator layer, and the Orchestrator.

Type groups
-----------
  Core pipeline  : RiskProfile, FinancialProfile, PlanTask, FinancialPlan,
                   CalculationResult, AgentResponse
  Validation     : ValidationIssue, ValidationResult
  Reasoning      : IncomeExpenseAnalysis, RiskProfileCheck,
                   TimeHorizonEval, ReasoningReport
  Compliance     : ComplianceResult
  Public output  : StructuredOutput   ← the type returned to callers
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class RiskProfile(BaseModel):
    """User's risk tolerance classification."""

    level: str = Field(..., description="conservative | moderate | aggressive")
    rationale: str = Field(..., description="One-line reason")


class FinancialProfile(BaseModel):
    """
    Extracted financial facts about the user.
    Any unknown field is None — triggers clarification questions.
    """

    name: Optional[str] = None
    age: Optional[int] = None
    monthly_income: Optional[float] = None
    monthly_expenses: Optional[float] = None
    monthly_savings: Optional[float] = None
    current_savings: Optional[float] = None
    existing_emergency_fund: Optional[float] = None
    has_home_loan: Optional[bool] = None
    home_loan_interest_annual: Optional[float] = None
    section_80c_investments: Optional[float] = None
    health_insurance_premium: Optional[float] = None
    goals: list[str] = Field(default_factory=list)
    risk_profile: Optional[RiskProfile] = None
    city_type: Optional[str] = None          # metro | non-metro
    target_retirement_age: Optional[int] = None
    is_complete: bool = False
    missing_fields: list[str] = Field(default_factory=list)
    clarification_questions: list[str] = Field(default_factory=list)


class PlanTask(BaseModel):
    """A single actionable task in the financial plan."""

    step: int
    action: str       # e.g. "Calculate emergency fund"
    tool: str         # e.g. "emergency_fund_calculator"
    priority: str     # immediate | short_term | long_term
    params: dict[str, Any]   # pre-filled params for the CalculatorAgent


class FinancialPlan(BaseModel):
    """Output of the PlannerAgent."""

    profile: FinancialProfile
    tasks: list[PlanTask]
    warnings: list[str] = Field(default_factory=list)


class CalculationResult(BaseModel):
    """One completed calculation."""

    tool: str
    result: dict[str, Any]
    success: bool


class AgentResponse(BaseModel):
    """Internal response assembled by the Orchestrator before formatting."""

    needs_clarification: bool
    clarification_questions: list[str] = Field(default_factory=list)
    calculations: list[CalculationResult] = Field(default_factory=list)
    advice: str = ""
    warnings: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# Validation layer types
# ─────────────────────────────────────────────────────────────────────────────

Severity = Literal["error", "warning", "info"]


class ValidationIssue(BaseModel):
    """A single data-quality problem detected in the user's financial profile."""

    field: str          # Which profile field triggered this issue
    severity: Severity  # "error" blocks execution; "warning" proceeds with note
    code: str           # Machine-readable code, e.g. "SIP_EXCEEDS_INCOME"
    message: str        # Human-readable explanation
    suggestion: str     # What the user should correct


class ValidationResult(BaseModel):
    """Outcome of the full validation pass over a FinancialProfile."""

    is_valid: bool                                  # False → at least one error
    blocked: bool                                   # True → hard stop, do not proceed
    issues: list[ValidationIssue] = Field(default_factory=list)
    # Auto-corrected profile (e.g. capped 80C to ₹1.5 L).
    # None means no corrections were made.
    corrected_profile: Optional["FinancialProfile"] = None


# ─────────────────────────────────────────────────────────────────────────────
# Reasoning layer types
# ─────────────────────────────────────────────────────────────────────────────

class IncomeExpenseAnalysis(BaseModel):
    """Cash-flow health check derived from the user's profile."""

    monthly_surplus: float          # income − expenses
    expense_ratio: float            # expenses / income  (0–1+)
    actual_savings_rate: float      # monthly_savings / income  (0–1)
    reported_savings_rate: float    # (income − expenses) / income
    savings_gap: float              # reported − actual  (should be ≤ 0)
    assessment: Literal["healthy", "tight", "deficit"]
    flags: list[str] = Field(default_factory=list)


class RiskProfileCheck(BaseModel):
    """Compares declared risk tolerance against inferred behavioural risk."""

    declared_level: str                             # from profile.risk_profile
    inferred_level: str                             # derived from goals / age / surplus
    mismatch_detected: bool
    mismatch_direction: Optional[str] = None        # "over_aggressive" | "over_conservative"
    flags: list[str] = Field(default_factory=list)


class TimeHorizonEval(BaseModel):
    """Feasibility of the user's primary goal within their stated time horizon."""

    years_to_goal: Optional[int] = None
    corpus_required: Optional[float] = None         # INR
    current_trajectory_corpus: Optional[float] = None
    shortfall: Optional[float] = None               # corpus_required − trajectory
    feasibility: Literal["achievable", "aggressive", "infeasible"]
    required_monthly_sip: Optional[float] = None    # to close shortfall
    flags: list[str] = Field(default_factory=list)


class ReasoningReport(BaseModel):
    """
    Full pre-advice reasoning summary.
    Passed to the ExplainerAgent as grounding context so advice is
    anchored to verified financial logic, not just user claims.
    """

    income_expense: IncomeExpenseAnalysis
    risk_check: RiskProfileCheck
    time_horizon: TimeHorizonEval
    overall_feasibility: Literal["proceed", "caution", "blocked"]
    advisor_notes: list[str] = Field(default_factory=list)  # injected into explainer


# ─────────────────────────────────────────────────────────────────────────────
# Compliance layer types
# ─────────────────────────────────────────────────────────────────────────────

class ComplianceResult(BaseModel):
    """Outcome of the compliance pass over generated advice text."""

    original_advice: str
    scrubbed_advice: str            # advice with banned content removed/replaced
    violations_found: list[str]     # list of banned patterns that were detected
    disclaimer_injected: bool


# ─────────────────────────────────────────────────────────────────────────────
# Public output contract  (what callers / the API layer receive)
# ─────────────────────────────────────────────────────────────────────────────

class StructuredOutput(BaseModel):
    """
    The canonical, versioned response contract for finmentor.

    Every code path — clarification, validation error, full advice — returns
    this type so callers never need to branch on response shape.
    """

    # ── Status ────────────────────────────────────────────────────────────
    status: Literal["ok", "clarification_needed", "validation_error", "blocked"]

    # ── Core payload ──────────────────────────────────────────────────────
    summary: str                                    # 2-3 sentence plain-English overview
    calculations: dict[str, Any] = Field(default_factory=dict)
    advice: str = ""                                # full formatted advice from Explainer
    next_steps: list[str] = Field(default_factory=list)

    # ── Diagnostic surfaces ───────────────────────────────────────────────
    warnings: list[str] = Field(default_factory=list)
    clarification_questions: list[str] = Field(default_factory=list)
    validation_issues: list[ValidationIssue] = Field(default_factory=list)
    reasoning_summary: Optional[str] = None        # condensed ReasoningReport for UIs

    # ── Compliance ────────────────────────────────────────────────────────
    disclaimer: str = ""

    # ── Metadata ──────────────────────────────────────────────────────────
    metadata: dict[str, Any] = Field(default_factory=dict)  # version, timestamp, model