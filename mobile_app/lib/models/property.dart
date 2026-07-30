/// نموذج العقار — El Mizan Real Estate (وهران)
class Property {
  const Property({
    required this.id,
    required this.title,
    required this.price,
    required this.district,
    this.description,
    this.areaSqm,
    this.rooms,
  });

  final int id;
  final String title;
  final double price;
  final String district;
  final String? description;
  final double? areaSqm;
  final int? rooms;

  factory Property.fromJson(Map<String, dynamic> json) {
    return Property(
      id: json['id'] as int,
      title: json['title'] as String,
      price: (json['price'] as num).toDouble(),
      district: json['district'] as String,
      description: json['description'] as String?,
      areaSqm: (json['area_sqm'] as num?)?.toDouble(),
      rooms: json['rooms'] as int?,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'title': title,
      'price': price,
      'district': district,
      'description': description,
      'area_sqm': areaSqm,
      'rooms': rooms,
    };
  }
}
