import 'dart:async';
import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mizan_frontend/features/chat/data/chat_exceptions.dart';
import 'package:mizan_frontend/features/chat/data/chat_message.dart';
import 'package:mizan_frontend/features/chat/data/chat_remote_data_source.dart';
import 'package:mizan_frontend/features/chat/data/chat_repository.dart';
import 'package:mizan_frontend/shared/exceptions/network_exception.dart';

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

  /// Frames handed to [sendMessage], for asserting the wire format.
  final List<String> sentFrames = <String>[];

  /// History the fake returns, or an error to throw instead.
  List<ChatMessage> history = <ChatMessage>[];
  Object? historyError;
  String? lastHistoryClientId;
  String? lastHistoryRoomId;
  int? lastHistoryLimit;

  /// Mirrors the real data source's "a channel is open" flag, which the
  /// real one derives from a channel this fake never creates.
  bool connected = false;

  @override
  bool get isConnected => connected;

  @override
  void sendMessage(String content) {
    if (!connected) {
      throw const ChatConnectionException(
        'لا يوجد اتصال بخدمة الدردشة. لم يتم إرسال الرسالة.',
      );
    }
    sentFrames.add(
        jsonEncode(<String, String>{'type': 'message', 'content': content}));
  }

  @override
  Future<List<ChatMessage>> fetchHistory({
    required String clientId,
    String roomId = kDefaultChatRoomId,
    int limit = 50,
  }) async {
    lastHistoryClientId = clientId;
    lastHistoryRoomId = roomId;
    lastHistoryLimit = limit;
    if (historyError != null) throw historyError!;
    return history;
  }

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
    connected = true;
    final StreamController<dynamic> controller = StreamController<dynamic>();
    _controllers.add(controller);
    return controller.stream;
  }

  @override
  Future<void> disconnect() async {
    disconnectCallCount++;
    connected = false;
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

  group('incomingMessages', () {
    test(
        'parses relayed messages and fans them out alongside the unread '
        'count, from the one socket subscription', () async {
      // A `WebSocketChannel`'s stream is single-subscription, so the
      // badge and the chat room cannot each listen to it directly —
      // both must be served from the same listen() call.
      final Stream<int> unread = await repository.connect(
        clientId: 'alice@example.com',
      );
      final Future<List<int>> unreadValues = unread.take(1).toList();
      final Future<List<ChatMessage>> messages =
          repository.incomingMessages.take(2).toList();

      dataSource.frames.add(
        _messageFrame(senderId: 'bob@example.com', content: 'أهلاً'),
      );
      dataSource.frames.add(
        _messageFrame(senderId: 'alice@example.com', content: 'وسهلاً'),
      );

      final List<ChatMessage> received = await messages;
      expect(
        received.map((ChatMessage m) => m.content),
        <String>['أهلاً', 'وسهلاً'],
      );
      // The user's own echo is a message but not an unread one.
      expect(await unreadValues, <int>[1]);
    });

    test('is a broadcast stream, so a second listener is allowed', () async {
      await repository.connect(clientId: 'alice@example.com');

      expect(repository.incomingMessages.isBroadcast, isTrue);
      final Future<ChatMessage> first = repository.incomingMessages.first;
      final Future<ChatMessage> second = repository.incomingMessages.first;

      dataSource.frames.add(_messageFrame(senderId: 'bob@example.com'));

      expect((await first).id, (await second).id);
    });

    test('emits join/leave notices too, leaving the filtering to the UI',
        () async {
      await repository.connect(clientId: 'alice@example.com');
      final Future<ChatMessage> next = repository.incomingMessages.first;

      dataSource.frames.add(
        jsonEncode(<String, dynamic>{
          'type': 'system',
          'data': <String, dynamic>{
            'id': 'sys-1',
            'room_id': kDefaultChatRoomId,
            'sender_id': 'system',
            'content': '"bob@example.com" joined the room.',
            'type': 'join',
            'created_at': '2026-01-01T00:00:00Z',
          },
        }),
      );

      final ChatMessage notice = await next;
      expect(notice.kind, ChatMessageKind.join);
      expect(notice.isConversational, isFalse);
    });

    test('drops pong, error, and malformed frames without killing the stream',
        () async {
      await repository.connect(clientId: 'alice@example.com');
      final Future<ChatMessage> next = repository.incomingMessages.first;

      dataSource.frames.add(jsonEncode(<String, String>{'type': 'pong'}));
      dataSource.frames.add(
        jsonEncode(<String, String>{'type': 'error', 'detail': 'nope'}),
      );
      dataSource.frames.add('not json at all');
      dataSource.frames.add(
        jsonEncode(<String, dynamic>{
          'type': 'message',
          'data': <String, dynamic>{'id': 'broken'},
        }),
      );
      dataSource.frames.add(
        _messageFrame(senderId: 'bob@example.com', content: 'survived'),
      );

      expect((await next).content, 'survived');
    });
  });

  group('sendMessage', () {
    test('sends the backend\'s client -> server envelope', () async {
      await repository.connect(clientId: 'alice@example.com');

      repository.sendMessage('السلام عليكم');

      expect(dataSource.sentFrames, hasLength(1));
      expect(
        jsonDecode(dataSource.sentFrames.single),
        <String, String>{'type': 'message', 'content': 'السلام عليكم'},
      );
    });

    test('trims the content before sending', () async {
      await repository.connect(clientId: 'alice@example.com');

      repository.sendMessage('  مرحبا  ');

      expect(
        (jsonDecode(dataSource.sentFrames.single)
            as Map<String, dynamic>)['content'],
        'مرحبا',
      );
    });

    test('rejects blank content instead of posting an empty message', () async {
      await repository.connect(clientId: 'alice@example.com');

      expect(() => repository.sendMessage('   '), throwsArgumentError);
      expect(dataSource.sentFrames, isEmpty);
    });

    test('reports a closed socket rather than dropping the message', () {
      // Never connected, so there is no channel to write to.
      expect(
        () => repository.sendMessage('مرحبا'),
        throwsA(isA<ChatConnectionException>()),
      );
    });
  });

  group('fetchHistory', () {
    ChatMessage message(String id) => ChatMessage.fromJson(<String, dynamic>{
          'id': id,
          'room_id': kDefaultChatRoomId,
          'sender_id': 'bob@example.com',
          'content': 'مرحبا',
          'type': 'text',
          'created_at': '2026-01-01T00:00:00Z',
        });

    test('passes the client id, room, and limit through', () async {
      dataSource.history = <ChatMessage>[message('m1'), message('m2')];

      final List<ChatMessage> history = await repository.fetchHistory(
        clientId: 'alice@example.com',
        roomId: 'general',
        limit: 25,
      );

      expect(history.map((ChatMessage m) => m.id), <String>['m1', 'm2']);
      expect(dataSource.lastHistoryClientId, 'alice@example.com');
      expect(dataSource.lastHistoryRoomId, 'general');
      expect(dataSource.lastHistoryLimit, 25);
    });

    test('maps a 403 to its own Arabic message', () async {
      // The backend answers 403 when the path client id is not the
      // caller's own, mirroring the socket's identity check.
      dataSource.historyError = DioException(
        requestOptions: RequestOptions(path: '/chat/history/x'),
        type: DioExceptionType.badResponse,
        response: Response<dynamic>(
          requestOptions: RequestOptions(path: '/chat/history/x'),
          statusCode: 403,
        ),
      );

      await expectLater(
        () => repository.fetchHistory(clientId: 'alice@example.com'),
        throwsA(
          isA<NetworkException>()
              .having((NetworkException e) => e.statusCode, 'statusCode', 403)
              .having(
                (NetworkException e) => e.message,
                'message',
                contains('لا تملك صلاحية'),
              ),
        ),
      );
    });

    test('falls back to the generic mapping for other failures', () async {
      dataSource.historyError = DioException(
        requestOptions: RequestOptions(path: '/chat/history/x'),
        type: DioExceptionType.connectionError,
      );

      await expectLater(
        () => repository.fetchHistory(clientId: 'alice@example.com'),
        throwsA(isA<NetworkException>()),
      );
    });
  });
}
