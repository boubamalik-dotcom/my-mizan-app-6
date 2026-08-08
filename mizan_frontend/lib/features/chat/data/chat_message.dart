/// What a message *is*, as distinct from the envelope it arrives in.
///
/// Mirrors the backend's `ChatMessageResponse.type`
/// (`layer_2_api/schemas/chat_schemas.py`): participant-authored text,
/// or one of the server-generated notices.
enum ChatMessageKind {
  /// A message a participant actually wrote — the only kind the room
  /// renders as a bubble.
  text,

  /// A server-generated notice.
  system,

  /// "<client> joined the room."
  join,

  /// "<client> left the room."
  leave;

  static ChatMessageKind fromWire(Object? value) {
    return switch (value) {
      'text' => ChatMessageKind.text,
      'join' => ChatMessageKind.join,
      'leave' => ChatMessageKind.leave,
      // Anything unrecognised is treated as a notice rather than
      // rejected: a backend that adds a new notice kind should not
      // break an older client's history load.
      _ => ChatMessageKind.system,
    };
  }
}

/// A single chat message.
///
/// One model covers both sources, because the backend deliberately
/// serializes the same `ChatMessageResponse` for each: the REST history
/// endpoint returns a list of them, and every relayed WebSocket frame
/// carries one as its `data` payload.
class ChatMessage {
  const ChatMessage({
    required this.id,
    required this.roomId,
    required this.senderId,
    required this.content,
    required this.kind,
    required this.createdAt,
  });

  final String id;
  final String roomId;

  /// The author's chat identity — their account **email**, which is
  /// also the JWT subject and the `client_id` the socket connects as.
  final String senderId;

  final String content;
  final ChatMessageKind kind;
  final DateTime createdAt;

  /// Whether this is a real message between participants, as opposed to
  /// a join/leave/system notice.
  bool get isConversational => kind == ChatMessageKind.text;

  /// Whether [viewerId] wrote this message, which decides how the
  /// bubble is styled and aligned.
  bool isMine(String viewerId) => senderId == viewerId;

  /// Parses one `ChatMessageResponse`.
  ///
  /// Throws [FormatException] if a required field is missing or of the
  /// wrong type, so a malformed payload fails loudly at the data-layer
  /// boundary instead of surfacing as a confusing null further up.
  factory ChatMessage.fromJson(Map<String, dynamic> json) {
    return ChatMessage(
      id: _requireString(json, 'id'),
      roomId: _requireString(json, 'room_id'),
      senderId: _requireString(json, 'sender_id'),
      content: _requireString(json, 'content'),
      kind: ChatMessageKind.fromWire(json['type']),
      createdAt: _requireDate(json, 'created_at'),
    );
  }

  static String _requireString(Map<String, dynamic> json, String field) {
    final Object? value = json[field];
    if (value is String) return value;
    throw FormatException('Expected a string `$field`, got: $value');
  }

  static DateTime _requireDate(Map<String, dynamic> json, String field) {
    final Object? value = json[field];
    if (value is! String) {
      throw FormatException('Expected an ISO-8601 `$field`, got: $value');
    }
    final DateTime? parsed = DateTime.tryParse(value);
    if (parsed == null) {
      throw FormatException('Could not parse `$field` as a date: $value');
    }
    // The backend stores naive UTC timestamps, so a value without an
    // offset must be read as UTC before being shown in local time —
    // otherwise every message is off by the device's offset.
    return parsed.isUtc
        ? parsed.toLocal()
        : DateTime.utc(
            parsed.year,
            parsed.month,
            parsed.day,
            parsed.hour,
            parsed.minute,
            parsed.second,
            parsed.millisecond,
            parsed.microsecond,
          ).toLocal();
  }

  /// Identity is the server-assigned [id]: the same message can arrive
  /// twice (once in the history page, once over the socket) when the
  /// two race, and the room de-duplicates on this.
  @override
  bool operator ==(Object other) => other is ChatMessage && other.id == id;

  @override
  int get hashCode => id.hashCode;

  @override
  String toString() => 'ChatMessage($id, $senderId, ${kind.name})';
}
