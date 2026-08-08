import 'package:flutter_test/flutter_test.dart';
import 'package:mizan_frontend/features/chat/data/chat_message.dart';

Map<String, dynamic> _payload({
  String id = 'msg-1',
  String roomId = 'general',
  String senderId = 'alice@example.com',
  String content = 'مرحباً',
  String type = 'text',
  String createdAt = '2026-08-08T19:30:00',
}) {
  return <String, dynamic>{
    'id': id,
    'room_id': roomId,
    'sender_id': senderId,
    'content': content,
    'type': type,
    'created_at': createdAt,
  };
}

void main() {
  group('fromJson', () {
    test('parses a text message', () {
      final ChatMessage message = ChatMessage.fromJson(_payload());

      expect(message.id, 'msg-1');
      expect(message.roomId, 'general');
      expect(message.senderId, 'alice@example.com');
      expect(message.content, 'مرحباً');
      expect(message.kind, ChatMessageKind.text);
      expect(message.isConversational, isTrue);
    });

    test('maps every message kind the backend can send', () {
      expect(
        ChatMessage.fromJson(_payload(type: 'join')).kind,
        ChatMessageKind.join,
      );
      expect(
        ChatMessage.fromJson(_payload(type: 'leave')).kind,
        ChatMessageKind.leave,
      );
      expect(
        ChatMessage.fromJson(_payload(type: 'system')).kind,
        ChatMessageKind.system,
      );
    });

    test('treats an unrecognised kind as a notice rather than failing', () {
      // A backend that adds a new notice kind must not break an older
      // client's whole history load.
      final ChatMessage message =
          ChatMessage.fromJson(_payload(type: 'something_new'));

      expect(message.kind, ChatMessageKind.system);
      expect(message.isConversational, isFalse);
    });

    test('reads a naive timestamp as UTC and converts it to local time', () {
      // The backend stores naive UTC; parsed as local it would be off by
      // the device offset.
      final ChatMessage message =
          ChatMessage.fromJson(_payload(createdAt: '2026-08-08T19:30:00'));

      expect(
        message.createdAt.toUtc(),
        DateTime.utc(2026, 8, 8, 19, 30),
      );
    });

    test('honours an explicit UTC offset', () {
      final ChatMessage message =
          ChatMessage.fromJson(_payload(createdAt: '2026-08-08T19:30:00Z'));

      expect(message.createdAt.toUtc(), DateTime.utc(2026, 8, 8, 19, 30));
    });

    test('rejects a payload missing a required field', () {
      final Map<String, dynamic> payload = _payload()..remove('content');

      expect(
        () => ChatMessage.fromJson(payload),
        throwsA(isA<FormatException>()),
      );
    });

    test('rejects an unparseable timestamp', () {
      expect(
        () => ChatMessage.fromJson(_payload(createdAt: 'not-a-date')),
        throwsA(isA<FormatException>()),
      );
    });
  });

  group('identity', () {
    test('two messages with the same id are equal, enabling de-duplication',
        () {
      // The same message arrives twice when a history fetch races the
      // socket, so the room de-duplicates on id.
      final ChatMessage fromHistory = ChatMessage.fromJson(_payload());
      final ChatMessage fromSocket =
          ChatMessage.fromJson(_payload(content: 'edited later'));

      expect(fromHistory, fromSocket);
      expect(<ChatMessage>[fromHistory].contains(fromSocket), isTrue);
    });

    test('different ids are not equal', () {
      expect(
        ChatMessage.fromJson(_payload(id: 'msg-1')),
        isNot(ChatMessage.fromJson(_payload(id: 'msg-2'))),
      );
    });
  });

  group('isMine', () {
    test('is true only for the viewer\'s own messages', () {
      final ChatMessage message =
          ChatMessage.fromJson(_payload(senderId: 'alice@example.com'));

      expect(message.isMine('alice@example.com'), isTrue);
      expect(message.isMine('bob@example.com'), isFalse);
    });
  });
}
