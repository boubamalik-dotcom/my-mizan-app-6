import 'dart:async';
import 'dart:convert';
import 'dart:math';

import 'package:web_socket_channel/web_socket_channel.dart';

import '../../../../shared/network/endpoints.dart';
import '../../../../shared/network/token_storage.dart';

/// Builds a [WebSocketChannel] for [uri]. Injected so tests can supply
/// a fake instead of opening a real socket.
typedef WebSocketChannelFactory = WebSocketChannel Function(Uri uri);

/// One clinic's queue state, as pushed over the socket.
///
/// Deliberately mirrors the fields of a `ClinicQueue` rather than being
/// a whole `ClinicQueue`: the frame carries no clinic name, specialty,
/// or district, because those do not change when a queue moves. The
/// cubit merges these figures into the clinic it already has.
class ClinicQueueUpdate {
  const ClinicQueueUpdate({
    required this.clinicId,
    required this.waitingCount,
    required this.isAcceptingPatients,
    required this.averageServiceMinutes,
    this.nowServingTicket,
  });

  final String clinicId;
  final int waitingCount;
  final bool isAcceptingPatients;
  final int averageServiceMinutes;

  /// The ticket currently with the clinician, or `null` if the room is
  /// free.
  final int? nowServingTicket;

  /// Parses a `queue_updated` frame, or returns `null` for anything
  /// else.
  ///
  /// Returning `null` rather than throwing on an unrecognised frame is
  /// deliberate: a server that later adds a second event type must not
  /// break a client that only understands this one.
  static ClinicQueueUpdate? tryParse(Object? raw) {
    if (raw is! String) return null;

    final Object? decoded;
    try {
      decoded = jsonDecode(raw);
    } on FormatException {
      return null;
    }
    if (decoded is! Map<String, dynamic>) return null;
    if (decoded['event'] != 'queue_updated') return null;

    final Object? clinicId = decoded['clinic_id'];
    final Object? waiting = decoded['waiting_count'];
    final Object? rate = decoded['average_service_minutes'];
    if (clinicId is! String || waiting is! int || rate is! int) return null;

    final Object? nowServing = decoded['now_serving_ticket'];
    return ClinicQueueUpdate(
      clinicId: clinicId,
      waitingCount: waiting,
      isAcceptingPatients: decoded['is_accepting_patients'] as bool? ?? true,
      averageServiceMinutes: rate,
      nowServingTicket: nowServing is int ? nowServing : null,
    );
  }
}

/// Keeps a live subscription to one clinic's queue, reconnecting on its
/// own when the socket drops.
///
/// A dropped socket is the normal case, not the exception: phones sleep,
/// networks change, and servers restart during a deploy. A queue screen
/// that silently stopped updating would be worse than one that never
/// claimed to be live, because the patient would trust a number that had
/// quietly frozen.
///
/// Reconnection backs off exponentially with jitter, rather than
/// retrying on a fixed timer. A fixed timer means every client that was
/// connected to a restarting server comes back in the same instant,
/// again and again — the clients turn a restart into a stampede. The
/// jitter spreads them out.
class QueueSocketDataSource {
  QueueSocketDataSource({
    TokenStorage? tokenStorage,
    WebSocketChannelFactory? channelFactory,
    Duration initialRetryDelay = const Duration(seconds: 1),
    Duration maxRetryDelay = const Duration(seconds: 30),
    Random? random,
  })  : _tokenStorage = tokenStorage ?? TokenStorage(),
        _channelFactory = channelFactory ?? WebSocketChannel.connect,
        _initialRetryDelay = initialRetryDelay,
        _maxRetryDelay = maxRetryDelay,
        _random = random ?? Random();

  final TokenStorage _tokenStorage;
  final WebSocketChannelFactory _channelFactory;
  final Duration _initialRetryDelay;
  final Duration _maxRetryDelay;
  final Random _random;

  /// Opens a self-healing subscription to `clinicId`'s queue.
  ///
  /// The returned stream stays open across reconnections and emits only
  /// parsed updates — a drop is not an error the caller has to handle,
  /// it is a gap between two events. Cancelling the subscription closes
  /// the socket and stops retrying.
  Stream<ClinicQueueUpdate> watch(String clinicId) {
    late final StreamController<ClinicQueueUpdate> controller;
    WebSocketChannel? channel;
    StreamSubscription<dynamic>? subscription;
    Timer? retryTimer;
    var attempt = 0;
    var closed = false;

    // Declared before `connect` and assigned after, because the two
    // call each other. Local to this call rather than a field on the
    // data source, so watching several clinics gives each its own
    // retry state instead of the last one clobbering the rest.
    late void Function() scheduleRetry;

    Future<void> connect() async {
      if (closed) return;

      final String? token = await _tokenStorage.readToken();
      if (closed) return;
      if (token == null) {
        // Not signed in, so there is nothing to authenticate with and
        // no point retrying on a timer: the screen will open a fresh
        // subscription after a login.
        await controller.close();
        return;
      }

      try {
        channel = _channelFactory(
          ApiEndpoints.clinicQueueWebSocket(clinicId: clinicId, token: token),
        );
      } on Exception {
        scheduleRetry();
        return;
      }

      subscription = channel!.stream.listen(
        (Object? frame) {
          // Any frame proves the connection is healthy, so the backoff
          // starts from scratch next time rather than from however far
          // it had climbed during an earlier outage.
          attempt = 0;
          final ClinicQueueUpdate? update = ClinicQueueUpdate.tryParse(frame);
          if (update != null && !controller.isClosed) controller.add(update);
        },
        onDone: scheduleRetry,
        onError: (Object _) => scheduleRetry(),
        cancelOnError: true,
      );
    }

    scheduleRetry = () {
      if (closed || controller.isClosed) return;
      subscription?.cancel();
      subscription = null;
      channel = null;
      retryTimer?.cancel();
      retryTimer = Timer(_backoffFor(attempt++), connect);
    };

    controller = StreamController<ClinicQueueUpdate>(
      onListen: connect,
      onCancel: () async {
        closed = true;
        retryTimer?.cancel();
        await subscription?.cancel();
        await channel?.sink.close();
      },
    );

    return controller.stream;
  }

  /// Exponential backoff with full jitter, capped at [_maxRetryDelay].
  ///
  /// The jitter is the point: without it every client of a restarting
  /// server retries in lockstep and hits it as one wave.
  Duration _backoffFor(int attempt) {
    final int ceilingMs = min(
      _maxRetryDelay.inMilliseconds,
      _initialRetryDelay.inMilliseconds * (1 << min(attempt, 10)),
    );
    // Never below the initial delay, so a flapping server cannot be
    // hammered with near-zero waits.
    final int floorMs = min(_initialRetryDelay.inMilliseconds, ceilingMs);
    return Duration(
      milliseconds: floorMs + _random.nextInt(max(1, ceilingMs - floorMs + 1)),
    );
  }
}
