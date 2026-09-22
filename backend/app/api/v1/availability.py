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


@router.get("/availability-status")
def get_availability_status(year: int, month: int, db: Session = Depends(get_db)):
    """월별 가능/불가능 시간 입력 현황 — 입력한 파트타이머별 설정 수 반환"""
    rows = (db.query(MonthlyAvailability.employee_id, MonthlyAvailability.entry_type)
            .filter_by(year=year, month=month)
            .all())

    # employee_id → {'AVAILABLE': count, 'UNAVAILABLE': count}
    status_map: dict = {}
    for emp_id, entry_type in rows:
        if emp_id not in status_map:
            status_map[emp_id] = {'AVAILABLE': 0, 'UNAVAILABLE': 0}
        etype = entry_type if entry_type in ('AVAILABLE', 'UNAVAILABLE') else 'UNAVAILABLE'
        status_map[emp_id][etype] += 1

    result = []
    for emp_id, counts in status_map.items():
        result.append({
            'employee_id': emp_id,
            'available_count': counts['AVAILABLE'],
            'unavailable_count': counts['UNAVAILABLE'],
        })

    # 기존 API 호환: employee_ids 필드도 유지
    return {
        'employee_ids': list(status_map.keys()),
        'details': result,
    }


def _check_part_timer(employee_id: int, db: Session) -> Employee:
    emp = db.query(Employee).filter(Employee.id == employee_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="직원을 찾을 수 없습니다.")
    if emp.employee_type != EmployeeType.PART_TIMER:
        raise HTTPException(status_code=400, detail="불가능시간 설정은 파트타이머만 가능합니다.")
    return emp


# ── 월별 가능/불가능 시간 (요일별) ──

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
    db.flush()

    new_rows = []
    for item in data.days:
        # AVAILABLE 레코드 저장 조건: is_working_day=True 또는 가능 시간 입력
        if item.is_working_day or item.available_start:
            row = MonthlyAvailability(
                employee_id=employee_id, year=year, month=month,
                day_of_week=item.day_of_week,
                entry_type='AVAILABLE',
                is_working_day=item.is_working_day,
                available_start=item.available_start,
                available_end=item.available_end if item.available_start else None,
                is_day_unavailable=False,
                unavailable_start=None,
                unavailable_end=None,
                memo=item.memo,
            )
            db.add(row)
            new_rows.append(row)

        # UNAVAILABLE 레코드 저장 조건: is_day_unavailable=True 또는 불가능 시간 입력
        if item.is_day_unavailable or item.unavailable_start:
            row = MonthlyAvailability(
                employee_id=employee_id, year=year, month=month,
                day_of_week=item.day_of_week,
                entry_type='UNAVAILABLE',
                is_working_day=False,
                available_start=None,
                available_end=None,
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


# ── 전체 직원 불가능 시간 일괄 복사 ──

@router.post("/availability/bulk-copy", response_model=dict)
def bulk_copy_availability(
    from_year: int, from_month: int,
    to_year: int, to_month: int,
    db: Session = Depends(get_db)
):
    """모든 파트타이머의 가능/불가능 시간 설정을 다른 달로 일괄 복사"""
    src_rows = db.query(MonthlyAvailability).filter_by(
        year=from_year, month=from_month
    ).all()

    if not src_rows:
        raise HTTPException(
            status_code=404,
            detail=f"{from_year}년 {from_month}월의 가용성 설정 데이터가 없습니다."
        )

    db.query(MonthlyAvailability).filter_by(year=to_year, month=to_month).delete()
    db.flush()

    seen: set = set()
    count = 0
    for r in src_rows:
        key = (r.employee_id, r.day_of_week, getattr(r, 'entry_type', 'UNAVAILABLE'))
        if key in seen:
            continue
        seen.add(key)
        new_r = MonthlyAvailability(
            employee_id=r.employee_id,
            year=to_year, month=to_month,
            day_of_week=r.day_of_week,
            entry_type=getattr(r, 'entry_type', 'UNAVAILABLE'),
            is_working_day=getattr(r, 'is_working_day', False),
            available_start=getattr(r, 'available_start', None),
            available_end=getattr(r, 'available_end', None),
            is_day_unavailable=r.is_day_unavailable,
            unavailable_start=r.unavailable_start,
            unavailable_end=r.unavailable_end,
            memo=r.memo,
        )
        db.add(new_r)
        count += 1

    db.commit()
    return {
        "message": f"{from_year}년 {from_month}월 → {to_year}년 {to_month}월: {count}개 복사 완료",
        "count": count,
        "success": True,
    }


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
