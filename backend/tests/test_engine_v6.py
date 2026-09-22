"""
스케줄 엔진 6차 테스트 — WorkBlock v1 정확성 검증

핵심 검증:
  - 동일 count 인접 슬롯 병합 → PT 근무시간 = 병합 범위
  - 다른 count 인접 슬롯 → 별도 WorkBlock → PT 근무시간 = 실제 필요한 슬롯만
  - required_count에서 기존 coverage(정규직 포함) 차감 후 필요 PT 수 결정
  - 인원 부족 시 경고
  - required_count 충족 시 초과 배정 없음
  - 하루 1회 제한

날짜 기준: 2026-10-07 = Wednesday
"""

import pytest
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.database import Base
from app.models.models import (
    Employee, EmployeeType, Store, Schedule, ScheduleStatus,
    StaffRequirement, DayOfWeek, EmployeeWorkPattern,
)
from app.schedule_engine.engine import ScheduleEngine

TEST_YEAR = 2026
TEST_MONTH = 10
OCT_7 = date(2026, 10, 7)


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


def _store(db, name="테스트매장") -> Store:
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


def _regular(db, store_id, name="정규직", dow=DayOfWeek.WED,
             start="09:00", end="18:00") -> Employee:
    e = Employee(
        name=name, employee_type=EmployeeType.REGULAR,
        hourly_wage=15000,
    )
    db.add(e)
    db.flush()
    p = EmployeeWorkPattern(
        employee_id=e.id, day_of_week=dow,
        is_day_off=False, store_id=store_id,
        start_time=start, end_time=end,
    )
    db.add(p)
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


def _get_drafts(db, work_date=None):
    q = db.query(Schedule).filter(
        Schedule.is_cancelled == False,
        Schedule.status == ScheduleStatus.DRAFT,
    )
    if work_date:
        q = q.filter(Schedule.work_date == work_date)
    return q.all()


def _pt_drafts(db, pt_ids, work_date=None):
    q = db.query(Schedule).filter(
        Schedule.is_cancelled == False,
        Schedule.status == ScheduleStatus.DRAFT,
        Schedule.employee_id.in_(pt_ids),
    )
    if work_date:
        q = q.filter(Schedule.work_date == work_date)
    return q.all()


# ═══════════════════════════════════════════════════════════════════════
# Test 1: 동일 count 인접 슬롯 병합 → PT 근무시간 = 병합 범위
# ═══════════════════════════════════════════════════════════════════════

class TestSameCountMerge:

    def test_same_count_adjacent_pt_covers_merged_range(self, db):
        """
        09:00-12:00 (count=2) + 12:00-15:00 (count=2) + 정규직(09-15)
        → 동일 count 인접 → WorkBlock 09:00-15:00 (6h, count=2)
        → 정규직 cov=1, ned=1
        → PT 1명 배정, 근무시간 = 09:00~15:00 (병합 범위 전체)

        정규직 DRAFT 1 + PT DRAFT 1 = 총 2 DRAFT
        """
        store = _store(db)
        reg = _regular(db, store.id, start="09:00", end="15:00")
        pts = [_pt(db, f"PT{i}") for i in range(3)]

        _req(db, store.id, DayOfWeek.WED, "09:00", "12:00", count=2)
        _req(db, store.id, DayOfWeek.WED, "12:00", "15:00", count=2)
        db.commit()

        result = ScheduleEngine().generate(TEST_YEAR, TEST_MONTH, db)

        oct7_pt = _pt_drafts(db, [p.id for p in pts], work_date=OCT_7)
        assert len(oct7_pt) == 1, (
            f"count=2 병합 블록, 정규직 1 → PT 1명만 필요. "
            f"실제 PT DRAFT={len(oct7_pt)}, warnings={result['warnings']}"
        )
        assert not result["warnings"]
        assert oct7_pt[0].start_time == "09:00"
        assert oct7_pt[0].end_time == "15:00", "PT 근무시간 = 병합 블록 전체 범위"


# ═══════════════════════════════════════════════════════════════════════
# Test 2: 다른 count 인접 슬롯 → PT 시간 = 실제 필요한 슬롯만
# ═══════════════════════════════════════════════════════════════════════

