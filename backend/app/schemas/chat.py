"""
schemas/chat.py
===============
Pydantic v2 contracts for mentor chat endpoints.

  POST /mentor/chat      → MentorChatRequest  → MentorChatResponse
  GET  /mentor/sessions  → list[SessionSummary]
  GET  /mentor/sessions/{session_id}/messages → list[MessageResponse]

Author : FinMentor Platform
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Chat request / response
# ---------------------------------------------------------------------------

class MentorChatRequest(BaseModel):
    message: str = Field(
        min_length=1, max_length=4000,
        description="User's natural-language message to the AI mentor",
    )
    session_id: Optional[uuid.UUID] = Field(
        default=None,
        description="Pass null to start a new session, or UUID to continue one",
    )


class EngineFunctionCall(BaseModel):
    """Structured record of a single engine function dispatched by CalculatorAgent."""
    function_name: str
    inputs: dict[str, Any]
    result_summary: str   # human-readable one-liner, not the full dict


class MentorChatResponse(BaseModel):
    session_id: uuid.UUID
    message_id: uuid.UUID
    role: Literal["assistant"] = "assistant"
    content: str = Field(description="Explainer Agent's markdown-formatted reply")
    engine_calls: list[EngineFunctionCall] = Field(
        default_factory=list,
        description="Audit trail of calculator functions invoked",
    )
    suggested_follow_ups: list[str] = Field(
        default_factory=list,
        description="2-3 context-aware follow-up question suggestions",
    )
    prompt_tokens: int
    completion_tokens: int


# ---------------------------------------------------------------------------
# Session listing
# ---------------------------------------------------------------------------

class SessionSummary(BaseModel):
    id: uuid.UUID
    title: Optional[str]
    primary_goal: Optional[str]
    message_count: int
    total_tokens_used: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Message listing
# ---------------------------------------------------------------------------

class MessageResponse(BaseModel):
    id: uuid.UUID
    sequence_no: int
    role: Literal["user", "assistant", "system"]
    content: str
    planner_plan: Optional[dict[str, Any]]
    engine_calls: Optional[list[Any]]
    prompt_tokens: int
    completion_tokens: int
    thumbs_up: Optional[bool]
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Feedback
# ---------------------------------------------------------------------------

class MessageFeedbackRequest(BaseModel):
    thumbs_up: bool
    feedback_note: Optional[str] = Field(default=None, max_length=500)