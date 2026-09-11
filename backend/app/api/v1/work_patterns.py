from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.database.database import get_db
from app.models.models import Employee, EmployeeType, EmployeeWorkPattern, Store, DayOfWeek
from app.schemas.schemas import WorkPatternUpsert, WorkPatternResponse

router = APIRouter(prefix="/employees", tags=["근무패턴 관리"])

DAY_ORDER = [DayOfWeek.MON, DayOfWeek.TUE, DayOfWeek.WED,
             DayOfWeek.THU, DayOfWeek.FRI, DayOfWeek.SAT, DayOfWeek.SUN]


@router.get("/{employee_id}/work-patterns", response_model=List[WorkPatternResponse])
def get_work_patterns(employee_id: int, db: Session = Depends(get_db)):
    """정규직 직원의 요일별 근무패턴 조회"""
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="직원을 찾을 수 없습니다.")
    if employee.employee_type != EmployeeType.REGULAR:
        raise HTTPException(status_code=400, detail="근무패턴은 정규직 직원만 설정할 수 있습니다.")

    patterns = (
        db.query(EmployeeWorkPattern)
        .filter(EmployeeWorkPattern.employee_id == employee_id)
        .all()
    )
    # 요일 순서대로 정렬
    patterns.sort(key=lambda p: DAY_ORDER.index(p.day_of_week))
    return patterns


@router.put("/{employee_id}/work-patterns", response_model=List[WorkPatternResponse])
def upsert_work_patterns(
    employee_id: int,
    data: WorkPatternUpsert,
    db: Session = Depends(get_db)
):
    """정규직 직원의 근무패턴 저장 (7일 전체를 한 번에 저장)"""
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="직원을 찾을 수 없습니다.")
    if employee.employee_type != EmployeeType.REGULAR:
        raise HTTPException(status_code=400, detail="근무패턴은 정규직 직원만 설정할 수 있습니다.")

    # 매장 ID 유효성 검사
    for item in data.patterns:
        if item.store_id:
            store = db.query(Store).filter(Store.id == item.store_id).first()
            if not store:
                raise HTTPException(
                    status_code=400,
                    detail=f"매장 ID {item.store_id}를 찾을 수 없습니다."
                )
        if not item.is_day_off and (not item.start_time or not item.end_time):
            raise HTTPException(
                status_code=400,
                detail=f"근무일({item.day_of_week.value})에는 시작시간과 종료시간을 입력해야 합니다."
            )

    # 기존 패턴 삭제 후 새로 저장
    db.query(EmployeeWorkPattern).filter(
        EmployeeWorkPattern.employee_id == employee_id
    ).delete()

    new_patterns = []
    for item in data.patterns:
        pattern = EmployeeWorkPattern(
            employee_id=employee_id,
            day_of_week=item.day_of_week,
            is_day_off=item.is_day_off,
            start_time=None if item.is_day_off else item.start_time,
            end_time=None if item.is_day_off else item.end_time,
            store_id=None if item.is_day_off else item.store_id,
        )
        db.add(pattern)
        new_patterns.append(pattern)

    db.commit()
    for p in new_patterns:
        db.refresh(p)

    new_patterns.sort(key=lambda p: DAY_ORDER.index(p.day_of_week))
    return new_patterns