class TestDifferentCountSeparateBlocks:

    def test_pt_assigned_only_to_understaffed_slot(self, db):
        """
        09:00-12:00 (count=1) + 12:00-15:00 (count=2) + 정규직(09-15)
        → 다른 count → 별도 WorkBlock
          BlockA: 09:00-12:00 (count=1): 정규직 cov=1, ned=0 → PT 불필요
          BlockB: 12:00-15:00 (count=2): 정규직 cov=1, ned=1 → PT 1명

        PT 1명, 근무시간 = 12:00~15:00 (09:00~15:00이 되면 안 됨)
        """
        store = _store(db)
        reg = _regular(db, store.id, start="09:00", end="15:00")
        pts = [_pt(db, f"PT{i}") for i in range(3)]

        _req(db, store.id, DayOfWeek.WED, "09:00", "12:00", count=1)
        _req(db, store.id, DayOfWeek.WED, "12:00", "15:00", count=2)
        db.commit()

        result = ScheduleEngine().generate(TEST_YEAR, TEST_MONTH, db)

        oct7_pt = _pt_drafts(db, [p.id for p in pts], work_date=OCT_7)
        assert len(oct7_pt) == 1, (
            f"BlockA 충족, BlockB ned=1 → PT 1명. "
            f"실제={len(oct7_pt)}, warnings={result['warnings']}"
        )
        assert not result["warnings"]
        assert oct7_pt[0].start_time == "12:00", "PT는 실제 필요한 BlockB 시간으로만 배정"
        assert oct7_pt[0].end_time == "15:00"

    def test_three_slots_pt_covers_only_middle_slot(self, db):
        """
        09:00-12:00 (count=1) + 12:00-15:00 (count=2) + 15:00-18:00 (count=1)
        + 정규직(09-18)
        → 3개 별도 WorkBlock
          09-12(1): 정규직 cov=1, ned=0
          12-15(2): 정규직 cov=1, ned=1 → PT 1명 (12:00~15:00)
          15-18(1): 정규직 cov=1, ned=0

        PT 1명, 근무시간 = 12:00~15:00
        절대로 09:00~18:00 전체가 되어서는 안 됨
        """
        store = _store(db)
        reg = _regular(db, store.id, start="09:00", end="18:00")
        pts = [_pt(db, f"PT{i}") for i in range(3)]

        _req(db, store.id, DayOfWeek.WED, "09:00", "12:00", count=1)
        _req(db, store.id, DayOfWeek.WED, "12:00", "15:00", count=2)
        _req(db, store.id, DayOfWeek.WED, "15:00", "18:00", count=1)
        db.commit()

        result = ScheduleEngine().generate(TEST_YEAR, TEST_MONTH, db)

        oct7_pt = _pt_drafts(db, [p.id for p in pts], work_date=OCT_7)
        assert len(oct7_pt) == 1, (
            f"가운데 블록만 ned=1 → PT 1명. "
            f"실제={len(oct7_pt)}, warnings={result['warnings']}"
        )
        assert not result["warnings"]
        assert oct7_pt[0].start_time == "12:00", "PT 근무 시작 = 실제 필요 시작"
        assert oct7_pt[0].end_time == "15:00", "PT 근무 종료 = 실제 필요 종료"


# ═══════════════════════════════════════════════════════════════════════
# Test 3: 후보 부족 시 경고
# ═══════════════════════════════════════════════════════════════════════

class TestInsufficientCandidates:

    def test_no_pt_available_generates_warning(self, db):
        """
        09:00-13:00 (count=2) + 정규직(09-13) + PT 0명
        → ned=1, 후보 없음 → 경고
        """
        store = _store(db)
        _regular(db, store.id, start="09:00", end="13:00")
        # PT 없음

        _req(db, store.id, DayOfWeek.WED, "09:00", "13:00", count=2)
        db.commit()

        result = ScheduleEngine().generate(TEST_YEAR, TEST_MONTH, db)

        oct7_pt = _pt_drafts(db, [], work_date=OCT_7)
        assert len(oct7_pt) == 0
        oct7_warnings = [w for w in result["warnings"] if "2026-10-07" in w]
        assert len(oct7_warnings) == 1, (
            f"PT 없음 → 경고 1개. warnings={result['warnings']}"
        )


