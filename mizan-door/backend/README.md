# Mizan Door — Backend (Step 1 + Step 2 + Step 3 additions)

FastAPI backend for the Mizan Door smart virtual queue system for clinics.

- **Step 1**: project structure, PostgreSQL connection, SQLAlchemy models,
  Alembic migrations, and basic CRUD REST endpoints.
- **Step 2**: real-time engine — Redis pub/sub, a WebSocket `ConnectionManager`,
  `POST /clinics/{clinic_id}/next` to call the next patient, and
  `WS /ws/clinics/{clinic_id}` for live queue updates.
- **Step 3 additions**: `GET /clinics` and `GET /clinics/{clinic_id}`, plus
  broadcasting on `POST /clinics/{clinic_id}/queue` — added to support the
  React dashboard's clinic picker and its "updates the instant a patient
  joins" requirement (see `../frontend-web/`).

## Folder structure

```
backend/
├── app/
│   ├── main.py                # FastAPI app, lifespan (create_all + Redis), CORS, REST + WS routes
│   ├── schemas.py              # Pydantic request/response models
│   ├── crud.py                 # Async SQLAlchemy CRUD functions
│   ├── socket_manager.py       # ConnectionManager: WebSockets <-> Redis pub/sub bridge
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
- Redis 6+

## Setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# edit .env to point DATABASE_URL at your PostgreSQL instance,
# and REDIS_URL at your Redis instance
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
| GET | `/clinics` | List all clinics (used by the dashboard's clinic picker) |
| GET | `/clinics/{clinic_id}` | Get a single clinic |
| POST | `/patients` | Register a patient (`name`, `phone` — must be unique, `409` on duplicate) |
| POST | `/clinics/{clinic_id}/queue` | Add a patient to the clinic's queue (`patient_id`, `is_urgent`) — assigns the next ticket number (scoped per clinic, reset daily) and broadcasts the updated queue over the clinic's WebSocket |
| GET | `/clinics/{clinic_id}/queue` | Get the clinic's current active queue (`waiting` / `in_consultation` entries), urgent first, then by ticket number |

Health checks: `GET /` and `GET /health`.

Both `clinic_id` and `patient_id` are validated to exist; unknown ids return `404`.

### Calling the next patient — `POST /clinics/{clinic_id}/next`

Completes the patient currently `in_consultation` (if any) and promotes the
next `waiting` patient (urgent first, then by ticket number) to
`in_consultation`. Returns the clinic's updated active queue and also
broadcasts it in real time (see below).

## Real-time updates (WebSockets + Redis)

`app/socket_manager.py` defines `ConnectionManager`, which bridges WebSocket
clients to Redis pub/sub:

- Clients connect to `WS /ws/clinics/{clinic_id}` and are tracked in
  `active_connections: dict[UUID, list[WebSocket]]`.
- On the first connection for a given clinic, the manager subscribes to that
  clinic's Redis channel (`clinic_queue_{clinic_id}`) via `pubsub_listener`,
  which re-broadcasts every message it receives to that clinic's
  locally-connected WebSockets.
- `POST /clinics/{clinic_id}/next` calls `manager.broadcast_queue_update(...)`,
  which publishes the clinic's fresh queue state as JSON to
  `clinic_queue_{clinic_id}`:

  ```json
  {
    "event": "queue_updated",
    "clinic_id": "<uuid>",
    "queue": [ /* same shape as GET /clinics/{clinic_id}/queue */ ]
  }
  ```

Publishing through Redis (rather than broadcasting directly in-process) means
the dashboard and patient app stay in sync even if the API runs as multiple
replicas, since every replica's `pubsub_listener` receives the same message.

Disconnects are handled by catching `WebSocketDisconnect` in the `/ws/...`
endpoint and calling `manager.disconnect(...)`, which removes the socket from
`active_connections` and cancels that clinic's listener task once no clients
remain.

The Redis connection is opened in `lifespan` on startup
(`manager.connect_redis(...)`) and closed on shutdown
(`manager.close_redis()`, which also cancels any running listener tasks).

## Migrations

Generate a new migration after changing models:

```bash
alembic revision --autogenerate -m "describe the change"
alembic upgrade head
```

## What's next (Step 3 & 4)

- Step 3 — Clinic Dashboard: React + Vite + Tailwind app with login, queue
  list, "Call Next Patient" button, connected to the REST API and the
  `/ws/clinics/{clinic_id}` WebSocket for real-time sync.
- Step 4 — Patient App: Flutter + Riverpod app with queue join flow, triage
  questions, real-time ticket tracking via `web_socket_channel`, and
  push/local notifications.
