"""
utils.py
========
Shared helper utilities for the Gaara Finance Engine.

All helpers are:
  - Deterministic and side-effect free
  - Return structured JSON-serialisable dicts

Author : Gaara Platform – Financial Engine v1.0
Python : 3.9+
"""

from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _round2(value: float) -> float:
    """Round to 2 decimal places (safe for monetary display)."""
    return round(value, 2)


def _success(data: dict[str, Any]) -> dict[str, Any]:
    return {"status": "success", "data": data}


def _error(code: str, message: str) -> dict[str, Any]:
    return {"status": "error", "error": {"code": code, "message": message}}