# ═══════════════════════════════════════════════════════════════════════
# Test 4: 2시간 WorkBlock → 배정 불가, 경고
# ═══════════════════════════════════════════════════════════════════════

class TestShortBlockWarning:

    def test_2h_block_cannot_assign_pt(self, db):
        """
        09:00-11:00 (2h, count=1) → blk.hours < 3.0 → 경고
        """
        store = _store(db)
        pt = _pt(db, "PT")

        _req(db, store.id, DayOfWeek.WED, "09:00", "11:00", count=1)
        db.commit()

        result = ScheduleEngine().generate(TEST_YEAR, TEST_MONTH, db)

        oct7_pt = _pt_drafts(db, [pt.id], work_date=OCT_7)
        assert len(oct7_pt) == 0, "2시간 블록 → PT 배정 없어야 함"
        oct7_warnings = [w for w in result["warnings"] if "2026-10-07" in w]
        assert len(oct7_warnings) == 1, (
            f"경고 1개 발생해야 함. warnings={result['warnings']}"
        )


# ═══════════════════════════════════════════════════════════════════════
# Test 5: required_count 충족 시 초과 배정 없음
# ═══════════════════════════════════════════════════════════════════════

class TestNoOverAssignment:

    def test_stops_when_required_count_reached(self, db):
        """
        09:00-13:00 (count=3) + 정규직(09-13) + PT 3명
        → 정규직 cov=1, ned=2
        → PT_0 배정 → cov=2, ned=1
        → PT_1 배정 → cov=3, ned=0 → 중단
        → PT_2 미배정

        PT DRAFT = 2
        """
        store = _store(db)
        _regular(db, store.id, start="09:00", end="13:00")
        pts = [_pt(db, f"PT{i}") for i in range(3)]

        _req(db, store.id, DayOfWeek.WED, "09:00", "13:00", count=3)
        db.commit()

        result = ScheduleEngine().generate(TEST_YEAR, TEST_MONTH, db)

        oct7_pt = _pt_drafts(db, [p.id for p in pts], work_date=OCT_7)
        assert len(oct7_pt) == 2, (
            f"required_count=3, 정규직 1 → PT 2명으로 충족. "
            f"실제={len(oct7_pt)}, warnings={result['warnings']}"
        )
        assert not result["warnings"]


# ═══════════════════════════════════════════════════════════════════════
# Test 6: 하루 1회 제한 — 블록A 배정 PT는 블록B에서 제외
# ═══════════════════════════════════════════════════════════════════════

class TestDailyLimit:

    def test_pt_on_block_a_excluded_from_block_b(self, db):
        """
        블록A: 09:00-13:00 (4h, count=1)
        블록B: 18:00-23:00 (5h, count=1)  — 비인접
        PT_A, PT_B 2명

        블록A → PT_A 배정 → _pt_assigned_days[PT_A].add(date)
        블록B → PT_A 제외 → PT_B만 배정

        결과: PT_A=09-13, PT_B=18-23
        """
        store = _store(db)
        pt_a = _pt(db, "A")
        pt_b = _pt(db, "B")

        _req(db, store.id, DayOfWeek.WED, "09:00", "13:00", count=1)
        _req(db, store.id, DayOfWeek.WED, "18:00", "23:00", count=1)
        db.commit()

        result = ScheduleEngine().generate(TEST_YEAR, TEST_MONTH, db)

        oct7_pt = _pt_drafts(db, [pt_a.id, pt_b.id], work_date=OCT_7)
        assert len(oct7_pt) == 2, (
            f"비인접 2블록 → 서로 다른 PT = 2 DRAFT. "
            f"실제={len(oct7_pt)}, warnings={result['warnings']}"
        )
        assert not result["warnings"]
        assigned_ids = [d.employee_id for d in oct7_pt]
        assert len(set(assigned_ids)) == 2, "두 블록에 서로 다른 PT 배정"
        start_times = sorted(d.start_time for d in oct7_pt)
        assert start_times == ["09:00", "18:00"]
