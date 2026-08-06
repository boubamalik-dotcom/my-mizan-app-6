import 'dart:async';
import 'dart:convert';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import '../config/constants.dart';
import '../models/queue_entry.dart';
import '../services/api_service.dart';
import 'api_providers.dart';

enum ConnectionStatus { connecting, open, closed }

class QueueState {
  final List<QueueEntry> queue;
  final bool loading;
  final String? error;
  final ConnectionStatus connectionStatus;

  const QueueState({
    this.queue = const [],
    this.loading = true,
    this.error,
    this.connectionStatus = ConnectionStatus.connecting,
  });

  QueueState copyWith({
    List<QueueEntry>? queue,
    bool? loading,
    String? error,
    bool clearError = false,
    ConnectionStatus? connectionStatus,
  }) {
    return QueueState(
      queue: queue ?? this.queue,
      loading: loading ?? this.loading,
      error: clearError ? null : (error ?? this.error),
      connectionStatus: connectionStatus ?? this.connectionStatus,
    );
  }
}

const _reconnectDelay = Duration(seconds: 2);

/// Loads a clinic's queue over REST, then keeps it in sync in real time via
/// `WS /ws/clinics/{clinicId}`, reconnecting automatically if the socket
/// drops. Mirrors `frontend-web/src/hooks/useClinicQueue.ts`.
class QueueController extends Notifier<QueueState> {
  final String clinicId;

  late final ApiService _apiService;
  WebSocketChannel? _channel;
  StreamSubscription? _subscription;
  Timer? _reconnectTimer;
  bool _disposed = false;

  QueueController(this.clinicId);

  @override
  QueueState build() {
    _apiService = ref.read(apiServiceProvider);
    ref.onDispose(_teardown);
    // `refresh()` touches `state` before its first `await`, so calling
    // `_init()` synchronously here would try to write `state` before this
    // `build()` call has finished returning it, which Riverpod rejects
    // ("Tried to read the state of an uninitialized provider"). Deferring
    // via a microtask ensures `build()` completes first.
    Future.microtask(_init);
    return const QueueState();
  }

  Future<void> _init() async {
    await refresh();
    _connect();
  }

  Future<void> refresh() async {
    state = state.copyWith(loading: true, clearError: true);
    try {
      final queue = await _apiService.getClinicQueue(clinicId);
      if (_disposed) return;
      state = state.copyWith(queue: queue, loading: false, clearError: true);
    } catch (_) {
      if (_disposed) return;
      state = state.copyWith(loading: false, error: 'Could not load the queue from the server.');
    }
  }

  void _connect() {
    if (_disposed) return;

    state = state.copyWith(connectionStatus: ConnectionStatus.connecting);
    final uri = Uri.parse('$wsBaseUrl/ws/clinics/$clinicId');
    final channel = WebSocketChannel.connect(uri);
    _channel = channel;

    channel.ready.then((_) {
      if (_disposed) return;
      state = state.copyWith(connectionStatus: ConnectionStatus.open);
    }).catchError((_) {
      _scheduleReconnect();
    });

    _subscription = channel.stream.listen(
      _handleMessage,
      onDone: _scheduleReconnect,
      onError: (_) => _scheduleReconnect(),
      cancelOnError: true,
    );
  }

  void _handleMessage(dynamic rawMessage) {
    if (_disposed) return;
    try {
      final decoded = jsonDecode(rawMessage as String) as Map<String, dynamic>;
      if (decoded['event'] == 'queue_updated' && decoded['clinic_id'] == clinicId) {
        final update = QueueUpdatedMessage.fromJson(decoded);
        state = state.copyWith(queue: update.queue, clearError: true);
      }
    } catch (_) {
      // Ignore malformed messages rather than crashing the listener.
    }
  }

  void _scheduleReconnect() {
    if (_disposed) return;
    state = state.copyWith(connectionStatus: ConnectionStatus.closed);
    _subscription?.cancel();
    _reconnectTimer?.cancel();
    _reconnectTimer = Timer(_reconnectDelay, _connect);
  }

  void _teardown() {
    _disposed = true;
    _reconnectTimer?.cancel();
    _subscription?.cancel();
    _channel?.sink.close();
  }
}

final queueControllerProvider = NotifierProvider.autoDispose
    .family<QueueController, QueueState, String>(QueueController.new);
