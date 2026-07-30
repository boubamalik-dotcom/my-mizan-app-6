"""
Inspections router — حجز وتأكيد المعاينات المحمية (عمولة الميزان 1.5%).
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.inspection import (
    MIZAN_COMMISSION_RATE,
    Inspection,
    InspectionStatus,
    generate_inspection_code,
)
from app.models.property import Property, PropertyStatus
from app.models.user import User
from app.schemas.inspection import (
    InspectionBookRequest,
    InspectionBookResponse,
    InspectionConfirmRequest,
    InspectionConfirmResponse,
)

router = APIRouter(prefix="/api/v1/inspections", tags=["Inspections"])


@router.post(
    "/book",
    response_model=InspectionBookResponse,
    status_code=status.HTTP_201_CREATED,
    summary="حجز موعد معاينة مع تعهد عمولة 1.5%",
)
def book_inspection(
    payload: InspectionBookRequest,
    db: Session = Depends(get_db),
) -> InspectionBookResponse:
    """
    حجز معاينة:
    - يتطلب commission_agreed=True صراحةً (عمولة الميزان 1.5%)
    - يولّد inspection_code عشوائي
    - لا يكشف نقطة التلاقي قبل تأكيد المالك
    """
    if payload.commission_agreed is not True:
        raise HTTPException(
            status_code=400,
            detail="يجب الموافقة الصريحة على تعهد عمولة الميزان 1.5% (commission_agreed=true)",
        )

    prop = db.query(Property).filter(Property.id == payload.property_id).first()
    if not prop:
        raise HTTPException(status_code=404, detail="العقار غير موجود")
    if prop.status not in {PropertyStatus.available, PropertyStatus.under_inspection}:
        raise HTTPException(status_code=400, detail="العقار غير متاح للمعاينة حالياً")

    buyer = db.query(User).filter(User.id == payload.buyer_id).first()
    if not buyer:
        raise HTTPException(status_code=404, detail="المشتري غير موجود")
    if buyer.id == prop.owner_id:
        raise HTTPException(status_code=400, detail="لا يمكن للمالك حجز معاينة على عقاره")

    code = generate_inspection_code()
    # ضمان التفرد البسيط
    while db.query(Inspection).filter(Inspection.inspection_code == code).first():
        code = generate_inspection_code()

    inspection = Inspection(
        property_id=prop.id,
        buyer_id=buyer.id,
        scheduled_at=payload.scheduled_at,
        status=InspectionStatus.pending,
        commission_agreed=True,
        inspection_code=code,
        meeting_point=None,
    )
    db.add(inspection)
    prop.status = PropertyStatus.under_inspection
    db.commit()
    db.refresh(inspection)

    district = prop.district.value if hasattr(prop.district, "value") else str(prop.district)
    return InspectionBookResponse(
        id=inspection.id,
        property_id=inspection.property_id,
        buyer_id=inspection.buyer_id,
        scheduled_at=inspection.scheduled_at,
        status=inspection.status,
        commission_agreed=True,
        commission_rate=MIZAN_COMMISSION_RATE,
        inspection_code=inspection.inspection_code,
        district=district,
        meeting_point_hidden=True,
    )


@router.post(
    "/confirm",
    response_model=InspectionConfirmResponse,
    summary="تأكيد المالك — إظهار نقطة التلاقي والتذكرة المتبادلة",
)
def confirm_inspection(
    payload: InspectionConfirmRequest,
    db: Session = Depends(get_db),
) -> InspectionConfirmResponse:
    """
    يؤكد المالك الموعد فقط؛ عندها تُكشف نقطة التلاقي والتذكرة المتبادلة.
    """
    inspection = (
        db.query(Inspection)
        .filter(Inspection.inspection_code == payload.inspection_code.upper())
        .first()
    )
    if not inspection:
        # try exact match if casing differs in stored value
        inspection = (
            db.query(Inspection)
            .filter(Inspection.inspection_code == payload.inspection_code)
            .first()
        )
    if not inspection:
        raise HTTPException(status_code=404, detail="رمز المعاينة غير موجود")

    prop = db.query(Property).filter(Property.id == inspection.property_id).first()
    if not prop:
        raise HTTPException(status_code=404, detail="العقار المرتبط غير موجود")

    if prop.owner_id != payload.owner_id:
        raise HTTPException(
            status_code=403,
            detail="غير مصرّح: تأكيد المعاينة متاح لمالك العقار فقط",
        )

    if inspection.status == InspectionStatus.confirmed:
        raise HTTPException(status_code=400, detail="المعاينة مؤكدة مسبقاً")

    if not inspection.commission_agreed:
        raise HTTPException(
            status_code=400,
            detail="لا يمكن التأكيد بدون موافقة على عمولة الميزان 1.5%",
        )

    owner = db.query(User).filter(User.id == prop.owner_id).first()
    buyer = db.query(User).filter(User.id == inspection.buyer_id).first()
    if not owner or not buyer:
        raise HTTPException(status_code=404, detail="أطراف المعاينة غير مكتملة")

    now = datetime.now(timezone.utc)
    inspection.status = InspectionStatus.confirmed
    inspection.meeting_point = prop.address
    inspection.confirmed_at = now
    db.commit()
    db.refresh(inspection)

    mutual_ticket = {
        "ticket_code": inspection.inspection_code,
        "property_title": prop.title,
        "district": prop.district.value if hasattr(prop.district, "value") else str(prop.district),
        "scheduled_at": inspection.scheduled_at.isoformat(),
        "commission_rate": MIZAN_COMMISSION_RATE,
        "commission_label": "عمولة الميزان 1.5%",
        "buyer": {"id": buyer.id, "full_name": buyer.full_name, "phone": buyer.phone},
        "owner": {"id": owner.id, "full_name": owner.full_name, "phone": owner.phone},
        "meeting_point": inspection.meeting_point,
        "note": "تذكرة متبادلة — يبرزها الطرفان عند نقطة التلاقي.",
    }

    return InspectionConfirmResponse(
        id=inspection.id,
        property_id=inspection.property_id,
        buyer_id=inspection.buyer_id,
        scheduled_at=inspection.scheduled_at,
        status=inspection.status,
        commission_agreed=True,
        commission_rate=MIZAN_COMMISSION_RATE,
        inspection_code=inspection.inspection_code,
        meeting_point=inspection.meeting_point,
        confirmed_at=inspection.confirmed_at,
        mutual_ticket=mutual_ticket,
    )
