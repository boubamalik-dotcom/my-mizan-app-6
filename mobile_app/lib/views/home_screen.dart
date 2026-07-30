import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:provider/provider.dart';
import 'package:speech_to_text/speech_to_text.dart' as stt;

import 'package:el_mizan_real_estate/controllers/property_controller.dart';
import 'package:el_mizan_real_estate/theme/app_theme.dart';
import 'package:el_mizan_real_estate/views/property_detail_screen.dart';
import 'package:el_mizan_real_estate/widgets/property_card.dart';

/// الشاشة الرئيسية — عرض عقارات وهران مع بحث ذكي بالدارجة
class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  final _searchController = TextEditingController();
  final _speech = stt.SpeechToText();
  bool _listening = false;
  bool _speechAvailable = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<PropertyController>().loadProperties();
      _initSpeech();
    });
  }

  Future<void> _initSpeech() async {
    _speechAvailable = await _speech.initialize(
      onError: (_) => setState(() => _listening = false),
      onStatus: (status) {
        if (status == 'done' || status == 'notListening') {
          setState(() => _listening = false);
        }
      },
    );
    if (mounted) setState(() {});
  }

  Future<void> _toggleVoice() async {
    if (!_speechAvailable) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('الميكروفون غير متاح على هذا الجهاز')),
      );
      return;
    }
    if (_listening) {
      await _speech.stop();
      setState(() => _listening = false);
      return;
    }
    setState(() => _listening = true);
    await _speech.listen(
      localeId: 'ar_DZ',
      onResult: (result) {
        setState(() => _searchController.text = result.recognizedWords);
        if (result.finalResult) {
          _runSearch();
        }
      },
    );
  }

  Future<void> _runSearch() async {
    final text = _searchController.text.trim();
    if (text.isEmpty) return;
    FocusScope.of(context).unfocus();
    final result = await context.read<PropertyController>().searchByPrompt(text);
    if (!mounted || result == null) return;
    final parts = <String>[
      if (result.district != null) 'الحي: ${result.district}',
      if (result.maxPrice != null)
        'حد السعر: ${result.maxPrice!.toStringAsFixed(0)} دج',
      if (result.propertyType != null) 'النوع: ${result.propertyType}',
      if (result.documentType != null) 'الوثيقة: ${result.documentType}',
    ];
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          parts.isEmpty ? 'تم تحليل الطلب' : parts.join(' · '),
        ),
      ),
    );
  }

  @override
  void dispose() {
    _searchController.dispose();
    _speech.stop();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final controller = context.watch<PropertyController>();

    return Scaffold(
      body: Container(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: [Color(0xFFDCECEA), AppColors.sand, Color(0xFFF3EFE6)],
          ),
        ),
        child: SafeArea(
          child: RefreshIndicator(
            color: AppColors.deepSea,
            onRefresh: () => context.read<PropertyController>().loadProperties(),
            child: CustomScrollView(
              physics: const AlwaysScrollableScrollPhysics(),
              slivers: [
                SliverToBoxAdapter(child: _buildHeader(context)),
                SliverToBoxAdapter(child: _buildSmartSearch(controller)),
                if (controller.lastParse != null)
                  SliverToBoxAdapter(child: _buildParseChips(controller)),
                if (controller.isLoading)
                  const SliverFillRemaining(
                    child: Center(child: CircularProgressIndicator()),
                  )
                else if (controller.properties.isEmpty)
                  SliverFillRemaining(
                    child: Center(
                      child: Text(
                        'ما لقيناش عقارات مطابقة لطلبك',
                        style: GoogleFonts.cairo(
                          fontSize: 16,
                          color: AppColors.muted,
                        ),
                      ),
                    ),
                  )
                else
                  SliverPadding(
                    padding: const EdgeInsets.fromLTRB(16, 8, 16, 28),
                    sliver: SliverList.separated(
                      itemCount: controller.properties.length,
                      separatorBuilder: (_, __) => const SizedBox(height: 14),
                      itemBuilder: (context, index) {
                        final property = controller.properties[index];
                        return PropertyCard(
                          property: property,
                          onTap: () {
                            Navigator.of(context).push(
                              MaterialPageRoute(
                                builder: (_) =>
                                    PropertyDetailScreen(property: property),
                              ),
                            );
                          },
                        );
                      },
                    ),
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildHeader(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 12, 20, 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'El Mizan',
            style: GoogleFonts.cairo(
              fontSize: 34,
              fontWeight: FontWeight.w900,
              color: AppColors.deepSea,
              height: 1.1,
            ),
          ),
          Text(
            'الميزان العقاري — وهران',
            style: GoogleFonts.cairo(
              fontSize: 16,
              fontWeight: FontWeight.w600,
              color: AppColors.lagoon,
            ),
          ),
          const SizedBox(height: 6),
          Text(
            'منطق الميزان يوازن السعر والثقة قبل أي معاينة.',
            style: GoogleFonts.cairo(fontSize: 14, color: AppColors.muted),
          ),
        ],
      ),
    );
  }

  Widget _buildSmartSearch(PropertyController controller) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
      child: Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: Colors.white.withOpacity(0.88),
          borderRadius: BorderRadius.circular(22),
          border: Border.all(color: AppColors.lagoon.withOpacity(0.15)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              'بحث ذكي بالدارجة الوهرانية',
              style: GoogleFonts.cairo(
                fontWeight: FontWeight.w700,
                color: AppColors.deepSea,
              ),
            ),
            const SizedBox(height: 8),
            Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _searchController,
                    textInputAction: TextInputAction.search,
                    onSubmitted: (_) => _runSearch(),
                    decoration: InputDecoration(
                      hintText: 'مثال: نحوس على F3 في بئر الجير حدود 1.2 مليار بعقد',
                      hintStyle: GoogleFonts.cairo(fontSize: 13, color: AppColors.muted),
                      prefixIcon: const Icon(Icons.auto_awesome, color: AppColors.lagoon),
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                IconButton.filledTonal(
                  onPressed: _toggleVoice,
                  style: IconButton.styleFrom(
                    backgroundColor: _listening
                        ? AppColors.high.withOpacity(0.2)
                        : AppColors.mist,
                  ),
                  icon: Icon(
                    _listening ? Icons.mic : Icons.mic_none_rounded,
                    color: _listening ? AppColors.high : AppColors.deepSea,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 10),
            FilledButton.icon(
              onPressed: controller.isParsing ? null : _runSearch,
              icon: controller.isParsing
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                    )
                  : const Icon(Icons.search_rounded),
              label: Text(controller.isParsing ? 'جارٍ التحليل...' : 'حلّل الطلب'),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildParseChips(PropertyController controller) {
    final p = controller.lastParse!;
    final chips = <String>[
      if (p.district != null) p.district!,
      if (p.propertyType != null) p.propertyType!,
      if (p.documentType != null) p.documentType!,
      if (p.maxPrice != null) '≤ ${p.maxPrice!.toStringAsFixed(0)} دج',
    ];
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 10, 16, 0),
      child: Wrap(
        spacing: 8,
        runSpacing: 8,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          ...chips.map(
            (c) => Chip(
              label: Text(c, style: GoogleFonts.cairo(fontSize: 12)),
              backgroundColor: AppColors.mist,
              side: BorderSide.none,
            ),
          ),
          TextButton(
            onPressed: () {
              _searchController.clear();
              controller.clearSearch();
            },
            child: Text('مسح الفلتر', style: GoogleFonts.cairo()),
          ),
        ],
      ),
    );
  }
}
