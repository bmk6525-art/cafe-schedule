from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database.database import get_db
from app.models.models import (
    Employee, EmployeeType, EmployeeWorkPattern, MonthlyAvailability,
    AvailabilityException, Schedule, ActualWork, MonthlyPayroll, WeeklyPayroll, ScheduleHistory,
)
from app.schemas.schemas import EmployeeCreate, EmployeeUpdate, EmployeeResponse, MessageResponse

router = APIRouter(prefix="/employees", tags=["직원 관리"])


@router.get("", response_model=List[EmployeeResponse])
def get_employees(
    include_inactive: bool = False,
    employee_type: Optional[EmployeeType] = None,
    db: Session = Depends(get_db)
):
    """직원 목록 조회 (정규직/파트타이머 필터 가능)"""
    query = db.query(Employee)
    if not include_inactive:
        query = query.filter(Employee.is_active == True)
    if employee_type:
        query = query.filter(Employee.employee_type == employee_type)
    return query.order_by(Employee.id).all()


@router.get("/{employee_id}", response_model=EmployeeResponse)
def get_employee(employee_id: int, db: Session = Depends(get_db)):
    """직원 상세 조회"""
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not employee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="직원을 찾을 수 없습니다."
        )
    return employee


@router.post("", response_model=EmployeeResponse, status_code=status.HTTP_201_CREATED)
def create_employee(employee_data: EmployeeCreate, db: Session = Depends(get_db)):
    """직원 추가"""
    if employee_data.preferred_store_id:
        from app.models.models import Store
        store = db.query(Store).filter(Store.id == employee_data.preferred_store_id).first()
        if not store:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="선호 매장을 찾을 수 없습니다."
            )
    employee = Employee(**employee_data.model_dump())
    db.add(employee)
    db.commit()
    db.refresh(employee)
    return employee


@router.put("/{employee_id}", response_model=EmployeeResponse)
def update_employee(employee_id: int, employee_data: EmployeeUpdate, db: Session = Depends(get_db)):
    """직원 정보 수정"""
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not employee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="직원을 찾을 수 없습니다."
        )
    update_data = employee_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(employee, field, value)
    db.commit()
    db.refresh(employee)
    return employee


@router.delete("/{employee_id}", response_model=MessageResponse)
def deactivate_employee(employee_id: int, db: Session = Depends(get_db)):
    """직원 비활성화 (soft delete)"""
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not employee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="직원을 찾을 수 없습니다."
        )
    employee.is_active = False
    db.commit()
    return {"message": f"'{employee.name}' 직원이 비활성화되었습니다.", "success": True}


@router.post("/{employee_id}/activate", response_model=MessageResponse)
def activate_employee(employee_id: int, db: Session = Depends(get_db)):
    """직원 활성화"""
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not employee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="직원을 찾을 수 없습니다."
        )
    employee.is_active = True
    db.commit()
    return {"message": f"'{employee.name}' 직원이 활성화되었습니다.", "success": True}


@router.delete("/{employee_id}/permanent", response_model=MessageResponse)
def hard_delete_employee(employee_id: int, db: Session = Depends(get_db)):
    """직원 영구 삭제 (모든 관련 데이터 포함)"""
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not employee:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="직원을 찾을 수 없습니다.")

    name = employee.name

    # 관련 급여 데이터 삭제
    db.query(WeeklyPayroll).filter(WeeklyPayroll.employee_id == employee_id).delete()
    db.query(MonthlyPayroll).filter(MonthlyPayroll.employee_id == employee_id).delete()

    # 실제 근무 삭제
    db.query(ActualWork).filter(ActualWork.employee_id == employee_id).delete()

    # 스케줄 이력 → 스케줄 삭제
    sch_ids = [s.id for s in db.query(Schedule.id).filter(Schedule.employee_id == employee_id).all()]
    if sch_ids:
        db.query(ScheduleHistory).filter(ScheduleHistory.schedule_id.in_(sch_ids)).delete(synchronize_session=False)
    db.query(Schedule).filter(Schedule.employee_id == employee_id).delete()

    # 불가능시간·패턴 삭제
    db.query(AvailabilityException).filter(AvailabilityException.employee_id == employee_id).delete()
    db.query(MonthlyAvailability).filter(MonthlyAvailability.employee_id == employee_id).delete()
    db.query(EmployeeWorkPattern).filter(EmployeeWorkPattern.employee_id == employee_id).delete()

    db.delete(employee)
    db.commit()
    return {"message": f"'{name}' 직원이 영구 삭제되었습니다.", "success": True}
