from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date
import json

from app.database.database import get_db
from app.models.models import (
    Schedule, ScheduleStatus, Employee, Store, ScheduleHistory, ChangeReason
)
from app.schemas.schemas import MessageResponse

router = APIRouter(prefix="/schedules", tags=["스케줄"])


# ── 조회 ──

@router.get("")
def get_schedules(
    year: int = Query(...), month: int = Query(...),
    store_id: Optional[int] = None,
    employee_id: Optional[int] = None,
    employee_type: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """월별 스케줄 조회 (다양한 필터 지원)"""
    start = date(year, month, 1)
    end = date(year + (1 if month == 12 else 0), 1 if month == 12 else month + 1, 1)

    q = (
        db.query(Schedule, Employee, Store)
        .outerjoin(Employee, Schedule.employee_id == Employee.id)
        .outerjoin(Store, Schedule.store_id == Store.id)
        .filter(
            Schedule.work_date >= start,
            Schedule.work_date < end,
            Schedule.is_cancelled == False,
        )
    )
    if store_id:
        q = q.filter(Schedule.store_id == store_id)
    if employee_id:
        q = q.filter(Schedule.employee_id == employee_id)
    if employee_type:
        q = q.filter(Employee.employee_type == employee_type)

    rows = q.order_by(Schedule.work_date, Schedule.start_time).all()

    # 직원·매장 정보 포함해서 응답
    result = []
    for s, emp, store in rows:
        result.append({
            'id': s.id,
            'employee_id': s.employee_id,
            'employee_name': emp.name if emp else '',
            'employee_type': emp.employee_type.value if emp else '',
            'store_id': s.store_id,
            'store_name': store.name if store else '',
            'work_date': str(s.work_date),
            'start_time': s.start_time,
            'end_time': s.end_time,
            'break_minutes': s.break_minutes,
            'status': s.status.value,
            'is_cancelled': s.is_cancelled,
            'memo': s.memo,
        })
    return result


# ── 수동 추가 ──

@router.post("")
def create_schedule(data: dict, db: Session = Depends(get_db)):
    """스케줄 수동 추가"""
    emp = db.query(Employee).filter_by(id=data.get('employee_id')).first()
    if not emp:
        raise HTTPException(status_code=404, detail="직원을 찾을 수 없습니다.")
    store = db.query(Store).filter_by(id=data.get('store_id')).first()
    if not store:
        raise HTTPException(status_code=404, detail="매장을 찾을 수 없습니다.")
    if not data.get('start_time') or not data.get('end_time'):
        raise HTTPException(status_code=400, detail="시작/종료 시간은 필수입니다.")
    if data['start_time'] >= data['end_time']:
        raise HTTPException(status_code=400, detail="종료 시간은 시작 시간보다 늦어야 합니다.")

    work_date = date.fromisoformat(data['work_date']) if isinstance(data.get('work_date'), str) else data.get('work_date')
    s = Schedule(
        employee_id=emp.id,
        store_id=store.id,
        work_date=work_date,
        start_time=data['start_time'],
        end_time=data['end_time'],
        break_minutes=data.get('break_minutes', 0),
        status=ScheduleStatus.DRAFT,
        memo=data.get('memo'),
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return {
        'id': s.id, 'employee_id': s.employee_id,
        'employee_name': emp.name, 'employee_type': emp.employee_type.value,
        'store_id': s.store_id, 'store_name': store.name,
        'work_date': str(s.work_date), 'start_time': s.start_time,
        'end_time': s.end_time, 'break_minutes': s.break_minutes,
        'status': s.status.value, 'is_cancelled': s.is_cancelled, 'memo': s.memo,
    }


# ── 자동 생성 ──

@router.post("/generate", response_model=dict)
def generate_schedule(year: int, month: int, db: Session = Depends(get_db)):
    """스케줄 자동 생성 (그리디 알고리즘)"""
    from app.schedule_engine.engine import engine
    result = engine.generate(year, month, db)
    return {
        'message': f"스케줄 생성 완료: {result['created']}개 생성",
        'created': result['created'],
        'warnings': result['warnings'],
        'success': True,
    }


# ── 수동 수정 ──

@router.put("/{schedule_id}")
def update_schedule(schedule_id: int, data: dict, db: Session = Depends(get_db)):
    """스케줄 수동 수정"""
    s = db.query(Schedule).filter_by(id=schedule_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="스케줄을 찾을 수 없습니다.")
    if s.status == ScheduleStatus.LOCKED:
        raise HTTPException(status_code=400, detail="잠금된 스케줄은 수정할 수 없습니다.")

    before = {'start_time': s.start_time, 'end_time': s.end_time,
               'store_id': s.store_id, 'break_minutes': s.break_minutes}

    allowed = ['employee_id', 'work_date', 'start_time', 'end_time', 'store_id', 'break_minutes', 'memo', 'status']
    for field in allowed:
        if field in data:
            setattr(s, field, data[field])

    # 변경 이력 저장
    history = ScheduleHistory(
        schedule_id=schedule_id,
        before_data=json.dumps(before, ensure_ascii=False),
        after_data=json.dumps(data, ensure_ascii=False),
        change_reason=ChangeReason(data.get('change_reason', '관리자수정')),
        memo=data.get('memo'),
    )
    db.add(history)
    db.commit()
    db.refresh(s)

    emp = db.query(Employee).filter_by(id=s.employee_id).first()
    store = db.query(Store).filter_by(id=s.store_id).first()
    return {
        'id': s.id, 'employee_name': emp.name if emp else '',
        'store_name': store.name if store else '',
        'work_date': str(s.work_date),
        'start_time': s.start_time, 'end_time': s.end_time,
        'break_minutes': s.break_minutes, 'status': s.status.value,
    }


@router.delete("/{schedule_id}", response_model=MessageResponse)
def cancel_schedule(schedule_id: int, reason: str = '관리자수정',
                    db: Session = Depends(get_db)):
    """스케줄 취소"""
    s = db.query(Schedule).filter_by(id=schedule_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="스케줄을 찾을 수 없습니다.")
    if s.status == ScheduleStatus.LOCKED:
        raise HTTPException(status_code=400, detail="잠금된 스케줄은 취소할 수 없습니다.")

    before = {'is_cancelled': False}
    s.is_cancelled = True

    history = ScheduleHistory(
        schedule_id=schedule_id,
        before_data=json.dumps(before),
        after_data=json.dumps({'is_cancelled': True}),
        change_reason=ChangeReason(reason),
    )
    db.add(history)
    db.commit()
    return {"message": "스케줄이 취소되었습니다.", "success": True}


@router.post("/{schedule_id}/lock", response_model=MessageResponse)
def lock_schedule(schedule_id: int, db: Session = Depends(get_db)):
    s = db.query(Schedule).filter_by(id=schedule_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="스케줄을 찾을 수 없습니다.")
    s.status = ScheduleStatus.LOCKED
    db.commit()
    return {"message": "스케줄이 잠금되었습니다.", "success": True}


@router.post("/{schedule_id}/confirm", response_model=MessageResponse)
def confirm_schedule(schedule_id: int, db: Session = Depends(get_db)):
    s = db.query(Schedule).filter_by(id=schedule_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="스케줄을 찾을 수 없습니다.")
    s.status = ScheduleStatus.CONFIRMED
    db.commit()
    return {"message": "스케줄이 확정되었습니다.", "success": True}


# ── 검증 ──

@router.get("/validate")
def validate_schedules(year: int = Query(...), month: int = Query(...),
                       db: Session = Depends(get_db)):
    """스케줄 검증 — HARD CONSTRAINT 위반 여부 확인"""
    from app.services.validation import validate_month
    issues = validate_month(year, month, db)
    return {'issues': issues, 'count': len(issues)}
