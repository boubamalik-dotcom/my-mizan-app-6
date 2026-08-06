# Mizan Door — Patient App (Step 4)

Flutter app patients use to join a clinic's virtual queue and track their
turn in real time, built for **Step 4** of the Mizan Door implementation
plan.

## Stack

- Flutter + Dart
- [flutter_riverpod](https://riverpod.dev/) for state management
- [http](https://pub.dev/packages/http) for REST calls to the FastAPI backend
- [web_socket_channel](https://pub.dev/packages/web_socket_channel) for real-time queue updates
- [shared_preferences](https://pub.dev/packages/shared_preferences) — added beyond the requested list to
  persist the patient's identity and in-progress queue visit locally, so the
  app can resume tracking after being closed and reopened, and a returning
  patient doesn't have to re-register

## Setup

```bash
cd frontend_mobile
flutter pub get
flutter run          # pick a connected device/emulator/simulator, or Chrome
```

The app expects the backend (`../backend`) to be running at port 8000 — see
`lib/config/constants.dart`.

## Configuration — `lib/config/constants.dart`

```dart
String get apiBaseUrl => 'http://$_host:8000';
String get wsBaseUrl => 'ws://$_host:8000';
```

`_host` is resolved automatically based on platform, since the right address
for reaching your host machine's backend differs by target:

| Target | Host used |
|---|---|
| Android emulator | `10.0.2.2` (the emulator's alias for the host machine — `localhost` inside the emulator refers to the emulator itself, not your machine) |
| iOS simulator, Flutter web, desktop | `127.0.0.1` (these share the host machine's network directly) |
| Physical device | Neither works — edit `_host` to your machine's LAN IP address |

**Platform-specific caveats for local HTTP:** since the backend runs over
plain HTTP/WS (no TLS) in local development, two OS-level protections had to
be relaxed for dev builds:
- **Android**: `android:usesCleartextTraffic="true"` in
  `android/app/src/main/AndroidManifest.xml` (Android blocks cleartext
  traffic by default since API 28), plus the `INTERNET` permission (present
  by default only in debug/profile manifests, added here to the main one too
  so release builds can reach the backend as well).
- **iOS**: `NSAppTransportSecurity` / `NSAllowsLocalNetworking` in
  `ios/Runner/Info.plist` (App Transport Security blocks non-HTTPS by
  default; this exception only covers loopback addresses).

Switch the backend to HTTPS/WSS and remove both before shipping to
production.

## Folder structure

```
frontend_mobile/lib/
├── main.dart                        # Riverpod ProviderScope, MaterialApp, session-based routing
├── config/
│   └── constants.dart                # apiBaseUrl / wsBaseUrl / nearTurnThreshold
├── models/
│   ├── clinic.dart, patient.dart, queue_entry.dart   # Mirror the backend's schemas
├── services/
│   └── api_service.dart              # http calls: listClinics, registerPatient, joinQueue, ...
├── providers/
│   ├── api_providers.dart            # apiServiceProvider, clinicsProvider
│   ├── patient_session_provider.dart # Persisted identity + active-queue tracking (shared_preferences)
│   └── queue_controller.dart         # REST fetch + WS /ws/clinics/{clinicId} sync, auto-reconnect
├── screens/
│   ├── clinic_select_screen.dart     # Pick a clinic
│   ├── join_queue_screen.dart        # Register/reuse patient + 2-question triage + join
│   └── queue_status_screen.dart      # Real-time "Your number" / "Currently serving" tracking
└── widgets/
    ├── connection_status_chip.dart   # "Live" / "Reconnecting…" indicator
    └── turn_alert_banner.dart        # In-app "your turn is near" / "it's your turn" alert
```

## How it works

1. **Clinic selection** (`ClinicSelectScreen`): fetches `GET /clinics` and
   lists them for the patient to pick.

2. **Join queue** (`JoinQueueScreen`): collects name + phone, plus a 2-part
   "smart triage":
   - *"How would you describe your condition?"* — Routine / Urgent.
   - *"Are you experiencing any of these symptoms?"* — severe pain,
     difficulty breathing, high fever (multi-select).

   `isUrgent` is true if either the patient picked "Urgent" or selected any
   severe symptom. On submit, the app looks up the patient by phone
   (`GET /patients/by-phone/{phone}`, added for this step) and reuses that
   patient if found, otherwise registers a new one (`POST /patients`) — so
   a returning patient can join from a new device without hitting the
   backend's unique-phone constraint. It then calls
   `POST /clinics/{clinicId}/queue` and navigates to the status screen.

3. **Real-time tracking** (`QueueStatusScreen` + `queue_controller.dart`):
   loads the clinic's queue over REST, then subscribes to
   `WS /ws/clinics/{clinicId}` and replaces its state on every
   `queue_updated` message — mirroring `frontend-web`'s `useClinicQueue`
   hook. It shows "Your number" vs. "Currently serving", the patient's own
   status, and how many patients are still waiting ahead of them. If the
   patient's entry disappears from the (active-only) queue after having
   been seen, that's treated as visit-complete.

4. **In-app "turn is near" alert** (`TurnAlertBanner`): shows an amber banner
   once `nearTurnThreshold` (5) or fewer patients remain ahead, and a green
   "it's your turn" banner once the patient's status becomes
   `in_consultation`. See the note in `turn_alert_banner.dart` for why this
   is an in-app banner rather than a native push/local notification: this
   environment has no Android/iOS device or emulator to verify native
   notification permissions/behavior on, and `flutter_local_notifications`'
   web support is limited, so an in-app banner (which works identically,
   and testably, on every Flutter target including the web build used to
   verify this app) was used instead. Swapping in real push notifications
   later only means adding a call alongside where this banner is shown.

## Testing without a device or emulator

This environment has no Android SDK or iOS toolchain, so the app was
verified with `flutter test` (see `test/widget_test.dart`, which mocks the
API client so it doesn't depend on a running backend) and by running the
Flutter **web** build (`flutter run -d chrome`) against the real backend —
the same Dart/widget code Android and iOS would run, just compiled for the
browser instead. If testing on an Android emulator or iOS simulator, no code
changes should be needed beyond what's already handled by
`lib/config/constants.dart` and the manifest/plist changes above.
