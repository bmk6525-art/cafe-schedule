"""
스케줄 엔진 6차 테스트 — Segment 기반 per-segment coverage 검증

핵심 검증:
  - 동일 count 인접 슬롯: 정규직 1 + 필요 count=2 → PT 1명
  - 다른 count 인접 슬롯: 정규직 1 + Segment(2)+Segment(3) → PT 2명
  - 후보자 부족 시 경고 발생
  - 2시간 블록 → 배정 불가, 경고
  - required_count=3, 정규직 1 → PT 2명만 (총합 3 달성 시 중단)
  - 하루 1회 제한: 블록A에 배정된 PT는 블록B 제외

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
             start="09:00", end="15:00") -> Employee:
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
# Test 1: 동일 count 인접 슬롯 + 정규직 1 → PT 1명
# ═══════════════════════════════════════════════════════════════════════

class TestSegmentCoverageSameCount:

    def test_same_count_segments_regular_covers_one(self, db):
        """
        09:00-12:00 (count=2) + 12:00-15:00 (count=2) + 정규직 1명
        → 병합: WorkBlock 09:00-15:00, Segment 09:00-15:00 (count=2, merged)
        → 정규직 cov=1, ned_block = max(2-1) = 1
        → PT 1명 배정

        정규직 DRAFT 1 + PT DRAFT 1 = 총 2 DRAFT
        """
        store = _store(db)
        reg = _regular(db, store.id, start="09:00", end="15:00")
        pt1 = _pt(db, "PT1")
        pt2 = _pt(db, "PT2")  # 여분

        _req(db, store.id, DayOfWeek.WED, "09:00", "12:00", count=2)
        _req(db, store.id, DayOfWeek.WED, "12:00", "15:00", count=2)
        db.commit()

        result = ScheduleEngine().generate(TEST_YEAR, TEST_MONTH, db)

        oct7_pt = _pt_drafts(db, [pt1.id, pt2.id], work_date=OCT_7)
        assert len(oct7_pt) == 1, (
            f"정규직 1 + count=2 → PT 1명만 필요. "
            f"실제 PT DRAFT={len(oct7_pt)}, warnings={result['warnings']}"
        )
        assert not result["warnings"]


# ═══════════════════════════════════════════════════════════════════════
# Test 2: 다른 count 인접 슬롯 + 정규직 1 → PT 2명
# ═══════════════════════════════════════════════════════════════════════

class TestSegmentCoverageDiffCount:

    def test_diff_count_segments_regular_covers_first(self, db):
        """
        09:00-12:00 (count=2) + 12:00-15:00 (count=3) + 정규직 1명
        → WorkBlock 09:00-15:00, Segments: [09-12(2), 12-15(3)]
        → 정규직 09:00-15:00 → 각 Segment cov=1
        → ned_block = max(2-1, 3-1) = max(1, 2) = 2
        → PT 2명 배정 (각각 09:00-15:00)
        """
        store = _store(db)
        reg = _regular(db, store.id, start="09:00", end="15:00")
        pts = [_pt(db, f"PT{i}") for i in range(3)]  # 3명 중 2명만 필요

        _req(db, store.id, DayOfWeek.WED, "09:00", "12:00", count=2)
        _req(db, store.id, DayOfWeek.WED, "12:00", "15:00", count=3)
        db.commit()

        result = ScheduleEngine().generate(TEST_YEAR, TEST_MONTH, db)

        oct7_pt = _pt_drafts(db, [p.id for p in pts], work_date=OCT_7)
        assert len(oct7_pt) == 2, (
            f"ned_block=2 → PT 2명 배정. "
            f"실제 PT DRAFT={len(oct7_pt)}, warnings={result['warnings']}"
        )
        assert not result["warnings"]
        # 두 PT 모두 블록 전체 범위 근무
        assert all(d.start_time == "09:00" and d.end_time == "15:00" for d in oct7_pt)


# ═══════════════════════════════════════════════════════════════════════
# Test 3: 정규직 1 + 후보 PT 1명뿐 → PT 1명 배정 + 경고
# ═══════════════════════════════════════════════════════════════════════

class TestSegmentCoverageShortfall:

    def test_only_one_pt_available_generates_warning(self, db):
        """
        09:00-12:00 (count=2) + 12:00-15:00 (count=3) + 정규직 1명
        + 가용 PT 1명뿐 → PT 1명 배정 후 ned_block=1 잔여 → 경고

        ned_block 초기=2, PT 1명 배정 후=1 → 후보 없음 → 경고
        """
        store = _store(db)
        reg = _regular(db, store.id, start="09:00", end="15:00")
        pt1 = _pt(db, "PT1")  # 단 1명

        _req(db, store.id, DayOfWeek.WED, "09:00", "12:00", count=2)
        _req(db, store.id, DayOfWeek.WED, "12:00", "15:00", count=3)
        db.commit()

        result = ScheduleEngine().generate(TEST_YEAR, TEST_MONTH, db)

        oct7_pt = _pt_drafts(db, [pt1.id], work_date=OCT_7)
        assert len(oct7_pt) == 1, (
            f"가용 PT 1명 → 1 DRAFT. 실제={len(oct7_pt)}"
        )
        oct7_warnings = [w for w in result["warnings"] if "2026-10-07" in w]
        assert len(oct7_warnings) == 1, (
            f"인원 부족 경고 1개 발생해야 함. warnings={result['warnings']}"
        )


# ═══════════════════════════════════════════════════════════════════════
# Test 4: 2시간 WorkBlock → 배정 불가, 경고
# ═══════════════════════════════════════════════════════════════════════

class TestShortBlockWarning:

    def test_2h_block_cannot_assign_pt(self, db):
        """
        09:00-11:00 (2h, count=1) → blk.hours < 3.0 → _cands=[] → 경고
        PT 없음, DRAFT 없음
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
# Test 5: required_count=3, 정규직 1, PT 3명 → PT 2명만 배정
# ═══════════════════════════════════════════════════════════════════════

