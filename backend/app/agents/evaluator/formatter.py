"""
finmentor — Output Formatter
==============================
Assembles the final StructuredOutput from the artefacts produced by
every stage of the pipeline.  This is the ONLY place that constructs
a StructuredOutput — no other module should instantiate it directly.

Every response path is handled here:
  • clarification_needed — profile incomplete, asking user for more info
  • validation_error     — hard-stop data error (e.g. expenses > income)
  • blocked              — reasoning layer says do not proceed (e.g. deficit)
  • ok                   — full advice path, all layers passed

Output contract (StructuredOutput fields)
-----------------------------------------
  status                 : one of the four statuses above
  summary                : 2-3 sentence plain-English overview
  calculations           : {tool_name: result_dict} for each CalculationResult
  advice                 : full formatted advice (compliance-scrubbed)
  next_steps             : extracted from advice or from reasoning flags
  warnings               : merged from all layers
  clarification_questions: forwarded when status=clarification_needed
  validation_issues      : forwarded when status=validation_error
  reasoning_summary      : condensed bullet list of advisor_notes
  disclaimer             : always populated (empty string only on clarification)
  metadata               : version, timestamp, model, violation counts
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from app.agents.shared.types import (
    AgentResponse,
    CalculationResult,
    ComplianceResult,
    ReasoningReport,
    StructuredOutput,
    ValidationIssue,
    ValidationResult,
)

# ─────────────────────────────────────────────────────────────────────────────
# Version stamp
# ─────────────────────────────────────────────────────────────────────────────

FINMENTOR_VERSION = "1.0.0"


# ─────────────────────────────────────────────────────────────────────────────
# Helper: flatten CalculationResult list → dict
# ─────────────────────────────────────────────────────────────────────────────

def _calc_results_to_dict(results: list[CalculationResult]) -> dict[str, Any]:
    """
    Convert a list of CalculationResult objects into a keyed dict.
    Duplicate tool names get a numeric suffix to avoid key collisions.

    Example output
    --------------
    {
      "emergency_fund_calculator": {"status": "success", "data": {...}},
      "sip_calculator":            {"status": "success", "data": {...}},
    }
    """
    out: dict[str, Any] = {}
    counts: dict[str, int] = {}

    for cr in results:
        key = cr.tool
        counts[key] = counts.get(key, 0) + 1
        if counts[key] > 1:
            key = f"{cr.tool}_{counts[key]}"
        out[key] = cr.result

    return out


# ─────────────────────────────────────────────────────────────────────────────
# Helper: extract next_steps from advice text
# ─────────────────────────────────────────────────────────────────────────────

_NEXT_STEP_RE = re.compile(
    r"(?:✅\s*Your\s+3\s+Next\s+Steps.*?)\n"   # heading
    r"((?:\d+\..+\n?)+)",                        # numbered lines
    re.IGNORECASE | re.DOTALL,
)


def _extract_next_steps(advice: str) -> list[str]:
    """
    Pull numbered next-step items out of the Explainer's formatted advice.
    Falls back to an empty list if the section is missing.
    """
    match = _NEXT_STEP_RE.search(advice)
    if not match:
        return []
    block = match.group(1).strip()
    steps = [
        re.sub(r"^\d+\.\s*", "", line).strip()
        for line in block.splitlines()
        if line.strip()
    ]
    return [s for s in steps if s]


# ─────────────────────────────────────────────────────────────────────────────
# Helper: build reasoning_summary string
# ─────────────────────────────────────────────────────────────────────────────

def _build_reasoning_summary(report: ReasoningReport) -> str:
    if not report.advisor_notes:
        return "No notable issues detected in the pre-advice analysis."
    lines = "\n".join(f"• {note}" for note in report.advisor_notes)
    return f"Pre-advice analysis ({report.overall_feasibility.upper()}):\n{lines}"


# ─────────────────────────────────────────────────────────────────────────────
# Helper: build metadata dict
# ─────────────────────────────────────────────────────────────────────────────

def _build_metadata(
    compliance: ComplianceResult | None = None,
    validation: ValidationResult | None = None,
    reasoning: ReasoningReport | None = None,
) -> dict[str, Any]:
    return {
        "version": FINMENTOR_VERSION,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "compliance_violations": (
            len(compliance.violations_found) if compliance else 0
        ),
        "validation_issue_count": (
            len(validation.issues) if validation else 0
        ),
        "overall_feasibility": (
            reasoning.overall_feasibility if reasoning else "unknown"
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Public format functions — one per response path
# ─────────────────────────────────────────────────────────────────────────────

def format_clarification(
    questions: list[str],
    warnings: list[str],
) -> StructuredOutput:
    """
    Build the StructuredOutput for the clarification-needed path.
    No calculations, advice, or disclaimer — just questions.
    """
    return StructuredOutput(
        status="clarification_needed",
        summary=(
            "I need a few more details before I can build your financial plan. "
            "Please answer the questions below."
        ),
        clarification_questions=questions,
        warnings=warnings,
        metadata=_build_metadata(),
    )


def format_validation_error(
    issues: list[ValidationIssue],
    warnings: list[str],
) -> StructuredOutput:
    """
    Build the StructuredOutput when validation finds blocking errors.
    """
    error_messages = [
        f"• [{i.code}] {i.message} — {i.suggestion}"
        for i in issues
        if i.severity == "error"
    ]
    summary = (
        "There are issues with the financial data you provided that must be "
        "corrected before I can give you accurate advice:\n"
        + "\n".join(error_messages)
    )
    return StructuredOutput(
        status="validation_error",
        summary=summary,
        validation_issues=issues,
        warnings=warnings,
        metadata=_build_metadata(),
    )


def format_blocked(
    reasoning: ReasoningReport,
    validation: ValidationResult,
    warnings: list[str],
) -> StructuredOutput:
    """
    Build the StructuredOutput when the reasoning layer blocks execution
    (e.g. income deficit — cannot plan investments).
    """
    summary = (
        "Based on your financial profile, your monthly expenses currently "
        "meet or exceed your income. Providing investment advice at this stage "
        "would not be responsible. Let's focus on stabilising your cash flow first."
    )
    return StructuredOutput(
        status="blocked",
        summary=summary,
        reasoning_summary=_build_reasoning_summary(reasoning),
        warnings=reasoning.advisor_notes + warnings,
        validation_issues=validation.issues,
        metadata=_build_metadata(
            reasoning=reasoning,
            validation=validation,
        ),
    )


def format_full_response(
    agent_response: AgentResponse,
    reasoning: ReasoningReport,
    validation: ValidationResult,
    compliance: ComplianceResult,
) -> StructuredOutput:
    """
    Build the complete StructuredOutput for the happy path.

    Parameters
    ----------
    agent_response : Internal response from Orchestrator (pre-compliance).
    reasoning      : ReasoningReport from the reasoning layer.
    validation     : ValidationResult (may contain warnings even on success).
    compliance     : ComplianceResult with scrubbed advice + disclaimer.
    """
    # Merge warnings from all layers (deduplicated, order: validation → plan → reasoning)
    all_warnings: list[str] = []
    seen: set[str] = set()
    for w in validation.issues:
        if w.severity == "warning" and w.message not in seen:
            all_warnings.append(f"[{w.code}] {w.message}")
            seen.add(w.message)
    for w in agent_response.warnings:
        if w not in seen:
            all_warnings.append(w)
            seen.add(w)
    for note in reasoning.advisor_notes:
        if note not in seen:
            all_warnings.append(note)
            seen.add(note)

    # Build summary: first 2-3 sentences of advice, or a fallback
    advice_text = compliance.scrubbed_advice
    first_sentences = ". ".join(advice_text.split(". ")[:3]) + "."

    # Extract structured next steps
    next_steps = _extract_next_steps(advice_text)

    # Determine status
    status = "ok" if reasoning.overall_feasibility == "proceed" else "ok"
    # (caution is still "ok" — it proceeds but with extra warnings)

    return StructuredOutput(
        status=status,
        summary=first_sentences,
        calculations=_calc_results_to_dict(agent_response.calculations),
        advice=advice_text,
        next_steps=next_steps or agent_response.next_steps,
        warnings=all_warnings,
        reasoning_summary=_build_reasoning_summary(reasoning),
        disclaimer=compliance.scrubbed_advice[
            compliance.scrubbed_advice.find("⚠️  Disclaimer:"):
        ] if "⚠️  Disclaimer:" in compliance.scrubbed_advice else "",
        metadata=_build_metadata(
            compliance=compliance,
            validation=validation,
            reasoning=reasoning,
        ),
    )