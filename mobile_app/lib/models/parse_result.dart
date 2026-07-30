/// نتيجة تحليل طلب المشتري (دارجة وهرانية / عربية)
class ParseResult {
  const ParseResult({
    this.district,
    this.maxPrice,
    this.propertyType,
    this.documentType,
    required this.rawInput,
    this.notes,
    this.source,
  });

  final String? district;
  final double? maxPrice;
  final String? propertyType;
  final String? documentType;
  final String rawInput;
  final String? notes;
  final String? source;

  factory ParseResult.fromJson(Map<String, dynamic> json) {
    return ParseResult(
      district: json['district'] as String?,
      maxPrice: (json['max_price'] as num?)?.toDouble(),
      propertyType: json['property_type'] as String?,
      documentType: json['document_type'] as String?,
      rawInput: json['raw_input'] as String? ?? '',
      notes: json['notes'] as String?,
      source: json['source'] as String?,
    );
  }
}
