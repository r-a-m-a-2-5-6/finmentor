"""
main.py
=======
FastAPI application factory, lifespan handler, CORS, and router registration.

Author : FinMentor Platform
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from finmentor.backend.app.config import settings
from finmentor.backend.app.db import engine
from finmentor.backend.app.models.base import Base


# ---------------------------------------------------------------------------
# Lifespan (startup / shutdown)
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup — create all tables (use Alembic in production)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    # Shutdown — dispose engine pool
    await engine.dispose()


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # ── CORS ─────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Global exception handler ─────────────────────────────────────────
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "An unexpected error occurred.", "type": type(exc).__name__},
        )

    # ── Routers ──────────────────────────────────────────────────────────
    from finmentor.backend.app.api.routes.auth import router as auth_router
    from finmentor.backend.app.api.routes.finance import (
        fire_router, sip_router, tax_router,
    )
    from finmentor.backend.app.api.routes.portfolio import router as portfolio_router
    from finmentor.backend.app.api.routes.mentor import router as mentor_router

    API_PREFIX = "/api/v1"

    app.include_router(auth_router,       prefix=API_PREFIX)
    app.include_router(fire_router,       prefix=API_PREFIX)
    app.include_router(sip_router,        prefix=API_PREFIX)
    app.include_router(tax_router,        prefix=API_PREFIX)
    app.include_router(portfolio_router,  prefix=API_PREFIX)
    app.include_router(mentor_router,     prefix=API_PREFIX)

    # ── Health check ─────────────────────────────────────────────────────
    @app.get("/health", tags=["System"])
    async def health():
        return {"status": "ok", "version": settings.APP_VERSION}

    return app


app = create_app()