from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from datetime import date

from app.database.database import get_db
from app.models.models import (
    Employee, EmployeeType, MonthlyAvailability, AvailabilityException, DayOfWeek
)
from app.schemas.schemas import (
    MonthlyAvailabilityUpsert, MonthlyAvailabilityResponse,
    AvailabilityExceptionCreate, AvailabilityExceptionResponse, MessageResponse
)

router = APIRouter(prefix="/employees", tags=["불가능시간 관리"])

DAY_ORDER = [DayOfWeek.MON, DayOfWeek.TUE, DayOfWeek.WED,
             DayOfWeek.THU, DayOfWeek.FRI, DayOfWeek.SAT, DayOfWeek.SUN]


def _check_part_timer(employee_id: int, db: Session) -> Employee:
    emp = db.query(Employee).filter(Employee.id == employee_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="직원을 찾을 수 없습니다.")
    if emp.employee_type != EmployeeType.PART_TIMER:
        raise HTTPException(status_code=400, detail="불가능시간 설정은 파트타이머만 가능합니다.")
    return emp


# ── 월별 불가능 시간 (요일별) ──

@router.get("/{employee_id}/availability/{year}/{month}",
            response_model=List[MonthlyAvailabilityResponse])
def get_monthly_availability(employee_id: int, year: int, month: int,
                              db: Session = Depends(get_db)):
    _check_part_timer(employee_id, db)
    rows = (db.query(MonthlyAvailability)
            .filter_by(employee_id=employee_id, year=year, month=month).all())
    rows.sort(key=lambda r: DAY_ORDER.index(r.day_of_week))
    return rows


@router.put("/{employee_id}/availability/{year}/{month}",
            response_model=List[MonthlyAvailabilityResponse])
def upsert_monthly_availability(employee_id: int, year: int, month: int,
                                 data: MonthlyAvailabilityUpsert,
                                 db: Session = Depends(get_db)):
    _check_part_timer(employee_id, db)

    db.query(MonthlyAvailability).filter_by(
        employee_id=employee_id, year=year, month=month
    ).delete()

    new_rows = []
    for item in data.days:
        # 종일 가능인 경우 저장하지 않음 (기본값이므로)
        if not item.is_day_unavailable and not item.unavailable_start:
            continue
        row = MonthlyAvailability(
            employee_id=employee_id, year=year, month=month,
            day_of_week=item.day_of_week,
            is_day_unavailable=item.is_day_unavailable,
            unavailable_start=item.unavailable_start if not item.is_day_unavailable else None,
            unavailable_end=item.unavailable_end if not item.is_day_unavailable else None,
            memo=item.memo,
        )
        db.add(row)
        new_rows.append(row)

    db.commit()
    for r in new_rows:
        db.refresh(r)
    new_rows.sort(key=lambda r: DAY_ORDER.index(r.day_of_week))
    return new_rows


# ── 특정 날짜 예외 ──

@router.get("/{employee_id}/exceptions/{year}/{month}",
            response_model=List[AvailabilityExceptionResponse])
def get_exceptions(employee_id: int, year: int, month: int,
                   db: Session = Depends(get_db)):
    _check_part_timer(employee_id, db)
    rows = (db.query(AvailabilityException)
            .filter(AvailabilityException.employee_id == employee_id,
                    AvailabilityException.exception_date >= date(year, month, 1))
            .all())
    month_end = date(year, month + 1, 1) if month < 12 else date(year + 1, 1, 1)
    rows = [r for r in rows if r.exception_date < month_end]
    rows.sort(key=lambda r: r.exception_date)
    return rows


@router.post("/{employee_id}/exceptions",
             response_model=AvailabilityExceptionResponse,
             status_code=status.HTTP_201_CREATED)
def add_exception(employee_id: int, data: AvailabilityExceptionCreate,
                  db: Session = Depends(get_db)):
    _check_part_timer(employee_id, db)
    existing = (db.query(AvailabilityException)
                .filter_by(employee_id=employee_id, exception_date=data.exception_date)
                .first())
    if existing:
        for field, val in data.model_dump().items():
            setattr(existing, field, val)
        db.commit()
        db.refresh(existing)
        return existing

    row = AvailabilityException(employee_id=employee_id, **data.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.delete("/exceptions/{exception_id}", response_model=MessageResponse)
def delete_exception(exception_id: int, db: Session = Depends(get_db)):
    row = db.query(AvailabilityException).filter_by(id=exception_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="예외 날짜를 찾을 수 없습니다.")
    db.delete(row)
    db.commit()
    return {"message": "삭제되었습니다.", "success": True}
