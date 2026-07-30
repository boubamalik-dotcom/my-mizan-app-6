"""Pydantic schemas for منطق الميزان AI endpoints."""

from typing import Any, Literal

from pydantic import BaseModel, Field


class EvaluatePriceRequest(BaseModel):
    title: str | None = None
    description: str | None = None
    price: float = Field(..., gt=0, description="السعر المطلوب بالدينار الجزائري")
    address: str | None = None
    district: str = Field(..., description="حي وهران، مثل بئر الجير أو الكورنيش")
    document_type: str | None = Field(
        default=None,
        description="عقد توثيقي / دفتر عقاري / عرفي",
    )
    property_type: str | None = Field(default=None, description="F2, F3, Villa...")


class MarketRange(BaseModel):
    min: float
    max: float


class EvaluatePriceResponse(BaseModel):
    price_balance: Literal["عادل", "مرتفع", "منخفض"]
    asking_price: float
    district: str
    district_avg_price: float
    market_range: MarketRange | dict[str, Any] | None = None
    deviation_percent: float | None = None
    reasoning: str
    confidence: float | None = None
    source: str | None = None
    logic: str = "منطق الميزان"


class ParsePromptRequest(BaseModel):
    user_input: str = Field(
        ...,
        min_length=2,
        examples=["نحوس على F3 في بئر الجير حدود 1.2 مليار بعقد"],
    )


class ParsePromptResponse(BaseModel):
    district: str | None = None
    max_price: float | None = None
    property_type: str | None = None
    document_type: str | None = None
    raw_input: str
    currency: str = "DZD"
    notes: str | None = None
    source: str | None = None
    logic: str = "منطق الميزان"
