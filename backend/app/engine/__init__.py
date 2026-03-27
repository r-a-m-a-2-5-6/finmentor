"""
app/engine/__init__.py
=====================

Importing from this package exposes all six core financial functions
as a flat, stable interface for AI agents and API consumers.

Usage
-----
    from app.engine import sip_future_value, fire_corpus_calculator
    from app.engine import emergency_fund_calculator, xirr_calculator
    from app.engine import india_tax_calculator, hra_exemption_calculator


Python : 3.9+
"""

from app.engine.sip_engine import sip_future_value
from app.engine.fire_calculator import fire_corpus_calculator
from app.engine.health_scorer import emergency_fund_calculator
from app.engine.portfolio_xray import xirr_calculator
from app.engine.tax_optimizer import india_tax_calculator, hra_exemption_calculator

__all__ = [
    "sip_future_value",
    "fire_corpus_calculator",
    "emergency_fund_calculator",
    "xirr_calculator",
    "india_tax_calculator",
    "hra_exemption_calculator",
]