# Mizan Door — Smart Virtual Queue SaaS for Clinics

Real-time virtual queue management for medical clinics: patients join a
queue from a mobile app and track their turn live, while clinic staff manage
the flow from a web dashboard.

This project is being built incrementally. Each step below will get its own
subfolder here.

## Implementation plan

- [x] **Step 1 — Backend Setup & Database** (`backend/`): FastAPI project
      structure, async PostgreSQL connection (SQLAlchemy + asyncpg), ORM
      models (`Clinic`, `Patient`, `QueueEntry`), Alembic migrations, and
      basic CRUD REST endpoints.
- [x] **Step 2 — Real-time Engine** (`backend/app/socket_manager.py`): Redis
      pub/sub connection, `ConnectionManager` for WebSockets,
      `POST /clinics/{clinic_id}/next` (updates DB + publishes to Redis),
      `WS /ws/clinics/{clinic_id}` for live queue updates. Joining the queue
      (`POST /clinics/{clinic_id}/queue`) also broadcasts, so the dashboard
      updates the instant a patient joins, not just on "Call Next Patient".
- [x] **Step 3 — Clinic Dashboard** (`frontend-web/`): React + Vite +
      TypeScript + Tailwind app with staff login/registration, a live queue
      list, a "Call Next Patient" button, and real-time sync over the
      `/ws/clinics/{clinic_id}` WebSocket.
- [x] **Step 4 — Patient App** (`frontend_mobile/`): Flutter + Riverpod app
      with clinic selection, a returning-patient-aware join flow, a 2-part
      smart triage that sets the urgent flag, and real-time ticket tracking
      over the `/ws/clinics/{clinic_id}` WebSocket, with an in-app "your
      turn is near" alert in place of native push notifications (see
      `frontend_mobile/README.md` for why).

All four MVP steps are implemented. See `backend/README.md`,
`frontend-web/README.md`, and `frontend_mobile/README.md` for setup and
implementation details on each piece.

## Authentication

Clinic staff (receptionists) have real accounts: email + password, hashed
with `bcrypt`, and JWT-based sessions (`app/core/security.py`). Registering
a clinic (`POST /auth/register`) creates the clinic and its first staff
account together; `POST /clinics/{clinic_id}/next` (calling the next
patient) requires a valid token *for that clinic*. Patients are
intentionally not authenticated — they only ever provide name + phone, per
the original spec ("Simple authentication for the clinic receptionist").
See `backend/README.md`'s "Authentication" section for the full design and
known limitations (no refresh tokens, no login rate limiting, no patient
identity verification).

## Internationalization

Both frontends support **French** (default) and **Arabic** (with automatic
right-to-left layout), switchable via an in-app language toggle:
`frontend-web` uses `i18next`/`react-i18next` with a `dir`-attribute sync on
`<html>`; `frontend_mobile` uses `easy_localization`, relying on Flutter's
built-in RTL handling for `Locale('ar')`. See the "Internationalization"
section in each app's README for details.
