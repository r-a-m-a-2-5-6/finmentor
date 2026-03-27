"""schemas/__init__.py — re-export all schema classes for clean imports."""

from finmentor.backend.app.schemas.auth import (
    RegisterRequest, LoginRequest, TokenResponse,
    UserResponse, ProfileUpdateRequest, ProfileResponse,
)
from finmentor.backend.app.schemas.finance import (
    FIRERequest, FIREResponse, FIREMilestone,
    SIPMaturityRequest, SIPMaturityResponse,
    SIPRequiredRequest, SIPRequiredResponse,
    TaxCompareRequest, TaxCompareResponse, TaxRegimeDetail,
    PortfolioXRayRequest, PortfolioXRayResponse, AllocationDrift,
    HealthScoreResponse, HealthDimension,
)
from finmentor.backend.app.schemas.portfolio import (
    CreatePortfolioRequest, PortfolioResponse,
    AddHoldingRequest, HoldingResponse,
    AddCashFlowRequest, CashFlowResponse,
)
from finmentor.backend.app.schemas.chat import (
    MentorChatRequest, MentorChatResponse, EngineFunctionCall,
    SessionSummary, MessageResponse, MessageFeedbackRequest,
)

__all__ = [
    # auth
    "RegisterRequest", "LoginRequest", "TokenResponse",
    "UserResponse", "ProfileUpdateRequest", "ProfileResponse",
    # finance
    "FIRERequest", "FIREResponse", "FIREMilestone",
    "SIPMaturityRequest", "SIPMaturityResponse",
    "SIPRequiredRequest", "SIPRequiredResponse",
    "TaxCompareRequest", "TaxCompareResponse", "TaxRegimeDetail",
    "PortfolioXRayRequest", "PortfolioXRayResponse", "AllocationDrift",
    "HealthScoreResponse", "HealthDimension",
    # portfolio
    "CreatePortfolioRequest", "PortfolioResponse",
    "AddHoldingRequest", "HoldingResponse",
    "AddCashFlowRequest", "CashFlowResponse",
    # chat
    "MentorChatRequest", "MentorChatResponse", "EngineFunctionCall",
    "SessionSummary", "MessageResponse", "MessageFeedbackRequest",
]