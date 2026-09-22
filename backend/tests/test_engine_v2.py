"""
스케줄 엔진 2차 개선 테스트 — 파트타이머 하루 1회 근무 제한

대상 수정사항:
  - 파트타이머 하루 최대 1개 스케줄 배정 정책 적용
  - CONFIRMED/LOCKED 기존 스케줄도 동일 날짜 차단에 반영
  - generate() 루프 내 신규 DRAFT도 실시간으로 차단

날짜 기준 (2026년 10월):
  Oct  1 = 목 / Oct  5 = 월 / Oct  6 = 화 / Oct  7 = 수
  Oct 14 = 수 / Oct 21 = 수 / Oct 28 = 수
"""

import pytest
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.database import Base
from app.models.models import (
    Employee, EmployeeType, Store, Schedule, ScheduleStatus,
    StaffRequirement, DayOfWeek,
)
from app.schedule_engine.engine import ScheduleEngine

TEST_YEAR = 2026
TEST_MONTH = 10

# Oct 7 = Wednesday, Oct 14 = Wednesday
OCT_7 = date(2026, 10, 7)
OCT_14 = date(2026, 10, 14)


# ── fixture ──────────────────────────────────────────────────────────

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

def _store(db, name="A매장") -> Store:
    s = Store(name=name, open_time="09:00", close_time="23:00")
    db.add(s)
    db.flush()
    return s


def _pt(db, name="파트", max_hours=None) -> Employee:
    e = Employee(
        name=name,
        employee_type=EmployeeType.PART_TIMER,
        hourly_wage=10000,
        monthly_max_hours=max_hours,
    )
    db.add(e)
    db.flush()
    return e


def _confirmed(db, emp_id, store_id, work_date, start, end,
               status=ScheduleStatus.CONFIRMED) -> Schedule:
    s = Schedule(
        employee_id=emp_id, store_id=store_id,
        work_date=work_date, start_time=start, end_time=end,
        break_minutes=0, status=status, is_cancelled=False,
    )
    db.add(s)
    db.flush()
    return s


def _req(db, store_id, dow, start, end, count=1):
    r = StaffRequirement(
        store_id=store_id,
        year=TEST_YEAR, month=TEST_MONTH,
        day_of_week=dow, start_time=start, end_time=end,
        required_count=count,
    )
    db.add(r)
    db.flush()
    return r


def _get_drafts(db, emp_id, work_date):
    return db.query(Schedule).filter(
        Schedule.employee_id == emp_id,
        Schedule.work_date == work_date,
        Schedule.is_cancelled == False,
        Schedule.status == ScheduleStatus.DRAFT,
    ).all()


# ═════════════════════════════════════════════════════════════════════
# Test 1 — 같은 매장, 같은 날, 겹치지 않는 두 슬롯
# ═════════════════════════════════════════════════════════════════════

class TestSameDaySingleStore:

    def test_one_pt_two_non_overlapping_slots_assigns_once(self, db):
        """
        [Test 1]
        같은 날 09:00-13:00 / 18:00-23:00 두 슬롯 모두 필요인원 1명.
        PT가 1명뿐 → 첫 슬롯(09-13)에만 배정, 두 번째 슬롯은 미배정 + warning.
        """
        store = _store(db)
        pt = _pt(db)
        _req(db, store.id, DayOfWeek.WED, "09:00", "13:00")
        _req(db, store.id, DayOfWeek.WED, "18:00", "23:00")
        db.commit()

        result = ScheduleEngine().generate(TEST_YEAR, TEST_MONTH, db)

        drafts = _get_drafts(db, pt.id, OCT_7)
        assert len(drafts) == 1, "하루 1회 제한: 1개 슬롯에만 배정되어야 함"
        assert drafts[0].start_time == "09:00", "먼저 처리되는 09-13 슬롯에 배정되어야 함"
        assert any("2026-10-07" in w for w in result["warnings"]), \
            "두 번째 슬롯 미배정은 warnings에 기록되어야 함"

    def test_two_pts_two_slots_each_gets_one(self, db):
        """
        PT 2명 + 슬롯 2개(겹치지 않음, 각 필요 1명) → 각 PT가 하나씩 배정
        """
        store = _store(db)
        pt_a = _pt(db, "A")
        pt_b = _pt(db, "B")
        _req(db, store.id, DayOfWeek.WED, "09:00", "13:00")
        _req(db, store.id, DayOfWeek.WED, "18:00", "23:00")
        db.commit()

        result = ScheduleEngine().generate(TEST_YEAR, TEST_MONTH, db)

        drafts_a = _get_drafts(db, pt_a.id, OCT_7)
        drafts_b = _get_drafts(db, pt_b.id, OCT_7)
        total = len(drafts_a) + len(drafts_b)
        assert total == 2, "PT 2명이 슬롯 2개를 하나씩 나눠 가져야 함"
        assert len(drafts_a) <= 1 and len(drafts_b) <= 1, \
            "각 PT는 하루에 최대 1개 슬롯만 가져야 함"
        assert not result["warnings"], f"2명이면 2슬롯 모두 충족. warnings={result['warnings']}"


