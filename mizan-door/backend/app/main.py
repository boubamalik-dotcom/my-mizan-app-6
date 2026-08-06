"""FastAPI application entrypoint for the Mizan Door backend."""
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud, schemas
from app.core.config import settings
from app.core.database import Base, engine, get_db
from app.core.security import (
    create_access_token,
    get_current_user,
    require_clinic_access,
    verify_password,
)
from app.models.user import User
from app.socket_manager import ConnectionManager

manager = ConnectionManager()


async def _broadcast_clinic_queue(db: AsyncSession, clinic_id: uuid.UUID) -> list[schemas.QueueEntryResponse]:
    """Fetch a clinic's current queue, broadcast it, and return it (as response models)."""
    entries = await crud.get_clinic_queue(db, clinic_id)
    response = [schemas.QueueEntryResponse.model_validate(entry) for entry in entries]
    queue_payload = [entry.model_dump(mode="json") for entry in response]
    await manager.broadcast_queue_update(clinic_id, queue_payload)
    return response


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


@app.post(
    "/auth/register",
    response_model=schemas.TokenResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["auth"],
)
async def register(payload: schemas.RegisterRequest, db: AsyncSession = Depends(get_db)) -> schemas.TokenResponse:
    """Register a new clinic together with its first staff account (the receptionist)."""
    existing = await crud.get_user_by_email(db, payload.email)
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    clinic, user = await crud.register_clinic_with_owner(db, payload)
    token = create_access_token(user.id, clinic.id)
    return schemas.TokenResponse(
        access_token=token,
        user=schemas.UserResponse.model_validate(user),
        clinic=schemas.ClinicResponse.model_validate(clinic),
    )


@app.post("/auth/login", response_model=schemas.TokenResponse, tags=["auth"])
async def login(payload: schemas.LoginRequest, db: AsyncSession = Depends(get_db)) -> schemas.TokenResponse:
    user = await crud.get_user_by_email(db, payload.email)
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    clinic = await crud.get_clinic(db, user.clinic_id)
    if clinic is None:
        # Should never happen (FK + cascade delete keep this consistent), but
        # guard against it rather than returning a broken response.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clinic not found")

    token = create_access_token(user.id, clinic.id)
    return schemas.TokenResponse(
        access_token=token,
        user=schemas.UserResponse.model_validate(user),
        clinic=schemas.ClinicResponse.model_validate(clinic),
    )


@app.get("/auth/me", response_model=schemas.MeResponse, tags=["auth"])
async def me(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> schemas.MeResponse:
    clinic = await crud.get_clinic(db, current_user.clinic_id)
    if clinic is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clinic not found")
    return schemas.MeResponse(
        user=schemas.UserResponse.model_validate(current_user),
        clinic=schemas.ClinicResponse.model_validate(clinic),
    )


@app.get("/clinics", response_model=list[schemas.ClinicResponse], tags=["clinics"])
async def list_clinics(db: AsyncSession = Depends(get_db)) -> list[schemas.ClinicResponse]:
    clinics = await crud.list_clinics(db)
    return [schemas.ClinicResponse.model_validate(clinic) for clinic in clinics]


@app.get("/clinics/{clinic_id}", response_model=schemas.ClinicResponse, tags=["clinics"])
async def get_clinic(clinic_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> schemas.ClinicResponse:
    clinic = await crud.get_clinic(db, clinic_id)
    if clinic is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clinic not found")
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


@app.get("/patients/by-phone/{phone}", response_model=schemas.PatientResponse, tags=["patients"])
async def get_patient_by_phone(phone: str, db: AsyncSession = Depends(get_db)) -> schemas.PatientResponse:
    """Look up an existing patient by phone number, so the mobile app can let a
    returning patient join a queue without re-registering on a new device."""
    patient = await crud.get_patient_by_phone(db, phone)
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")
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
    response = schemas.QueueEntryResponse.model_validate(entry)

    # Broadcast so the dashboard updates the moment a patient joins, without
    # waiting for the next "Call Next Patient" click.
    await _broadcast_clinic_queue(db, clinic_id)

    return response


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
    clinic_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[schemas.QueueEntryResponse]:
    """Complete the current consultation, call the next patient, and broadcast the new queue.

    Staff-only: requires a valid login, and only for the clinic the
    authenticated user belongs to (a receptionist can't call patients for a
    different clinic).
    """
    require_clinic_access(current_user, clinic_id)

    clinic = await crud.get_clinic(db, clinic_id)
    if clinic is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clinic not found")

    await crud.advance_queue(db, clinic_id)
    return await _broadcast_clinic_queue(db, clinic_id)


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
