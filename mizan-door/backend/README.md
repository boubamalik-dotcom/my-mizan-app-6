# Mizan Door — Backend (Step 1: Setup & Database)

FastAPI backend for the Mizan Door smart virtual queue system for clinics.

This is **Step 1** of the implementation plan: project structure, PostgreSQL
connection, SQLAlchemy models, Alembic migrations, and basic CRUD REST
endpoints. WebSockets and Redis pub/sub for real-time updates land in Step 2.

## Folder structure

```
backend/
├── app/
│   ├── main.py                # FastAPI app, lifespan (create_all), CORS, REST routes
│   ├── schemas.py              # Pydantic request/response models
│   ├── crud.py                 # Async SQLAlchemy CRUD functions
│   ├── core/
│   │   ├── config.py          # Settings loaded from environment (.env)
│   │   └── database.py        # Async SQLAlchemy engine/session, Base, get_db()
│   └── models/                 # SQLAlchemy ORM models
│       ├── clinic.py
│       ├── patient.py
│       └── queue_entry.py
├── alembic/                     # Database migrations
│   ├── env.py
│   └── versions/
├── alembic.ini
├── requirements.txt
└── .env.example
```

## Requirements

- Python 3.11+
- PostgreSQL 14+

## Setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# edit .env to point DATABASE_URL at your PostgreSQL instance
```

Create the database (adjust user/password as needed):

```bash
createdb mizan_door
# or: psql -U postgres -c "CREATE DATABASE mizan_door;"
```

Apply migrations:

```bash
alembic upgrade head
```

Run the API:

```bash
uvicorn app.main:app --reload
```

The API is served at `http://localhost:8000`. Interactive docs are available
at `http://localhost:8000/docs`.

> In debug mode (`DEBUG=true`), the app also calls `create_all()` on startup
> as a convenience for local development. Alembic migrations are the source
> of truth for schema changes and should be used in staging/production.

## Database models

| Model | Table | Fields |
|---|---|---|
| `Clinic` | `clinics` | `id` (UUID), `name`, `specialty`, `created_at` |
| `Patient` | `patients` | `id` (UUID), `name`, `phone` (unique), `created_at` |
| `QueueEntry` | `queue_entries` | `id` (UUID), `clinic_id` (FK), `patient_id` (FK), `queue_number`, `status` (`waiting` \| `in_consultation` \| `completed` \| `cancelled`), `is_urgent`, `joined_at` |

`queue_number` is assigned automatically per clinic, resetting daily (based on
`joined_at`). Queue listings sort urgent entries first, then by ticket number.

## REST API

| Method | Path | Description |
|---|---|---|
| POST | `/clinics` | Create a clinic (`name`, `specialty`) |
| POST | `/patients` | Register a patient (`name`, `phone` — must be unique, `409` on duplicate) |
| POST | `/clinics/{clinic_id}/queue` | Add a patient to the clinic's queue (`patient_id`, `is_urgent`) — assigns the next ticket number, scoped per clinic and reset daily |
| GET | `/clinics/{clinic_id}/queue` | Get the clinic's current active queue (`waiting` / `in_consultation` entries), urgent first, then by ticket number |

Health checks: `GET /` and `GET /health`.

Both `clinic_id` and `patient_id` are validated to exist; unknown ids return `404`.

## Migrations

Generate a new migration after changing models:

```bash
alembic revision --autogenerate -m "describe the change"
alembic upgrade head
```

## What's next (Step 2)

- Redis connection and pub/sub.
- `ConnectionManager` for WebSocket clients.
- `POST /clinics/{clinic_id}/next` to call the next patient (updates DB + publishes to Redis).
- `WS /ws/clinics/{clinic_id}` for the dashboard and patient app to receive real-time updates.
