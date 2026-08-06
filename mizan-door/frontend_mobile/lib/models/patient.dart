class Patient {
  final String id;
  final String name;
  final String phone;
  final DateTime createdAt;

  const Patient({
    required this.id,
    required this.name,
    required this.phone,
    required this.createdAt,
  });

  factory Patient.fromJson(Map<String, dynamic> json) {
    return Patient(
      id: json['id'] as String,
      name: json['name'] as String,
      phone: json['phone'] as String,
      createdAt: DateTime.parse(json['created_at'] as String),
    );
  }
}