# ═════════════════════════════════════════════════════════════════════
# Test 2 — 다른 매장, 같은 날
# ═════════════════════════════════════════════════════════════════════

class TestSameDayDifferentStores:

    def test_one_pt_two_stores_same_day_assigns_once(self, db):
        """
        [Test 2]
        매장 1: WED 09:00-13:00 (1명 필요)
        매장 2: WED 18:00-23:00 (1명 필요)
        PT 1명 → 시간이 겹치지 않아도 다른 날 아닌 이상 두 매장 모두 배정 불가.
        PT는 먼저 처리되는 매장 1에만 배정, 매장 2는 warning.
        """
        store1 = _store(db, "A매장")
        store2 = _store(db, "B매장")
        pt = _pt(db)
        _req(db, store1.id, DayOfWeek.WED, "09:00", "13:00")
        _req(db, store2.id, DayOfWeek.WED, "18:00", "23:00")
        db.commit()

        result = ScheduleEngine().generate(TEST_YEAR, TEST_MONTH, db)

        all_drafts_oct7 = db.query(Schedule).filter(
            Schedule.employee_id == pt.id,
            Schedule.work_date == OCT_7,
            Schedule.is_cancelled == False,
            Schedule.status == ScheduleStatus.DRAFT,
        ).all()
        assert len(all_drafts_oct7) == 1, "두 매장을 합쳐도 하루 1개 슬롯에만 배정"
        assert any("2026-10-07" in w for w in result["warnings"]), \
            "두 번째 매장 미배정은 warnings에 기록"

    def test_two_pts_two_stores_each_assigned(self, db):
        """
        매장 1 + 매장 2, 각 필요 1명, PT 2명 → 각 매장에 하나씩 배정 (warning 없음)
        """
        store1 = _store(db, "A매장")
        store2 = _store(db, "B매장")
        pt_a = _pt(db, "A")
        pt_b = _pt(db, "B")
        _req(db, store1.id, DayOfWeek.WED, "09:00", "13:00")
        _req(db, store2.id, DayOfWeek.WED, "18:00", "23:00")
        db.commit()

        result = ScheduleEngine().generate(TEST_YEAR, TEST_MONTH, db)

        total_oct7 = db.query(Schedule).filter(
            Schedule.work_date == OCT_7,
            Schedule.is_cancelled == False,
            Schedule.status == ScheduleStatus.DRAFT,
        ).count()
        assert total_oct7 == 2
        assert not result["warnings"]


# ═════════════════════════════════════════════════════════════════════
# Test 3 — 기존 CONFIRMED가 같은 날 자동배정 차단
# ═════════════════════════════════════════════════════════════════════

class TestConfirmedBlocksSameDay:

    def test_confirmed_morning_blocks_evening_auto(self, db):
        """
        [Test 3]
        PT_A: Oct 7 CONFIRMED 09:00-13:00 존재
        자동생성: Oct 7 WED 18:00-23:00 (1명 필요)
        → PT_A는 후보에서 제외, 미배정 + warning
        """
        store = _store(db)
        pt = _pt(db)
        _confirmed(db, pt.id, store.id, OCT_7, "09:00", "13:00")
        _req(db, store.id, DayOfWeek.WED, "18:00", "23:00")
        db.commit()

        result = ScheduleEngine().generate(TEST_YEAR, TEST_MONTH, db)

        # CONFIRMED는 보호되어야 함
        conf = db.query(Schedule).filter(
            Schedule.employee_id == pt.id,
            Schedule.work_date == OCT_7,
            Schedule.status == ScheduleStatus.CONFIRMED,
            Schedule.is_cancelled == False,
        ).first()
        assert conf is not None, "CONFIRMED 스케줄이 삭제되어서는 안 됨"

        # 새 DRAFT는 생성되어서는 안 됨
        new_drafts = _get_drafts(db, pt.id, OCT_7)
        assert len(new_drafts) == 0, "CONFIRMED가 있는 날은 DRAFT 추가 배정 불가"
        assert any("2026-10-07" in w for w in result["warnings"])

    def test_locked_morning_blocks_evening_auto(self, db):
        """
        LOCKED 스케줄도 동일하게 같은 날 자동배정을 차단해야 함
        """
        store = _store(db)
        pt = _pt(db)
        _confirmed(db, pt.id, store.id, OCT_7, "09:00", "13:00",
                   status=ScheduleStatus.LOCKED)
        _req(db, store.id, DayOfWeek.WED, "18:00", "23:00")
        db.commit()

        result = ScheduleEngine().generate(TEST_YEAR, TEST_MONTH, db)

        new_drafts = _get_drafts(db, pt.id, OCT_7)
        assert len(new_drafts) == 0, "LOCKED가 있는 날도 DRAFT 추가 배정 불가"
        assert any("2026-10-07" in w for w in result["warnings"])


