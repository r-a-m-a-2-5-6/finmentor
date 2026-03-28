"""
finmentor — Orchestrator Package
==================================
Re-exports the public surface of the orchestrator sub-package so callers
can write:

    from app.agents.orchestrator import FinancialMentorOrchestrator

instead of reaching into the internal module path.

Contents
--------
  main.py   — FinancialMentorOrchestrator (the 9-stage pipeline coordinator)
  guards.py — apply_risk_guardrails, is_profile_complete (stateless helpers)
"""

from app.agents.orchestrator.guards import apply_risk_guardrails, is_profile_complete
from app.agents.orchestrator.main import FinMentorOrchestrator

__all__ = [
    "FinMentorOrchestrator",
    "apply_risk_guardrails",
    "is_profile_complete",
]