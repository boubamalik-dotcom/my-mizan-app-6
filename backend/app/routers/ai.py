"""
AI endpoints — منطق الميزان
تقييم الأسعار وتحليل طلبات المشترين بالدارجة الوهرانية.
"""

from fastapi import APIRouter, HTTPException

from app.schemas.ai import (
    EvaluatePriceRequest,
    EvaluatePriceResponse,
    ParsePromptRequest,
    ParsePromptResponse,
)
from app.services.ai_engine import evaluate_property_price, parse_buyer_prompt

router = APIRouter(prefix="/api/v1/ai", tags=["AI — منطق الميزان"])


@router.post(
    "/evaluate-price",
    response_model=EvaluatePriceResponse,
    summary="تقييم سعر العقار قبل النشر (ميزان السعر)",
)
def evaluate_price(payload: EvaluatePriceRequest) -> EvaluatePriceResponse:
    """Compare asking price against Oran district averages via Mizan logic."""
    try:
        result = evaluate_property_price(payload.model_dump())
        return EvaluatePriceResponse.model_validate(result)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"فشل تقييم السعر: {exc}") from exc


@router.post(
    "/parse-prompt",
    response_model=ParsePromptResponse,
    summary="تحويل كلام المشتري إلى استعلام بحث ذكي",
)
def parse_prompt(payload: ParsePromptRequest) -> ParsePromptResponse:
    """Parse Oranian Darija / Arabic buyer intent into structured search fields."""
    try:
        result = parse_buyer_prompt(payload.user_input)
        return ParsePromptResponse.model_validate(result)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"فشل تحليل الطلب: {exc}") from exc