# ═════════════════════════════════════════════════════════════════════
# Test 4 — generate() 루프 내 신규 DRAFT가 실시간으로 차단
# ═════════════════════════════════════════════════════════════════════

class TestIntraLoopBlocking:

    def test_first_slot_draft_blocks_second_slot_in_same_run(self, db):
        """
        [Test 4]
        같은 generate() 호출 내에서:
        1. 09:00-13:00 슬롯 → PT 배정 → _pt_assigned_days 에 Oct 7 추가
        2. 18:00-23:00 슬롯 → PT 이미 Oct 7에 배정됨 → 후보 제외
        """
        store = _store(db)
        pt = _pt(db)
        # 두 슬롯 모두 등록
        _req(db, store.id, DayOfWeek.WED, "09:00", "13:00")
        _req(db, store.id, DayOfWeek.WED, "18:00", "23:00")
        db.commit()

        ScheduleEngine().generate(TEST_YEAR, TEST_MONTH, db)

        oct7_drafts = _get_drafts(db, pt.id, OCT_7)
        assert len(oct7_drafts) == 1, \
            "generate() 루프 내 첫 배정이 두 번째 슬롯을 차단해야 함"

    def test_three_non_overlapping_slots_one_pt(self, db):
        """
        슬롯 3개(09-13, 14-18, 19-23), PT 1명 → 1개 슬롯만 배정
        """
        store = _store(db)
        pt = _pt(db)
        _req(db, store.id, DayOfWeek.WED, "09:00", "13:00")
        _req(db, store.id, DayOfWeek.WED, "14:00", "18:00")
        _req(db, store.id, DayOfWeek.WED, "19:00", "23:00")
        db.commit()

        result = ScheduleEngine().generate(TEST_YEAR, TEST_MONTH, db)

        oct7_drafts = _get_drafts(db, pt.id, OCT_7)
        assert len(oct7_drafts) == 1, "슬롯 3개 있어도 하루 1회만 배정"
        # 나머지 2개는 warning
        oct7_warnings = [w for w in result["warnings"] if "2026-10-07" in w]
        assert len(oct7_warnings) == 2, "미배정 2개 슬롯 warning 2개여야 함"


# ═════════════════════════════════════════════════════════════════════
# Test 5 — 다른 날짜에는 정상 배정
# ═════════════════════════════════════════════════════════════════════

class TestDifferentDateAllowed:

    def test_different_wednesday_each_gets_assigned(self, db):
        """
        [Test 5]
        PT가 Oct 7(수)에 배정되어도 Oct 14(수)에는 정상 배정 가능.
        """
        store = _store(db)
        pt = _pt(db)
        # WED 09:00-13:00 → Oct 7, 14, 21, 28 모두 해당
        _req(db, store.id, DayOfWeek.WED, "09:00", "13:00")
        db.commit()

        ScheduleEngine().generate(TEST_YEAR, TEST_MONTH, db)

        # Oct 2026의 수요일: 7, 14, 21, 28 → 각각 1개씩 총 4개
        all_wed_drafts = db.query(Schedule).filter(
            Schedule.employee_id == pt.id,
            Schedule.is_cancelled == False,
            Schedule.status == ScheduleStatus.DRAFT,
        ).all()
        assert len(all_wed_drafts) == 4, "매 주 수요일마다 각각 1개씩 4개 배정"

    def test_confirmed_one_date_does_not_block_other_dates(self, db):
        """
        Oct 7 CONFIRMED가 있어도 Oct 14는 정상 배정
        """
        store = _store(db)
        pt = _pt(db)
        _confirmed(db, pt.id, store.id, OCT_7, "09:00", "13:00")
        _req(db, store.id, DayOfWeek.WED, "09:00", "13:00")
        db.commit()

        ScheduleEngine().generate(TEST_YEAR, TEST_MONTH, db)

        oct14_drafts = _get_drafts(db, pt.id, OCT_14)
        assert len(oct14_drafts) == 1, "Oct 14는 Oct 7 CONFIRMED와 무관하게 배정 가능"

        oct7_drafts = _get_drafts(db, pt.id, OCT_7)
        assert len(oct7_drafts) == 0, "Oct 7은 CONFIRMED가 있으므로 DRAFT 없음"


