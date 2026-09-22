"""
스케줄 엔진 5차 테스트 — WorkBlock 병합 및 최소 3시간 제약

핵심 검증:
  - 인접 + 동일 required_count 슬롯 → 단일 WorkBlock으로 병합
  - 인접이어도 required_count 다르면 별도 WorkBlock
  - 시간 간격 있으면 별도 WorkBlock
  - 3시간 미만 WorkBlock → 배정 불가 (경고 발생)
  - 3시간 이상 WorkBlock → 정상 배정
  - 병합된 블록도 3시간 미만이면 경고
  - 하루 1회 제한이 WorkBlock 단위로도 유지됨

날짜 기준: 2026-10-07 = Wednesday (Oct 2026 수요일: 7, 14, 21, 28)
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


# ═════════════════════════════════════════════════════════════════════
# WorkBlock 병합 동작 검증
# ═════════════════════════════════════════════════════════════════════

class TestWorkBlockMerging:

    def test_adjacent_same_count_merges_to_one_block(self, db):
        """
        인접 슬롯 + 동일 required_count → 단일 WorkBlock으로 병합

        09:00-11:00 (2h, count=1) + 11:00-13:00 (2h, count=1)
        → WorkBlock: 09:00-13:00 (4h, count=1)
        → 1개 DRAFT (start=09:00, end=13:00)
        """
        store = _store(db)
        pt = _pt(db, "PT")

        _req(db, store.id, DayOfWeek.WED, "09:00", "11:00")
        _req(db, store.id, DayOfWeek.WED, "11:00", "13:00")
        db.commit()

        result = ScheduleEngine().generate(TEST_YEAR, TEST_MONTH, db)

        oct7_drafts = _get_drafts(db, work_date=OCT_7)
        assert len(oct7_drafts) == 1, (
            f"병합된 1개 블록 → 1개 DRAFT여야 함. "
            f"실제={len(oct7_drafts)}, warnings={result['warnings']}"
        )
        assert oct7_drafts[0].start_time == "09:00", "병합 블록 시작 시간 확인"
        assert oct7_drafts[0].end_time == "13:00", "병합 블록 종료 시간 확인"
        assert not result["warnings"]

    def test_adjacent_different_count_merges_into_one_block(self, db):
        """
        인접 슬롯은 required_count가 달라도 하나의 WorkBlock으로 병합
        (v2 설계: 모든 인접 슬롯 병합, 내부 Segment로 required_count 경계 보존)

        09:00-13:00 (4h, count=1) + 13:00-18:00 (5h, count=2)
        → WorkBlock: 09:00-18:00 (Segment1: count=1, Segment2: count=2)
        → ned_block = max(1, 2) = 2
        → 3명 PT 중 2명 배정 (모두 09:00-18:00), 1명 초과는 배정 안됨
        """
        store = _store(db)
        pts = [_pt(db, f"PT{i}") for i in range(3)]

        _req(db, store.id, DayOfWeek.WED, "09:00", "13:00", count=1)
        _req(db, store.id, DayOfWeek.WED, "13:00", "18:00", count=2)
        db.commit()

        result = ScheduleEngine().generate(TEST_YEAR, TEST_MONTH, db)

        oct7_drafts = _get_drafts(db, work_date=OCT_7)
        assert len(oct7_drafts) == 2, (
            f"병합된 1개 WorkBlock, ned_block=2 → 2 DRAFT여야 함. "
            f"실제={len(oct7_drafts)}, warnings={result['warnings']}"
        )
        assert not result["warnings"]
        # 두 DRAFT 모두 블록 전체 범위 (09:00-18:00)
        assert all(d.start_time == "09:00" for d in oct7_drafts)
        assert all(d.end_time == "18:00" for d in oct7_drafts)

    def test_gap_creates_separate_blocks(self, db):
        """
        시간 간격(gap) 있으면 별도 WorkBlock

        09:00-12:00 (3h) → gap → 14:00-17:00 (3h)
        end[0]=12:00 ≠ start[1]=14:00 → 2개의 독립 WorkBlock
        → 2명 PT → 각 1명씩 = 2 DRAFT
        """
        store = _store(db)
        pts = [_pt(db, f"PT{i}") for i in range(2)]

        _req(db, store.id, DayOfWeek.WED, "09:00", "12:00")
        _req(db, store.id, DayOfWeek.WED, "14:00", "17:00")
        db.commit()

        result = ScheduleEngine().generate(TEST_YEAR, TEST_MONTH, db)

        oct7_drafts = _get_drafts(db, work_date=OCT_7)
        assert len(oct7_drafts) == 2, (
            f"간격으로 분리된 2블록 → 2 DRAFT여야 함. "
            f"실제={len(oct7_drafts)}, warnings={result['warnings']}"
        )
        assert not result["warnings"]
        start_times = sorted(d.start_time for d in oct7_drafts)
        assert start_times == ["09:00", "14:00"]


# ═════════════════════════════════════════════════════════════════════
# 최소 3시간 제약 검증
# ═════════════════════════════════════════════════════════════════════

class TestMinimum3HoursConstraint:

    def test_short_block_under_3h_generates_warning(self, db):
        """
        3시간 미만 단일 WorkBlock → 배정 불가, 경고 발생

        09:00-11:00 (2h) → _cands=[] → 경고 발생, DRAFT 없음
        """
        store = _store(db)
        pt = _pt(db, "PT")

        _req(db, store.id, DayOfWeek.WED, "09:00", "11:00")
        db.commit()

        result = ScheduleEngine().generate(TEST_YEAR, TEST_MONTH, db)

        oct7_drafts = _get_drafts(db, work_date=OCT_7)
        assert len(oct7_drafts) == 0, "2시간 블록 → 배정 없어야 함"
        oct7_warnings = [w for w in result["warnings"] if "2026-10-07" in w]
        assert len(oct7_warnings) == 1, f"경고 1개 발생해야 함: {result['warnings']}"

    def test_block_exactly_3h_can_be_assigned(self, db):
        """
        정확히 3시간 WorkBlock → 배정 가능 (≥3h 조건 충족)

        09:00-12:00 (3h) → 정상 배정
        """
        store = _store(db)
        pt = _pt(db, "PT")

        _req(db, store.id, DayOfWeek.WED, "09:00", "12:00")
        db.commit()

        result = ScheduleEngine().generate(TEST_YEAR, TEST_MONTH, db)

        oct7_drafts = _get_drafts(db, work_date=OCT_7)
        assert len(oct7_drafts) == 1, f"3시간 블록 → 1 DRAFT여야 함. warnings={result['warnings']}"
        assert not result["warnings"]

    def test_merged_short_block_still_generates_warning(self, db):
        """
        병합 후에도 3시간 미만이면 경고 발생

        09:00-10:00 (1h) + 10:00-11:00 (1h) → 병합 → 09:00-11:00 (2h)
        2h < 3h → 배정 불가, 경고 발생
        """
        store = _store(db)
        pt = _pt(db, "PT")

        _req(db, store.id, DayOfWeek.WED, "09:00", "10:00")
        _req(db, store.id, DayOfWeek.WED, "10:00", "11:00")
        db.commit()

        result = ScheduleEngine().generate(TEST_YEAR, TEST_MONTH, db)

        oct7_drafts = _get_drafts(db, work_date=OCT_7)
        assert len(oct7_drafts) == 0, "병합 후 2시간 블록 → 배정 없어야 함"
        oct7_warnings = [w for w in result["warnings"] if "2026-10-07" in w]
        assert len(oct7_warnings) == 1, f"경고 1개 발생해야 함: {result['warnings']}"


# ═════════════════════════════════════════════════════════════════════
# 하루 1회 제한 + WorkBlock 결합 동작
# ═════════════════════════════════════════════════════════════════════

class TestDailyLimitWithWorkBlocks:

    def test_assigned_pt_excluded_from_same_day_other_block(self, db):
        """
        한 WorkBlock에 배정된 PT는 같은 날 다른 WorkBlock에서 제외

        블록A: 09:00-13:00 (4h), 블록B: 18:00-23:00 (5h) — 비인접
        PT_A, PT_B 2명 → 각자 다른 블록에 배정, 2 DRAFT
        """
        store = _store(db)
        pt_a = _pt(db, "A")
        pt_b = _pt(db, "B")

        _req(db, store.id, DayOfWeek.WED, "09:00", "13:00")
        _req(db, store.id, DayOfWeek.WED, "18:00", "23:00")
        db.commit()

        result = ScheduleEngine().generate(TEST_YEAR, TEST_MONTH, db)

        oct7_drafts = _get_drafts(db, work_date=OCT_7)
        assert len(oct7_drafts) == 2, (
            f"2블록 2명 → 각각 다른 PT 배정 = 2 DRAFT. warnings={result['warnings']}"
        )
        assert not result["warnings"]
        pt_ids = [d.employee_id for d in oct7_drafts]
        assert len(set(pt_ids)) == 2, "블록마다 다른 PT가 배정되어야 함"
