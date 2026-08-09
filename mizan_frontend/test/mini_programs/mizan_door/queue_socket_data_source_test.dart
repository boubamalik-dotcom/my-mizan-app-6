import 'dart:async';
import 'dart:convert';
import 'dart:math';

import 'package:flutter_test/flutter_test.dart';
import 'package:mizan_frontend/mini_programs/mizan_door/data/datasources/queue_socket_data_source.dart';
import 'package:mizan_frontend/shared/network/token_storage.dart';
import 'package:mocktail/mocktail.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

class MockTokenStorage extends Mock implements TokenStorage {}

/// A [WebSocketChannel] backed by a controller the test drives, so a
/// test can push frames and close the socket at will.
class FakeChannel implements WebSocketChannel {
  FakeChannel() : _incoming = StreamController<dynamic>.broadcast();

  final StreamController<dynamic> _incoming;
  bool sinkClosed = false;

  void push(Object frame) => _incoming.add(frame);
  void drop() => _incoming.close();

  @override
  Stream<dynamic> get stream => _incoming.stream;

  @override
  WebSocketSink get sink => _FakeSink(this);

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _FakeSink implements WebSocketSink {
  _FakeSink(this._channel);

  final FakeChannel _channel;

  @override
  Future<void> close([int? closeCode, String? closeReason]) async {
    _channel.sinkClosed = true;
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

String _frame({
  String clinicId = 'c1',
  int waiting = 3,
  int? nowServing = 7,
  bool accepting = true,
  int rate = 8,
}) {
  return jsonEncode(<String, dynamic>{
    'event': 'queue_updated',
    'clinic_id': clinicId,
    'waiting_count': waiting,
    'now_serving_ticket': nowServing,
    'is_accepting_patients': accepting,
    'average_service_minutes': rate,
    'estimated_wait_minutes': waiting * rate,
  });
}

void main() {
  late MockTokenStorage tokenStorage;

  setUp(() {
    tokenStorage = MockTokenStorage();
    when(() => tokenStorage.readToken()).thenAnswer((_) async => 'a-token');
  });

  group('parsing', () {
    test('reads a queue_updated frame', () {
      final ClinicQueueUpdate? update = ClinicQueueUpdate.tryParse(_frame());

      expect(update, isNotNull);
      expect(update!.clinicId, 'c1');
      expect(update.waitingCount, 3);
      expect(update.nowServingTicket, 7);
      expect(update.averageServiceMinutes, 8);
    });

    test('reads an empty room as no ticket', () {
      final ClinicQueueUpdate? update =
          ClinicQueueUpdate.tryParse(_frame(nowServing: null));

      expect(update!.nowServingTicket, isNull);
    });

    test('ignores an event it does not understand', () {
      // A server adding a second event type must not break a client
      // that only knows this one.
      final String other = jsonEncode(<String, dynamic>{
        'event': 'clinic_closed',
        'clinic_id': 'c1',
      });

      expect(ClinicQueueUpdate.tryParse(other), isNull);
    });

    test('ignores malformed frames rather than throwing', () {
      for (final Object? junk in <Object?>[
        'not json',
        '[]',
        '{"event":"queue_updated"}',
        jsonEncode(<String, dynamic>{'event': 'queue_updated', 'clinic_id': 1}),
        null,
        42,
      ]) {
        expect(ClinicQueueUpdate.tryParse(junk), isNull);
      }
    });
  });

  group('subscribing', () {
    test('connects with the stored token and emits pushed updates', () async {
      final FakeChannel channel = FakeChannel();
      Uri? requested;
      final QueueSocketDataSource source = QueueSocketDataSource(
        tokenStorage: tokenStorage,
        channelFactory: (Uri uri) {
          requested = uri;
          return channel;
        },
      );

      final Future<ClinicQueueUpdate> first = source.watch('c1').first;
      await Future<void>.delayed(Duration.zero);
      channel.push(_frame(waiting: 5));

      expect((await first).waitingCount, 5);
      expect(requested!.path, contains('/queues/ws/c1'));
      expect(requested!.queryParameters['token'], 'a-token');
    });

    test('closes without connecting when nobody is signed in', () async {
      // No credential to present, and no point retrying on a timer: a
      // fresh subscription opens after a login.
      when(() => tokenStorage.readToken()).thenAnswer((_) async => null);
      var opened = false;
      final QueueSocketDataSource source = QueueSocketDataSource(
        tokenStorage: tokenStorage,
        channelFactory: (Uri uri) {
          opened = true;
          return FakeChannel();
        },
      );

      await expectLater(source.watch('c1'), emitsDone);
      expect(opened, isFalse);
    });

    test('reconnects after the socket drops', () async {
      final List<FakeChannel> channels = <FakeChannel>[];
      final QueueSocketDataSource source = QueueSocketDataSource(
        tokenStorage: tokenStorage,
        initialRetryDelay: const Duration(milliseconds: 1),
        maxRetryDelay: const Duration(milliseconds: 2),
        channelFactory: (Uri uri) {
          final FakeChannel channel = FakeChannel();
          channels.add(channel);
          return channel;
        },
      );

      final List<ClinicQueueUpdate> seen = <ClinicQueueUpdate>[];
      final StreamSubscription<ClinicQueueUpdate> subscription =
          source.watch('c1').listen(seen.add);

      await Future<void>.delayed(const Duration(milliseconds: 5));
      channels.first.push(_frame(waiting: 1));
      await Future<void>.delayed(const Duration(milliseconds: 5));

      // The server goes away mid-session.
      channels.first.drop();
      await Future<void>.delayed(const Duration(milliseconds: 40));

      expect(channels.length, greaterThan(1), reason: 'never reconnected');
      channels.last.push(_frame(waiting: 2));
      await Future<void>.delayed(const Duration(milliseconds: 5));

      // The stream survived the drop: the caller never saw an error and
      // never had to resubscribe.
      expect(seen.map((ClinicQueueUpdate u) => u.waitingCount), <int>[1, 2]);
      await subscription.cancel();
    });

    test('cancelling stops retrying and closes the socket', () async {
      final List<FakeChannel> channels = <FakeChannel>[];
      final QueueSocketDataSource source = QueueSocketDataSource(
        tokenStorage: tokenStorage,
        initialRetryDelay: const Duration(milliseconds: 1),
        maxRetryDelay: const Duration(milliseconds: 2),
        channelFactory: (Uri uri) {
          final FakeChannel channel = FakeChannel();
          channels.add(channel);
          return channel;
        },
      );

      final StreamSubscription<ClinicQueueUpdate> subscription =
          source.watch('c1').listen((_) {});
      await Future<void>.delayed(const Duration(milliseconds: 5));
      await subscription.cancel();

      final int openedAtCancel = channels.length;
      await Future<void>.delayed(const Duration(milliseconds: 40));

      expect(channels.length, openedAtCancel, reason: 'kept reconnecting');
      expect(channels.first.sinkClosed, isTrue);
    });

    test('two clinics get independent subscriptions', () async {
      // Retry state used to live on the data source, where a second
      // watch would clobber the first's.
      final Map<String, FakeChannel> byClinic = <String, FakeChannel>{};
      final QueueSocketDataSource source = QueueSocketDataSource(
        tokenStorage: tokenStorage,
        channelFactory: (Uri uri) {
          final FakeChannel channel = FakeChannel();
          byClinic[uri.pathSegments.last] = channel;
          return channel;
        },
      );

      final List<String> seen = <String>[];
      final StreamSubscription<ClinicQueueUpdate> a = source
          .watch('c1')
          .listen((ClinicQueueUpdate u) => seen.add(u.clinicId));
      final StreamSubscription<ClinicQueueUpdate> b = source
          .watch('c2')
          .listen((ClinicQueueUpdate u) => seen.add(u.clinicId));
      await Future<void>.delayed(const Duration(milliseconds: 5));

      byClinic['c1']!.push(_frame(clinicId: 'c1'));
      byClinic['c2']!.push(_frame(clinicId: 'c2'));
      await Future<void>.delayed(const Duration(milliseconds: 5));

      expect(seen, containsAll(<String>['c1', 'c2']));
      await a.cancel();
      await b.cancel();
    });
  });

  group('backoff', () {
    /// Counts reconnection attempts against a server that refuses every
    /// one, over a fixed window.
    Future<int> attemptsAgainstADeadServer({
      required Duration initial,
      required Duration cap,
    }) async {
      var attempts = 0;
      final QueueSocketDataSource source = QueueSocketDataSource(
        tokenStorage: tokenStorage,
        initialRetryDelay: initial,
        maxRetryDelay: cap,
        random: Random(1),
        channelFactory: (Uri uri) {
          attempts += 1;
          final FakeChannel channel = FakeChannel();
          scheduleMicrotask(channel.drop);
          return channel;
        },
      );

      final StreamSubscription<ClinicQueueUpdate> subscription =
          source.watch('c1').listen((_) {});
      await Future<void>.delayed(const Duration(milliseconds: 300));
      await subscription.cancel();
      return attempts;
    }

    test('slows down instead of hammering a server that is down', () async {
      // The behaviour a fixed retry timer would not have: with a flat
      // 10ms delay this window fits ~30 attempts. Exponential backoff
      // should reach nowhere near that.
      final int attempts = await attemptsAgainstADeadServer(
        initial: const Duration(milliseconds: 10),
        cap: const Duration(milliseconds: 80),
      );

      expect(attempts, greaterThan(1), reason: 'never retried at all');
      expect(attempts, lessThan(15), reason: 'retried at a near-flat rate');
    });

    test('keeps retrying rather than giving up', () async {
      // A patient whose phone slept for an hour should find the queue
      // live again on waking, not permanently frozen.
      final int attempts = await attemptsAgainstADeadServer(
        initial: const Duration(milliseconds: 5),
        cap: const Duration(milliseconds: 20),
      );

      expect(attempts, greaterThan(3));
    });
  });
}
