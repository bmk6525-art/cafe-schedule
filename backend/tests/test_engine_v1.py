"""
스케줄 엔진 1차 개선 테스트

대상 수정사항:
  1. CONFIRMED/LOCKED 근무시간을 pt_hours 초기값에 반영
  2. monthly_max_hours 초과 시 배정 불가
  3. 빈 예외 레코드가 월별 요일 설정을 무시하는 버그 수정
"""

import pytest
from datetime import date
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.database import Base
from app.models.models import (
    Employee, EmployeeType, Store, Schedule, ScheduleStatus,
    StaffRequirement, MonthlyAvailability, AvailabilityException,
    DayOfWeek,
)
from app.schedule_engine.engine import ScheduleEngine

# 2026-10-01 = Thursday(3), 2026-10-05 = Monday(0), 2026-10-07 = Wednesday(2)
TEST_YEAR = 2026
TEST_MONTH = 10


# ── 인메모리 SQLite ──────────────────────────────────────────────────

@pytest.fixture(scope="function")
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


# ── 공통 헬퍼 ────────────────────────────────────────────────────────

def _add_store(db) -> Store:
    store = Store(name="테스트매장", open_time="09:00", close_time="22:00")
    db.add(store)
    db.flush()
    return store


def _add_part_timer(db, name="파트", max_hours=None) -> Employee:
    pt = Employee(
        name=name,
        employee_type=EmployeeType.PART_TIMER,
        hourly_wage=10000,
        monthly_max_hours=max_hours,
    )
    db.add(pt)
    db.flush()
    return pt


def _add_confirmed(db, emp_id, store_id, work_date, start, end,
                   status=ScheduleStatus.CONFIRMED):
    s = Schedule(
        employee_id=emp_id,
        store_id=store_id,
        work_date=work_date,
        start_time=start,
        end_time=end,
        break_minutes=0,
        status=status,
        is_cancelled=False,
    )
    db.add(s)
    db.flush()
    return s


def _add_requirement(db, store_id, dow, start, end, required_count=1):
    req = StaffRequirement(
        store_id=store_id,
        year=TEST_YEAR, month=TEST_MONTH,
        day_of_week=dow,
        start_time=start,
        end_time=end,
        required_count=required_count,
    )
    db.add(req)
    db.flush()
    return req


def _get_draft(db, emp_id, work_date):
    return db.query(Schedule).filter(
        Schedule.employee_id == emp_id,
        Schedule.work_date == work_date,
        Schedule.is_cancelled == False,
        Schedule.status == ScheduleStatus.DRAFT,
    ).all()


# ═════════════════════════════════════════════════════════════════════
# 통합 테스트 — generate() 전체 흐름
# ═════════════════════════════════════════════════════════════════════

class TestConfirmedHoursReflected:
    """수정 1: CONFIRMED 근무시간이 pt_hours 초기값에 반영되는지"""

    def test_confirmed_hours_reflected_in_priority(self, db):
        """
        [Test 3]
        PT_A: CONFIRMED 20h → pt_hours 시작값 20h
        PT_B: CONFIRMED 없음 → pt_hours 시작값 0h
        필요인원 1명 → pt_hours가 낮은 PT_B가 우선 배정되어야 함
        (기존 코드는 둘 다 0h로 시작해 ID 순서로 PT_A가 배정됨)
        """
        store = _add_store(db)
        pt_a = _add_part_timer(db, name="파트A_heavy")
        pt_b = _add_part_timer(db, name="파트B_light")

        # PT_A: 2 × 10h = 20h CONFIRMED (Oct 1, 2: Thu/Fri)
        _add_confirmed(db, pt_a.id, store.id, date(2026, 10, 1), "09:00", "19:00")
        _add_confirmed(db, pt_a.id, store.id, date(2026, 10, 2), "09:00", "19:00")

        # Oct 7 (Wed) 09:00-18:00 = 9h, 필요인원 1명
        _add_requirement(db, store.id, DayOfWeek.WED, "09:00", "18:00", required_count=1)
        db.commit()

        ScheduleEngine().generate(TEST_YEAR, TEST_MONTH, db)

        oct7 = db.query(Schedule).filter(
            Schedule.work_date == date(2026, 10, 7),
            Schedule.is_cancelled == False,
            Schedule.status == ScheduleStatus.DRAFT,
        ).first()

        assert oct7 is not None, "Oct 7 슬롯에 누군가는 배정되어야 함"
        assert oct7.employee_id == pt_b.id, (
            "CONFIRMED 시간이 없는 PT_B(0h)가 PT_A(20h)보다 우선 배정되어야 함. "
            "기존 코드(둘 다 0h 시작)라면 ID 순서로 PT_A가 배정됨."
        )

    def test_confirmed_not_regenerated(self, db):
        """
        CONFIRMED 스케줄은 재생성되지 않아야 함 (보호)
        """
        store = _add_store(db)
        pt = _add_part_timer(db)

        confirmed = _add_confirmed(
            db, pt.id, store.id, date(2026, 10, 1), "09:00", "18:00"
        )
        db.commit()

        ScheduleEngine().generate(TEST_YEAR, TEST_MONTH, db)

        # 기존 CONFIRMED는 그대로 남아 있어야 함
        still_there = db.query(Schedule).filter(
            Schedule.id == confirmed.id,
            Schedule.is_cancelled == False,
            Schedule.status == ScheduleStatus.CONFIRMED,
        ).first()
        assert still_there is not None, "CONFIRMED 스케줄은 삭제/변경되어서는 안 됨"


