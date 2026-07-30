import React, { useState, useEffect } from 'react';
import {
  Camera,
  Share2,
  ArrowRight,
  CheckCircle,
  BarChart3,
  Home,
  Menu,
  BookOpen,
} from 'lucide-react';

const MizanBrandedApp = () => {
  const [screen, setScreen] = useState('dashboard');
  const [scanProgress, setScanProgress] = useState(0);
  const [fatigueLevel, setFatigueLevel] = useState('green');
  const [activeTab, setActiveTab] = useState('linguistic');

  // Simulate scan progress
  useEffect(() => {
    if (screen !== 'scanner') return;

    if (scanProgress >= 100) {
      const transitionTimer = setTimeout(() => setScreen('results'), 1500);
      return () => clearTimeout(transitionTimer);
    }

    const timer = setTimeout(() => {
      setScanProgress(prev => Math.min(prev + Math.random() * 25, 100));
    }, 400);
    return () => clearTimeout(timer);
  }, [screen, scanProgress]);

  // Simulate fatigue changes
  useEffect(() => {
    const fatigueTimer = setInterval(() => {
      const levels = ['green', 'orange', 'red'];
      setFatigueLevel(levels[Math.floor(Math.random() * 3)]);
    }, 4000);
    return () => clearInterval(fatigueTimer);
  }, []);

  const getFatigueColor = () => {
    switch (fatigueLevel) {
      case 'green':
        return { bg: 'bg-emerald-50', border: 'border-emerald-400', text: 'text-emerald-700', icon: '✅', msg: 'ممتاز! أنت في تركيز عالي' };
      case 'orange':
        return { bg: 'bg-amber-50', border: 'border-amber-400', text: 'text-amber-700', icon: '⚠️', msg: 'خذ فترة راحة 15 دقيقة' };
      case 'red':
        return { bg: 'bg-red-50', border: 'border-red-400', text: 'text-red-700', icon: '🔴', msg: 'توقف واسترح اليوم' };
      default:
        return { bg: 'bg-emerald-50', border: 'border-emerald-400', text: 'text-emerald-700', icon: '✅', msg: 'ممتاز!' };
    }
  };

  // Color palette from image
  const brandColors = {
    deepTeal: '#1a4d52',
    emeraldGreen: '#2d7a5e',
    darkGreen: '#1e5f47',
    gold: '#d4af37',
    lightTeal: '#e8f4f6',
    darkText: '#0d3d44'
  };

  const layers = [
    { name: 'معالجة الصورة', icon: '📸', progress: scanProgress > 15 ? 100 : scanProgress * 6.67 },
    { name: 'قراءة النص', icon: '📝', progress: scanProgress > 30 ? 100 : Math.max(0, (scanProgress - 15) * 6.67) },
    { name: 'تحليل لغوي', icon: '🔍', progress: scanProgress > 50 ? 100 : Math.max(0, (scanProgress - 30) * 5) },
    { name: 'تقييم منطقي', icon: '⚙️', progress: scanProgress > 75 ? 100 : Math.max(0, (scanProgress - 50) * 4) },
    { name: 'توليد التقرير', icon: '📊', progress: scanProgress > 90 ? 100 : Math.max(0, (scanProgress - 75) * 6.67) }
  ];

  const feedbackTabs = {
    linguistic: {
      score: 4.0,
      icon: '📝',
      title: 'التحليل اللغوي',
      details: [
        '✅ المصطلحات العلمية دقيقة',
        '⚠️ حرف صغير في "الانقسام"',
        '✅ البنية النحوية صحيحة'
      ]
    },
    logic: {
      score: 4.5,
      icon: '⚙️',
      title: 'التحليل المنطقي',
      details: [
        '✅ تسلسل الاستدلال منطقي',
        '✅ ربط المفاهيم صحيح',
        '⚠️ نقص توضيح العلاقات'
      ]
    },
    regulatory: {
      score: 4.2,
      icon: '📋',
      title: 'معايير الباريم',
      details: [
        '✅ تطابق 95% مع المعايير',
        '✅ العناصر الأساسية مكتملة',
        '⚠️ يمكن إضافة أمثلة'
      ]
    },
    execution: {
      score: 3.8,
      icon: '🎯',
      title: 'خطة التحسين',
      details: [
        '📍 ركز على الوراثة (12 ساعة)',
        '📍 حل 5 تمارين إضافية',
        '📍 شاهد شرح الأليلات'
      ]
    }
  };

  // ==================== DASHBOARD SCREEN ====================
  const DashboardScreen = () => {
    const fatigueColors = getFatigueColor();

    return (
      <div className="min-h-screen" style={{ background: `linear-gradient(135deg, ${brandColors.lightTeal} 0%, white 100%)` }}>
        {/* Header */}
        <div className="sticky top-0 z-50 backdrop-blur-sm" style={{ backgroundColor: brandColors.deepTeal }}>
          <div className="px-6 py-4">
            <div className="flex items-center justify-between mb-4">
              {/* Logo */}
              <div className="flex items-center gap-2">
                <div className="w-10 h-10 rounded-lg flex items-center justify-center" style={{ backgroundColor: brandColors.gold }}>
                  <span className="text-lg font-bold" style={{ color: brandColors.deepTeal }}>⚖️</span>
                </div>
                <div>
                  <h1 className="text-white font-bold text-lg">الميزان</h1>
                  <p className="text-xs" style={{ color: brandColors.gold }}>MIZAN AI</p>
                </div>
              </div>
              <button className="p-2 hover:bg-white hover:bg-opacity-10 rounded-lg transition text-white">
                <Menu size={24} />
              </button>
            </div>
          </div>
        </div>

        {/* Main Content */}
        <div className="px-4 md:px-6 py-8 max-w-2xl mx-auto space-y-6">
          {/* Welcome */}
          <div className="space-y-2">
            <h2 className="text-3xl font-bold text-gray-900">مرحباً محمد! 👋</h2>
            <p style={{ color: brandColors.deepTeal }} className="font-medium">استعد لتقييم إجاباتك بذكاء اصطناعي</p>
          </div>

          {/* Bio-Feedback Widget */}
          <div className={`p-6 rounded-2xl border-2 transition-all ${fatigueColors.bg} ${fatigueColors.border}`}>
            <div className="flex items-center gap-4 mb-4">
              <span className="text-4xl">{fatigueColors.icon}</span>
              <div>
                <h3 className={`font-bold text-lg ${fatigueColors.text}`}>مستوى الطاقة</h3>
                <p className={fatigueColors.text}>{fatigueColors.msg}</p>
              </div>
            </div>
            <div className="w-full h-3 bg-gray-200 rounded-full overflow-hidden">
              <div
                className={`h-full transition-all ${
                  fatigueLevel === 'green' ? 'bg-emerald-500 w-[85%]' :
                  fatigueLevel === 'orange' ? 'bg-amber-500 w-[50%]' :
                  'bg-red-500 w-[20%]'
                }`}
              />
            </div>
          </div>

          {/* Stats Grid */}
          <div className="grid grid-cols-2 gap-4">
            <div className="p-4 rounded-xl bg-white shadow-sm hover:shadow-md transition border-l-4" style={{ borderLeftColor: brandColors.emeraldGreen }}>
              <p className="text-sm text-gray-600 mb-1">متوسط درجاتك</p>
              <p className="text-2xl font-bold text-gray-900">14.2/20</p>
              <p className="text-xs mt-2" style={{ color: brandColors.emeraldGreen }}>↑ +0.8 من الأسبوع الماضي</p>
            </div>

            <div className="p-4 rounded-xl bg-white shadow-sm hover:shadow-md transition border-l-4" style={{ borderLeftColor: brandColors.gold }}>
              <p className="text-sm text-gray-600 mb-1">توقع البكالوريا</p>
              <p className="text-2xl font-bold text-gray-900">14.8/20</p>
              <p className="text-xs mt-2" style={{ color: brandColors.deepTeal }}>دقة 95%</p>
            </div>

            <div className="p-4 rounded-xl bg-white shadow-sm hover:shadow-md transition border-l-4" style={{ borderLeftColor: brandColors.deepTeal }}>
              <p className="text-sm text-gray-600 mb-1">إجاباتك</p>
              <p className="text-2xl font-bold text-gray-900">23</p>
              <p className="text-xs mt-2 text-gray-500">هذا الشهر</p>
            </div>

            <div className="p-4 rounded-xl bg-white shadow-sm hover:shadow-md transition border-l-4 border-red-400">
              <p className="text-sm text-gray-600 mb-1">المادة الضعيفة</p>
              <p className="text-2xl font-bold text-red-600">الوراثة</p>
              <p className="text-xs mt-2 text-red-500">متوسط: 12/20</p>
            </div>
          </div>

          {/* Main CTA */}
          <button
            onClick={() => {
              setScanProgress(0);
              setScreen('scanner');
            }}
            className="w-full py-4 px-6 rounded-xl font-bold text-white text-lg shadow-lg hover:shadow-xl transition transform hover:scale-105 active:scale-95 flex items-center justify-center gap-3"
            style={{ background: `linear-gradient(135deg, ${brandColors.emeraldGreen}, ${brandColors.darkGreen})` }}
          >
            <Camera size={24} />
            صوّر إجابتك الآن
            <ArrowRight size={20} />
          </button>

          {/* Secondary Actions */}
          <div className="grid grid-cols-2 gap-3">
            <button className="py-3 px-4 rounded-xl border-2 font-semibold transition hover:bg-opacity-5" style={{ borderColor: brandColors.emeraldGreen, color: brandColors.emeraldGreen }}>
              <BookOpen className="w-5 h-5 mx-auto mb-1" />
              تمارين
            </button>
            <button className="py-3 px-4 rounded-xl border-2 font-semibold transition hover:bg-opacity-5" style={{ borderColor: brandColors.deepTeal, color: brandColors.deepTeal }}>
              <BarChart3 className="w-5 h-5 mx-auto mb-1" />
              الإحصائيات
            </button>
          </div>
        </div>
      </div>
    );
  };

  // ==================== SCANNER SCREEN ====================
  const ScannerScreen = () => {
    return (
      <div className="min-h-screen" style={{ background: `linear-gradient(135deg, ${brandColors.deepTeal}, ${brandColors.darkGreen})` }} >
        {/* Animated Loader */}
        <div className="relative w-32 h-32 mb-12">
          <div className="absolute inset-0 rounded-full border-4 border-white border-opacity-30"></div>
          <div className="absolute inset-0 rounded-full border-4 border-transparent border-t-white animate-spin"></div>
          <div className="absolute inset-4 rounded-full flex items-center justify-center text-4xl">
            📸
          </div>
        </div>

        {/* Progress Text */}
        <div className="w-full max-w-sm mb-12 text-white text-center">
          <h2 className="text-2xl font-bold mb-3">جاري التقييم...</h2>
          <p className="text-white text-opacity-80 mb-6">{Math.round(scanProgress)}%</p>

          <div className="w-full h-3 bg-white bg-opacity-30 rounded-full overflow-hidden mb-8">
            <div
              className="h-full bg-white rounded-full transition-all duration-300"
              style={{ width: `${scanProgress}%` }}
            />
          </div>
        </div>

        {/* 5-Layer Progress */}
        <div className="w-full max-w-sm space-y-3 mb-8">
          {layers.map((layer, idx) => (
            <div key={idx} className="bg-white bg-opacity-10 backdrop-blur rounded-xl p-4 border border-white border-opacity-20">
              <div className="flex items-center gap-3 mb-2">
                <span className="text-2xl">{layer.icon}</span>
                <span className="text-white font-medium flex-1">{layer.name}</span>
                {layer.progress === 100 && <CheckCircle size={20} className="text-emerald-300" />}
              </div>
              <div className="w-full h-2 bg-white bg-opacity-20 rounded-full overflow-hidden">
                <div
                  className={`h-full transition-all duration-300 ${
                    layer.progress === 100 ? 'bg-emerald-400' : 'bg-white'
                  }`}
                  style={{ width: `${layer.progress}%` }}
                />
              </div>
            </div>
          ))}
        </div>

        <p className="text-white text-opacity-80 text-center text-sm">
          لا تغلق التطبيق، جاري تحليل إجابتك...
        </p>
      </div>
    );
  };

  // ==================== RESULTS SCREEN ====================
  const ResultsScreen = () => {
    const currentFeedback = feedbackTabs[activeTab];

    return (
      <div className="min-h-screen" style={{ background: `linear-gradient(135deg, ${brandColors.lightTeal} 0%, white 100%)` }} >
        {/* Header */}
        <div className="sticky top-0 z-50 backdrop-blur-sm" style={{ backgroundColor: brandColors.deepTeal }}>
          <div className="px-6 py-4 flex items-center justify-between">
            <h1 className="text-xl font-bold text-white">نتائج التقييم</h1>
            <button
              onClick={() => {
                setScanProgress(0);
                setScreen('dashboard');
              }}
              className="p-2 hover:bg-white hover:bg-opacity-20 rounded-lg transition text-white"
            >
              <Home size={24} />
            </button>
          </div>
        </div>

        {/* Main Content */}
        <div className="px-4 md:px-6 py-8 max-w-2xl mx-auto space-y-6">
          {/* Grade Card */}
          <div
            className="rounded-2xl p-8 text-white shadow-xl"
            style={{ background: `linear-gradient(135deg, ${brandColors.emeraldGreen}, ${brandColors.darkGreen})` }}
          >
            <p className="text-center text-white text-opacity-90 mb-4">العلوم الطبيعية - السؤال 3</p>

            <div className="flex items-center justify-center gap-4 mb-8">
              <div className="text-7xl font-bold">14.5</div>
              <div>
                <div className="text-3xl text-white text-opacity-90">/20</div>
                <div className="text-sm text-white text-opacity-75 mt-1">درجة ممتازة</div>
              </div>
            </div>

            <div className="grid grid-cols-3 gap-3 pt-6 border-t border-white border-opacity-20">
              <div className="text-center">
                <p className="text-white text-opacity-70 text-sm">التحسن</p>
                <p className="text-xl font-bold">+2.0</p>
              </div>
              <div className="text-center">
                <p className="text-white text-opacity-70 text-sm">الترتيب</p>
                <p className="text-xl font-bold">#5</p>
              </div>
              <div className="text-center">
                <p className="text-white text-opacity-70 text-sm">الثقة</p>
                <p className="text-xl font-bold">96%</p>
              </div>
            </div>
          </div>

          {/* Prediction Card */}
          <div className="p-6 rounded-xl" style={{ background: `linear-gradient(135deg, ${brandColors.lightTeal}, white)`, border: `2px solid ${brandColors.gold}` }}>
            <div className="flex items-center justify-between">
              <div>
                <p className="text-gray-600 mb-1">توقع البكالوريا</p>
                <p className="text-3xl font-bold" style={{ color: brandColors.deepTeal }}>14.8/20</p>
              </div>
              <span className="text-4xl">🎯</span>
            </div>
            <p className="text-sm mt-3" style={{ color: brandColors.deepTeal }}>دقة: 95%</p>
          </div>

          {/* Tabs */}
          <div className="flex gap-2 overflow-x-auto pb-2 border-b-2" style={{ borderBottomColor: brandColors.lightTeal }}>
            {Object.entries(feedbackTabs).map(([key, data]) => (
              <button
                key={key}
                onClick={() => setActiveTab(key)}
                className={`px-4 py-3 rounded-lg font-medium whitespace-nowrap transition-all ${
                  activeTab === key
                    ? 'text-white'
                    : 'text-gray-600 hover:text-gray-900'
                }`}
                style={{
                  backgroundColor: activeTab === key ? brandColors.emeraldGreen : 'transparent'
                }}
              >
                <span className="mr-2">{data.icon}</span>
                {data.title}
              </button>
            ))}
          </div>

          {/* Tab Content */}
          <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-4">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-bold text-gray-900">{currentFeedback.title}</h3>
              <div className="text-right">
                <p className="text-sm text-gray-600">النقاط</p>
                <p className="text-2xl font-bold" style={{ color: brandColors.emeraldGreen }}>{currentFeedback.score}</p>
              </div>
            </div>

            <div className="space-y-3 pt-4 border-t border-gray-200">
              {currentFeedback.details.map((detail, idx) => (
                <div
                  key={idx}
                  className="p-3 rounded-lg"
                  style={{
                    backgroundColor: detail.includes('✅') ? '#dcfce7' : detail.includes('⚠️') ? '#fef3c7' : '#dbeafe',
                    borderLeft: `4px solid ${
                      detail.includes('✅') ? '#22c55e' : detail.includes('⚠️') ? '#f59e0b' : '#3b82f6'
                    }`
                  }}
                >
                  <p className="text-gray-900">{detail}</p>
                </div>
              ))}
            </div>
          </div>

          {/* CTA */}
          <div className="p-6 rounded-xl" style={{ backgroundColor: `${brandColors.emeraldGreen}20`, border: `2px solid ${brandColors.emeraldGreen}` }}>
            <p className="font-bold text-gray-900 mb-3">هل استفدت من التقييم؟</p>
            <button
              onClick={() => alert('تم نسخ رابط المشاركة! 🎉')}
              className="w-full py-3 px-4 rounded-lg text-white font-bold flex items-center justify-center gap-2 transition hover:shadow-lg"
              style={{ background: `linear-gradient(135deg, ${brandColors.emeraldGreen}, ${brandColors.darkGreen})` }}
            >
              <Share2 size={20} />
              شارك النتيجة
            </button>
          </div>

          {/* Bottom Actions */}
          <div className="grid grid-cols-2 gap-3">
            <button
              onClick={() => {
                setScanProgress(0);
                setScreen('scanner');
              }}
              className="py-3 px-4 rounded-xl border-2 font-bold transition"
              style={{ borderColor: brandColors.deepTeal, color: brandColors.deepTeal }}
            >
              قيّم إجابة أخرى
            </button>
            <button
              className="py-3 px-4 rounded-xl font-bold text-white transition"
              style={{ backgroundColor: brandColors.emeraldGreen }}
            >
              اسأل المعلم
            </button>
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className="min-h-screen bg-white font-['Tajawal']" dir="rtl">
      {screen === 'dashboard' && <DashboardScreen />}
      {screen === 'scanner' && <ScannerScreen />}
      {screen === 'results' && <ResultsScreen />}
    </div>
  );
};

export default MizanBrandedApp;
