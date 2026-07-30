import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:intl/intl.dart';

import 'package:el_mizan_real_estate/models/property.dart';
import 'package:el_mizan_real_estate/services/api_service.dart';
import 'package:el_mizan_real_estate/theme/app_theme.dart';
import 'package:el_mizan_real_estate/views/booking_success_screen.dart';
import 'package:el_mizan_real_estate/widgets/mizan_badge.dart';

/// تفاصيل العقار + تقرير الميزان + حجز المعاينة
class PropertyDetailScreen extends StatefulWidget {
  const PropertyDetailScreen({
    super.key,
    required this.property,
    this.apiService,
    this.buyerId = 2,
  });

  final Property property;
  final ApiService? apiService;
  final int buyerId;

  @override
  State<PropertyDetailScreen> createState() => _PropertyDetailScreenState();
}

class _PropertyDetailScreenState extends State<PropertyDetailScreen> {
  late final ApiService _api = widget.apiService ?? ApiService();
  bool _booking = false;

  Future<void> _openBookingDialog() async {
    final scheduledAt = DateTime.now().add(const Duration(days: 2));
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) {
        return Directionality(
          textDirection: TextDirection.rtl,
          child: AlertDialog(
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(22)),
            title: Text(
              'تعهد عمولة الميزان',
              style: GoogleFonts.cairo(fontWeight: FontWeight.w800),
            ),
            content: SingleChildScrollView(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'قبل حجز المعاينة، نطلب موافقتك الصريحة على منطق الميزان الشفاف:',
                    style: GoogleFonts.cairo(height: 1.5),
                  ),
                  const SizedBox(height: 12),
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.all(14),
                    decoration: BoxDecoration(
                      color: AppColors.mist,
                      borderRadius: BorderRadius.circular(16),
                    ),
                    child: Text(
                      'أتعهد بدفع عمولة الوساطة بنسبة 1.5٪ فقط عند إتمام الصفقة عبر تطبيق El Mizan Real Estate. '
                      'لا تُكشف بيانات التواصل ولا العنوان الدقيق إلا بعد تأكيد المالك للموعد.',
                      style: GoogleFonts.cairo(
                        fontWeight: FontWeight.w600,
                        height: 1.55,
                        color: AppColors.deepSea,
                      ),
                    ),
                  ),
                  const SizedBox(height: 10),
                  Text(
                    'الموعد المقترح: ${DateFormat('yyyy/MM/dd — HH:mm', 'ar').format(scheduledAt)}',
                    style: GoogleFonts.cairo(color: AppColors.muted),
                  ),
                ],
              ),
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(context, false),
                child: Text('إلغاء', style: GoogleFonts.cairo()),
              ),
              FilledButton(
                onPressed: () => Navigator.pop(context, true),
                child: Text('أوافق وأؤكد الحجز', style: GoogleFonts.cairo()),
              ),
            ],
          ),
        );
      },
    );

    if (confirmed != true || !mounted) return;
    setState(() => _booking = true);
    try {
      final booking = await _api.bookInspection(
        propertyId: widget.property.id,
        buyerId: widget.buyerId,
        scheduledAt: scheduledAt,
        commissionAgreed: true,
      );
      if (!mounted) return;
      Navigator.of(context).pushReplacement(
        MaterialPageRoute(
          builder: (_) => BookingSuccessScreen(
            booking: booking,
            propertyTitle: widget.property.title,
          ),
        ),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            'تعذّر الحجز. تأكد من تشغيل الخادم ووجود مشتري برقم ${widget.buyerId}.\n$e',
            style: GoogleFonts.cairo(),
          ),
        ),
      );
    } finally {
      if (mounted) setState(() => _booking = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final p = widget.property;
    final eval = p.mizanEvaluation;
    final priceFmt = NumberFormat.decimalPattern('ar');

    return Scaffold(
      body: Container(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [Color(0xFFE7F1F0), AppColors.sand],
          ),
        ),
        child: SafeArea(
          child: Column(
            children: [
              AppBar(
                title: Text('تفاصيل العقار', style: GoogleFonts.cairo()),
                backgroundColor: Colors.transparent,
              ),
              Expanded(
                child: ListView(
                  padding: const EdgeInsets.fromLTRB(16, 0, 16, 24),
                  children: [
                    Text(
                      p.title,
                      style: GoogleFonts.cairo(
                        fontSize: 26,
                        fontWeight: FontWeight.w900,
                        color: AppColors.deepSea,
                      ),
                    ),
                    const SizedBox(height: 8),
                    Row(
                      children: [
                        const Icon(Icons.place_outlined, color: AppColors.lagoon),
                        const SizedBox(width: 4),
                        Expanded(
                          child: Text(
                            p.approximateLocation ?? 'وهران — ${p.district}',
                            style: GoogleFonts.cairo(
                              fontSize: 15,
                              color: AppColors.muted,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 12),
                    Text(
                      '${priceFmt.format(p.price)} دج',
                      style: GoogleFonts.cairo(
                        fontSize: 24,
                        fontWeight: FontWeight.w800,
                        color: AppColors.ink,
                      ),
                    ),
                    const SizedBox(height: 10),
                    Wrap(
                      spacing: 8,
                      runSpacing: 8,
                      children: [
                        MizanBadge(balance: p.priceBalance),
                        if (p.documentType != null)
                          Chip(
                            label: Text(p.documentType!, style: GoogleFonts.cairo()),
                            backgroundColor: Colors.white,
                          ),
                      ],
                    ),
                    const SizedBox(height: 18),
                    _sectionCard(
                      title: 'عن العقار',
                      child: Text(
                        p.description?.isNotEmpty == true
                            ? p.description!
                            : 'لا يوجد وصف إضافي.',
                        style: GoogleFonts.cairo(height: 1.6, fontSize: 15),
                      ),
                    ),
                    const SizedBox(height: 14),
                    _sectionCard(
                      title: 'تقرير منطق الميزان (شفاف)',
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          if (eval == null)
                            Text(
                              'لا يتوفر تقييم بعد.',
                              style: GoogleFonts.cairo(color: AppColors.muted),
                            )
                          else ...[
                            _kv('الحكم', eval.priceBalance),
                            _kv(
                              'متوسط الحي',
                              eval.districtAvgPrice == null
                                  ? '—'
                                  : '${priceFmt.format(eval.districtAvgPrice)} دج',
                            ),
                            _kv(
                              'الانحراف',
                              eval.deviationPercent == null
                                  ? '—'
                                  : '${eval.deviationPercent!.toStringAsFixed(1)}٪',
                            ),
                            const SizedBox(height: 8),
                            Text(
                              eval.reasoning ?? '',
                              style: GoogleFonts.cairo(
                                height: 1.65,
                                fontSize: 14.5,
                                color: AppColors.ink,
                              ),
                            ),
                          ],
                        ],
                      ),
                    ),
                    const SizedBox(height: 14),
                    _sectionCard(
                      title: 'درع الخصوصية',
                      child: Text(
                        p.privacyNote ??
                            'العنوان الدقيق ورقم المالك يُكشفان فقط بعد تأكيد المعاينة.',
                        style: GoogleFonts.cairo(height: 1.55, color: AppColors.muted),
                      ),
                    ),
                  ],
                ),
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
                child: SizedBox(
                  width: double.infinity,
                  child: FilledButton.icon(
                    onPressed: _booking ? null : _openBookingDialog,
                    icon: _booking
                        ? const SizedBox(
                            width: 18,
                            height: 18,
                            child: CircularProgressIndicator(
                              strokeWidth: 2,
                              color: Colors.white,
                            ),
                          )
                        : const Text('📅', style: TextStyle(fontSize: 18)),
                    label: Text(
                      _booking ? 'جارٍ تأكيد الحجز...' : 'حجز موعد معاينة',
                      style: GoogleFonts.cairo(fontSize: 17, fontWeight: FontWeight.w800),
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _sectionCard({required String title, required Widget child}) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white.withOpacity(0.9),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: AppColors.lagoon.withOpacity(0.12)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: GoogleFonts.cairo(
              fontSize: 16,
              fontWeight: FontWeight.w800,
              color: AppColors.deepSea,
            ),
          ),
          const SizedBox(height: 10),
          child,
        ],
      ),
    );
  }

  Widget _kv(String k, String v) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 4),
      child: Row(
        children: [
          Text('$k: ', style: GoogleFonts.cairo(fontWeight: FontWeight.w700)),
          Expanded(child: Text(v, style: GoogleFonts.cairo())),
        ],
      ),
    );
  }
}
