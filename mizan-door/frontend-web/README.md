# Mizan Door — Clinic Dashboard

React + TypeScript + Vite dashboard for clinic receptionists.

## Stack

- [Vite](https://vitejs.dev/) + React + TypeScript
- [Tailwind CSS](https://tailwindcss.com/) v3 for styling
- [axios](https://axios-http.com/) for REST calls to the FastAPI backend
- [lucide-react](https://lucide.dev/) for icons
- [i18next](https://www.i18next.com/) + [react-i18next](https://react.i18next.com/) for French/Arabic translations and RTL support
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
├── main.tsx                    # React entrypoint (imports i18n/i18n.ts)
├── App.tsx                     # Auth session state (persisted to localStorage), routes to AuthScreen/QueueDashboard
├── config.ts                   # API_BASE_URL / WS_BASE_URL
├── types.ts                    # Clinic / Patient / User / AuthSession / QueueEntry / WS message types
├── api.ts                      # axios client + REST calls + bearer-token header helper
├── i18n/
│   ├── i18n.ts                 # i18next setup, default language (fr), <html dir/lang> sync
│   ├── fr.json                 # French translations (default language)
│   └── ar.json                 # Arabic translations
├── hooks/
│   └── useClinicQueue.ts       # REST fetch + WebSocket subscription with auto-reconnect
└── components/
    ├── AuthScreen.tsx          # Login / "register a new clinic" screen (real auth, see below)
    ├── QueueDashboard.tsx      # Header, summary cards, "Call Next Patient", queue list, logout
    ├── QueueEntryCard.tsx      # A single queue entry (ticket #, patient, urgent badge, status)
    ├── ConnectionBadge.tsx     # "Live" / "Reconnecting…" WebSocket status indicator
    └── LanguageToggle.tsx      # FR/AR switcher (on the auth screen and the dashboard header)
```

## How it works

1. **Authentication** (`AuthScreen`): a real login/registration screen for
   clinic staff — see "Authentication" below.

2. **Dashboard** (`QueueDashboard`) shows:
   - The clinic's name/specialty and a live WebSocket connection badge.
   - "Currently serving" and "Waiting" summary cards.
   - A big **Call Next Patient** button (`POST /clinics/{clinic_id}/next`,
     sent with the staff member's bearer token).
   - The active queue (`GET /clinics/{clinic_id}/queue` on load), with urgent
     patients flagged and sorted first.
   - A **Déconnexion / تسجيل الخروج (Logout)** button.

3. **Real-time sync** (`useClinicQueue`): after the initial REST fetch, the
   dashboard opens `WS /ws/clinics/{clinic_id}` and listens for
   `{"event": "queue_updated", "clinic_id": ..., "queue": [...]}` messages,
   replacing its local queue state on every message — no polling or manual
   refresh needed. If the socket drops, it automatically reconnects after a
   short delay and shows "Reconnecting…" in the meantime.

## Authentication

`AuthScreen` replaces the earlier "pick your clinic from a list" placeholder
with real login/registration against the backend's JWT-based staff auth
(see `../backend/README.md`'s "Authentication" section):

- **Login tab**: email + password → `POST /auth/login`.
- **"Nouvelle clinique" (register) tab**: clinic name, specialty, staff name,
  email, password → `POST /auth/register`, which creates the clinic and this
  first staff account together.
- On success, `{ access_token, user, clinic }` is stored in `localStorage`
  (`mizan-door.auth-session`) and the token is attached as
  `Authorization: Bearer <token>` on all subsequent API calls
  (`setAuthToken` in `api.ts`, called from `App.tsx`).
- On load, if a session is cached, `App.tsx` calls `GET /auth/me` to confirm
  the token is still valid before trusting it (tokens expire after 12 hours
  by default) — an expired/invalid token clears the cached session and shows
  the login screen again. `QueueDashboard` does the same if a `401` comes
  back from `POST /clinics/{clinic_id}/next` mid-session.
- **Logout** clears the stored session and the `Authorization` header.

Patients never log in — `GET /clinics`, `POST /patients`,
`POST /clinics/{clinic_id}/queue`, and `GET /clinics/{clinic_id}/queue`
remain public, since the mobile patient app relies on them without any staff
credentials.

## Internationalization (French / Arabic) & RTL

- `src/i18n/i18n.ts` initializes `i18next` with `fr` (default) and `ar`
  resources, persists the chosen language to `localStorage`
  (`mizan-door.language`), and keeps `<html dir="..." lang="...">` in sync
  with the active language on every change — `ar` sets `dir="rtl"`, `fr`
  sets `dir="ltr"`.
- All UI copy is translated via `useTranslation()`/`t('namespace.key')`
  (see `src/i18n/fr.json` / `ar.json` for the full key list). Clinic/patient
  data (names, specialties, phone numbers) is real user data from the
  backend and is intentionally **not** translated.
- `LanguageToggle` (FR/AR buttons) appears on the auth screen and in the
  dashboard header.
- Tailwind v3.3+'s logical-property utilities (`text-start`/`text-end`,
  `ms-*`/`me-*`, `ps-*`/`pe-*`) are used instead of physical ones
  (`text-left`/`right`, `ml-*`/`mr-*`, `pl-*`/`pr-*`) so spacing/alignment
  automatically flips under `dir="rtl"`. Flex layouts (`flex-row`, the
  default) already reverse visually under RTL per the CSS spec, with no
  extra classes needed.

## Known limitations (by design)

- **No "add patient to queue" UI here.** Per the project plan, patients join
  the queue from the Flutter app; this dashboard only *manages* an existing
  queue (view + call next).
- **No token refresh/revocation UI.** A session simply expires after 12
  hours and the receptionist has to log in again; there's no "remember me"
  or refresh-token flow (matches the backend's current scope).
