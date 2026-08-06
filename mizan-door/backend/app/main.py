from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import init_db
from app.routers import clinics, patients, queue


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Convenient for local development. In staging/production, schema changes
    # should be applied via Alembic migrations instead (see alembic/).
    if settings.debug:
        await init_db()
    yield


app = FastAPI(
    title=settings.app_name,
    description="Smart virtual queue management API for medical clinics.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(clinics.router)
app.include_router(patients.router)
app.include_router(queue.router)


@app.get("/", tags=["health"])
async def root() -> dict[str, str]:
    return {"app": settings.app_name, "status": "ok"}


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "healthy"}