# ═════════════════════════════════════════════════════════════════════
# 기존 기능 regression 검증
# ═════════════════════════════════════════════════════════════════════

class TestRegressionExistingFeatures:

    def test_confirmed_not_deleted(self, db):
        """CONFIRMED 스케줄은 generate() 후에도 보호"""
        store = _store(db)
        pt = _pt(db)
        conf = _confirmed(db, pt.id, store.id, OCT_7, "09:00", "18:00")
        db.commit()

        ScheduleEngine().generate(TEST_YEAR, TEST_MONTH, db)

        still_there = db.query(Schedule).filter(
            Schedule.id == conf.id,
            Schedule.is_cancelled == False,
            Schedule.status == ScheduleStatus.CONFIRMED,
        ).first()
        assert still_there is not None

    def test_time_overlap_still_blocked(self, db):
        """시간 겹침 중복 방지는 여전히 동작"""
        store = _store(db)
        pt = _pt(db)
        # WED 09:00-18:00 overlaps with 15:00-23:00
        _req(db, store.id, DayOfWeek.WED, "09:00", "18:00", count=1)
        _req(db, store.id, DayOfWeek.WED, "15:00", "23:00", count=1)
        db.commit()

        ScheduleEngine().generate(TEST_YEAR, TEST_MONTH, db)

        oct7_drafts = _get_drafts(db, pt.id, OCT_7)
        # 겹치는 슬롯이므로 하루 1회 + 시간 겹침 모두 막힘 → 1개만
        assert len(oct7_drafts) == 1

    def test_max_hours_still_enforced(self, db):
        """monthly_max_hours 제한은 동일하게 작동"""
        store = _store(db)
        pt = _pt(db, max_hours=40.0)
        # 5 × 7h = 35h CONFIRMED
        for day in [1, 2, 3, 4, 5]:
            _confirmed(db, pt.id, store.id, date(2026, 10, day), "09:00", "16:00")
        _req(db, store.id, DayOfWeek.WED, "09:00", "17:00")  # 8h → 43h 초과
        db.commit()

        result = ScheduleEngine().generate(TEST_YEAR, TEST_MONTH, db)

        oct7_drafts = _get_drafts(db, pt.id, OCT_7)
        assert len(oct7_drafts) == 0, "35+8=43 > 40 이므로 배정 불가"
        assert any("2026-10-07" in w for w in result["warnings"])

    def test_required_count_filled_with_multiple_pts(self, db):
        """필요인원 2명 슬롯에 PT 3명 → 2명만 배정"""
        store = _store(db)
        pts = [_pt(db, f"파트{i}") for i in range(3)]
        _req(db, store.id, DayOfWeek.WED, "09:00", "18:00", count=2)
        db.commit()

        ScheduleEngine().generate(TEST_YEAR, TEST_MONTH, db)

        oct7_drafts = db.query(Schedule).filter(
            Schedule.work_date == OCT_7,
            Schedule.is_cancelled == False,
            Schedule.status == ScheduleStatus.DRAFT,
        ).all()
        assert len(oct7_drafts) == 2, "필요인원 2명에 맞게 2명만 배정"

    def test_draft_reset_on_regenerate(self, db):
        """generate() 재실행 시 기존 DRAFT 초기화 후 재생성"""
        store = _store(db)
        pt = _pt(db)
        _req(db, store.id, DayOfWeek.WED, "09:00", "18:00")
        db.commit()

        eng = ScheduleEngine()
        eng.generate(TEST_YEAR, TEST_MONTH, db)
        eng.generate(TEST_YEAR, TEST_MONTH, db)

        all_drafts = db.query(Schedule).filter(
            Schedule.work_date == OCT_7,
            Schedule.is_cancelled == False,
            Schedule.status == ScheduleStatus.DRAFT,
        ).all()
        assert len(all_drafts) == 1, "재생성 후에도 중복 DRAFT 없이 1개만 존재"
