# Mizan Door — Backend

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
- **Step 4 addition**: `GET /patients/by-phone/{phone}` — lets the Flutter
  app reuse an existing patient record by phone number instead of hitting
  the unique-phone `409` when a returning patient joins from a new device
  (see `../frontend_mobile/`).
- **Staff authentication**: real accounts (email + password + JWT) for clinic
  staff, replacing the earlier "just pick a clinic" placeholder. See
  "Authentication" below.

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
│   │   ├── database.py        # Async SQLAlchemy engine/session, Base, get_db()
│   │   └── security.py        # Password hashing, JWT issuing/verification, get_current_user
│   └── models/                 # SQLAlchemy ORM models
│       ├── clinic.py
│       ├── patient.py
│       ├── queue_entry.py
│       └── user.py             # Clinic staff account (email/password, belongs to one clinic)
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
# REDIS_URL at your Redis instance, and set a real JWT_SECRET_KEY
# (see "Authentication" below - the default is dev-only and insecure)
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
| `User` | `users` | `id` (UUID), `clinic_id` (FK), `email` (unique), `hashed_password`, `full_name`, `created_at` — a clinic staff account |

`queue_number` is assigned automatically per clinic, resetting daily (based on
`joined_at`). Queue listings sort urgent entries first, then by ticket number.

## REST API

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/auth/register` | — | Create a clinic **and** its first staff account together (`clinic_name`, `specialty`, `full_name`, `email`, `password`) — returns a JWT + user + clinic. `409` if the email is already registered |
| POST | `/auth/login` | — | Log in with `email` + `password` — returns a JWT + user + clinic. `401` on invalid credentials |
| GET | `/auth/me` | 🔒 | Get the authenticated user + their clinic |
| GET | `/clinics` | — | List all clinics (used by the patient app's clinic picker) |
| GET | `/clinics/{clinic_id}` | — | Get a single clinic |
| POST | `/patients` | — | Register a patient (`name`, `phone` — must be unique, `409` on duplicate) |
| GET | `/patients/by-phone/{phone}` | — | Look up an existing patient by phone (used by the mobile app so a returning patient can join from a new device without re-registering) |
| POST | `/clinics/{clinic_id}/queue` | — | Add a patient to the clinic's queue (`patient_id`, `is_urgent`) — assigns the next ticket number (scoped per clinic, reset daily) and broadcasts the updated queue over the clinic's WebSocket |
| GET | `/clinics/{clinic_id}/queue` | — | Get the clinic's current active queue (`waiting` / `in_consultation` entries), urgent first, then by ticket number |
| POST | `/clinics/{clinic_id}/next` | 🔒 | Call the next patient (see below) |

🔒 = requires `Authorization: Bearer <token>`. Endpoints without 🔒 are
intentionally public — patients never log in in this design (see
"Authentication" below).

Health checks: `GET /` and `GET /health`.

Both `clinic_id` and `patient_id` are validated to exist; unknown ids return `404`.

### Calling the next patient — `POST /clinics/{clinic_id}/next`

Staff-only. Completes the patient currently `in_consultation` (if any) and
promotes the next `waiting` patient (urgent first, then by ticket number) to
`in_consultation`. Returns the clinic's updated active queue and also
broadcasts it in real time (see below). Requires a valid token *for that
clinic* — a receptionist authenticated for one clinic gets `403` if they try
to call patients for a different `clinic_id`.

## Authentication

Clinic staff (e.g. receptionists) now have real accounts instead of the
earlier "just pick a clinic from a list" placeholder:

- **Registering a clinic** (`POST /auth/register`) creates the `Clinic` row
  and its first `User` in one transaction, so a clinic always has at least
  one owner account. There's no separate "create a clinic with no staff"
  endpoint anymore.
- **Passwords** are hashed with `bcrypt` (`app/core/security.py`) — never
  stored or returned in plaintext.
- **Tokens** are signed JWTs (`PyJWT`, HS256) containing the user id and
  clinic id, valid for `ACCESS_TOKEN_EXPIRE_MINUTES` (default 12 hours — about
  one staff shift). `get_current_user` (a FastAPI dependency) decodes the
  `Authorization: Bearer <token>` header and loads the `User`; 🔒 routes use
  it, plus `require_clinic_access` to enforce the token's `clinic_id` matches
  the `clinic_id` in the URL.
- **`JWT_SECRET_KEY`** defaults to an insecure dev value
  (`dev-insecure-secret-change-in-production`) — **always** override it via
  the environment in any shared/deployed environment; anyone who knows this
  secret can forge a valid staff token for any clinic.
- **Patients are intentionally not authenticated.** The original spec only
  calls for receptionist login ("Simple authentication for the clinic
  receptionist"); patient identity is just name + phone (see
  `../frontend_mobile/README.md`'s "Known limitations" for the tradeoffs of
  that design).

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

## Known limitations

- No refresh tokens or token revocation (e.g. no way to invalidate a token
  before it expires, such as on password change) — acceptable for an MVP
  with a 12-hour expiry, but worth adding before a real production launch.
- No rate limiting on `/auth/login` (brute-force protection).
- No patient identity verification (no OTP/SMS) — see
  `../frontend_mobile/README.md`.
