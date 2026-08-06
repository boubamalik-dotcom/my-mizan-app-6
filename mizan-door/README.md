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
      TypeScript + Tailwind app with clinic selection, a live queue list,
      a "Call Next Patient" button, and real-time sync over the
      `/ws/clinics/{clinic_id}` WebSocket.
- [ ] **Step 4 — Patient App** (`mobile_app/`): Flutter + Riverpod app with
      queue join flow, triage questions, real-time ticket tracking, and
      push/local notifications.

See `backend/README.md` for details on the current step.
