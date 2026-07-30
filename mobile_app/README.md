# El Mizan Real Estate — Mobile App

تطبيق Flutter لوسيط عقاري ذكي لمدينة **وهران** يعمل بمنطق الميزان.

## الشاشات

| الملف | الوظيفة |
|--------|---------|
| `views/home_screen.dart` | بطاقات العقارات + ميزان السعر + بحث ذكي (نص/صوت) |
| `views/property_detail_screen.dart` | التفاصيل + تقرير AI + حجز معاينة مع تعهد 1.5% |
| `views/booking_success_screen.dart` | تذكرة رقمية بـ `inspection_code` |

## التشغيل

```bash
flutter pub get
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000   # Android emulator
# أو
flutter run --dart-define=API_BASE_URL=http://127.0.0.1:8000  # iOS / desktop
```

تأكد من تشغيل خادم الـ backend على المنفذ `8000`.
