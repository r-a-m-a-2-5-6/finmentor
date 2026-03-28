"""
api/routes/mentor.py
====================
AI Mentor conversation endpoints.

  POST /mentor/chat                         — send message, get AI response
  GET  /mentor/sessions                     — list user's sessions
  GET  /mentor/sessions/{session_id}        — get session + messages
  DELETE /mentor/sessions/{session_id}      — delete session
  POST /mentor/sessions/{session_id}/messages/{message_id}/feedback — thumbs

Author : FinMentor Platform
"""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_db
from app.models.chat import ChatMessage, ChatSession
from app.models.user import User, FinancialProfile          # ← ADD FinancialProfile
from app.schemas.chat import (
    MentorChatRequest, MentorChatResponse,
    MessageFeedbackRequest, MessageResponse,
    SessionSummary,
)
from app.utils.auth import get_current_user

router = APIRouter(prefix="/mentor", tags=["AI Mentor"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_session_or_404(
    session_id: uuid.UUID,
    user: User,
    db: AsyncSession,
    load_messages: bool = False,
) -> ChatSession:
    q = select(ChatSession).where(
        ChatSession.id == session_id,
        ChatSession.user_id == user.id,
    )
    if load_messages:
        q = q.options(selectinload(ChatSession.messages))
    result = await db.execute(q)
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found.")
    return session


# ===========================================================================
# POST /mentor/chat
# ===========================================================================

@router.post(
    "/chat",
    response_model=MentorChatResponse,
    summary="Send a message to the AI mentor and receive a response",
)
async def mentor_chat(
    body: MentorChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MentorChatResponse:
    """
    Orchestrates the 3-agent pipeline:
        1. PlannerAgent  — extract structured intent + parameter dict
        2. CalculatorAgent — dispatch to finance engine functions
        3. ExplainerAgent  — compose India-context markdown response

    The full pipeline is implemented in finmentor.app.agents.orchestrator.
    This route wires HTTP I/O to the async orchestrator and persists the turn.
    """
    from app.agents.orchestrator import FinMentorOrchestrator

    # ── Fetch user's financial profile ────────────────────────────────────
    profile_result = await db.execute(
        select(FinancialProfile).where(FinancialProfile.user_id == current_user.id)
    )
    user_profile = profile_result.scalar_one_or_none()

    # ── Resolve or create session ─────────────────────────────────────────
    if body.session_id:
        session = await _get_session_or_404(body.session_id, current_user, db)
    else:
        session = ChatSession(user_id=current_user.id)
        db.add(session)
        await db.flush()   # get session.id before using it

    # ── Load message history for context ────────────────────────────────
    history_result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session.id)
        .order_by(ChatMessage.sequence_no)
        .limit(20)   # last 20 turns to stay within context window
    )
    history = history_result.scalars().all()

    history_dicts = [
        {"role": m.role, "content": m.content} for m in history
    ]

    # ── Persist user message ──────────────────────────────────────────────
    seq = session.message_count + 1
    user_msg = ChatMessage(
        session_id=session.id,
        sequence_no=seq,
        role="user",
        content=body.message,
    )
    db.add(user_msg)
    session.message_count = seq

    # ── Run orchestrator (now with user_profile) ─────────────────────────
    orchestrator = FinMentorOrchestrator()
    agent_response = await orchestrator.run(
        user_message=body.message,
        history=history_dicts,
        user_id=str(current_user.id),
        user_profile=user_profile,           # ← PASS PROFILE
    )

    # ── Persist assistant message ─────────────────────────────────────────
    assistant_seq = seq + 1
    assistant_msg = ChatMessage(
        session_id=session.id,
        sequence_no=assistant_seq,
        role="assistant",
        content=agent_response["content"],
        planner_plan=agent_response.get("planner_plan"),
        engine_calls=agent_response.get("engine_calls_raw"),
        prompt_tokens=agent_response.get("prompt_tokens", 0),
        completion_tokens=agent_response.get("completion_tokens", 0),
    )
    db.add(assistant_msg)
    session.message_count = assistant_seq
    session.total_tokens_used += (
        agent_response.get("prompt_tokens", 0)
        + agent_response.get("completion_tokens", 0)
    )

    # Auto-title from first user message
    if session.title is None and seq == 1:
        session.title = body.message[:80].strip()

    # Detect primary goal from planner plan
    if session.primary_goal is None and agent_response.get("planner_plan"):
        session.primary_goal = agent_response["planner_plan"].get("goal")

    await db.commit()
    await db.refresh(assistant_msg)

    return MentorChatResponse(
        session_id=session.id,
        message_id=assistant_msg.id,
        content=agent_response["content"],
        engine_calls=agent_response.get("engine_calls", []),
        suggested_follow_ups=agent_response.get("suggested_follow_ups", []),
        prompt_tokens=agent_response.get("prompt_tokens", 0),
        completion_tokens=agent_response.get("completion_tokens", 0),
    )


# ===========================================================================
# GET /mentor/sessions
# ===========================================================================

@router.get(
    "/sessions",
    response_model=list[SessionSummary],
    summary="List all chat sessions for the current user",
)
async def list_sessions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ChatSession]:
    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.user_id == current_user.id)
        .order_by(ChatSession.updated_at.desc())
    )
    return result.scalars().all()


# ===========================================================================
# GET /mentor/sessions/{session_id}
# ===========================================================================

@router.get(
    "/sessions/{session_id}",
    response_model=list[MessageResponse],
    summary="Get all messages in a chat session",
)
async def get_session_messages(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[MessageResponse]:

    session = await _get_session_or_404(
        session_id, current_user, db, load_messages=True
    )

    import json

    messages = []

    for msg in session.messages:
        engine_calls = msg.engine_calls
        if isinstance(engine_calls, str):
            try:
                engine_calls = json.loads(engine_calls)
            except Exception:
                engine_calls = []

        messages.append(
            MessageResponse(
                id=msg.id,
                session_id=msg.session_id,
                sequence_no=msg.sequence_no,
                role=msg.role,
                content=msg.content,
                planner_plan=msg.planner_plan or {},
                engine_calls=engine_calls,
                suggested_follow_ups=[],
                prompt_tokens=msg.prompt_tokens or 0,
                completion_tokens=msg.completion_tokens or 0,
                thumbs_up=msg.thumbs_up,
                created_at=msg.created_at,
            )
        )

    return messages


# ===========================================================================
# DELETE /mentor/sessions/{session_id}
# ===========================================================================

@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a chat session and all its messages",
)
async def delete_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    session = await _get_session_or_404(session_id, current_user, db)
    await db.delete(session)
    await db.commit()


# ===========================================================================
# POST /mentor/sessions/{session_id}/messages/{message_id}/feedback
# ===========================================================================

@router.post(
    "/sessions/{session_id}/messages/{message_id}/feedback",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Submit thumbs-up/down feedback on an assistant message",
)
async def message_feedback(
    session_id: uuid.UUID,
    message_id: uuid.UUID,
    body: MessageFeedbackRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    await _get_session_or_404(session_id, current_user, db)

    result = await db.execute(
        select(ChatMessage).where(
            ChatMessage.id == message_id,
            ChatMessage.session_id == session_id,
            ChatMessage.role == "assistant",
        )
    )
    message = result.scalar_one_or_none()
    if not message:
        raise HTTPException(
            status_code=404, detail="Assistant message not found."
        )

    message.thumbs_up = body.thumbs_up
    message.feedback_note = body.feedback_note
    await db.commit()