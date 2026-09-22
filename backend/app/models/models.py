"""
카페 근무 스케줄 관리 - 데이터베이스 모델

설계 원칙:
- 직원 기본정보와 월별 정보를 분리하여 과거 데이터 보존
- soft delete(is_active) 사용으로 데이터 보존
- 스케줄 데이터와 급여 데이터를 별도 테이블로 분리
"""

import enum
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Boolean, Float, DateTime,
    ForeignKey, Enum as SAEnum, Text, Date, UniqueConstraint, Index
)
from sqlalchemy.orm import relationship
from app.database.database import Base


# ───────────────────────────────────────────────
# ENUM 정의
# ───────────────────────────────────────────────

class EmployeeType(str, enum.Enum):
    REGULAR = "REGULAR"         # 정규 직원
    PART_TIMER = "PART_TIMER"   # 파트타이머


class DayOfWeek(str, enum.Enum):
    MON = "MON"
    TUE = "TUE"
    WED = "WED"
    THU = "THU"
    FRI = "FRI"
    SAT = "SAT"
    SUN = "SUN"


class ScheduleStatus(str, enum.Enum):
    DRAFT = "DRAFT"         # 작성 중
    CONFIRMED = "CONFIRMED" # 확정
    LOCKED = "LOCKED"       # 잠금


class ChangeReason(str, enum.Enum):
    PERSONAL = "개인사정"
    ABSENT = "결근"
    SUBSTITUTE = "대체근무"
    STORE_CHANGE = "매장변경"
    TIME_CHANGE = "시간변경"
    ADMIN_EDIT = "관리자수정"
    OTHER = "기타"


# ───────────────────────────────────────────────
# 매장 (Store)
# ───────────────────────────────────────────────

class Store(Base):
    __tablename__ = "stores"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True)
    open_time = Column(String(5), nullable=False)   # "HH:MM" 형식
    close_time = Column(String(5), nullable=False)  # "HH:MM" 형식
    is_active = Column(Boolean, default=True, nullable=False)
    memo = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    staff_requirements = relationship("StaffRequirement", back_populates="store")
    schedules = relationship("Schedule", back_populates="store")


# ───────────────────────────────────────────────
# 직원 (Employee) - 정규직 + 파트타이머 통합
# ───────────────────────────────────────────────

class Employee(Base):
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    employee_type = Column(SAEnum(EmployeeType), nullable=False)
    hourly_wage = Column(Integer, nullable=False, default=0)    # 시급 (원)
    phone = Column(String(20), nullable=True)
    hire_date = Column(Date, nullable=True)
    resign_date = Column(Date, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    preferred_store_id = Column(Integer, ForeignKey("stores.id"), nullable=True)
    memo = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # 목표 근무시간 (파트타이머용 SOFT CONSTRAINT)
    monthly_target_hours = Column(Float, nullable=True)
    monthly_min_hours = Column(Float, nullable=True)
    monthly_max_hours = Column(Float, nullable=True)

    # Relationships
    preferred_store = relationship("Store", foreign_keys=[preferred_store_id])
    work_patterns = relationship("EmployeeWorkPattern", back_populates="employee")
    monthly_availabilities = relationship("MonthlyAvailability", back_populates="employee")
    schedules = relationship("Schedule", back_populates="employee")
    actual_works = relationship("ActualWork", back_populates="employee")


# ───────────────────────────────────────────────
# 정규직 기본 근무패턴 (EmployeeWorkPattern)
# 요일별 기본 근무시간 저장
# ───────────────────────────────────────────────

class EmployeeWorkPattern(Base):
    __tablename__ = "employee_work_patterns"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    day_of_week = Column(SAEnum(DayOfWeek), nullable=False)
    is_day_off = Column(Boolean, default=False, nullable=False)  # 해당 요일 휴무 여부
    start_time = Column(String(5), nullable=True)   # "HH:MM", 휴무일이면 NULL
    end_time = Column(String(5), nullable=True)     # "HH:MM", 휴무일이면 NULL
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=True)  # 기본 배정 매장
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("employee_id", "day_of_week", name="uq_work_pattern_employee_day"),
    )

    # Relationships
    employee = relationship("Employee", back_populates="work_patterns")
    store = relationship("Store")


