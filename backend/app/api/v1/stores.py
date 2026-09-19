from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.database.database import get_db
from app.models.models import Store, Employee, EmployeeWorkPattern, StaffRequirement, Schedule, ActualWork, ScheduleHistory
from app.schemas.schemas import StoreCreate, StoreUpdate, StoreResponse, MessageResponse

router = APIRouter(prefix="/stores", tags=["매장 관리"])


@router.get("", response_model=List[StoreResponse])
def get_stores(include_inactive: bool = False, db: Session = Depends(get_db)):
    """매장 목록 조회"""
    query = db.query(Store)
    if not include_inactive:
        query = query.filter(Store.is_active == True)
    return query.order_by(Store.id).all()


@router.get("/{store_id}", response_model=StoreResponse)
def get_store(store_id: int, db: Session = Depends(get_db)):
    """매장 상세 조회"""
    store = db.query(Store).filter(Store.id == store_id).first()
    if not store:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="매장을 찾을 수 없습니다."
        )
    return store


@router.post("", response_model=StoreResponse, status_code=status.HTTP_201_CREATED)
def create_store(store_data: StoreCreate, db: Session = Depends(get_db)):
    """매장 추가"""
    existing = db.query(Store).filter(Store.name == store_data.name).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"'{store_data.name}' 이름의 매장이 이미 존재합니다."
        )
    store = Store(**store_data.model_dump())
    db.add(store)
    db.commit()
    db.refresh(store)
    return store


@router.put("/{store_id}", response_model=StoreResponse)
def update_store(store_id: int, store_data: StoreUpdate, db: Session = Depends(get_db)):
    """매장 정보 수정"""
    store = db.query(Store).filter(Store.id == store_id).first()
    if not store:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="매장을 찾을 수 없습니다."
        )
    update_data = store_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(store, field, value)
    db.commit()
    db.refresh(store)
    return store


@router.delete("/{store_id}", response_model=MessageResponse)
def deactivate_store(store_id: int, db: Session = Depends(get_db)):
    """매장 비활성화 (soft delete)"""
    store = db.query(Store).filter(Store.id == store_id).first()
    if not store:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="매장을 찾을 수 없습니다."
        )
    store.is_active = False
    db.commit()
    return {"message": f"'{store.name}' 매장이 비활성화되었습니다.", "success": True}


@router.post("/{store_id}/activate", response_model=MessageResponse)
def activate_store(store_id: int, db: Session = Depends(get_db)):
    """매장 활성화"""
    store = db.query(Store).filter(Store.id == store_id).first()
    if not store:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="매장을 찾을 수 없습니다."
        )
    store.is_active = True
    db.commit()
    return {"message": f"'{store.name}' 매장이 활성화되었습니다.", "success": True}


@router.delete("/{store_id}/permanent", response_model=MessageResponse)
def hard_delete_store(store_id: int, db: Session = Depends(get_db)):
    """매장 영구 삭제 (모든 관련 데이터 포함)"""
    store = db.query(Store).filter(Store.id == store_id).first()
    if not store:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="매장을 찾을 수 없습니다.")

    name = store.name

    # 직원 선호매장 null 처리
    db.query(Employee).filter(Employee.preferred_store_id == store_id).update(
        {Employee.preferred_store_id: None}, synchronize_session=False
    )
    # 근무패턴 매장 null 처리
    db.query(EmployeeWorkPattern).filter(EmployeeWorkPattern.store_id == store_id).update(
        {EmployeeWorkPattern.store_id: None}, synchronize_session=False
    )
    # 필요인원 삭제
    db.query(StaffRequirement).filter(StaffRequirement.store_id == store_id).delete()

    # 스케줄 이력 → 실제근무 → 스케줄 삭제
    sch_ids = [s.id for s in db.query(Schedule.id).filter(Schedule.store_id == store_id).all()]
    if sch_ids:
        db.query(ScheduleHistory).filter(ScheduleHistory.schedule_id.in_(sch_ids)).delete(synchronize_session=False)
        db.query(ActualWork).filter(ActualWork.schedule_id.in_(sch_ids)).delete(synchronize_session=False)
    db.query(Schedule).filter(Schedule.store_id == store_id).delete()

    db.delete(store)
    db.commit()
    return {"message": f"'{name}' 매장이 영구 삭제되었습니다.", "success": True}