class TestMonthlyMaxHours:
    """수정 2: monthly_max_hours 초과 시 배정 불가"""

    def test_under_limit_assigns(self, db):
        """
        [Test 1]
        CONFIRMED 30h + 새 슬롯 8h = 38h ≤ max 40h → 배정 가능
        """
        store = _add_store(db)
        pt = _add_part_timer(db, name="파트A", max_hours=40.0)

        # 3 × 10h = 30h CONFIRMED (Oct 1, 2, 3: Thu/Fri/Sat)
        for day in [1, 2, 3]:
            _add_confirmed(db, pt.id, store.id, date(2026, 10, day), "09:00", "19:00")

        # Oct 7 (Wed) 09:00-17:00 = 8h
        _add_requirement(db, store.id, DayOfWeek.WED, "09:00", "17:00")
        db.commit()

        result = ScheduleEngine().generate(TEST_YEAR, TEST_MONTH, db)

        new = _get_draft(db, pt.id, date(2026, 10, 7))
        assert len(new) == 1, (
            f"38h ≤ 40h 이므로 배정되어야 함. warnings={result['warnings']}"
        )

    def test_over_limit_blocks(self, db):
        """
        [Test 2]
        CONFIRMED 35h + 새 슬롯 8h = 43h > max 40h → 배정 불가
        """
        store = _add_store(db)
        pt = _add_part_timer(db, name="파트B", max_hours=40.0)

        # 5 × 7h = 35h CONFIRMED (Oct 1-5: Thu/Fri/Sat/Sun/Mon)
        for day in [1, 2, 3, 4, 5]:
            _add_confirmed(db, pt.id, store.id, date(2026, 10, day), "09:00", "16:00")

        # Oct 7 (Wed) 09:00-17:00 = 8h
        _add_requirement(db, store.id, DayOfWeek.WED, "09:00", "17:00")
        db.commit()

        result = ScheduleEngine().generate(TEST_YEAR, TEST_MONTH, db)

        new = _get_draft(db, pt.id, date(2026, 10, 7))
        assert len(new) == 0, "43h > 40h 이므로 배정되어서는 안 됨"
        assert any("2026-10-07" in w for w in result['warnings']), (
            "배정 실패는 warnings에 기록되어야 함"
        )

    def test_exactly_at_limit_assigns(self, db):
        """
        경계값: CONFIRMED 32h + 새 슬롯 8h = 40h == max 40h → 배정 가능
        """
        store = _add_store(db)
        pt = _add_part_timer(db, name="파트C", max_hours=40.0)

        # 4 × 8h = 32h CONFIRMED (Oct 1-4)
        for day in [1, 2, 3, 4]:
            _add_confirmed(db, pt.id, store.id, date(2026, 10, day), "09:00", "17:00")

        # Oct 7 (Wed) 09:00-17:00 = 8h
        _add_requirement(db, store.id, DayOfWeek.WED, "09:00", "17:00")
        db.commit()

        result = ScheduleEngine().generate(TEST_YEAR, TEST_MONTH, db)

        new = _get_draft(db, pt.id, date(2026, 10, 7))
        assert len(new) == 1, (
            f"32+8=40h == max 40h 이므로 배정 가능해야 함. warnings={result['warnings']}"
        )

    def test_no_max_hours_always_assigns(self, db):
        """
        monthly_max_hours=None 이면 시간 제한 없이 배정 가능.
        주의: Oct 7(수)에는 CONFIRMED 스케줄을 넣지 않아야 함.
        Oct 7에 CONFIRMED가 있으면 covered=1 → needed=0 이 되어 DRAFT가 생성되지 않음.
        """
        store = _add_store(db)
        pt = _add_part_timer(db, name="파트D", max_hours=None)

        # Oct 7(수)을 제외한 날에 10 × 10h = 100h CONFIRMED
        non_wed_days = [1, 2, 3, 4, 5, 6, 8, 9, 10, 11]  # Thu~Sat 반복
        for day in non_wed_days:
            _add_confirmed(db, pt.id, store.id, date(2026, 10, day), "09:00", "19:00")

        _add_requirement(db, store.id, DayOfWeek.WED, "09:00", "17:00")
        db.commit()

        result = ScheduleEngine().generate(TEST_YEAR, TEST_MONTH, db)

        new = _get_draft(db, pt.id, date(2026, 10, 7))
        assert len(new) == 1, (
            f"max_hours 미설정이면 초과 여부 무관하게 배정되어야 함. warnings={result['warnings']}"
        )

    def test_locked_schedules_counted_in_pt_hours(self, db):
        """
        LOCKED 스케줄도 pt_hours에 반영되어야 함
        """
        store = _add_store(db)
        pt = _add_part_timer(db, name="파트E", max_hours=40.0)

        # 5 × 7h = 35h LOCKED (Oct 1-5)
        for day in [1, 2, 3, 4, 5]:
            _add_confirmed(
                db, pt.id, store.id, date(2026, 10, day),
                "09:00", "16:00", status=ScheduleStatus.LOCKED
            )

        # Oct 7 (Wed) 09:00-17:00 = 8h → 35+8=43 > 40 → 불가
        _add_requirement(db, store.id, DayOfWeek.WED, "09:00", "17:00")
        db.commit()

        result = ScheduleEngine().generate(TEST_YEAR, TEST_MONTH, db)

        new = _get_draft(db, pt.id, date(2026, 10, 7))
        assert len(new) == 0, "LOCKED 시간도 pt_hours에 반영되어 43h > 40h 이므로 불가"


