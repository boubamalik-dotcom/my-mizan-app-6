import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/widgets.dart' show Locale;
import 'dart:io' as io;

/// Bilingual support (Arabic and French) from Day 1. Arabic is a built-in
/// RTL language in Flutter, so `MaterialApp` automatically mirrors the
/// entire UI (text alignment, `Row` order, `Scaffold` drawer edge, etc.)
/// once `locale` is set to `Locale('ar')` - no manual RTL plumbing needed
/// beyond setting the locale (see main.dart and widgets/language_toggle.dart).
const List<Locale> supportedLocales = [Locale('fr'), Locale('ar')];
const Locale fallbackLocale = Locale('fr');

/// Backend host resolution.
///
/// The FastAPI backend (see ../../../backend) is expected to be running on
/// port 8000, reachable at a different address depending on where the app
/// runs:
///   - Android emulator: the emulator's loopback to the host machine is
///     `10.0.2.2`, NOT `localhost`/`127.0.0.1`.
///   - iOS simulator, Flutter web, and desktop: the simulator/browser shares
///     the host machine's network, so `127.0.0.1` (a.k.a. `localhost`) works.
///
/// `_host` picks the right one automatically so you don't have to edit this
/// file when switching targets. If you're testing on a *physical* device,
/// replace `_host` with your machine's LAN IP address instead.
String get _host {
  if (kIsWeb) return '127.0.0.1';
  if (io.Platform.isAndroid) return '10.0.2.2';
  return '127.0.0.1'; // iOS simulator, macOS/Linux/Windows desktop
}

String get apiBaseUrl => 'http://$_host:8000';
String get wsBaseUrl => 'ws://$_host:8000';

/// Once fewer than this many patients remain ahead of you, the app shows an
/// in-app "you're almost up" alert (see lib/widgets/turn_alert_banner.dart).
const int nearTurnThreshold = 5;
