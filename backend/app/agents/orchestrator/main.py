"""
finmentor — Orchestrator
==========================
Top-level coordinator for the finmentor multi-agent system.

Full 9-stage pipeline
---------------------
  User message
    ① PlannerAgent      — extract profile, generate task list
    ② ValidationLayer   — check for unrealistic / inconsistent inputs
         → validation_error path  (hard-stop data errors)
    ③ GuardLayer        — risk guardrails (emergency fund injection, etc.)
    ④ CompletenessCheck — ask clarification if minimum profile not met
         → clarification_needed path
    ⑤ ReasoningLayer    — deterministic pre-advice analysis
         → blocked path  (e.g. expenses exceed income)
    ⑥ CalculatorAgent   — execute PlanTasks via deterministic tools
    ⑦ ExplainerAgent    — generate advice grounded in reasoning report
    ⑧ ComplianceLayer   — scrub stock names, inject disclaimer
    ⑨ FormatterLayer    — assemble final StructuredOutput
"""

from __future__ import annotations

import json
from typing import Any, Optional

from app.agents.calculator.agent import CalculatorAgent
from app.agents.evaluator import (
    format_blocked,
    format_clarification,
    format_full_response,
    format_validation_error,
    run_compliance,
    run_reasoning,
    validate_profile,
)
from app.agents.explainer.agent import ExplainerAgent
from app.agents.orchestrator.guards import apply_risk_guardrails, is_profile_complete
from app.agents.planner.agent import PlannerAgent
from app.agents.shared.types import AgentResponse, FinancialProfile, StructuredOutput


class FinMentorOrchestrator:
    """
    Coordinates the 9-stage finmentor pipeline and returns StructuredOutput.
    """

    def __init__(self) -> None:
        self.planner    = PlannerAgent()
        self.calculator = CalculatorAgent()
        self.explainer  = ExplainerAgent()

        self.conversation_history: list[dict] = []
        self.last_profile: Optional[FinancialProfile] = None

    # ─────────────────────────────────────────────────────────────────────
    # Async adapter — called by mentor.py HTTP route
    # ─────────────────────────────────────────────────────────────────────

    async def run(
        self,
        user_message: str,
        history: list[dict[str, str]],
        user_id: str,
        user_profile: Any = None,               # ← NEW: DB FinancialProfile ORM object
    ) -> dict[str, Any]:
        """
        Async entry point for the mentor.py HTTP route.

        Parameters
        ----------
        user_message : Latest user message text.
        history      : Conversation turns loaded by the route.
        user_id      : String UUID for logging / future personalisation.
        user_profile : SQLAlchemy FinancialProfile ORM instance (or None).
        """
        self.conversation_history = list(history)

        # Run the full synchronous 9-stage pipeline.
        output: StructuredOutput = self.chat(user_message, user_profile=user_profile)

        try:
            dump: dict[str, Any] = output.model_dump()
        except Exception:
            dump = {}

        return {
            "content": dump.get("advice") or dump.get("content", ""),
            "planner_plan": (
                dump.get("planner_plan")
                or dump.get("profile")
                or {}
            ),
            "engine_calls": dump.get("engine_calls") or [],
            "engine_calls_raw": (
                dump.get("engine_calls_raw")
                or json.dumps(dump.get("engine_calls") or [])
            ),
            "suggested_follow_ups": dump.get("suggested_follow_ups") or [],
            "prompt_tokens":        dump.get("prompt_tokens", 0),
            "completion_tokens":    dump.get("completion_tokens", 0),
        }

    # ─────────────────────────────────────────────────────────────────────
    # Synchronous pipeline — original entry point
    # ─────────────────────────────────────────────────────────────────────

    def chat(self, user_message: str, user_profile: Any = None) -> StructuredOutput:
        """
        Process one user message through the full 9-stage pipeline.

        Parameters
        ----------
        user_message : Latest user message text.
        user_profile : Optional ORM FinancialProfile to pre-populate planner context.
        """

        # ── ① Plan ───────────────────────────────────────────────────────
        plan = self.planner.run(
            user_message,
            self.conversation_history,
            user_profile=user_profile,          # ← PASS PROFILE
        )

        # ── ② Validate ───────────────────────────────────────────────────
        validation = validate_profile(plan.profile, plan)

        if validation.blocked:
            self._record_turn(
                user=user_message,
                assistant="Validation errors found — cannot proceed.",
            )
            return format_validation_error(
                issues=validation.issues,
                warnings=plan.warnings,
            )

        effective_profile = validation.corrected_profile or plan.profile

        # ── ③ Risk guardrails ────────────────────────────────────────────
        plan.profile = effective_profile
        plan = apply_risk_guardrails(plan)

        # ── ④ Completeness gate ──────────────────────────────────────────
        if not is_profile_complete(effective_profile):
            self._record_turn(
                user=user_message,
                assistant="Clarification required: "
                          + " | ".join(effective_profile.clarification_questions),
            )
            return format_clarification(
                questions=effective_profile.clarification_questions,
                warnings=plan.warnings,
            )

        # ── ⑤ Reasoning ──────────────────────────────────────────────────
        reasoning = run_reasoning(effective_profile, plan)

        if reasoning.overall_feasibility == "blocked":
            self._record_turn(
                user=user_message,
                assistant="Blocked — income deficit detected.",
            )
            return format_blocked(
                reasoning=reasoning,
                validation=validation,
                warnings=plan.warnings,
            )

        # ── ⑥ Calculate ──────────────────────────────────────────────────
        calculation_results = self.calculator.run(plan.tasks)

        # ── ⑦ Explain ────────────────────────────────────────────────────
        raw_advice = self.explainer.run(
            profile=effective_profile,
            calculation_results=calculation_results,
            original_query=user_message,
            reasoning_report=reasoning,
        )

        print("🧠 RAW ADVICE:", raw_advice)

        # ── ⑧ Compliance ─────────────────────────────────────────────────
        compliance = run_compliance(raw_advice)

        # ── ⑨ Format & return ────────────────────────────────────────────
        internal_response = AgentResponse(
            needs_clarification=False,
            calculations=calculation_results,
            advice=compliance.scrubbed_advice,
            warnings=plan.warnings,
        )

        output = format_full_response(
            agent_response=internal_response,
            reasoning=reasoning,
            validation=validation,
            compliance=compliance,
        )

        self._record_turn(user=user_message, assistant=output.advice)
        self.last_profile = effective_profile

        return output

    def reset(self) -> None:
        """Clear conversation history and start a new session."""
        self.conversation_history = []
        self.last_profile = None

    # ─────────────────────────────────────────────────────────────────────
    # Private helpers
    # ─────────────────────────────────────────────────────────────────────

    def _record_turn(self, *, user: str, assistant: str) -> None:
        """Append a user/assistant exchange to the internal history."""
        self.conversation_history.append({"role": "user",      "content": user})
        self.conversation_history.append({"role": "assistant", "content": assistant})