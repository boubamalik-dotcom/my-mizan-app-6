"""
محرك منطق الميزان — El Mizan Real Estate AI Engine

يقيم أسعار عقارات وهران ويفهم طلبات المشترين بالدارجة الوهرانية/العربية.
يستخدم OpenAI عند توفر المفتاح، مع محرك محلي احتياطي (منطق الميزان).
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)

# متوسط أسعار تقريبية لشقق F3 في أحياء وهران (بالدينار الجزائري DZD)
# تُحدَّث دورياً — مرجع لمنطق الميزان عند غياب الـ API
ORAN_MARKET_AVERAGES_DZD: dict[str, dict[str, Any]] = {
    "بئر الجير": {
        "avg_f3": 11_000_000,
        "range": (8_000_000, 15_000_000),
        "aliases": ["بير الجير", "bir el djir", "bir djir", "biredjir"],
    },
    "العقيد لطفي": {
        "avg_f3": 9_500_000,
        "range": (7_000_000, 13_000_000),
        "aliases": ["العقيد", "akid lotfi", "lotfi", "العقيد لطفي"],
    },
    "USTO": {
        "avg_f3": 8_500_000,
        "range": (6_000_000, 12_000_000),
        "aliases": ["إيساتو", "ايساتو", "usto", "جامعة العلوم"],
    },
    "الكورنيش": {
        "avg_f3": 18_000_000,
        "range": (14_000_000, 30_000_000),
        "aliases": ["كورنيش", "corniche", "الواجهة البحرية"],
    },
    "المنزه": {
        "avg_f3": 12_500_000,
        "range": (9_000_000, 17_000_000),
        "aliases": ["منهز", "el menzeh", "menzeh"],
    },
    "الصدِّيقية": {
        "avg_f3": 10_000_000,
        "range": (7_500_000, 14_000_000),
        "aliases": ["الصديقية", "seddikia"],
    },
    "حي البدر": {
        "avg_f3": 9_000_000,
        "range": (6_500_000, 12_000_000),
        "aliases": ["البدر", "el badr"],
    },
}

DOCUMENT_ALIASES: dict[str, str] = {
    "عقد": "عقد توثيقي",
    "عقد توثيقي": "عقد توثيقي",
    "توثيقي": "عقد توثيقي",
    "دفتر": "دفتر عقاري",
    "دفتر عقاري": "دفتر عقاري",
    "عرفي": "عرفي",
    "ورقة عرفية": "عرفي",
}

PROPERTY_TYPE_PATTERN = re.compile(
    r"\b(F[1-6]|Studio|Villa|فيلا|فيلاّ|دوبلكس|duplex|منزل|شقة)\b",
    re.IGNORECASE,
)


def _get_openai_client():
    """Return OpenAI client if API key is configured, else None."""
    api_key = settings.openai_api_key or os.getenv("OPENAI_API_KEY", "")
    if not api_key or api_key.startswith("your_"):
        return None
    try:
        from openai import OpenAI

        return OpenAI(api_key=api_key)
    except Exception as exc:  # noqa: BLE001
        logger.warning("OpenAI client unavailable: %s", exc)
        return None


def _normalize_district(raw: str | None) -> str | None:
    if not raw:
        return None
    text = raw.strip()
    for district, meta in ORAN_MARKET_AVERAGES_DZD.items():
        if text == district or text.lower() == district.lower():
            return district
        for alias in meta["aliases"]:
            if alias.lower() in text.lower() or text.lower() in alias.lower():
                return district
    return text


def _price_balance_label(asking: float, low: float, high: float, avg: float) -> str:
    if asking < low:
        return "منخفض"
    if asking > high:
        return "مرتفع"
    # Within range — finer check vs average
    deviation = (asking - avg) / avg if avg else 0
    if deviation > 0.12:
        return "مرتفع"
    if deviation < -0.12:
        return "منخفض"
    return "عادل"


def _local_evaluate_property_price(property_data: dict) -> dict:
    """Heuristic ميزان السعر using Oran district averages (no external API)."""
    district = _normalize_district(
        property_data.get("district") or property_data.get("address")
    )
    asking = float(property_data.get("price") or 0)
    title = property_data.get("title") or "عقار"
    document_type = property_data.get("document_type")

    market = ORAN_MARKET_AVERAGES_DZD.get(district or "")
    if not market:
        # Fallback city-wide mid estimate
        avg = 10_000_000.0
        low, high = 6_000_000.0, 20_000_000.0
        district_label = district or "وهران (عام)"
    else:
        avg = float(market["avg_f3"])
        low, high = (float(x) for x in market["range"])
        district_label = district or "وهران"

    balance = _price_balance_label(asking, low, high, avg)
    deviation = round(((asking - avg) / avg) * 100, 1) if avg else 0.0

    if balance == "عادل":
        reasoning = (
            f"ميزان السعر لعقار «{title}» في {district_label}: السعر المطلوب "
            f"{asking:,.0f} دج قريب من متوسط الحي ({avg:,.0f} دج لشقق F3 تقريباً). "
            f"الانحراف عن المتوسط {deviation:+.1f}% ضمن نطاق السوق ({low:,.0f}–{high:,.0f} دج)."
        )
    elif balance == "مرتفع":
        reasoning = (
            f"ميزان السعر يشير إلى أن «{title}» في {district_label} مرتفع نسبياً: "
            f"{asking:,.0f} دج مقابل متوسط حوالي {avg:,.0f} دج "
            f"(انحراف {deviation:+.1f}%). يُنصح بمراجعة السعر قبل النشر أو توضيح مزايا إضافية."
        )
    else:
        reasoning = (
            f"ميزان السعر يشير إلى أن «{title}» في {district_label} منخفض عن السوق: "
            f"{asking:,.0f} دج مقابل متوسط حوالي {avg:,.0f} دج "
            f"(انحراف {deviation:+.1f}%). قد يجذب مشترين بسرعة — تحقق من الوثائق والموقع."
        )

    if document_type:
        reasoning += f" نوع الوثيقة المذكور: {document_type}."

    return {
        "price_balance": balance,
        "asking_price": asking,
        "district": district_label,
        "district_avg_price": avg,
        "market_range": {"min": low, "max": high},
        "deviation_percent": deviation,
        "reasoning": reasoning,
        "confidence": 0.72,
        "source": "mizan_local",
        "logic": "منطق الميزان",
    }


def _openai_json_completion(system: str, user: str) -> dict | None:
    client = _get_openai_client()
    if client is None:
        return None
    try:
        response = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            temperature=0.2,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        content = response.choices[0].message.content or "{}"
        return json.loads(content)
    except Exception as exc:  # noqa: BLE001
        logger.warning("OpenAI request failed, falling back to local engine: %s", exc)
        return None


def evaluate_property_price(property_data: dict) -> dict:
    """
    تحليل سعر العقار مقارنة بمتوسط أسعار أحياء وهران (ميزان السعر).

    Returns:
        dict with price_balance: عادل | مرتفع | منخفض + Arabic reasoning.
    """
    market_context = {
        name: {"avg_f3_dzd": meta["avg_f3"], "range_dzd": meta["range"]}
        for name, meta in ORAN_MARKET_AVERAGES_DZD.items()
    }
    system = (
        "أنت خبير عقاري لوهران (الجزائر) ضمن تطبيق El Mizan Real Estate. "
        "طبّق «منطق الميزان»: قارن السعر بمتوسط الحي وأعد JSON فقط بالحقول: "
        "price_balance (عادل|مرتفع|منخفض), asking_price, district, district_avg_price, "
        "market_range {min,max}, deviation_percent, reasoning (تعليل وظيفي بالعربية), confidence (0-1)."
    )
    user = (
        f"بيانات العقار:\n{json.dumps(property_data, ensure_ascii=False)}\n\n"
        f"مراجع السوق التقريبية (DZD لـ F3):\n{json.dumps(market_context, ensure_ascii=False)}"
    )
    ai_result = _openai_json_completion(system, user)
    if ai_result and ai_result.get("price_balance") in {"عادل", "مرتفع", "منخفض"}:
        ai_result.setdefault("source", "openai")
        ai_result.setdefault("logic", "منطق الميزان")
        return ai_result
    return _local_evaluate_property_price(property_data)


def _extract_max_price(text: str) -> float | None:
    """
    استخراج السعر الأقصى من عبارات مثل:
    - حدود 1.2 مليار / مليار سنتيم
    - 12000000 / 12 مليون
    في العرف العقاري الجزائري: «مليار» غالباً = مليار سنتيم = 10 ملايين دج.
    """
    # X.Y مليار / X مليار
    m = re.search(
        r"(\d+(?:[.,]\d+)?)\s*(مليار|milyar|md)",
        text,
        re.IGNORECASE,
    )
    if m:
        value = float(m.group(1).replace(",", "."))
        # مليار سنتيم → دج (÷ 100) لكن العرف يقول 1.2 مليار ≈ 12_000_000 دج
        # أي: الرقم × 10_000_000
        return value * 10_000_000

    m = re.search(
        r"(\d+(?:[.,]\d+)?)\s*(مليون|million)",
        text,
        re.IGNORECASE,
    )
    if m:
        value = float(m.group(1).replace(",", "."))
        return value * 1_000_000

    m = re.search(r"(\d{6,12})", text.replace(" ", "").replace(".", "").replace(",", ""))
    if m:
        return float(m.group(1))

    return None


def _extract_document_type(text: str) -> str | None:
    lowered = text.lower()
    # Prefer longer / more specific matches
    for key in sorted(DOCUMENT_ALIASES.keys(), key=len, reverse=True):
        if key.lower() in lowered:
            return DOCUMENT_ALIASES[key]
    return None


def _extract_property_type(text: str) -> str | None:
    match = PROPERTY_TYPE_PATTERN.search(text)
    if not match:
        return None
    raw = match.group(1)
    upper = raw.upper()
    if upper.startswith("F"):
        return upper
    mapping = {
        "فيلا": "Villa",
        "فيلاّ": "Villa",
        "villa": "Villa",
        "دوبلكس": "Duplex",
        "duplex": "Duplex",
        "منزل": "Maison",
        "شقة": "Appartement",
        "studio": "Studio",
    }
    return mapping.get(raw.lower(), raw)


def _extract_district_from_text(text: str) -> str | None:
    lowered = text.lower()
    for district, meta in ORAN_MARKET_AVERAGES_DZD.items():
        if district.lower() in lowered:
            return district
        for alias in meta["aliases"]:
            if alias.lower() in lowered:
                return district
    return None


def _local_parse_buyer_prompt(user_input: str) -> dict:
    """Rule-based parser for Oranian Darija / Arabic buyer prompts."""
    district = _extract_district_from_text(user_input)
    max_price = _extract_max_price(user_input)
    property_type = _extract_property_type(user_input)
    document_type = _extract_document_type(user_input)

    return {
        "district": district,
        "max_price": max_price,
        "property_type": property_type,
        "document_type": document_type,
        "raw_input": user_input,
        "currency": "DZD",
        "notes": (
            "تم تفسير «مليار» وفق العرف العقاري الجزائري "
            "(1 مليار ≈ 10 ملايين دينار / مليار سنتيم)."
            if max_price is not None and "مليار" in user_input
            else None
        ),
        "source": "mizan_local",
        "logic": "منطق الميزان",
    }


def parse_buyer_prompt(user_input: str) -> dict:
    """
    فهم طلب المشتري بالدارجة الوهرانية أو العربية واستخراج حقول البحث.

    Example:
        "نحوس على F3 في بئر الجير حدود 1.2 مليار بعقد"
    """
    system = (
        "أنت محلل طلبات عقارية لوهران في تطبيق El Mizan. "
        "افهم الدارجة الوهرانية والعربية. أعد JSON فقط بالحقول: "
        "district (اسم الحي أو null), max_price (رقم بالدينار الجزائري DZD أو null), "
        "property_type (مثل F2/F3/F4/Villa أو null), document_type "
        "(عقد توثيقي|دفتر عقاري|عرفي أو null), notes (اختياري). "
        "ملاحظة: في الجزائر «1.2 مليار» في العقارات ≈ 12_000_000 دج (مليار سنتيم)."
    )
    ai_result = _openai_json_completion(system, user_input)
    if ai_result and any(
        ai_result.get(k) for k in ("district", "max_price", "property_type", "document_type")
    ):
        return {
            "district": _normalize_district(ai_result.get("district")),
            "max_price": ai_result.get("max_price"),
            "property_type": ai_result.get("property_type"),
            "document_type": ai_result.get("document_type"),
            "raw_input": user_input,
            "currency": "DZD",
            "notes": ai_result.get("notes"),
            "source": "openai",
            "logic": "منطق الميزان",
        }
    return _local_parse_buyer_prompt(user_input)
