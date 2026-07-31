/// نموذج العقار العام (Privacy Shield) — El Mizan Real Estate
class Property {
  const Property({
    required this.id,
    required this.title,
    required this.price,
    required this.district,
    this.description,
    this.documentType,
    this.status,
    this.approximateLocation,
    this.addressHidden = true,
    this.ownerContactHidden = true,
    this.mizanEvaluation,
    this.privacyNote,
  });

  final int id;
  final String title;
  final double price;
  final String district;
  final String? description;
  final String? documentType;
  final String? status;
  final String? approximateLocation;
  final bool addressHidden;
  final bool ownerContactHidden;
  final MizanEvaluation? mizanEvaluation;
  final String? privacyNote;

  String get priceBalance => mizanEvaluation?.priceBalance ?? '—';

  factory Property.fromJson(Map<String, dynamic> json) {
    final eval = json['mizan_evaluation'];
    return Property(
      id: json['id'] as int,
      title: json['title'] as String,
      price: (json['price'] as num).toDouble(),
      district: json['district'] as String,
      description: json['description'] as String?,
      documentType: json['document_type'] as String?,
      status: json['status'] as String?,
      approximateLocation: json['approximate_location'] as String?,
      addressHidden: json['address_hidden'] as bool? ?? true,
      ownerContactHidden: json['owner_contact_hidden'] as bool? ?? true,
      mizanEvaluation: eval is Map<String, dynamic>
          ? MizanEvaluation.fromJson(eval)
          : null,
      privacyNote: json['privacy_note'] as String?,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'title': title,
      'price': price,
      'district': district,
      'description': description,
      'document_type': documentType,
      'status': status,
      'approximate_location': approximateLocation,
      'address_hidden': addressHidden,
      'owner_contact_hidden': ownerContactHidden,
      'mizan_evaluation': mizanEvaluation?.toJson(),
      'privacy_note': privacyNote,
    };
  }
}

class MizanEvaluation {
  const MizanEvaluation({
    required this.priceBalance,
    required this.askingPrice,
    required this.district,
    this.districtAvgPrice,
    this.deviationPercent,
    this.reasoning,
    this.confidence,
    this.source,
  });

  final String priceBalance;
  final double askingPrice;
  final String district;
  final double? districtAvgPrice;
  final double? deviationPercent;
  final String? reasoning;
  final double? confidence;
  final String? source;

  factory MizanEvaluation.fromJson(Map<String, dynamic> json) {
    return MizanEvaluation(
      priceBalance: json['price_balance'] as String? ?? '—',
      askingPrice: (json['asking_price'] as num?)?.toDouble() ?? 0,
      district: json['district'] as String? ?? '',
      districtAvgPrice: (json['district_avg_price'] as num?)?.toDouble(),
      deviationPercent: (json['deviation_percent'] as num?)?.toDouble(),
      reasoning: json['reasoning'] as String?,
      confidence: (json['confidence'] as num?)?.toDouble(),
      source: json['source'] as String?,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'price_balance': priceBalance,
      'asking_price': askingPrice,
      'district': district,
      'district_avg_price': districtAvgPrice,
      'deviation_percent': deviationPercent,
      'reasoning': reasoning,
      'confidence': confidence,
      'source': source,
    };
  }
}
