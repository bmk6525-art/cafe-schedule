"""
스케줄 엔진 4차 개선 테스트 — 가능/불가능 병행 가용성 체계

핵심 검증:
  1. 가능 시간 범위 내 슬롯 → 배정 가능
  2. 가능 시간 범위 밖 슬롯 → 배정 불가
  3. 가능+불가능 겹침 → 불가능 우선
  4. 가능 요일 설정 시 미설정 요일 → 불가능
  5. 불가능 요일(종일) → 배정 불가
  6. 날짜 예외(가능)가 기본 불가능 요일 override
  7. 날짜 예외(불가능)가 기본 가능 요일 override
  8. 특정 날짜 불가능 + 시간 미입력 → 종일 불가능
  9. 가능+불가능 시간 겹침 → 불가능 우선 (단위 테스트)
  10. 희소 슬롯 candidate_count에 가능/불가능 설정이 반영되는지 확인

날짜 기준: 2026-10-12 = Monday, 2026-10-07 = Wednesday
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
    StaffRequirement, MonthlyAvailability, AvailabilityException, DayOfWeek,
)
from app.schedule_engine.engine import ScheduleEngine

TEST_YEAR = 2026
TEST_MONTH = 10
OCT_12 = date(2026, 10, 12)  # Monday
OCT_07 = date(2026, 10, 7)   # Wednesday
OCT_14 = date(2026, 10, 14)  # Wednesday

_se = ScheduleEngine()


# ── DB fixture ────────────────────────────────────────────────────────

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


# ── 공통 헬퍼 ─────────────────────────────────────────────────────────

def _store(db, name="A매장") -> Store:
    s = Store(name=name, open_time="09:00", close_time="23:00")
    db.add(s)
    db.flush()
    return s


def _pt(db, name, max_hours=None) -> Employee:
    e = Employee(
        name=name, employee_type=EmployeeType.PART_TIMER,
        hourly_wage=10000, monthly_max_hours=max_hours,
    )
    db.add(e)
    db.flush()
    return e


def _req(db, store_id, dow, start, end, count=1):
    r = StaffRequirement(
        store_id=store_id, year=TEST_YEAR, month=TEST_MONTH,
        day_of_week=dow, start_time=start, end_time=end, required_count=count,
    )
    db.add(r)
    db.flush()
    return r


def _available(db, emp_id, dow, avail_start=None, avail_end=None, is_working_day=True):
    """AVAILABLE 레코드 등록"""
    a = MonthlyAvailability(
        employee_id=emp_id,
        year=TEST_YEAR, month=TEST_MONTH,
        day_of_week=dow,
        entry_type='AVAILABLE',
        is_working_day=is_working_day,
        available_start=avail_start,
        available_end=avail_end,
        is_day_unavailable=False,
        unavailable_start=None,
        unavailable_end=None,
    )
    db.add(a)
    db.flush()
    return a


def _unavailable(db, emp_id, dow, start=None, end=None, day_off=False):
    """UNAVAILABLE 레코드 등록"""
    a = MonthlyAvailability(
        employee_id=emp_id,
        year=TEST_YEAR, month=TEST_MONTH,
        day_of_week=dow,
        entry_type='UNAVAILABLE',
        is_working_day=False,
        available_start=None,
        available_end=None,
        is_day_unavailable=day_off,
        unavailable_start=start,
        unavailable_end=end,
    )
    db.add(a)
    db.flush()
    return a


def _exception(db, emp_id, exc_date, is_override=False,
               is_day_unavail=False, start=None, end=None):
    e = AvailabilityException(
        employee_id=emp_id,
        exception_date=exc_date,
        is_available_override=is_override,
        is_day_unavailable=is_day_unavail,
        unavailable_start=start,
        unavailable_end=end,
    )
    db.add(e)
    db.flush()
    return e


def _get_drafts(db, work_date=None, emp_id=None):
    q = db.query(Schedule).filter(Schedule.is_cancelled == False,
                                   Schedule.status == ScheduleStatus.DRAFT)
    if work_date:
        q = q.filter(Schedule.work_date == work_date)
    if emp_id:
        q = q.filter(Schedule.employee_id == emp_id)
    return q.all()


# ── 단위 테스트 헬퍼 (SimpleNamespace 기반) ────────────────────────────

def _make_pt(id_=1):
    p = SimpleNamespace()
    p.id = id_
    p.monthly_max_hours = None
    p.preferred_store_id = None
    return p


def _av_entry(avail_start=None, avail_end=None, is_working_day=True,
              unavail_start=None, unavail_end=None, day_off=False):
    """av_map 엔트리 생성 헬퍼"""
    av = None
    if is_working_day or avail_start:
        av = SimpleNamespace(
            is_working_day=is_working_day,
            available_start=avail_start,
            available_end=avail_end,
            entry_type='AVAILABLE',
        )
    unav = None
    if day_off or unavail_start:
        unav = SimpleNamespace(
            is_day_unavailable=day_off,
            unavailable_start=unavail_start,
            unavailable_end=unavail_end,
            entry_type='UNAVAILABLE',
        )
    return {'AVAILABLE': av, 'UNAVAILABLE': unav}


# ═══════════════════════════════════════════════════════════════════════
# Test 1 — 가능 시간 범위 내 슬롯 → 배정 가능
# ═══════════════════════════════════════════════════════════════════════

class TestAvailableTimeRange:

    def test_slot_inside_available_window_is_allowed(self):
        """가능: 월 09~18 → 월 10~14 배정 가능"""
        pt = _make_pt(1)
        av_map = {(1, DayOfWeek.MON): _av_entry(avail_start='09:00', avail_end='18:00')}
        result = _se._is_available_cached(
            pt, OCT_12, DayOfWeek.MON, '10:00', '14:00',
            av_map, {}, [], frozenset([1])
        )
        assert result is True, "가능 시간 범위 내 슬롯은 배정 가능해야 함"

    def test_slot_outside_available_window_is_blocked(self):
        """가능: 월 09~18 → 월 18~23 배정 불가 (Test 2)"""
        pt = _make_pt(1)
        av_map = {(1, DayOfWeek.MON): _av_entry(avail_start='09:00', avail_end='18:00')}
        result = _se._is_available_cached(
            pt, OCT_12, DayOfWeek.MON, '18:00', '23:00',
            av_map, {}, [], frozenset([1])
        )
        assert result is False, "가능 시간 범위 밖 슬롯은 배정 불가해야 함"

    def test_slot_partially_outside_available_window_is_blocked(self):
        """가능: 월 09~18 → 월 17~20 배정 불가 (가능 범위 부분 초과)"""
        pt = _make_pt(1)
        av_map = {(1, DayOfWeek.MON): _av_entry(avail_start='09:00', avail_end='18:00')}
        result = _se._is_available_cached(
            pt, OCT_12, DayOfWeek.MON, '17:00', '20:00',
            av_map, {}, [], frozenset([1])
        )
        assert result is False, "가능 시간을 초과하는 슬롯은 배정 불가해야 함"


# ═══════════════════════════════════════════════════════════════════════
# Test 3 — 가능+불가능 겹침 → 불가능 우선
# ═══════════════════════════════════════════════════════════════════════

class TestAvailableUnavailableConflict:

    def test_unavailable_within_available_blocks_slot(self):
        """가능 09~18 / 불가능 13~15 → 13~15 슬롯 배정 불가 (Test 9)"""
        pt = _make_pt(1)
        av_map = {(1, DayOfWeek.MON): _av_entry(
            avail_start='09:00', avail_end='18:00',
            unavail_start='13:00', unavail_end='15:00',
        )}
        result = _se._is_available_cached(
            pt, OCT_12, DayOfWeek.MON, '13:00', '15:00',
            av_map, {}, [], frozenset([1])
        )
        assert result is False, "불가능 시간이 가능 시간보다 우선해야 함"

    def test_slot_before_unavailable_within_available_is_ok(self):
        """가능 09~18 / 불가능 13~15 → 10~12 슬롯 배정 가능"""
        pt = _make_pt(1)
        av_map = {(1, DayOfWeek.MON): _av_entry(
            avail_start='09:00', avail_end='18:00',
            unavail_start='13:00', unavail_end='15:00',
        )}
        result = _se._is_available_cached(
            pt, OCT_12, DayOfWeek.MON, '10:00', '12:00',
            av_map, {}, [], frozenset([1])
        )
        assert result is True, "가능 시간 내 불가능 시간과 겹치지 않는 슬롯은 가능해야 함"

    def test_slot_after_unavailable_within_available_is_ok(self):
        """가능 09~18 / 불가능 13~15 → 15~18 슬롯 배정 가능"""
        pt = _make_pt(1)
        av_map = {(1, DayOfWeek.MON): _av_entry(
            avail_start='09:00', avail_end='18:00',
            unavail_start='13:00', unavail_end='15:00',
        )}
        result = _se._is_available_cached(
            pt, OCT_12, DayOfWeek.MON, '15:00', '18:00',
            av_map, {}, [], frozenset([1])
        )
        assert result is True, "불가능 시간 이후 가능 시간 내 슬롯은 가능해야 함"


# ═══════════════════════════════════════════════════════════════════════
# Test 4 — 가능 요일 설정 시 미설정 요일 → 불가능
# ═══════════════════════════════════════════════════════════════════════

class TestWorkingDayRestriction:

    def test_unset_day_blocked_when_pt_has_available_records(self):
        """가능 요일: 월/화만 설정 → 수요일(OCT_07) 배정 불가 (Test 4)"""
        pt = _make_pt(1)
        # MON, TUE AVAILABLE 레코드만 있음
        av_map = {
            (1, DayOfWeek.MON): _av_entry(is_working_day=True),
            (1, DayOfWeek.TUE): _av_entry(is_working_day=True),
        }
        # WED에는 AVAILABLE 레코드 없음 → pt_has_available에 포함된 직원 → 불가능
        result = _se._is_available_cached(
            pt, OCT_07, DayOfWeek.WED, '09:00', '18:00',
            av_map, {}, [], frozenset([1])
        )
        assert result is False, "가능 요일 외 요일은 배정 불가해야 함"

    def test_set_day_allowed_when_pt_has_available_records(self):
        """가능 요일: 월만 설정 → 월요일(OCT_12) 배정 가능"""
        pt = _make_pt(1)
        av_map = {(1, DayOfWeek.MON): _av_entry(is_working_day=True)}
        result = _se._is_available_cached(
            pt, OCT_12, DayOfWeek.MON, '09:00', '18:00',
            av_map, {}, [], frozenset([1])
        )
        assert result is True, "가능 요일로 설정된 요일은 배정 가능해야 함"

    def test_no_available_records_defaults_to_available(self):
        """AVAILABLE 레코드 없으면 기존처럼 기본 가능 (하위 호환)"""
        pt = _make_pt(1)
        # pt_has_available이 비어있으면 기존 동작 유지
        result = _se._is_available_cached(
            pt, OCT_07, DayOfWeek.WED, '09:00', '18:00',
            {}, {}, [], frozenset()
        )
        assert result is True, "AVAILABLE 레코드 없는 직원은 기존처럼 기본 가능이어야 함"


# ═══════════════════════════════════════════════════════════════════════
# Test 5 — 불가능 요일(종일) 설정 → 배정 불가
# ═══════════════════════════════════════════════════════════════════════

class TestUnavailableDay:

    def test_day_off_blocks_all_slots(self):
        """불가능 요일: 토요일 → 토요일 배정 불가 (Test 5)"""
        pt = _make_pt(1)
        # 2026-10-10 = Saturday
        oct_10 = date(2026, 10, 10)
        av_map = {(1, DayOfWeek.SAT): _av_entry(
            is_working_day=False, avail_start=None, avail_end=None,
            day_off=True,
        )}
        result = _se._is_available_cached(
            pt, oct_10, DayOfWeek.SAT, '09:00', '18:00',
            av_map, {}, [], frozenset()
        )
        assert result is False, "종일 불가능 요일은 모든 슬롯에서 배정 불가해야 함"


# ═══════════════════════════════════════════════════════════════════════
# Test 6 — 날짜 예외(가능)가 기본 불가능 요일 override
# ═══════════════════════════════════════════════════════════════════════

class TestExceptionOverrideAvailability:

    def test_positive_exception_overrides_unavailable_day(self, db):
        """
        월요일 기본 불가능 / 특정 날짜 2026-10-12 가능 → 10월 12일 배정 가능 (Test 6)
        """
        st = _store(db)
        pt = _pt(db, 'PT_A')
        _req(db, st.id, DayOfWeek.MON, '09:00', '18:00', count=1)
        # MON 종일 불가능
        _unavailable(db, pt.id, DayOfWeek.MON, day_off=True)
        # 2026-10-12(MON) 가능 예외
        _exception(db, pt.id, OCT_12, is_override=True)

        result = ScheduleEngine().generate(TEST_YEAR, TEST_MONTH, db)
        oct12_drafts = _get_drafts(db, work_date=OCT_12, emp_id=pt.id)
        assert len(oct12_drafts) >= 1, "가능 예외는 불가능 요일 설정을 override 해야 함"

    def test_negative_exception_overrides_available_day(self, db):
        """
        월요일 기본 가능 / 특정 날짜 2026-10-12 불가능 → 10월 12일 배정 불가 (Test 7)
        """
        st = _store(db)
        pt = _pt(db, 'PT_A')
        _req(db, st.id, DayOfWeek.MON, '09:00', '18:00', count=1)
        # MON 가능 (기본)
        _available(db, pt.id, DayOfWeek.MON, is_working_day=True)
        # 2026-10-12(MON) 불가능 예외
        _exception(db, pt.id, OCT_12, is_override=False, is_day_unavail=True)

        result = ScheduleEngine().generate(TEST_YEAR, TEST_MONTH, db)
        oct12_drafts = _get_drafts(db, work_date=OCT_12, emp_id=pt.id)
        assert len(oct12_drafts) == 0, "불가능 예외는 가능 요일 설정을 override 해야 함"


# ═══════════════════════════════════════════════════════════════════════
# Test 8 — 특정 날짜 불가능 + 시간 미입력 → 종일 불가능
# ═══════════════════════════════════════════════════════════════════════

class TestAllDayUnavailableException:

    def test_date_exception_no_time_blocks_all_day(self, db):
        """특정 날짜 불가능 + 시간 미입력 → 해당 날짜 종일 불가능 (Test 8)"""
        st = _store(db)
        pt = _pt(db, 'PT_A')
        # MON 오전/오후 두 슬롯
        _req(db, st.id, DayOfWeek.MON, '09:00', '13:00', count=1)
        _req(db, st.id, DayOfWeek.MON, '14:00', '18:00', count=1)
        # 2026-10-12(MON) 종일 불가능 (시간 없음)
        _exception(db, pt.id, OCT_12, is_override=False, is_day_unavail=True)

        result = ScheduleEngine().generate(TEST_YEAR, TEST_MONTH, db)
        oct12_drafts = _get_drafts(db, work_date=OCT_12, emp_id=pt.id)
        assert len(oct12_drafts) == 0, "종일 불가능 예외 시 모든 슬롯이 배정 불가해야 함"


# ═══════════════════════════════════════════════════════════════════════
# Test 10 — 희소 슬롯 candidate_count 반영 확인
# ═══════════════════════════════════════════════════════════════════════

class TestScarcityWithAvailability:

    def test_candidate_count_reflects_available_time_range(self, db):
        """
        희소 슬롯 candidate_count가 새 가능/불가능 설정을 반영하는지 확인 (Test 10)

        설정:
          슬롯A: 09~13 (PT_A, PT_B 모두 가능)
          슬롯B: 18~23 (PT_A만 가능, PT_B는 가능 시간 09~18이라 불가)

        기대:
          슬롯B(후보1)가 먼저 처리 → PT_A가 18~23에 배정
          슬롯A(후보2) → PT_B만 가능 → PT_B가 09~13에 배정
          두 슬롯 모두 충족
        """
        st = _store(db)
        pt_a = _pt(db, 'PT_A')
        pt_b = _pt(db, 'PT_B')

        _req(db, st.id, DayOfWeek.WED, '09:00', '13:00', count=1)
        _req(db, st.id, DayOfWeek.WED, '18:00', '23:00', count=1)

        # PT_A: 가능 시간 미설정 (기본 가능, 제한 없음)
        # PT_B: 가능 시간 09:00~18:00 만 설정
        _available(db, pt_b.id, DayOfWeek.WED,
                   avail_start='09:00', avail_end='18:00')

        result = ScheduleEngine().generate(TEST_YEAR, TEST_MONTH, db)

        # 2026-10에는 수요일이 4번(7,14,21,28). 각 날짜의 두 슬롯 모두 충족 여부 확인
        oct7_drafts = _get_drafts(db, work_date=OCT_07)
        slot_morning = [s for s in oct7_drafts if s.start_time == '09:00']
        slot_evening = [s for s in oct7_drafts if s.start_time == '18:00']

        assert len(slot_morning) == 1, "09~13 슬롯 충족"
        assert len(slot_evening) == 1, "18~23 슬롯 충족"

        # PT_B는 18~23에 배정되지 않아야 함 (가능 시간 초과)
        pt_b_evening = [s for s in slot_evening if s.employee_id == pt_b.id]
        assert len(pt_b_evening) == 0, "PT_B는 가능 시간(09~18) 밖인 18~23에 배정되면 안 됨"

        # PT_A는 18~23에 배정되어야 함 (희소 슬롯 우선)
        pt_a_evening = [s for s in slot_evening if s.employee_id == pt_a.id]
        assert len(pt_a_evening) == 1, "PT_A가 희소 슬롯(18~23)에 배정되어야 함"


# ═══════════════════════════════════════════════════════════════════════
# 통합 테스트 — 가능 시간 설정이 엔진에서 정확히 적용되는지
# ═══════════════════════════════════════════════════════════════════════

class TestIntegrationWithEngine:

    def test_available_time_blocks_out_of_range_slot_in_engine(self, db):
        """엔진: 가능 시간 09~18 설정 → 18~23 슬롯 배정 안 됨"""
        st = _store(db)
        pt = _pt(db, 'PT_A')
        _req(db, st.id, DayOfWeek.WED, '18:00', '23:00', count=1)
        # 가능 시간 09~18
        _available(db, pt.id, DayOfWeek.WED,
                   avail_start='09:00', avail_end='18:00')

        result = ScheduleEngine().generate(TEST_YEAR, TEST_MONTH, db)
        oct7_drafts = _get_drafts(db, work_date=OCT_07, emp_id=pt.id)
        assert len(oct7_drafts) == 0, "가능 시간 밖 슬롯은 배정되면 안 됨"
        # 경고 발생 확인
        assert any('18:00' in w for w in result['warnings']), "미충족 슬롯 경고가 있어야 함"

    def test_working_day_setting_blocks_other_days(self, db):
        """엔진: 가능 요일 수요일만 설정 → 월요일 배정 안 됨"""
        st = _store(db)
        pt = _pt(db, 'PT_A')
        _req(db, st.id, DayOfWeek.MON, '09:00', '18:00', count=1)
        _req(db, st.id, DayOfWeek.WED, '09:00', '18:00', count=1)
        # 수요일만 가능 요일로 설정
        _available(db, pt.id, DayOfWeek.WED, is_working_day=True)

        result = ScheduleEngine().generate(TEST_YEAR, TEST_MONTH, db)
        oct12_drafts = _get_drafts(db, work_date=OCT_12, emp_id=pt.id)  # MON
        oct7_drafts = _get_drafts(db, work_date=OCT_07, emp_id=pt.id)   # WED

        assert len(oct12_drafts) == 0, "가능 요일이 아닌 월요일에는 배정되면 안 됨"
        assert len(oct7_drafts) == 1, "가능 요일인 수요일에는 배정되어야 함"

    def test_backward_compat_no_available_record_defaults_available(self, db):
        """하위 호환: AVAILABLE 레코드 없는 직원은 기존처럼 불가능 시간 외 전부 가능"""
        st = _store(db)
        pt = _pt(db, 'PT_A')
        _req(db, st.id, DayOfWeek.MON, '09:00', '18:00', count=1)
        # AVAILABLE 레코드 없음, UNAVAILABLE도 없음 → 모든 요일 가능
        # (기존 동작 유지)

        result = ScheduleEngine().generate(TEST_YEAR, TEST_MONTH, db)
        oct12_drafts = _get_drafts(db, work_date=OCT_12, emp_id=pt.id)
        assert len(oct12_drafts) == 1, "AVAILABLE 레코드 없으면 기존처럼 배정되어야 함"
