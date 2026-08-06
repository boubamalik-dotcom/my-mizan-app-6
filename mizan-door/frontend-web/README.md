# Mizan Door — Clinic Dashboard (Step 3)

React + TypeScript + Vite dashboard for clinic receptionists, built for **Step 3**
of the Mizan Door implementation plan.

## Stack

- [Vite](https://vitejs.dev/) + React + TypeScript
- [Tailwind CSS](https://tailwindcss.com/) v3 for styling
- [axios](https://axios-http.com/) for REST calls to the FastAPI backend
- [lucide-react](https://lucide.dev/) for icons
- The browser's native `WebSocket` API for real-time updates (no extra library needed)

## Setup

```bash
cd frontend-web
npm install
npm run dev
```

The app is served at `http://localhost:5173` and expects the backend
(`../backend`) to be running at `http://localhost:8000` (REST) /
`ws://localhost:8000` (WebSocket) — see `src/config.ts`.

```bash
npm run build     # type-check + production build to dist/
npm run preview   # preview the production build
```

## Folder structure

```
frontend-web/src/
├── main.tsx                    # React entrypoint
├── App.tsx                     # Selected-clinic state (persisted to localStorage)
├── config.ts                   # API_BASE_URL / WS_BASE_URL
├── types.ts                    # Clinic / Patient / QueueEntry / WS message types
├── api.ts                      # axios client + REST calls
├── hooks/
│   └── useClinicQueue.ts       # REST fetch + WebSocket subscription with auto-reconnect
└── components/
    ├── ClinicSelect.tsx        # Pick an existing clinic or register a new one
    ├── QueueDashboard.tsx      # Header, summary cards, "Call Next Patient", queue list
    ├── QueueEntryCard.tsx      # A single queue entry (ticket #, patient, urgent badge, status)
    └── ConnectionBadge.tsx     # "Live" / "Reconnecting…" WebSocket status indicator
```

## How it works

1. **Clinic selection** (`ClinicSelect`) acts as a lightweight "login" for the
   receptionist: it lists existing clinics (`GET /clinics`) to pick from, or
   lets you register a new one (`POST /clinics`). The backend doesn't yet have
   user accounts/auth (only clinic/patient/queue models), so this is a
   simplification — see "Known limitations" below. The chosen clinic is
   persisted to `localStorage` so it survives a page refresh.

2. **Dashboard** (`QueueDashboard`) shows:
   - The clinic's name/specialty and a live WebSocket connection badge.
   - "Currently serving" and "Waiting" summary cards.
   - A big **Call Next Patient** button (`POST /clinics/{clinic_id}/next`).
   - The active queue (`GET /clinics/{clinic_id}/queue` on load), with urgent
     patients flagged and sorted first.

3. **Real-time sync** (`useClinicQueue`): after the initial REST fetch, the
   dashboard opens `WS /ws/clinics/{clinic_id}` and listens for
   `{"event": "queue_updated", "clinic_id": ..., "queue": [...]}` messages,
   replacing its local queue state on every message — no polling or manual
   refresh needed. If the socket drops, it automatically reconnects after a
   short delay and shows "Reconnecting…" in the meantime.

## Known limitations (by design, for this step)

- **No real authentication.** The backend doesn't have clinic staff
  accounts; "selecting your clinic" is used as a stand-in for login. Adding
  real auth would be a backend change outside this step's scope.
- **No "add patient to queue" UI here.** Per the project plan, patients join
  the queue from the Flutter app (Step 4); this dashboard only *manages* an
  existing queue (view + call next).
