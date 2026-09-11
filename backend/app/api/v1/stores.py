from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.database.database import get_db
from app.models.models import Store
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
