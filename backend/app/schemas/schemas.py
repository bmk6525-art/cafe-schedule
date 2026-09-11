"""
Pydantic 스키마 - API 요청/응답 데이터 형식 정의
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date, datetime
from app.models.models import EmployeeType, DayOfWeek, ScheduleStatus, ChangeReason


# ───────────────────────────────────────────────
# Store 스키마
# ───────────────────────────────────────────────

class StoreBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    open_time: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    close_time: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    memo: Optional[str] = None


class StoreCreate(StoreBase):
    pass


# ───────────────────────────────────────────────
# 필요인원 스키마
# ───────────────────────────────────────────────

class StaffRequirementItem(BaseModel):
    day_of_week: DayOfWeek
    start_time: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    end_time: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    required_count: int = Field(..., ge=0)

class StaffRequirementBulk(BaseModel):
    items: List[StaffRequirementItem]

class StaffRequirementResponse(StaffRequirementItem):
    id: int
    store_id: int
    year: int
    month: int
    model_config = {"from_attributes": True}


class StoreUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    open_time: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    close_time: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    is_active: Optional[bool] = None
    memo: Optional[str] = None


class StoreResponse(StoreBase):
    id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ───────────────────────────────────────────────
# Employee 스키마
# ───────────────────────────────────────────────

class EmployeeBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    employee_type: EmployeeType
    hourly_wage: int = Field(..., ge=0)
    phone: Optional[str] = None
    hire_date: Optional[date] = None
    resign_date: Optional[date] = None
    preferred_store_id: Optional[int] = None
    memo: Optional[str] = None
    monthly_target_hours: Optional[float] = None
    monthly_min_hours: Optional[float] = None
    monthly_max_hours: Optional[float] = None


class EmployeeCreate(EmployeeBase):
    pass


class EmployeeUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    employee_type: Optional[EmployeeType] = None
    hourly_wage: Optional[int] = Field(None, ge=0)
    phone: Optional[str] = None
    hire_date: Optional[date] = None
    resign_date: Optional[date] = None
    is_active: Optional[bool] = None
    preferred_store_id: Optional[int] = None
    memo: Optional[str] = None
    monthly_target_hours: Optional[float] = None
    monthly_min_hours: Optional[float] = None
    monthly_max_hours: Optional[float] = None


class EmployeeResponse(EmployeeBase):
    id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ───────────────────────────────────────────────
# 월별 불가능 시간 스키마 (파트타이머용)
# ───────────────────────────────────────────────

class AvailabilityDayItem(BaseModel):
    day_of_week: DayOfWeek
    is_day_unavailable: bool = False
    unavailable_start: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    unavailable_end: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    memo: Optional[str] = None

class MonthlyAvailabilityUpsert(BaseModel):
    days: List[AvailabilityDayItem]

class MonthlyAvailabilityResponse(BaseModel):
    id: int
    employee_id: int
    year: int
    month: int
    day_of_week: DayOfWeek
    is_day_unavailable: bool
    unavailable_start: Optional[str]
    unavailable_end: Optional[str]
    memo: Optional[str]
    model_config = {"from_attributes": True}

class AvailabilityExceptionCreate(BaseModel):
    exception_date: date
    is_day_unavailable: bool = False
    unavailable_start: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    unavailable_end: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    memo: Optional[str] = None

class AvailabilityExceptionResponse(AvailabilityExceptionCreate):
    id: int
    employee_id: int
    model_config = {"from_attributes": True}


# ───────────────────────────────────────────────
# 근무패턴 스키마 (정규직용)
# ───────────────────────────────────────────────

class WorkPatternItem(BaseModel):
    day_of_week: DayOfWeek
    is_day_off: bool = False
    start_time: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    end_time: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    store_id: Optional[int] = None


class WorkPatternUpsert(BaseModel):
    patterns: List[WorkPatternItem]


class WorkPatternResponse(WorkPatternItem):
    id: int
    employee_id: int

    model_config = {"from_attributes": True}


# ───────────────────────────────────────────────
# 공통 응답 스키마
# ───────────────────────────────────────────────

class MessageResponse(BaseModel):
    message: str
    success: bool = True


class PaginatedResponse(BaseModel):
    items: List
    total: int
    page: int
    page_size: int
