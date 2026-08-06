# Mizan Door — Backend (Step 1: Setup & Database)

FastAPI backend for the Mizan Door smart virtual queue system for clinics.

This is **Step 1** of the implementation plan: project structure, PostgreSQL
connection, SQLAlchemy models, Alembic migrations, and basic CRUD REST
endpoints. WebSockets and Redis pub/sub for real-time updates land in Step 2.

## Folder structure

```
backend/
├── app/
│   ├── main.py                # FastAPI app, CORS, router registration
│   ├── core/
│   │   ├── config.py          # Settings loaded from environment (.env)
│   │   └── database.py        # Async SQLAlchemy engine/session, Base, get_db()
│   ├── models/                # SQLAlchemy ORM models
│   │   ├── clinic.py
│   │   ├── patient.py
│   │   └── queue_entry.py
│   ├── schemas/                # Pydantic request/response schemas
│   │   ├── clinic.py
│   │   ├── patient.py
│   │   └── queue_entry.py
│   ├── crud/                   # Database access functions
│   │   ├── clinic.py
│   │   ├── patient.py
│   │   └── queue_entry.py
│   └── routers/                 # FastAPI routers (REST endpoints)
│       ├── clinics.py
│       ├── patients.py
│       └── queue.py
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

### Clinics — `/api/v1/clinics`

| Method | Path | Description |
|---|---|---|
| POST | `/` | Create a clinic |
| GET | `/` | List clinics |
| GET | `/{clinic_id}` | Get a clinic |
| PATCH | `/{clinic_id}` | Update a clinic |
| DELETE | `/{clinic_id}` | Delete a clinic |

### Patients — `/api/v1/patients`

| Method | Path | Description |
|---|---|---|
| POST | `/` | Register a patient (phone must be unique) |
| GET | `/` | List patients |
| GET | `/{patient_id}` | Get a patient |
| PATCH | `/{patient_id}` | Update a patient |
| DELETE | `/{patient_id}` | Delete a patient |

### Queue — `/api/v1/queue`

| Method | Path | Description |
|---|---|---|
| POST | `/` | Join a clinic's queue (`clinic_id`, `patient_id`, `is_urgent`) — assigns the next ticket number |
| GET | `/clinic/{clinic_id}` | List a clinic's queue (defaults to today only), urgent first |
| GET | `/{entry_id}` | Get a queue entry |
| PATCH | `/{entry_id}` | Update status (`waiting` \| `in_consultation` \| `completed` \| `cancelled`) or urgency |
| DELETE | `/{entry_id}` | Remove a queue entry |

Health checks: `GET /` and `GET /health`.

## Migrations

Generate a new migration after changing models:

```bash
alembic revision --autogenerate -m "describe the change"
alembic upgrade head
```

## What's next (Step 2)

- Redis connection and pub/sub.
- `ConnectionManager` for WebSocket clients.
- `POST /api/v1/clinics/{clinic_id}/next` to call the next patient (updates DB + publishes to Redis).
- `WS /ws/clinics/{clinic_id}` for the dashboard and patient app to receive real-time updates.
