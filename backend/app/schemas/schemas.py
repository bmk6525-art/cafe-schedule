"""
Pydantic 스키마 - API 요청/응답 데이터 형식 정의
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import date, datetime
from app.models.models import EmployeeType, DayOfWeek, ScheduleStatus, ChangeReason


def _validate_5min(v: Optional[str]) -> Optional[str]:
    if v is None:
        return v
    try:
        minute = int(v.split(':')[1])
    except (IndexError, ValueError):
        raise ValueError(f"시간 형식이 올바르지 않습니다: {v}")
    if minute % 5 != 0:
        raise ValueError(f"시간은 5분 단위여야 합니다 (입력값: {v})")
    return v


# ───────────────────────────────────────────────
# Store 스키마
# ───────────────────────────────────────────────

class StoreBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    open_time: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    close_time: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    memo: Optional[str] = None

    @field_validator('open_time', 'close_time')
    @classmethod
    def open_close_5min(cls, v: str) -> str:
        return _validate_5min(v)


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

    @field_validator('start_time', 'end_time')
    @classmethod
    def req_time_5min(cls, v: str) -> str:
        return _validate_5min(v)

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

    @field_validator('open_time', 'close_time')
    @classmethod
    def update_time_5min(cls, v: Optional[str]) -> Optional[str]:
        return _validate_5min(v)


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
    # 가능 설정 (신규)
    is_working_day: bool = False          # 이 요일 근무 가능 여부
    store_id: Optional[int] = None        # NULL = 전체 호점
    available_start: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    available_end: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    # 불가능 설정 (기존 유지)
    is_day_unavailable: bool = False
    unavailable_start: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    unavailable_end: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    memo: Optional[str] = None

    @field_validator('available_start', 'available_end', 'unavailable_start', 'unavailable_end')
    @classmethod
    def av_time_5min(cls, v: Optional[str]) -> Optional[str]:
        return _validate_5min(v)

class MonthlyAvailabilityUpsert(BaseModel):
    days: List[AvailabilityDayItem]

class MonthlyAvailabilityResponse(BaseModel):
    id: int
    employee_id: int
    year: int
    month: int
    day_of_week: DayOfWeek
    entry_type: str = 'UNAVAILABLE'
    is_working_day: bool = False
    store_id: Optional[int] = None
    available_start: Optional[str] = None
    available_end: Optional[str] = None
    is_day_unavailable: bool
    unavailable_start: Optional[str]
    unavailable_end: Optional[str]
    memo: Optional[str]
    model_config = {"from_attributes": True}

class AvailabilityExceptionCreate(BaseModel):
    exception_date: date
    is_day_unavailable: bool = False
    is_available_override: bool = False  # True='가능' 예외, False='불가능' 예외
    unavailable_start: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    unavailable_end: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    memo: Optional[str] = None

    @field_validator('unavailable_start', 'unavailable_end')
    @classmethod
    def exc_time_5min(cls, v: Optional[str]) -> Optional[str]:
        return _validate_5min(v)

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

    @field_validator('start_time', 'end_time')
    @classmethod
    def wp_time_5min(cls, v: Optional[str]) -> Optional[str]:
        return _validate_5min(v)


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
