/// نتيجة حجز معاينة الميزان
class InspectionBooking {
  const InspectionBooking({
    required this.id,
    required this.propertyId,
    required this.buyerId,
    required this.scheduledAt,
    required this.status,
    required this.commissionAgreed,
    required this.commissionRate,
    required this.inspectionCode,
    required this.district,
    this.meetingPointHidden = true,
    this.message,
  });

  final int id;
  final int propertyId;
  final int buyerId;
  final DateTime scheduledAt;
  final String status;
  final bool commissionAgreed;
  final double commissionRate;
  final String inspectionCode;
  final String district;
  final bool meetingPointHidden;
  final String? message;

  factory InspectionBooking.fromJson(Map<String, dynamic> json) {
    return InspectionBooking(
      id: json['id'] as int,
      propertyId: json['property_id'] as int,
      buyerId: json['buyer_id'] as int,
      scheduledAt: DateTime.parse(json['scheduled_at'] as String),
      status: json['status'] as String,
      commissionAgreed: json['commission_agreed'] as bool? ?? false,
      commissionRate: (json['commission_rate'] as num?)?.toDouble() ?? 0.015,
      inspectionCode: json['inspection_code'] as String,
      district: json['district'] as String? ?? '',
      meetingPointHidden: json['meeting_point_hidden'] as bool? ?? true,
      message: json['message'] as String?,
    );
  }
}
