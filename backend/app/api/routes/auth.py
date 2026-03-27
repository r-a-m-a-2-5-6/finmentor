"""
api/routes/auth.py
==================
Authentication and user profile endpoints.

  POST /auth/register   — create account
  POST /auth/login      — issue JWT
  GET  /auth/me         — current user
  PATCH /auth/profile   — upsert financial profile

Author : FinMentor Platform
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_db
from app.models.user import FinancialProfile, User
from app.schemas.auth import (
    LoginRequest, ProfileResponse, ProfileUpdateRequest,
    RegisterRequest, TokenResponse, UserResponse,
)
from app.utils.auth import (
    create_access_token, get_current_user,
    get_password_hash, verify_password,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


# ---------------------------------------------------------------------------
# POST /auth/register
# ---------------------------------------------------------------------------

@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new user account",
)
async def register(
    body: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> User:
    # Check duplicate email
    existing = await db.execute(
        select(User).where(User.email == body.email)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    user = User(
        email=body.email,
        hashed_password=get_password_hash(body.password),
        full_name=body.full_name,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


# ---------------------------------------------------------------------------
# POST /auth/login
# ---------------------------------------------------------------------------

@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Authenticate and receive a JWT",
)
async def login(
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await db.execute(
        select(User).where(User.email == body.email)
    )
    user: User | None = result.scalar_one_or_none()

    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated.",
        )

    token = create_access_token(subject=str(user.id))
    return {"access_token": token, "token_type": "bearer", "expires_in": 86400}


# ---------------------------------------------------------------------------
# GET /auth/me
# ---------------------------------------------------------------------------

@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get the currently authenticated user",
)
async def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


# ---------------------------------------------------------------------------
# PATCH /auth/profile
# ---------------------------------------------------------------------------

@router.patch(
    "/profile",
    response_model=ProfileResponse,
    summary="Create or update the user's financial profile",
)
async def upsert_profile(
    body: ProfileUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FinancialProfile:
    # Load existing profile (or create new)
    result = await db.execute(
        select(FinancialProfile).where(
            FinancialProfile.user_id == current_user.id
        )
    )
    profile: FinancialProfile | None = result.scalar_one_or_none()

    if profile is None:
        profile = FinancialProfile(user_id=current_user.id)
        db.add(profile)

    # Partial update — only write provided fields
    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(profile, field, value)

    await db.commit()
    await db.refresh(profile)
    return profile


# ---------------------------------------------------------------------------
# GET /auth/profile
# ---------------------------------------------------------------------------

@router.get(
    "/profile",
    response_model=ProfileResponse,
    summary="Get the user's financial profile",
)
async def get_profile(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FinancialProfile:
    result = await db.execute(
        select(FinancialProfile).where(
            FinancialProfile.user_id == current_user.id
        )
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Financial profile not found. Complete onboarding first.",
        )
    return profile