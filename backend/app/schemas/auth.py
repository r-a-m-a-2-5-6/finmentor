"""
schemas/auth.py
===============
Pydantic v2 request/response contracts for auth and user profile endpoints.

  POST /auth/register  → RegisterRequest  → UserResponse
  POST /auth/login     → LoginRequest     → TokenResponse
  PATCH /auth/profile  → ProfileUpdateRequest → ProfileResponse

Author : FinMentor Platform
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: Optional[str] = Field(default=None, max_length=255)

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit.")
        if not any(c.isalpha() for c in v):
            raise ValueError("Password must contain at least one letter.")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(description="Seconds until expiry")


class UserResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    full_name: Optional[str]
    is_active: bool
    is_verified: bool

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Financial Profile  (PATCH /auth/profile)
# ---------------------------------------------------------------------------

class ProfileUpdateRequest(BaseModel):
    """
    All fields optional — supports partial PATCH semantics.
    Only provided fields are written to the database.
    """
    current_age: Optional[int] = Field(default=None, ge=18, le=80)
    target_retirement_age: Optional[int] = Field(default=None, ge=19, le=90)
    life_expectancy: Optional[int] = Field(default=None, ge=50, le=110)

    monthly_income: Optional[Decimal] = Field(default=None, ge=0)
    monthly_expenses: Optional[Decimal] = Field(default=None, ge=0)
    monthly_emi: Optional[Decimal] = Field(default=None, ge=0)
    monthly_insurance_premium: Optional[Decimal] = Field(default=None, ge=0)

    current_corpus: Optional[Decimal] = Field(default=None, ge=0)
    existing_emergency_fund: Optional[Decimal] = Field(default=None, ge=0)

    risk_profile: Optional[Literal["conservative", "moderate", "aggressive"]] = None
    job_stability: Optional[Literal[
        "stable", "semi_stable", "unstable", "self_employed"
    ]] = None
    dependents: Optional[int] = Field(default=None, ge=0, le=20)
    metro_city: Optional[bool] = None

    gross_annual_income: Optional[Decimal] = Field(default=None, ge=0)
    preferred_tax_regime: Optional[Literal["old", "new"]] = None

    @model_validator(mode="after")
    def retirement_age_gt_current(self) -> "ProfileUpdateRequest":
        if (
            self.current_age is not None
            and self.target_retirement_age is not None
            and self.target_retirement_age <= self.current_age
        ):
            raise ValueError("target_retirement_age must be greater than current_age.")
        return self


class ProfileResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    current_age: Optional[int]
    target_retirement_age: Optional[int]
    life_expectancy: int
    monthly_income: Optional[Decimal]
    monthly_expenses: Optional[Decimal]
    monthly_emi: Decimal
    monthly_insurance_premium: Decimal
    current_corpus: Decimal
    existing_emergency_fund: Decimal
    risk_profile: Optional[str]
    job_stability: str
    dependents: int
    metro_city: bool
    gross_annual_income: Optional[Decimal]
    preferred_tax_regime: str

    model_config = {"from_attributes": True}