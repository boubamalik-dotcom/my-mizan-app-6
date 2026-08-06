class Clinic {
  final String id;
  final String name;
  final String specialty;
  final DateTime createdAt;

  const Clinic({
    required this.id,
    required this.name,
    required this.specialty,
    required this.createdAt,
  });

  factory Clinic.fromJson(Map<String, dynamic> json) {
    return Clinic(
      id: json['id'] as String,
      name: json['name'] as String,
      specialty: json['specialty'] as String,
      createdAt: DateTime.parse(json['created_at'] as String),
    );
  }
}
