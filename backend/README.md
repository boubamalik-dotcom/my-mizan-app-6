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

## المسارات التجريبية

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | هوية التطبيق |
| GET | `/health` | Health check |
| GET | `/api/v1/health` | Health check للإصدار v1 |

وثائق OpenAPI: `http://localhost:8000/docs`