# ───────────────────────────────────────────────
# 파트타이머 월별 근무 불가능 시간 (MonthlyAvailability)
# "불가능 시간"을 요일별로 저장하는 방식 사용
# 해당 요일 전체 불가능 → is_day_unavailable = True
# 특정 시간대 불가능 → unavailable_start/end 에 시간대 저장
# ───────────────────────────────────────────────

class MonthlyAvailability(Base):
    __tablename__ = "monthly_availability"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False)
    day_of_week = Column(SAEnum(DayOfWeek), nullable=False)
    # 'UNAVAILABLE' (기존 불가능 레코드) or 'AVAILABLE' (신규 가능 레코드)
    entry_type = Column(String(20), default='UNAVAILABLE', nullable=False, server_default='UNAVAILABLE')
    # 가능 필드 (entry_type='AVAILABLE'일 때 사용)
    is_working_day = Column(Boolean, default=False, nullable=False, server_default='0')  # 근무 가능 요일
    available_start = Column(String(5), nullable=True)   # 가능 시작시간 "HH:MM"
    available_end = Column(String(5), nullable=True)     # 가능 종료시간 "HH:MM"
    # 불가능 필드 (entry_type='UNAVAILABLE'일 때 사용, 기존 유지)
    is_day_unavailable = Column(Boolean, default=False, nullable=False)  # 종일 불가능
    unavailable_start = Column(String(5), nullable=True)   # 불가능 시작시간 "HH:MM"
    unavailable_end = Column(String(5), nullable=True)     # 불가능 종료시간 "HH:MM"
    memo = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    employee = relationship("Employee", back_populates="monthly_availabilities")


# ───────────────────────────────────────────────
# 특정 날짜 예외 (AvailabilityException)
# 요일 기본 설정보다 우선 적용
# ───────────────────────────────────────────────

class AvailabilityException(Base):
    __tablename__ = "availability_exceptions"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    exception_date = Column(Date, nullable=False)
    is_day_unavailable = Column(Boolean, default=False, nullable=False)  # 종일 불가능
    # True = '가능' 예외(요일 불가 설정 무시), False = '불가능' 예외(기존 동작)
    is_available_override = Column(Boolean, default=False, nullable=False, server_default='0')
    unavailable_start = Column(String(5), nullable=True)  # 불가/가능 시간 시작
    unavailable_end = Column(String(5), nullable=True)    # 불가/가능 시간 종료
    memo = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("employee_id", "exception_date", name="uq_exception_employee_date"),
    )

    employee = relationship("Employee")


# ───────────────────────────────────────────────
# 매장별 시간대 필요인원 (StaffRequirement)
# 요일별 / 시간대별 필요 인원 관리
# ───────────────────────────────────────────────

class StaffRequirement(Base):
    __tablename__ = "staff_requirements"

    id = Column(Integer, primary_key=True, index=True)
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=False)
    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False)
    day_of_week = Column(SAEnum(DayOfWeek), nullable=False)
    start_time = Column(String(5), nullable=False)  # "HH:MM"
    end_time = Column(String(5), nullable=False)    # "HH:MM"
    required_count = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    store = relationship("Store", back_populates="staff_requirements")


# ───────────────────────────────────────────────
# 스케줄 (Schedule) - 계획 근무
# ───────────────────────────────────────────────

class Schedule(Base):
    __tablename__ = "schedules"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=False)
    work_date = Column(Date, nullable=False)
    start_time = Column(String(5), nullable=False)  # "HH:MM"
    end_time = Column(String(5), nullable=False)    # "HH:MM"
    break_minutes = Column(Integer, default=0, nullable=False)  # 휴게시간 (분)
    status = Column(SAEnum(ScheduleStatus), default=ScheduleStatus.DRAFT, nullable=False)
    is_cancelled = Column(Boolean, default=False, nullable=False)
    memo = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        # 월별 조회·삭제·중복정리 쿼리 핵심 인덱스
        Index('ix_schedules_date_status', 'work_date', 'is_cancelled', 'status'),
        # 직원별·매장별 조회용
        Index('ix_schedules_emp_date', 'employee_id', 'work_date'),
        Index('ix_schedules_store_date', 'store_id', 'work_date'),
    )

    # Relationships
    employee = relationship("Employee", back_populates="schedules")
    store = relationship("Store", back_populates="schedules")
    actual_work = relationship("ActualWork", back_populates="schedule", uselist=False)
    history = relationship("ScheduleHistory", back_populates="schedule")


