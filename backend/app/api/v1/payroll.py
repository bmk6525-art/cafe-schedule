from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import date

from app.database.database import get_db
from app.models.models import Schedule, ActualWork, Employee, Store, MonthlyPayroll, EmployeeType
from app.payroll_engine.calculator import (
    calculate_monthly_payroll,
    calculate_all_payroll,
    get_payroll_data,
    finalize_all_payroll,
)

router = APIRouter(tags=["급여 관리"])


# ── 실제 근무시간 입력 ──

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


# ── 급여 조회 ──

@router.get("/payroll/{year}/{month}")
def get_all_payroll(year: int, month: int, db: Session = Depends(get_db)):
    """
    해당 월 전체 파트타이머 급여 조회
    - 확정된 월: MonthlyPayroll DB 값 반환 (시급 변경 등 영향 없음)
    - 미확정 월: 실시간 계산 (배치 최적화)
    """
    is_fin = db.query(MonthlyPayroll).filter_by(year=year, month=month, is_finalized=True).count() > 0
    if is_fin:
        part_timers = db.query(Employee).filter_by(
            employee_type=EmployeeType.PART_TIMER, is_active=True
        ).all()
        results = []
        for pt in part_timers:
            data = get_payroll_data(year, month, pt.id, db)
            if data:
                results.append(data)
        return results
    else:
        return calculate_all_payroll(year, month, db)


@router.get("/payroll/{year}/{month}/store-summary")
def get_store_payroll_summary(year: int, month: int, db: Session = Depends(get_db)):
    """매장별 인건비 요약 (실시간 계산)"""
    start = date(year, month, 1)
    end = date(year + (1 if month == 12 else 0), 1 if month == 12 else month + 1, 1)

    stores = db.query(Store).filter_by(is_active=True).all()

    # 해당 월 스케줄·ActualWork·직원 배치 조회
    all_schedules = db.query(Schedule).filter(
        Schedule.work_date >= start,
        Schedule.work_date < end,
        Schedule.is_cancelled == False,
    ).all()
    sch_ids = [s.id for s in all_schedules]
    actuals_map = {}
    if sch_ids:
        for a in db.query(ActualWork).filter(ActualWork.schedule_id.in_(sch_ids)).all():
            actuals_map[a.schedule_id] = a
    emp_ids = list({s.employee_id for s in all_schedules})
    emps_map = {}
    if emp_ids:
        for e in db.query(Employee).filter(Employee.id.in_(emp_ids)).all():
            emps_map[e.id] = e

    result = []
    for store in stores:
        total_cost = 0.0
        for s in all_schedules:
            if s.store_id != store.id:
                continue
            emp = emps_map.get(s.employee_id)
            if not emp:
                continue
            actual = actuals_map.get(s.id)
            if actual and actual.is_absent:
                continue
            if actual and actual.actual_start and actual.actual_end:
                break_m = actual.actual_break_minutes or 0
                mins = max(0, _t(actual.actual_end) - _t(actual.actual_start) - break_m)
            else:
                break_m = s.break_minutes or 0
                mins = max(0, _t(s.end_time) - _t(s.start_time) - break_m)
            total_cost += (mins / 60) * (emp.hourly_wage or 0)
        result.append({'store_id': store.id, 'store_name': store.name, 'total_cost': round(total_cost)})

    return result


@router.get("/payroll/{year}/{month}/finalize-status")
def get_finalize_status(year: int, month: int, db: Session = Depends(get_db)):
    """해당 월 급여 확정 상태 조회"""
    rec = db.query(MonthlyPayroll).filter_by(year=year, month=month, is_finalized=True).first()
    count = db.query(MonthlyPayroll).filter_by(year=year, month=month, is_finalized=True).count()
    return {
        "is_finalized": rec is not None,
        "finalized_count": count,
        "finalized_at": rec.updated_at.isoformat() if rec else None,
    }


@router.post("/payroll/{year}/{month}/finalize")
def finalize_payroll(year: int, month: int, db: Session = Depends(get_db)):
    """해당 월 급여 확정 — 계산값을 DB에 저장하고 잠금"""
    existing = db.query(MonthlyPayroll).filter_by(year=year, month=month, is_finalized=True).count()
    if existing > 0:
        raise HTTPException(
            status_code=400,
            detail=f"{year}년 {month}월은 이미 급여가 확정되어 있습니다.",
        )
    result = finalize_all_payroll(year, month, db)
    return {
        "message": f"{year}년 {month}월 급여가 확정되었습니다. (총 {result['finalized_count']}명)",
        "finalized_count": result['finalized_count'],
        "success": True,
    }


@router.get("/payroll/{year}/{month}/{employee_id}")
def get_employee_payroll(year: int, month: int, employee_id: int, db: Session = Depends(get_db)):
    """개인별 급여 상세 조회 (확정 데이터 우선, 없으면 실시간)"""
    emp = db.query(Employee).filter_by(id=employee_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="직원을 찾을 수 없습니다.")
    return get_payroll_data(year, month, employee_id, db)


def _t(s: str) -> int:
    h, m = map(int, s.split(':'))
    return h * 60 + m