class TestNoOverassignment:

    def test_stops_at_required_count_satisfied(self, db):
        """
        09:00-13:00 (count=3) + 정규직 1명 + PT 3명
        → 정규직 cov=1, ned=2
        → PT_1 배정 → cov=2, ned=1
        → PT_2 배정 → cov=3, ned=0 → 중단
        → PT_3 미배정
        총 PT DRAFT = 2
        """
        store = _store(db)
        reg = _regular(db, store.id, start="09:00", end="13:00")
        pts = [_pt(db, f"PT{i}") for i in range(3)]

        _req(db, store.id, DayOfWeek.WED, "09:00", "13:00", count=3)
        db.commit()

        result = ScheduleEngine().generate(TEST_YEAR, TEST_MONTH, db)

        oct7_pt = _pt_drafts(db, [p.id for p in pts], work_date=OCT_7)
        assert len(oct7_pt) == 2, (
            f"required_count=3, 정규직 1 → PT 2명으로 충족. "
            f"실제 PT DRAFT={len(oct7_pt)}, warnings={result['warnings']}"
        )
        assert not result["warnings"]


# ═══════════════════════════════════════════════════════════════════════
# Test 6: 블록A 배정 PT는 블록B 같은 날 제외
# ═══════════════════════════════════════════════════════════════════════

class TestDailyLimitCrossBlocks:

    def test_pt_assigned_to_block_a_excluded_from_block_b(self, db):
        """
        블록A: 09:00-13:00 (4h), 블록B: 18:00-23:00 (5h) — 비인접
        PT_A, PT_B 2명

        블록A 처리: PT_A 배정 → _pt_assigned_days[PT_A].add(date)
        블록B 처리: PT_A 제외 → PT_B만 후보 → PT_B 배정

        결과: PT_A = 블록A, PT_B = 블록B (서로 다른 블록)
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
            f"비인접 2블록 → 각각 다른 PT = 2 DRAFT. "
            f"실제={len(oct7_pt)}, warnings={result['warnings']}"
        )
        assert not result["warnings"]
        assigned_ids = [d.employee_id for d in oct7_pt]
        assert len(set(assigned_ids)) == 2, "두 블록에 서로 다른 PT가 배정되어야 함"
        start_times = sorted(d.start_time for d in oct7_pt)
        assert start_times == ["09:00", "18:00"], "블록A와 블록B에 각각 배정"
