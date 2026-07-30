"""
El Mizan Real Estate — Backend API
وسيط عقاري ذكي لمدينة وهران يعمل بمنطق الميزان
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.database import init_db


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Create database tables on startup."""
    init_db()
    yield


app = FastAPI(
    title="El Mizan Real Estate API",
    description="وسيط عقاري ذكي لمدينة وهران — منطق الميزان",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    """Root endpoint — app identity."""
    return {
        "app": "El Mizan Real Estate",
        "city": "Oran",
        "logic": "منطق الميزان",
        "message": "مرحباً بك في تطبيق الميزان العقاري",
    }


@app.get("/health")
def health_check():
    """Health check endpoint for monitoring and readiness probes."""
    return {
        "status": "ok",
        "service": "el-mizan-real-estate",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/v1/health")
def api_health_check():
    """Versioned API health check."""
    return {
        "status": "healthy",
        "api_version": "v1",
        "app": "El Mizan Real Estate",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
