/// A clinic that runs a virtual waiting queue.
///
/// Free of any JSON or transport concern — `QueueModel` in the data
/// layer is what builds one of these from an API payload.
class Clinic {
  const Clinic({
    required this.id,
    required this.name,
    required this.specialty,
    required this.district,
  });

  final String id;

  /// Arabic display name, e.g. "عيادة الأمل".
  final String name;

  /// The medical specialty, e.g. "طب عام".
  final String specialty;

  /// Neighbourhood, shown under the name.
  final String district;

  @override
  bool operator ==(Object other) => other is Clinic && other.id == id;

  @override
  int get hashCode => id.hashCode;

  @override
  String toString() => 'Clinic($id, $name)';
}
