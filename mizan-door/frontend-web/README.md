# Mizan Door — Clinic Dashboard (Step 3)

React + TypeScript + Vite dashboard for clinic receptionists, built for **Step 3**
of the Mizan Door implementation plan.

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
├── App.tsx                     # Selected-clinic state (persisted to localStorage)
├── config.ts                   # API_BASE_URL / WS_BASE_URL
├── types.ts                    # Clinic / Patient / QueueEntry / WS message types
├── api.ts                      # axios client + REST calls
├── i18n/
│   ├── i18n.ts                 # i18next setup, default language (fr), <html dir/lang> sync
│   ├── fr.json                 # French translations (default language)
│   └── ar.json                 # Arabic translations
├── hooks/
│   └── useClinicQueue.ts       # REST fetch + WebSocket subscription with auto-reconnect
└── components/
    ├── ClinicSelect.tsx        # Pick an existing clinic or register a new one
    ├── QueueDashboard.tsx      # Header, summary cards, "Call Next Patient", queue list
    ├── QueueEntryCard.tsx      # A single queue entry (ticket #, patient, urgent badge, status)
    ├── ConnectionBadge.tsx     # "Live" / "Reconnecting…" WebSocket status indicator
    └── LanguageToggle.tsx      # FR/AR switcher (in the dashboard header and clinic-select screen)
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
- `LanguageToggle` (FR/AR buttons) appears in the clinic-selection screen and
  in the dashboard header.
- Tailwind v3.3+'s logical-property utilities (`text-start`/`text-end`,
  `ms-*`/`me-*`, `ps-*`/`pe-*`) are used instead of physical ones
  (`text-left`/`right`, `ml-*`/`mr-*`, `pl-*`/`pr-*`) so spacing/alignment
  automatically flips under `dir="rtl"`. Flex layouts (`flex-row`, the
  default) already reverse visually under RTL per the CSS spec, with no
  extra classes needed.

## Known limitations (by design, for this step)

- **No real authentication.** The backend doesn't have clinic staff
  accounts; "selecting your clinic" is used as a stand-in for login. Adding
  real auth would be a backend change outside this step's scope.
- **No "add patient to queue" UI here.** Per the project plan, patients join
  the queue from the Flutter app (Step 4); this dashboard only *manages* an
  existing queue (view + call next).
