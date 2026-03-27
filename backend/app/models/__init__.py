"""
models/__init__.py
==================
Exports all ORM models in dependency order so Alembic's autogenerate
can discover every table in a single `from finmentor.app.models import *`.
"""

from finmentor.backend.app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from finmentor.backend.app.models.user import User, FinancialProfile
from finmentor.backend.app.models.portfolio import Portfolio, PortfolioHolding, CashFlowEntry
from finmentor.backend.app.models.chat import ChatSession, ChatMessage

__all__ = [
    "Base",
    "TimestampMixin",
    "UUIDPrimaryKeyMixin",
    "User",
    "FinancialProfile",
    "Portfolio",
    "PortfolioHolding",
    "CashFlowEntry",
    "ChatSession",
    "ChatMessage",
]