from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.database.database import get_db
from app.models.models import Store, StaffRequirement, DayOfWeek
from app.schemas.schemas import StaffRequirementBulk, StaffRequirementResponse, MessageResponse

router = APIRouter(prefix="/stores", tags=["필요인원 관리"])

DAY_ORDER = [DayOfWeek.MON, DayOfWeek.TUE, DayOfWeek.WED,
             DayOfWeek.THU, DayOfWeek.FRI, DayOfWeek.SAT, DayOfWeek.SUN]


@router.get("/{store_id}/requirements/{year}/{month}",
            response_model=List[StaffRequirementResponse])
def get_requirements(store_id: int, year: int, month: int, db: Session = Depends(get_db)):
    """매장의 해당 월 필요인원 조회"""
    store = db.query(Store).filter_by(id=store_id).first()
    if not store:
        raise HTTPException(status_code=404, detail="매장을 찾을 수 없습니다.")
    rows = (db.query(StaffRequirement)
            .filter_by(store_id=store_id, year=year, month=month)
            .order_by(StaffRequirement.day_of_week, StaffRequirement.start_time)
            .all())
    return rows


@router.put("/{store_id}/requirements/{year}/{month}",
            response_model=List[StaffRequirementResponse])
def upsert_requirements(store_id: int, year: int, month: int,
                        data: StaffRequirementBulk,
                        db: Session = Depends(get_db)):
    """매장의 해당 월 필요인원 전체 저장 (기존 삭제 후 재등록)"""
    store = db.query(Store).filter_by(id=store_id).first()
    if not store:
        raise HTTPException(status_code=404, detail="매장을 찾을 수 없습니다.")

    db.query(StaffRequirement).filter_by(
        store_id=store_id, year=year, month=month
    ).delete()

    new_rows = []
    for item in data.items:
        row = StaffRequirement(
            store_id=store_id, year=year, month=month,
            day_of_week=item.day_of_week,
            start_time=item.start_time,
            end_time=item.end_time,
            required_count=item.required_count,
        )
        db.add(row)
        new_rows.append(row)

    db.commit()
    for r in new_rows:
        db.refresh(r)
    return new_rows


@router.post("/{store_id}/requirements/{year}/{month}/copy-from",
             response_model=MessageResponse)
def copy_requirements(store_id: int, year: int, month: int,
                      from_store_id: int = None,
                      from_year: int = None, from_month: int = None,
                      db: Session = Depends(get_db)):
    """다른 매장 또는 다른 월의 필요인원 설정을 복사"""
    src_store = from_store_id or store_id
    src_year = from_year or year
    src_month = from_month or (month - 1 if month > 1 else 12)
    if src_month == 12 and from_month is None:
        src_year = year - 1

    src_rows = db.query(StaffRequirement).filter_by(
        store_id=src_store, year=src_year, month=src_month
    ).all()

    if not src_rows:
        raise HTTPException(status_code=404, detail="복사할 원본 데이터가 없습니다.")

    db.query(StaffRequirement).filter_by(
        store_id=store_id, year=year, month=month
    ).delete()

    for r in src_rows:
        new_r = StaffRequirement(
            store_id=store_id, year=year, month=month,
            day_of_week=r.day_of_week,
            start_time=r.start_time,
            end_time=r.end_time,
            required_count=r.required_count,
        )
        db.add(new_r)

    db.commit()
    return {"message": f"{len(src_rows)}개의 필요인원 설정이 복사되었습니다.", "success": True}
