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
# نافذة 1 — Backend
cd backend && uvicorn app.main:app --reload

# نافذة 2 — تطبيق الهاتف
cd mobile_app && flutter run
```

اختياري لتحديد عنوان الـ API:

```bash
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000   # Android emulator
flutter run --dart-define=API_BASE_URL=http://127.0.0.1:8000  # iOS / desktop
```
