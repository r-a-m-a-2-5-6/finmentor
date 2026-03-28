"""
finmentor — Evaluator Package
===============================
This package implements the four cross-cutting quality layers that run
around the core Planner → Calculator → Explainer pipeline.

Modules
-------
  validator   — Input validation (unrealistic/inconsistent data detection)
  reasoning   — Deterministic pre-advice analysis (income, risk, time horizon)
  compliance  — Stock scrubbing + mandatory disclaimer injection
  formatter   — Assembles the final StructuredOutput from all layer outputs

Why is __init__.py required?
-----------------------------
In Python, a directory is only importable as a *package* (i.e., you can
write ``from app.agents.evaluator.validator import validate_profile``) if
it contains an ``__init__.py`` file — even if that file is empty.

This applies to EVERY directory in the import chain:
  finmentor/          ← needs __init__.py  (top-level package)
  app/                ← needs __init__.py
  app/agents/         ← needs __init__.py
  app/agents/shared/  ← needs __init__.py
  app/agents/planner/ ← needs __init__.py
  ... and so on for every sub-package

Without __init__.py, Python treats the directory as a plain folder and
``import`` statements will raise ModuleNotFoundError at runtime.

Exception: Python 3.3+ supports "namespace packages" (directories WITHOUT
__init__.py) in some edge cases, but they are not recommended for
application code because they interact badly with tools like pytest, mypy,
and setuptools.  Always create __init__.py for application packages.

Re-exports (for convenience)
-----------------------------
Import the most commonly used symbols directly from this package:
"""

from app.agents.evaluator.compliance import run_compliance
from app.agents.evaluator.formatter import (
    format_blocked,
    format_clarification,
    format_full_response,
    format_validation_error,
)
from app.agents.evaluator.reasoning import run_reasoning
from app.agents.evaluator.validator import validate_profile

__all__ = [
    "validate_profile",
    "run_reasoning",
    "run_compliance",
    "format_clarification",
    "format_validation_error",
    "format_blocked",
    "format_full_response",
]