# ───────────────────────────────────────────────
# 실제 근무시간 (ActualWork)
# 계획과 별도 저장 - 급여 계산에 사용
# ───────────────────────────────────────────────

class ActualWork(Base):
    __tablename__ = "actual_work"

    id = Column(Integer, primary_key=True, index=True)
    schedule_id = Column(Integer, ForeignKey("schedules.id"), nullable=False, unique=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    actual_start = Column(String(5), nullable=True)     # "HH:MM"
    actual_end = Column(String(5), nullable=True)       # "HH:MM"
    actual_break_minutes = Column(Integer, default=0, nullable=False)
    is_absent = Column(Boolean, default=False, nullable=False)
    memo = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    schedule = relationship("Schedule", back_populates="actual_work")
    employee = relationship("Employee", back_populates="actual_works")


# ───────────────────────────────────────────────
# 월별 급여 스냅샷 (MonthlyPayroll)
# 시급 변경으로 과거 급여가 변경되지 않도록 스냅샷 저장
# ───────────────────────────────────────────────

class MonthlyPayroll(Base):
    __tablename__ = "payroll"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False)
    # 급여 계산 시점의 시급 스냅샷 (과거 데이터 보존용)
    hourly_wage_snapshot = Column(Integer, nullable=False)
    total_work_hours = Column(Float, nullable=False, default=0)
    base_pay = Column(Integer, nullable=False, default=0)           # 기본급
    holiday_pay = Column(Integer, nullable=False, default=0)        # 주휴수당
    total_pay = Column(Integer, nullable=False, default=0)          # 총 지급액
    is_finalized = Column(Boolean, default=False, nullable=False)   # 월 마감 여부
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("employee_id", "year", "month", name="uq_payroll_employee_month"),
    )

    employee = relationship("Employee")
    weekly_payrolls = relationship("WeeklyPayroll", back_populates="monthly_payroll")


# ───────────────────────────────────────────────
# 주차별 급여 (WeeklyPayroll)
# 주휴수당 계산 단위
# ───────────────────────────────────────────────

class WeeklyPayroll(Base):
    __tablename__ = "weekly_payroll"

    id = Column(Integer, primary_key=True, index=True)
    monthly_payroll_id = Column(Integer, ForeignKey("payroll.id"), nullable=False)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False)
    week_number = Column(Integer, nullable=False)   # 1~5주차
    total_hours = Column(Float, nullable=False, default=0)
    # 주휴수당 발생 여부 (주 15시간 이상 근무 시)
    is_holiday_pay_eligible = Column(Boolean, default=False, nullable=False)
    holiday_pay_amount = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("employee_id", "year", "month", "week_number",
                         name="uq_weekly_payroll_employee_week"),
    )

    monthly_payroll = relationship("MonthlyPayroll", back_populates="weekly_payrolls")
    employee = relationship("Employee")


# ───────────────────────────────────────────────
# 스케줄 변경 이력 (ScheduleHistory)
# ───────────────────────────────────────────────

class ScheduleHistory(Base):
    __tablename__ = "schedule_history"

    id = Column(Integer, primary_key=True, index=True)
    schedule_id = Column(Integer, ForeignKey("schedules.id"), nullable=False)
    changed_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    changed_by = Column(String(100), nullable=True)     # 향후 사용자 시스템 연동
    # 변경 전/후 데이터를 JSON 문자열로 저장
    before_data = Column(Text, nullable=True)
    after_data = Column(Text, nullable=True)
    change_reason = Column(SAEnum(ChangeReason), default=ChangeReason.ADMIN_EDIT, nullable=False)
    memo = Column(Text, nullable=True)

    schedule = relationship("Schedule", back_populates="history")


# ───────────────────────────────────────────────
# 월별 설정 (MonthlySettings)
# 월별 스케줄 작성 상태 및 메타데이터
# ───────────────────────────────────────────────

class MonthlySettings(Base):
    __tablename__ = "monthly_settings"

    id = Column(Integer, primary_key=True, index=True)
    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False)
    is_finalized = Column(Boolean, default=False, nullable=False)   # 월 마감 여부
    finalized_at = Column(DateTime, nullable=True)
    memo = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("year", "month", name="uq_monthly_settings"),
    )
