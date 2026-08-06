"""FastAPI application entrypoint for the Mizan Door backend."""
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud, schemas
from app.core.config import settings
from app.core.database import Base, engine, get_db
from app.socket_manager import ConnectionManager

manager = ConnectionManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Creates tables directly from the ORM models on startup. Handy for local
    # development; use Alembic migrations (see alembic/) for staging/production.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    await manager.connect_redis(settings.redis_url)
    yield
    await manager.close_redis()


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


@app.get("/", tags=["health"])
async def root() -> dict[str, str]:
    return {"app": settings.app_name, "status": "ok"}


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "healthy"}


@app.post("/clinics", response_model=schemas.ClinicResponse, status_code=status.HTTP_201_CREATED, tags=["clinics"])
async def create_clinic(payload: schemas.ClinicCreate, db: AsyncSession = Depends(get_db)) -> schemas.ClinicResponse:
    clinic = await crud.create_clinic(db, payload)
    return schemas.ClinicResponse.model_validate(clinic)


@app.post("/patients", response_model=schemas.PatientResponse, status_code=status.HTTP_201_CREATED, tags=["patients"])
async def create_patient(
    payload: schemas.PatientCreate, db: AsyncSession = Depends(get_db)
) -> schemas.PatientResponse:
    existing = await crud.get_patient_by_phone(db, payload.phone)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Patient with this phone already exists"
        )
    patient = await crud.create_patient(db, payload)
    return schemas.PatientResponse.model_validate(patient)


@app.post(
    "/clinics/{clinic_id}/queue",
    response_model=schemas.QueueEntryResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["queue"],
)
async def join_clinic_queue(
    clinic_id: uuid.UUID, payload: schemas.QueueEntryCreate, db: AsyncSession = Depends(get_db)
) -> schemas.QueueEntryResponse:
    clinic = await crud.get_clinic(db, clinic_id)
    if clinic is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clinic not found")

    patient = await crud.get_patient(db, payload.patient_id)
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")

    entry = await crud.add_patient_to_queue(db, clinic_id, payload.patient_id, payload.is_urgent)
    return schemas.QueueEntryResponse.model_validate(entry)


@app.get(
    "/clinics/{clinic_id}/queue",
    response_model=list[schemas.QueueEntryResponse],
    tags=["queue"],
)
async def get_clinic_queue(clinic_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> list[schemas.QueueEntryResponse]:
    clinic = await crud.get_clinic(db, clinic_id)
    if clinic is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clinic not found")

    entries = await crud.get_clinic_queue(db, clinic_id)
    return [schemas.QueueEntryResponse.model_validate(entry) for entry in entries]


@app.post(
    "/clinics/{clinic_id}/next",
    response_model=list[schemas.QueueEntryResponse],
    tags=["queue"],
)
async def call_next_patient(
    clinic_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> list[schemas.QueueEntryResponse]:
    """Complete the current consultation, call the next patient, and broadcast the new queue."""
    clinic = await crud.get_clinic(db, clinic_id)
    if clinic is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clinic not found")

    await crud.advance_queue(db, clinic_id)

    entries = await crud.get_clinic_queue(db, clinic_id)
    response = [schemas.QueueEntryResponse.model_validate(entry) for entry in entries]

    queue_payload = [entry.model_dump(mode="json") for entry in response]
    await manager.broadcast_queue_update(clinic_id, queue_payload)

    return response


@app.websocket("/ws/clinics/{clinic_id}")
async def clinic_queue_websocket(websocket: WebSocket, clinic_id: uuid.UUID) -> None:
    """Real-time queue updates for a clinic, consumed by the dashboard and patient app."""
    await manager.connect(websocket, clinic_id)
    try:
        while True:
            # Clients don't need to send anything; this just keeps the
            # connection open and detects disconnects.
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, clinic_id)
