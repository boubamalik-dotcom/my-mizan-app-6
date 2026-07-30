"""
Properties router — إدارة العقارات مع Privacy Shield وتقييم الميزان.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.property import Property, PropertyStatus
from app.models.user import User
from app.schemas.property import (
    PropertyCreate,
    PropertyCreateResponse,
    PropertyPublicRead,
    PropertyRead,
)
from app.services.ai_engine import evaluate_property_price

router = APIRouter(prefix="/api/v1/properties", tags=["Properties"])


def _to_public(prop: Property) -> PropertyPublicRead:
    district_value = prop.district.value if hasattr(prop.district, "value") else str(prop.district)
    return PropertyPublicRead(
        id=prop.id,
        title=prop.title,
        description=prop.description,
        price=prop.price,
        district=prop.district,
        document_type=prop.document_type,
        status=prop.status,
        approximate_location=f"وهران — حي {district_value} (عنوان تقريبي)",
        address_hidden=True,
        owner_contact_hidden=True,
        mizan_evaluation=prop.mizan_evaluation,
    )


@router.get(
    "/",
    response_model=list[PropertyPublicRead],
    summary="قائمة العقارات المتاحة (Privacy Shield)",
)
def list_available_properties(db: Session = Depends(get_db)) -> list[PropertyPublicRead]:
    """
    عرض العقارات المتاحة مع إخفاء:
    - رقم هاتف المالك
    - العنوان الدقيق
    """
    properties = (
        db.query(Property)
        .filter(Property.status == PropertyStatus.available)
        .order_by(Property.id.desc())
        .all()
    )
    return [_to_public(prop) for prop in properties]


@router.post(
    "/",
    response_model=PropertyCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="إضافة عقار مع تقييم منطق الميزان التلقائي",
)
def create_property(
    payload: PropertyCreate,
    db: Session = Depends(get_db),
) -> PropertyCreateResponse:
    """إنشاء عقار واستدعاء evaluate_property_price لحفظ التقييم في قاعدة البيانات."""
    owner = db.query(User).filter(User.id == payload.owner_id).first()
    if not owner:
        raise HTTPException(status_code=404, detail="المالك غير موجود")

    evaluation = evaluate_property_price(
        {
            "title": payload.title,
            "description": payload.description,
            "price": payload.price,
            "address": payload.address,
            "district": payload.district.value,
            "document_type": payload.document_type.value,
        }
    )

    prop = Property(
        title=payload.title,
        description=payload.description,
        price=payload.price,
        address=payload.address,
        district=payload.district,
        document_type=payload.document_type,
        status=payload.status,
        owner_id=payload.owner_id,
        mizan_evaluation=evaluation,
    )
    db.add(prop)
    db.commit()
    db.refresh(prop)

    return PropertyCreateResponse(
        property=PropertyRead.model_validate(prop),
        mizan_evaluation=evaluation,
    )
