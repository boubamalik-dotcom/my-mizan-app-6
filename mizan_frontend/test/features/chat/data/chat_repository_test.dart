import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:mizan_frontend/features/chat/data/chat_remote_data_source.dart';
import 'package:mizan_frontend/features/chat/data/chat_repository.dart';

/// A [ChatRemoteDataSource] stand-in that hands the test direct
/// control of the frame stream, so unread-counting can be exercised
/// without a real WebSocket.
///
/// Both methods `ChatRepository` ever calls — `connect`/`disconnect` —
/// are overridden, so the inherited `TokenStorage`/channel factory are
/// never touched (constructing them has no side effects; only
/// `readToken()`/an actual handshake would).
class FakeChatRemoteDataSource extends ChatRemoteDataSource {
  final List<StreamController<dynamic>> _controllers =
      <StreamController<dynamic>>[];

  int connectCallCount = 0;
  int disconnectCallCount = 0;
  String? lastClientId;

  /// The controller feeding the most recent [connect] call — the one a
  /// test pushes frames into.
  StreamController<dynamic> get frames => _controllers.last;

  /// Hands out a *fresh* stream per call, exactly as a real
  /// `WebSocketChannel.connect` yields a brand-new channel: reusing one
  /// single-subscription stream across reconnects would fail in the
  /// fake for reasons production never hits.
  @override
  Future<Stream<dynamic>> connect(
    String clientId, {
    String roomId = kDefaultChatRoomId,
  }) async {
    connectCallCount++;
    lastClientId = clientId;
    final StreamController<dynamic> controller = StreamController<dynamic>();
    _controllers.add(controller);
    return controller.stream;
  }

  @override
  Future<void> disconnect() async {
    disconnectCallCount++;
  }

  Future<void> closeAll() async {
    for (final StreamController<dynamic> controller in _controllers) {
      if (!controller.isClosed) await controller.close();
    }
  }
}

String _messageFrame({required String senderId, String content = 'مرحبا'}) {
  return jsonEncode(<String, dynamic>{
    'type': 'message',
    'data': <String, dynamic>{
      'id': 'm1',
      'room_id': kDefaultChatRoomId,
      'sender_id': senderId,
      'content': content,
      'type': 'text',
      'created_at': '2026-01-01T00:00:00Z',
    },
  });
}

void main() {
  late FakeChatRemoteDataSource dataSource;
  late ChatRepository repository;

  setUp(() {
    dataSource = FakeChatRemoteDataSource();
    repository = ChatRepository(remoteDataSource: dataSource);
  });

  tearDown(() async {
    await repository.disconnect();
    await dataSource.closeAll();
  });

  test('connect passes the client id through to the data source', () async {
    await repository.connect(clientId: 'alice@example.com');

    expect(dataSource.connectCallCount, 1);
    expect(dataSource.lastClientId, 'alice@example.com');
  });

  test('counts an incoming message from another participant', () async {
    final Stream<int> unread = await repository.connect(
      clientId: 'alice@example.com',
    );
    final Future<List<int>> collected = unread.take(2).toList();

    dataSource.frames.add(_messageFrame(senderId: 'bob@example.com'));
    dataSource.frames.add(_messageFrame(senderId: 'bob@example.com'));

    expect(await collected, <int>[1, 2]);
    expect(repository.unreadCount, 2);
  });

  test("never counts the echo of the user's own message", () async {
    final Stream<int> unread = await repository.connect(
      clientId: 'alice@example.com',
    );
    final Future<List<int>> collected = unread.take(1).toList();

    // The backend deliberately relays a sender their own message back.
    dataSource.frames.add(_messageFrame(senderId: 'alice@example.com'));
    dataSource.frames.add(_messageFrame(senderId: 'bob@example.com'));

    expect(await collected, <int>[1]);
    expect(repository.unreadCount, 1);
  });

  test('ignores system, pong, error, and malformed frames', () async {
    final Stream<int> unread = await repository.connect(
      clientId: 'alice@example.com',
    );
    final Future<List<int>> collected = unread.take(1).toList();

    dataSource.frames.add(
      jsonEncode(<String, dynamic>{
        'type': 'system',
        'data': <String, dynamic>{
          'sender_id': 'system',
          'type': 'join',
          'content': '"bob" joined the room.',
        },
      }),
    );
    dataSource.frames.add(jsonEncode(<String, dynamic>{'type': 'pong'}));
    dataSource.frames.add(
      jsonEncode(<String, dynamic>{'type': 'error', 'detail': 'nope'}),
    );
    dataSource.frames.add('not json at all');
    dataSource.frames.add(<int>[1, 2, 3]); // not even a String

    // Only this last, genuine message should register.
    dataSource.frames.add(_messageFrame(senderId: 'bob@example.com'));

    expect(await collected, <int>[1]);
    expect(repository.unreadCount, 1);
  });

  test('markAllAsRead resets the count and publishes the reset', () async {
    final Stream<int> unread = await repository.connect(
      clientId: 'alice@example.com',
    );
    final Future<List<int>> collected = unread.take(2).toList();

    dataSource.frames.add(_messageFrame(senderId: 'bob@example.com'));
    await Future<void>.delayed(Duration.zero);
    repository.markAllAsRead();

    expect(await collected, <int>[1, 0]);
    expect(repository.unreadCount, 0);
  });

  test('closes the unread stream when the socket closes', () async {
    final Stream<int> unread = await repository.connect(
      clientId: 'alice@example.com',
    );
    bool done = false;
    unread.listen(null, onDone: () => done = true);

    await dataSource.frames.close();
    await Future<void>.delayed(Duration.zero);

    expect(done, isTrue);
  });

  test('forwards a socket error to the unread stream', () async {
    final Stream<int> unread = await repository.connect(
      clientId: 'alice@example.com',
    );
    final Completer<Object> errorCompleter = Completer<Object>();
    unread.listen(null, onError: errorCompleter.complete);

    dataSource.frames.addError(StateError('socket died'));

    expect(await errorCompleter.future, isA<StateError>());
  });

  test('disconnect closes the socket and resets the count', () async {
    await repository.connect(clientId: 'alice@example.com');
    dataSource.frames.add(_messageFrame(senderId: 'bob@example.com'));
    await Future<void>.delayed(Duration.zero);
    expect(repository.unreadCount, 1);

    await repository.disconnect();

    expect(dataSource.disconnectCallCount, greaterThanOrEqualTo(1));
    expect(repository.unreadCount, 0);
  });

  test('reconnecting tears the previous connection down first', () async {
    await repository.connect(clientId: 'alice@example.com');
    await repository.connect(clientId: 'alice@example.com');

    expect(dataSource.connectCallCount, 2);
    expect(dataSource.disconnectCallCount, greaterThanOrEqualTo(1));
  });
}
