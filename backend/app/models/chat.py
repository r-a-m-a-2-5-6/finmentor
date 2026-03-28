"""
models/chat.py
==============
AI mentor conversation persistence.

One User → many ChatSessions (one per conversation thread)
One ChatSession → many ChatMessages (ordered by sequence_no)

Design decisions:
  - Messages store both the raw content and the structured engine_calls
    (JSON blob) so the explainer agent can be replayed without re-running
    the calculators.
  - token_usage stored per-message for cost tracking.
  - session-level metadata (goal, context_summary) support long-running
    multi-turn conversations with context compression.

Author : FinMentor Platform
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean, Enum, ForeignKey, Integer,
    String, Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.user import User


# ---------------------------------------------------------------------------
# ChatSession
# ---------------------------------------------------------------------------

class ChatSession(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    A single conversation thread between the user and the AI mentor.

    Sessions are open-ended; the client sends session_id=null to start a
    new session, or an existing UUID to continue a thread.
    """
    __tablename__ = "chat_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    title: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True,
        comment="Auto-generated from first message, editable by user",
    )

    # Compressed summary used to keep context window manageable
    context_summary: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
        comment="Periodically updated summary injected as system context",
    )

    # Detected intent from the first user message
    primary_goal: Mapped[Optional[str]] = mapped_column(
        Enum(
            "fire", "sip_planning", "tax_optimisation",
            "portfolio_review", "emergency_fund", "general",
            name="session_goal_enum",
        ),
        nullable=True,
    )

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    message_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tokens_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # ── Relationships ─────────────────────────────────────────────────────
    user: Mapped["User"] = relationship("User", back_populates="chat_sessions")
    messages: Mapped[list["ChatMessage"]] = relationship(
        "ChatMessage", back_populates="session",
        cascade="all, delete-orphan",
        order_by="ChatMessage.sequence_no",
    )

    def __repr__(self) -> str:
        return f"<ChatSession id={self.id} user_id={self.user_id}>"


# ---------------------------------------------------------------------------
# ChatMessage
# ---------------------------------------------------------------------------

class ChatMessage(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Individual turn (user or assistant) within a ChatSession.

    engine_calls  — JSONB blob: list of {function, inputs, result} dicts
                    recorded by CalculatorAgent for auditability.
    planner_plan  — JSONB blob: the structured plan the PlannerAgent produced
                    before dispatching to Calculator/Explainer.
    """
    __tablename__ = "chat_messages"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    # turn ordering (1-indexed per session)
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)

    role: Mapped[str] = mapped_column(
        Enum("user", "assistant", "system", name="message_role_enum"),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # Structured artefacts from the agent pipeline
    planner_plan: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True,
        comment="Raw JSON plan from PlannerAgent",
    )
    engine_calls: Mapped[Optional[list]] = mapped_column(
        JSONB, nullable=True,
        comment="List of {function, inputs, result} dispatched by CalculatorAgent",
    )

    # LLM cost tracking
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Feedback
    thumbs_up: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    feedback_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ── Relationship ──────────────────────────────────────────────────────
    session: Mapped["ChatSession"] = relationship(
        "ChatSession", back_populates="messages"
    )

    def __repr__(self) -> str:
        return (
            f"<ChatMessage session={self.session_id} "
            f"seq={self.sequence_no} role={self.role}>"
        )