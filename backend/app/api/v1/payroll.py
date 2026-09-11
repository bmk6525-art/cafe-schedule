from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional

from app.database.database import get_db
from app.models.models import Schedule, ActualWork, Employee
from app.payroll_engine.calculator import calculate_monthly_payroll, calculate_all_payroll

router = APIRouter(tags=["급여 관리"])


# ── 실제 근무시간 입력 (PHASE 9) ──

@router.put("/schedules/{schedule_id}/actual")
def upsert_actual_work(schedule_id: int, data: dict, db: Session = Depends(get_db)):
    """실제 근무시간 입력/수정"""
    s = db.query(Schedule).filter_by(id=schedule_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="스케줄을 찾을 수 없습니다.")

    actual = db.query(ActualWork).filter_by(schedule_id=schedule_id).first()
    if not actual:
        actual = ActualWork(schedule_id=schedule_id, employee_id=s.employee_id)
        db.add(actual)

    for field in ['actual_start', 'actual_end', 'actual_break_minutes', 'is_absent', 'memo']:
        if field in data:
            setattr(actual, field, data[field])

    db.commit()
    db.refresh(actual)
    return {
        'schedule_id': schedule_id,
        'actual_start': actual.actual_start,
        'actual_end': actual.actual_end,
        'actual_break_minutes': actual.actual_break_minutes,
        'is_absent': actual.is_absent,
    }


@router.get("/schedules/{schedule_id}/actual")
def get_actual_work(schedule_id: int, db: Session = Depends(get_db)):
    actual = db.query(ActualWork).filter_by(schedule_id=schedule_id).first()
    if not actual:
        return None
    return {
        'schedule_id': schedule_id,
        'actual_start': actual.actual_start,
        'actual_end': actual.actual_end,
        'actual_break_minutes': actual.actual_break_minutes,
        'is_absent': actual.is_absent,
    }


# ── 급여 조회 (PHASE 10) ──

@router.get("/payroll/{year}/{month}")
def get_all_payroll(year: int, month: int, db: Session = Depends(get_db)):
    """해당 월 전체 파트타이머 급여 조회"""
    result = calculate_all_payroll(year, month, db)
    return result


@router.get("/payroll/{year}/{month}/store-summary")
def get_store_payroll_summary(year: int, month: int, db: Session = Depends(get_db)):
    """매장별 인건비 요약"""
    from app.models.models import Store, ScheduleStatus
    from datetime import date
    from collections import defaultdict

    stores = db.query(Store).filter_by(is_active=True).all()
    start = date(year, month, 1)
    end = date(year + (1 if month == 12 else 0), 1 if month == 12 else month + 1, 1)

    result = []
    for store in stores:
        schedules = db.query(Schedule).filter(
            Schedule.store_id == store.id,
            Schedule.work_date >= start,
            Schedule.work_date < end,
            Schedule.is_cancelled == False,
        ).all()

        total_cost = 0
        for s in schedules:
            emp = db.query(Employee).filter_by(id=s.employee_id).first()
            if not emp:
                continue
            actual = db.query(ActualWork).filter_by(schedule_id=s.id).first()
            if actual and actual.is_absent:
                continue
            if actual and actual.actual_start and actual.actual_end:
                mins = max(0, _t(actual.actual_end) - _t(actual.actual_start) - actual.actual_break_minutes)
            else:
                mins = max(0, _t(s.end_time) - _t(s.start_time) - s.break_minutes)
            total_cost += (mins / 60) * emp.hourly_wage

        result.append({'store_id': store.id, 'store_name': store.name, 'total_cost': round(total_cost)})
    return result


@router.get("/payroll/{year}/{month}/{employee_id}")
def get_employee_payroll(year: int, month: int, employee_id: int,
                         db: Session = Depends(get_db)):
    """개인별 급여 상세 조회"""
    emp = db.query(Employee).filter_by(id=employee_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="직원을 찾을 수 없습니다.")
    return calculate_monthly_payroll(year, month, employee_id, db)


def _t(s: str) -> int:
    h, m = map(int, s.split(':'))
    return h * 60 + m
