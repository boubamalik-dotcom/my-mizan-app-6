import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:intl/intl.dart';

import 'package:el_mizan_real_estate/models/inspection_booking.dart';
import 'package:el_mizan_real_estate/theme/app_theme.dart';
import 'package:el_mizan_real_estate/views/home_screen.dart';

/// تذكرة المعاينة الرقمية بعد الحجز الناجح
class BookingSuccessScreen extends StatelessWidget {
  const BookingSuccessScreen({
    super.key,
    required this.booking,
    required this.propertyTitle,
  });

  final InspectionBooking booking;
  final String propertyTitle;

  @override
  Widget build(BuildContext context) {
    final dateFmt = DateFormat('EEEE d MMMM yyyy — HH:mm', 'ar');

    return Scaffold(
      body: Container(
        width: double.infinity,
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: [Color(0xFF0F3D3E), Color(0xFF1F6F6A), Color(0xFFE8F1F0)],
            stops: [0, 0.35, 0.35],
          ),
        ),
        child: SafeArea(
          child: Padding(
            padding: const EdgeInsets.all(20),
            child: Column(
              children: [
                const SizedBox(height: 12),
                Text(
                  'تم حجز المعاينة',
                  style: GoogleFonts.cairo(
                    fontSize: 26,
                    fontWeight: FontWeight.w900,
                    color: Colors.white,
                  ),
                ),
                Text(
                  'تذكرتك الرقمية جاهزة',
                  style: GoogleFonts.cairo(color: Colors.white70, fontSize: 15),
                ),
                const SizedBox(height: 24),
                Expanded(
                  child: Container(
                    width: double.infinity,
                    padding: const EdgeInsets.all(20),
                    decoration: BoxDecoration(
                      color: AppColors.card,
                      borderRadius: BorderRadius.circular(28),
                      boxShadow: [
                        BoxShadow(
                          color: Colors.black.withOpacity(0.12),
                          blurRadius: 24,
                          offset: const Offset(0, 12),
                        ),
                      ],
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Text(
                          'El Mizan — تذكرة معاينة',
                          textAlign: TextAlign.center,
                          style: GoogleFonts.cairo(
                            fontWeight: FontWeight.w800,
                            fontSize: 18,
                            color: AppColors.deepSea,
                          ),
                        ),
                        const SizedBox(height: 18),
                        _ticketRow('العقار', propertyTitle),
                        _ticketRow('الحي', booking.district),
                        _ticketRow(
                          'الموعد',
                          dateFmt.format(booking.scheduledAt.toLocal()),
                        ),
                        _ticketRow(
                          'العمولة',
                          '${(booking.commissionRate * 100).toStringAsFixed(1)}٪ (متعهَّد بها)',
                        ),
                        _ticketRow('الحالة', booking.status),
                        const SizedBox(height: 16),
                        Container(
                          padding: const EdgeInsets.symmetric(
                            vertical: 16,
                            horizontal: 12,
                          ),
                          decoration: BoxDecoration(
                            color: AppColors.mist,
                            borderRadius: BorderRadius.circular(18),
                            border: Border.all(
                              color: AppColors.lagoon.withOpacity(0.25),
                            ),
                          ),
                          child: Column(
                            children: [
                              Text(
                                'رمز المعاينة',
                                style: GoogleFonts.cairo(
                                  color: AppColors.muted,
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                              const SizedBox(height: 6),
                              SelectableText(
                                booking.inspectionCode,
                                style: GoogleFonts.cairo(
                                  fontSize: 32,
                                  fontWeight: FontWeight.w900,
                                  letterSpacing: 1.5,
                                  color: AppColors.deepSea,
                                ),
                              ),
                              TextButton.icon(
                                onPressed: () {
                                  Clipboard.setData(
                                    ClipboardData(text: booking.inspectionCode),
                                  );
                                  ScaffoldMessenger.of(context).showSnackBar(
                                    SnackBar(
                                      content: Text(
                                        'تم نسخ الرمز',
                                        style: GoogleFonts.cairo(),
                                      ),
                                    ),
                                  );
                                },
                                icon: const Icon(Icons.copy_rounded, size: 18),
                                label: Text('نسخ الرمز', style: GoogleFonts.cairo()),
                              ),
                            ],
                          ),
                        ),
                        const Spacer(),
                        Container(
                          padding: const EdgeInsets.all(12),
                          decoration: BoxDecoration(
                            color: const Color(0xFFFFF8E8),
                            borderRadius: BorderRadius.circular(14),
                          ),
                          child: Text(
                            'ملاحظة حماية البيانات: نقطة التلاقي والعنوان الدقيق '
                            'ورقم المالك لن تظهر إلا بعد تأكيد المالك للموعد. '
                            'احتفظ برمز المعاينة كتذكرة متبادلة.',
                            style: GoogleFonts.cairo(
                              fontSize: 13,
                              height: 1.55,
                              color: AppColors.ink,
                            ),
                          ),
                        ),
                        if (booking.message != null) ...[
                          const SizedBox(height: 10),
                          Text(
                            booking.message!,
                            style: GoogleFonts.cairo(
                              fontSize: 12.5,
                              color: AppColors.muted,
                              height: 1.4,
                            ),
                          ),
                        ],
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 16),
                SizedBox(
                  width: double.infinity,
                  child: FilledButton(
                    onPressed: () {
                      Navigator.of(context).pushAndRemoveUntil(
                        MaterialPageRoute(builder: (_) => const HomeScreen()),
                        (_) => false,
                      );
                    },
                    child: Text('العودة للرئيسية', style: GoogleFonts.cairo()),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _ticketRow(String label, String value) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 80,
            child: Text(
              label,
              style: GoogleFonts.cairo(
                color: AppColors.muted,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
          Expanded(
            child: Text(
              value,
              style: GoogleFonts.cairo(
                fontWeight: FontWeight.w700,
                color: AppColors.ink,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
