# El Mizan Real Estate — Backend

واجهة FastAPI لوسيط عقاري ذكي لمدينة **وهران** يعمل بمنطق الميزان.

## المتطلبات

- Python 3.10+
- PostgreSQL (اختياري للتطوير الأولي)

## التثبيت والتشغيل

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## نماذج قاعدة البيانات

| الجدول | الوصف |
|--------|--------|
| `users` | مشترٍ / بائع / وسيط |
| `properties` | عقارات وهران (بئر الجير، العقيد لطفي، USTO، الكورنيش) |
| `inspections` | معاينات مع عمولة الميزان 1.5% عند `commission_agreed=true` |

تُنشأ الجداول تلقائياً عند تشغيل التطبيق عبر `init_db()`.

الافتراضي محلياً: SQLite (`el_mizan.db`). للإنتاج عيّن `DATABASE_URL` إلى PostgreSQL.

## منطق الميزان (AI)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/ai/evaluate-price` | ميزان السعر قبل نشر العقار |
| POST | `/api/v1/ai/parse-prompt` | تحويل الدارجة الوهرانية إلى استعلام بحث |

المحرك: `app/services/ai_engine.py` — يستخدم OpenAI عند توفر `OPENAI_API_KEY`، وإلا يعمل بمحرك محلي احتياطي لمعدلات أحياء وهران.

## العقارات والمعاينات

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/properties/` | قائمة عامة مع Privacy Shield (بدون هاتف/عنوان دقيق) |
| POST | `/api/v1/properties/` | نشر عقار + حفظ تقييم الميزان تلقائياً |
| POST | `/api/v1/inspections/book` | حجز معاينة (يتطلب `commission_agreed=true`) |
| POST | `/api/v1/inspections/confirm` | تأكيد المالك → نقطة التلاقي + التذكرة المتبادلة |

## المسارات التجريبية

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | هوية التطبيق |
| GET | `/health` | Health check |
| GET | `/api/v1/health` | Health check للإصدار v1 |

وثائق OpenAPI: `http://localhost:8000/docs`
