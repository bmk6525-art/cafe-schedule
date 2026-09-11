from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import date, datetime

from app.database.database import get_db
from app.models.models import (
    Schedule, MonthlySettings, StaffRequirement,
    EmployeeWorkPattern, Employee, EmployeeType
)

router = APIRouter(tags=["월별 관리"])


def _get_or_create_settings(year: int, month: int, db: Session) -> MonthlySettings:
    ms = db.query(MonthlySettings).filter_by(year=year, month=month).first()
    if not ms:
        ms = MonthlySettings(year=year, month=month)
        db.add(ms)
        db.commit()
        db.refresh(ms)
    return ms


@router.get("/monthly/{year}/{month}/status")
def get_month_status(year: int, month: int, db: Session = Depends(get_db)):
    start = date(year, month, 1)
    end = date(year + (1 if month == 12 else 0), 1 if month == 12 else month + 1, 1)

    schedules = db.query(Schedule).filter(
        Schedule.work_date >= start,
        Schedule.work_date < end,
        Schedule.is_cancelled == False,
    ).all()

    from app.models.models import ScheduleStatus
    confirmed = [s for s in schedules if s.status == ScheduleStatus.CONFIRMED]

    ms = db.query(MonthlySettings).filter_by(year=year, month=month).first()
    return {
        "year": year,
        "month": month,
        "is_finalized": ms.is_finalized if ms else False,
        "finalized_at": ms.finalized_at.isoformat() if ms and ms.finalized_at else None,
        "schedule_count": len(schedules),
        "confirmed_count": len(confirmed),
    }


@router.post("/monthly/{year}/{month}/finalize")
def finalize_month(year: int, month: int, db: Session = Depends(get_db)):
    ms = _get_or_create_settings(year, month, db)
    if ms.is_finalized:
        raise HTTPException(status_code=400, detail="이미 확정된 월입니다.")

    start = date(year, month, 1)
    end = date(year + (1 if month == 12 else 0), 1 if month == 12 else month + 1, 1)
    from app.models.models import ScheduleStatus
    db.query(Schedule).filter(
        Schedule.work_date >= start,
        Schedule.work_date < end,
        Schedule.is_cancelled == False,
        Schedule.status == ScheduleStatus.CONFIRMED,
    ).update({"status": ScheduleStatus.LOCKED})

    ms.is_finalized = True
    ms.finalized_at = datetime.utcnow()
    db.commit()
    return {"message": f"{year}년 {month}월이 확정되었습니다."}


@router.post("/monthly/{year}/{month}/copy-settings")
def copy_settings(year: int, month: int, body: dict, db: Session = Depends(get_db)):
    from_year = body.get("from_year")
    from_month = body.get("from_month")
    if not from_year or not from_month:
        raise HTTPException(status_code=422, detail="from_year, from_month 필요")

    # 필요 인원 복사
    src_reqs = db.query(StaffRequirement).filter_by(year=from_year, month=from_month).all()
    for req in src_reqs:
        exists = db.query(StaffRequirement).filter_by(
            store_id=req.store_id, year=year, month=month,
            day_of_week=req.day_of_week, start_time=req.start_time
        ).first()
        if not exists:
            new_req = StaffRequirement(
                store_id=req.store_id, year=year, month=month,
                day_of_week=req.day_of_week, start_time=req.start_time,
                end_time=req.end_time, required_count=req.required_count,
            )
            db.add(new_req)

    db.commit()
    return {"message": f"{from_year}년 {from_month}월 설정을 복사했습니다.", "copied_requirements": len(src_reqs)}
