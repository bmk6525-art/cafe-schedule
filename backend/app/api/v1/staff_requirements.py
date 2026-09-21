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
    """매장의 해당 월 필요인원 전체 저장 (기존 삭제 후 재등록, 중복 방지)"""
    store = db.query(Store).filter_by(id=store_id).first()
    if not store:
        raise HTTPException(status_code=404, detail="매장을 찾을 수 없습니다.")

    db.query(StaffRequirement).filter_by(
        store_id=store_id, year=year, month=month
    ).delete()
    db.flush()  # 삭제 먼저 반영 후 삽입

    # 중복 item 제거 (같은 day_of_week + start_time + end_time)
    seen: set = set()
    new_rows = []
    for item in data.items:
        key = (item.day_of_week, item.start_time, item.end_time)
        if key in seen:
            continue
        seen.add(key)
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
    db.flush()

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


@router.post("/requirements/bulk-copy", response_model=dict)
def bulk_copy_requirements(
    from_year: int, from_month: int,
    to_year: int, to_month: int,
    db: Session = Depends(get_db)
):
    """모든 매장의 필요인원 설정을 다른 달로 일괄 복사"""
    src_rows = db.query(StaffRequirement).filter_by(
        year=from_year, month=from_month
    ).all()

    if not src_rows:
        raise HTTPException(
            status_code=404,
            detail=f"{from_year}년 {from_month}월의 필요인원 데이터가 없습니다."
        )

    db.query(StaffRequirement).filter_by(year=to_year, month=to_month).delete()
    db.flush()

    seen: set = set()
    count = 0
    for r in src_rows:
        key = (r.store_id, r.day_of_week, r.start_time, r.end_time)
        if key in seen:
            continue
        seen.add(key)
        new_r = StaffRequirement(
            store_id=r.store_id, year=to_year, month=to_month,
            day_of_week=r.day_of_week,
            start_time=r.start_time, end_time=r.end_time,
            required_count=r.required_count,
        )
        db.add(new_r)
        count += 1

    db.commit()
    return {
        "message": f"{from_year}년 {from_month}월 → {to_year}년 {to_month}월: {count}개 복사 완료",
        "count": count,
        "success": True,
    }
