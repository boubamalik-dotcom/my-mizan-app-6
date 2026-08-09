"""Layer 2 — master API router.

Aggregates every feature router under a single object that `main.py`
mounts onto the FastAPI app, so `main.py` never needs to know about
individual feature routes.
"""
from __future__ import annotations

from fastapi import APIRouter

from .audit.audit_routes import router as audit_router
from .auth.auth_routes import router as auth_router
from .routes.chat_routes import router as chat_router
from .routes.queue_routes import router as queue_router
from .routes.wallet_routes import router as wallet_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(audit_router)
api_router.include_router(chat_router)
api_router.include_router(queue_router)
api_router.include_router(wallet_router)