# ═════════════════════════════════════════════════════════════════════
# 단위 테스트 — _is_available_cached 직접 호출
# ═════════════════════════════════════════════════════════════════════

_se = ScheduleEngine()

# 2026-10-05 = Monday
_MON_DATE = date(2026, 10, 5)
_MON_DOW = DayOfWeek.MON


def _make_pt(id_=1):
    p = SimpleNamespace()
    p.id = id_
    p.monthly_max_hours = None
    p.preferred_store_id = None
    return p


def _make_av(emp_id, dow, is_day_unavail=False, start=None, end=None):
    a = SimpleNamespace()
    a.employee_id = emp_id
    a.day_of_week = dow
    a.is_day_unavailable = is_day_unavail
    a.unavailable_start = start
    a.unavailable_end = end
    return a


def _make_exc(emp_id, exc_date, is_day_unavail=False, is_override=False,
              start=None, end=None):
    e = SimpleNamespace()
    e.employee_id = emp_id
    e.exception_date = exc_date
    e.is_day_unavailable = is_day_unavail
    e.is_available_override = is_override
    e.unavailable_start = start
    e.unavailable_end = end
    return e


class TestAvailabilityExceptionLogic:
    """수정 3: 특정 날짜 예외 처리 로직 버그 수정"""

    def test_empty_exception_does_not_skip_monthly_availability(self):
        """
        [Test 4]
        빈 예외 레코드(실질적 내용 없음)가 존재해도
        월별 요일 기본 설정(MON 종일 불가)이 정상 적용되어야 한다.
        """
        pt = _make_pt(1)
        av_map = {(1, _MON_DOW): _make_av(1, _MON_DOW, is_day_unavail=True)}
        # 빈 예외: is_available_override=False, is_day_unavailable=False, 시간 없음
        exc_map = {(1, _MON_DATE): _make_exc(1, _MON_DATE)}

        result = _se._is_available_cached(
            pt, _MON_DATE, _MON_DOW, "09:00", "18:00",
            av_map, exc_map, []
        )
        assert result is False, (
            "빈 예외 레코드는 월별 요일 불가능 설정을 무시해서는 안 됨"
        )

    def test_positive_override_beats_monthly_unavailability(self):
        """
        [Test 5]
        월별 MON 불가능 설정이 있어도,
        특정 날짜 '가능' 예외(is_available_override=True)가 있으면 배정 가능.
        """
        pt = _make_pt(1)
        av_map = {(1, _MON_DOW): _make_av(1, _MON_DOW, is_day_unavail=True)}
        exc_map = {(1, _MON_DATE): _make_exc(1, _MON_DATE, is_override=True)}

        result = _se._is_available_cached(
            pt, _MON_DATE, _MON_DOW, "09:00", "18:00",
            av_map, exc_map, []
        )
        assert result is True, "가능 예외는 요일 불가능 설정을 이겨야 함"

    def test_negative_exception_beats_monthly_availability(self):
        """
        [Test 6]
        월별 설정에 제한이 없어도,
        특정 날짜 종일 불가능 예외가 있으면 배정 불가.
        """
        pt = _make_pt(1)
        av_map = {}
        exc_map = {(1, _MON_DATE): _make_exc(1, _MON_DATE, is_day_unavail=True)}

        result = _se._is_available_cached(
            pt, _MON_DATE, _MON_DOW, "09:00", "18:00",
            av_map, exc_map, []
        )
        assert result is False, "불가능 예외는 기본 가능 설정을 이겨야 함"

    def test_no_exception_no_monthly_av_available(self):
        """
        예외도 없고 요일 제한도 없으면 가용 (기존 동작 유지)
        """
        pt = _make_pt(1)
        result = _se._is_available_cached(
            pt, _MON_DATE, _MON_DOW, "09:00", "18:00",
            {}, {}, []
        )
        assert result is True

    def test_time_overlap_exception_blocks_overlapping_slot(self):
        """
        불가능 예외의 시간 범위와 슬롯이 겹치면 배정 불가
        """
        pt = _make_pt(1)
        exc_map = {
            (1, _MON_DATE): _make_exc(
                1, _MON_DATE, start="13:00", end="18:00"
            )
        }
        # 슬롯 14:00-20:00 은 불가능 시간 13:00-18:00 과 겹침
        result = _se._is_available_cached(
            pt, _MON_DATE, _MON_DOW, "14:00", "20:00",
            {}, exc_map, []
        )
        assert result is False

    def test_time_overlap_exception_allows_non_overlapping_slot(self):
        """
        불가능 예외의 시간 범위와 슬롯이 겹치지 않으면 배정 가능
        (슬롯이 예외 시간 이전 또는 이후)
        """
        pt = _make_pt(1)
        exc_map = {
            (1, _MON_DATE): _make_exc(
                1, _MON_DATE, start="13:00", end="18:00"
            )
        }
        # 슬롯 09:00-13:00 은 불가능 시간 13:00-18:00 과 겹치지 않음
        result = _se._is_available_cached(
            pt, _MON_DATE, _MON_DOW, "09:00", "13:00",
            {}, exc_map, []
        )
        assert result is True

    def test_schedule_conflict_blocks_regardless_of_exception(self):
        """
        가능 예외가 있어도 기존 배정 스케줄과 시간이 겹치면 배정 불가
        """
        pt = _make_pt(1)
        exc_map = {(1, _MON_DATE): _make_exc(1, _MON_DATE, is_override=True)}

        existing = SimpleNamespace()
        existing.start_time = "10:00"
        existing.end_time = "15:00"
        existing.is_cancelled = False

        # 슬롯 12:00-18:00 은 기존 10:00-15:00 과 겹침
        result = _se._is_available_cached(
            pt, _MON_DATE, _MON_DOW, "12:00", "18:00",
            {}, exc_map, [existing]
        )
        assert result is False

    def test_positive_override_with_window_blocks_slot_outside_window(self):
        """
        '가능' 예외에 특정 시간 윈도우가 있을 때,
        슬롯이 해당 윈도우를 벗어나면 배정 불가
        """
        pt = _make_pt(1)
        # 가능 윈도우: 10:00-16:00 만 가능
        exc_map = {
            (1, _MON_DATE): _make_exc(
                1, _MON_DATE, is_override=True, start="10:00", end="16:00"
            )
        }
        av_map = {(1, _MON_DOW): _make_av(1, _MON_DOW, is_day_unavail=True)}

        # 슬롯 09:00-18:00 은 윈도우 10:00-16:00 밖
        result = _se._is_available_cached(
            pt, _MON_DATE, _MON_DOW, "09:00", "18:00",
            av_map, exc_map, []
        )
        assert result is False

    def test_positive_override_with_window_allows_slot_inside_window(self):
        """
        '가능' 예외에 특정 시간 윈도우가 있을 때,
        슬롯이 해당 윈도우 안에 완전히 포함되면 배정 가능
        """
        pt = _make_pt(1)
        exc_map = {
            (1, _MON_DATE): _make_exc(
                1, _MON_DATE, is_override=True, start="10:00", end="16:00"
            )
        }
        av_map = {(1, _MON_DOW): _make_av(1, _MON_DOW, is_day_unavail=True)}

        # 슬롯 10:00-16:00 은 윈도우 안
        result = _se._is_available_cached(
            pt, _MON_DATE, _MON_DOW, "10:00", "16:00",
            av_map, exc_map, []
        )
        assert result is True
