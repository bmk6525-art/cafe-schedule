"""
스케줄 엔진 3차 개선 테스트 — 희소 슬롯 우선 배정

핵심 검증:
  - 배정 가능 후보자가 적은 슬롯을 먼저 처리하여 전체 충족률 향상
  - 슬롯 처리 후 후보자 수 재계산 정확성
  - 하루 1회 제한과 희소 슬롯 우선의 결합 동작
  - 기존 직원 선택 로직(누적시간 균등화) 유지

날짜 기준: 2026-10-07 = Wednesday
"""

import time
import pytest
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.database import Base
from app.models.models import (
    Employee, EmployeeType, Store, Schedule, ScheduleStatus,
    StaffRequirement, MonthlyAvailability, DayOfWeek,
)
from app.schedule_engine.engine import ScheduleEngine

TEST_YEAR = 2026
TEST_MONTH = 10
OCT_7 = date(2026, 10, 7)   # Wednesday
OCT_14 = date(2026, 10, 14) # Wednesday


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


def _unavailable(db, emp_id, dow, start=None, end=None, day_off=False):
    """파트타이머 월별 불가능 시간 등록"""
    a = MonthlyAvailability(
        employee_id=emp_id,
        year=TEST_YEAR, month=TEST_MONTH,
        day_of_week=dow,
        is_day_unavailable=day_off,
        unavailable_start=start,
        unavailable_end=end,
    )
    db.add(a)
    db.flush()
    return a


def _confirmed(db, emp_id, store_id, work_date, start, end,
               status=ScheduleStatus.CONFIRMED):
    s = Schedule(
        employee_id=emp_id, store_id=store_id,
        work_date=work_date, start_time=start, end_time=end,
        break_minutes=0, status=status, is_cancelled=False,
    )
    db.add(s)
    db.flush()
    return s


def _get_drafts(db, work_date=None, emp_id=None):
    q = db.query(Schedule).filter(
        Schedule.is_cancelled == False,
        Schedule.status == ScheduleStatus.DRAFT,
    )
    if work_date:
        q = q.filter(Schedule.work_date == work_date)
    if emp_id:
        q = q.filter(Schedule.employee_id == emp_id)
    return q.all()


# ═════════════════════════════════════════════════════════════════════
# Test 1 — 희소 슬롯이 먼저 처리되어 전체 충족률 개선
# ═════════════════════════════════════════════════════════════════════

class TestScarcityFirstImprovesFillRate:

    def test_scarce_slot_filled_first_both_slots_satisfied(self, db):
        """
        [Test 1 — 핵심 케이스]
        구성:
          PT_A: 종일 가능 (09-23)
          PT_B: 09:00-13:00만 가능 (13:00 이후 불가)

        슬롯:
          09:00-13:00 → 후보 2명 (A, B)
          18:00-23:00 → 후보 1명 (A만 가능)

        희소 슬롯 우선: 18-23(후보 1명)을 먼저 처리 → A 배정
        이후 09-13(후보 B만 남음) → B 배정
        → 두 슬롯 모두 충족

        구 알고리즘(start_time 순): 09-13에 A 배정 → 18-23 후보 없음 → 미충족
        """
        store = _store(db)
        pt_a = _pt(db, "A_전일가능")
        pt_b = _pt(db, "B_오전만가능")

        # PT_B: 수요일 13:00-23:00 불가능
        _unavailable(db, pt_b.id, DayOfWeek.WED, start="13:00", end="23:00")

        _req(db, store.id, DayOfWeek.WED, "09:00", "13:00")
        _req(db, store.id, DayOfWeek.WED, "18:00", "23:00")
        db.commit()

        result = ScheduleEngine().generate(TEST_YEAR, TEST_MONTH, db)

        oct7_drafts = _get_drafts(db, work_date=OCT_7)
        assert len(oct7_drafts) == 2, (
            f"희소 슬롯 우선 처리로 두 슬롯 모두 충족되어야 함. "
            f"생성된 슬롯={len(oct7_drafts)}, warnings={result['warnings']}"
        )
        assert not result["warnings"], f"모든 슬롯 충족 시 warning 없어야 함: {result['warnings']}"

    def test_scarce_slot_assigned_to_universal_employee(self, db):
        """
        [Test 1 계속]
        희소 슬롯(18-23, 후보 1명)에 A가 배정되고,
        일반 슬롯(09-13)에 B가 배정되어야 함.
        """
        store = _store(db)
        pt_a = _pt(db, "A_전일가능")
        pt_b = _pt(db, "B_오전만가능")
        _unavailable(db, pt_b.id, DayOfWeek.WED, start="13:00", end="23:00")

        _req(db, store.id, DayOfWeek.WED, "09:00", "13:00")
        _req(db, store.id, DayOfWeek.WED, "18:00", "23:00")
        db.commit()

        ScheduleEngine().generate(TEST_YEAR, TEST_MONTH, db)

        draft_18 = db.query(Schedule).filter(
            Schedule.work_date == OCT_7,
            Schedule.start_time == "18:00",
            Schedule.is_cancelled == False,
        ).first()
        draft_09 = db.query(Schedule).filter(
            Schedule.work_date == OCT_7,
            Schedule.start_time == "09:00",
            Schedule.is_cancelled == False,
        ).first()

        assert draft_18 is not None, "18-23 슬롯이 배정되어야 함"
        assert draft_09 is not None, "09-13 슬롯이 배정되어야 함"
        assert draft_18.employee_id == pt_a.id, \
            "희소한 18-23 슬롯에는 종일 가능한 A가 배정되어야 함"
        assert draft_09.employee_id == pt_b.id, \
            "09-13 슬롯에는 오전만 가능한 B가 배정되어야 함"

    def test_three_slots_scarcity_order(self, db):
        """
        슬롯 3개, 각각 후보 수가 다를 때 후보 적은 순서대로 처리

        구성:
          PT_A: 종일 가능
          PT_B: 09-13만 가능 (13:00 이후 불가)
          PT_C: 09-18만 가능 (18:00 이후 불가)

        초기 후보:
          09-13 → A, B, C = 3명
          14-18 → A, C = 2명
          19-23 → A = 1명  ← 가장 희소

        희소 처리 순서: 19-23 → 14-18 → 09-13
        → 세 슬롯 모두 충족
        (슬롯 간 간격으로 WorkBlock 병합 없이 3개의 독립 블록으로 처리)
        """
        store = _store(db)
        pt_a = _pt(db, "A")
        pt_b = _pt(db, "B")
        pt_c = _pt(db, "C")

        # B: 수요일 13:00 이후 불가
        _unavailable(db, pt_b.id, DayOfWeek.WED, start="13:00", end="23:00")
        # C: 수요일 18:00 이후 불가
        _unavailable(db, pt_c.id, DayOfWeek.WED, start="18:00", end="23:00")

        _req(db, store.id, DayOfWeek.WED, "09:00", "13:00")
        _req(db, store.id, DayOfWeek.WED, "14:00", "18:00")
        _req(db, store.id, DayOfWeek.WED, "19:00", "23:00")
        db.commit()

        result = ScheduleEngine().generate(TEST_YEAR, TEST_MONTH, db)

        oct7_drafts = _get_drafts(db, work_date=OCT_7)
        assert len(oct7_drafts) == 3, (
            f"세 슬롯 모두 충족되어야 함 (희소 슬롯 우선). "
            f"생성={len(oct7_drafts)}, warnings={result['warnings']}"
        )
        assert not result["warnings"]


# ═════════════════════════════════════════════════════════════════════
# Test 2 — 하루 1회 제한 + 희소 슬롯 우선 결합
# ═════════════════════════════════════════════════════════════════════

class TestScarcityWithDailyLimit:

    def test_universal_pt_assigned_to_scarce_slot_not_common(self, db):
        """
        [Test 2]
        A가 여러 슬롯에 가능해도 희소한 슬롯에 먼저 배정되고
        다른 슬롯에서는 하루 1회 제한으로 제외되어야 함.

        PT_A: 종일 가능
        PT_B: 18-23만 가능

        슬롯: 09-13(후보: A=1명), 18-23(후보: A,B=2명)
        희소: 09-13이 더 희소 → 09-13 먼저 → A 배정
        이후 18-23 → B만 남음 → B 배정
        → 두 슬롯 모두 충족
        """
        store = _store(db)
        pt_a = _pt(db, "A")
        pt_b = _pt(db, "B")

        # B: 수요일 09:00-18:00 불가 (18시 이후만 가능)
        _unavailable(db, pt_b.id, DayOfWeek.WED, start="09:00", end="18:00")

        _req(db, store.id, DayOfWeek.WED, "09:00", "13:00")   # 후보: A만 = 1명
        _req(db, store.id, DayOfWeek.WED, "18:00", "23:00")   # 후보: A, B = 2명
        db.commit()

        result = ScheduleEngine().generate(TEST_YEAR, TEST_MONTH, db)

        oct7_drafts = _get_drafts(db, work_date=OCT_7)
        assert len(oct7_drafts) == 2, (
            f"희소 우선으로 두 슬롯 모두 충족. warnings={result['warnings']}"
        )
        assert not result["warnings"]

    def test_only_one_slot_possible_when_all_candidates_exhaust(self, db):
        """
        PT 1명, 슬롯 2개 → 희소 슬롯에 배정 후 나머지는 warning
        (하루 1회 제한 때문에 두 슬롯 모두 채울 수 없음)
        """
        store = _store(db)
        pt_a = _pt(db, "A")

        _req(db, store.id, DayOfWeek.WED, "09:00", "13:00")
        _req(db, store.id, DayOfWeek.WED, "18:00", "23:00")
        db.commit()

        result = ScheduleEngine().generate(TEST_YEAR, TEST_MONTH, db)

        oct7_drafts = _get_drafts(db, work_date=OCT_7)
        assert len(oct7_drafts) == 1, "PT 1명이면 하루 1개만 배정"
        # 두 슬롯 모두 후보 1명으로 동점 → 원본 순서(09-13)가 먼저
        assert oct7_drafts[0].start_time == "09:00", "동점일 때 원본 순서 유지"
        # WED 요구사항은 Oct 7,14,21,28 모두에 적용 → 각 날짜 18-23 미배정 warning
        oct7_warnings = [w for w in result["warnings"] if "2026-10-07" in w]
        assert len(oct7_warnings) == 1, "Oct 7의 18-23 슬롯은 warning 1개"


# ═════════════════════════════════════════════════════════════════════
# Test 3 — 후보자 수 재계산: 배정 후 다른 슬롯의 후보 수 감소 반영
# ═════════════════════════════════════════════════════════════════════

class TestCandidateCountRecalculation:

    def test_assignment_reduces_candidates_for_subsequent_slots(self, db):
        """
        [Test 3]
        처음 평가: 슬롯X 후보 3명(A,B,C), 슬롯Y 후보 2명(A,B)
        → 슬롯Y 먼저 처리(희소), A 배정
        → 슬롯X 재평가: A 제외 → 후보 B, C만 남음 → 정상 배정

        구성:
          PT_A: 09-23 가능
          PT_B: 09-23 가능
          PT_C: 09-13만 가능 (13:00 이후 불가)

          슬롯 09-13: 후보 A,B,C = 3명
          슬롯 18-23: 후보 A,B = 2명 ← 더 희소

        희소 처리: 18-23 먼저 → A 배정
        이후 09-13: B, C 중 B(누적시간 같으면 먼저 나온 순) 배정
        → 두 슬롯 모두 충족
        """
        store = _store(db)
        pt_a = _pt(db, "A")
        pt_b = _pt(db, "B")
        pt_c = _pt(db, "C_오전한정")

        # C: 수요일 13:00-23:00 불가
        _unavailable(db, pt_c.id, DayOfWeek.WED, start="13:00", end="23:00")

        _req(db, store.id, DayOfWeek.WED, "09:00", "13:00")  # 후보 A,B,C = 3명
        _req(db, store.id, DayOfWeek.WED, "18:00", "23:00")  # 후보 A,B = 2명
        db.commit()

        result = ScheduleEngine().generate(TEST_YEAR, TEST_MONTH, db)

        oct7_drafts = _get_drafts(db, work_date=OCT_7)
        assert len(oct7_drafts) == 2, (
            f"재계산 후에도 두 슬롯 모두 충족. warnings={result['warnings']}"
        )
        assert not result["warnings"]

        # 18-23에는 A 또는 B 중 하나 (C는 불가)
        draft_18 = db.query(Schedule).filter(
            Schedule.work_date == OCT_7,
            Schedule.start_time == "18:00",
            Schedule.is_cancelled == False,
        ).first()
        assert draft_18.employee_id in {pt_a.id, pt_b.id}, \
            "18-23 슬롯에는 A 또는 B가 배정"

    def test_multiple_rounds_candidate_count_shrinks(self, db):
        """
        3슬롯, 3명 PT, 각 1명씩 필요 → 매 라운드 후보 재계산으로 정확한 배정
        (슬롯 간 간격으로 WorkBlock 병합 없이 3개의 독립 블록으로 처리)
        """
        store = _store(db)
        pts = [_pt(db, f"PT{i}") for i in range(3)]

        _req(db, store.id, DayOfWeek.WED, "09:00", "13:00")
        _req(db, store.id, DayOfWeek.WED, "14:00", "18:00")
        _req(db, store.id, DayOfWeek.WED, "19:00", "23:00")
        db.commit()

        result = ScheduleEngine().generate(TEST_YEAR, TEST_MONTH, db)

        oct7_drafts = _get_drafts(db, work_date=OCT_7)
        assert len(oct7_drafts) == 3, "3명 3슬롯 → 각 1명씩 총 3 DRAFT"
        # 각 PT는 최대 1개 슬롯만 배정
        pt_ids = [d.employee_id for d in oct7_drafts]
        assert len(set(pt_ids)) == 3, "3명이 각각 다른 슬롯에 배정"
        assert not result["warnings"]


# ═════════════════════════════════════════════════════════════════════
# Test 4 — 동점 시 원본 순서(기존 매장·시간 순서) 유지
# ═════════════════════════════════════════════════════════════════════

class TestTieBreaking:

    def test_equal_scarcity_preserves_original_order(self, db):
        """
        모든 슬롯 후보 수가 같을 때 기존 순서(start_time 오름차순) 유지
        """
        store = _store(db)
        pt_a = _pt(db, "A")
        pt_b = _pt(db, "B")

        # 두 슬롯 모두 후보 2명(A,B) → 동점
        _req(db, store.id, DayOfWeek.WED, "09:00", "13:00")
        _req(db, store.id, DayOfWeek.WED, "18:00", "23:00")
        db.commit()

        result = ScheduleEngine().generate(TEST_YEAR, TEST_MONTH, db)

        oct7_drafts = _get_drafts(db, work_date=OCT_7)
        assert len(oct7_drafts) == 2
        start_times = sorted(d.start_time for d in oct7_drafts)
        assert start_times == ["09:00", "18:00"], "두 슬롯 모두 배정"

    def test_equal_scarcity_different_stores_preserves_store_order(self, db):
        """
        다른 매장, 동일 후보 수 → 매장 원본 순서 유지
        (낮은 ID 매장이 먼저 처리됨)
        """
        store1 = _store(db, "A매장")
        store2 = _store(db, "B매장")
        pt = _pt(db, "PT")

        _req(db, store1.id, DayOfWeek.WED, "09:00", "13:00")
        _req(db, store2.id, DayOfWeek.WED, "18:00", "23:00")
        db.commit()

        ScheduleEngine().generate(TEST_YEAR, TEST_MONTH, db)

        # store1 슬롯(동점 시 원본 순서 앞)에 PT 배정되어야 함
        store1_draft = db.query(Schedule).filter(
            Schedule.store_id == store1.id,
            Schedule.work_date == OCT_7,
            Schedule.is_cancelled == False,
            Schedule.status == ScheduleStatus.DRAFT,
        ).first()
        assert store1_draft is not None
        assert store1_draft.employee_id == pt.id


# ═════════════════════════════════════════════════════════════════════
# 기존 기능 regression — 희소 슬롯 우선 도입 후에도 기존 동작 유지
# ═════════════════════════════════════════════════════════════════════

class TestRegressionAfterScarcity:

    def test_required_count_filled_correctly(self, db):
        """필요인원 2명 슬롯에 PT 3명 → 정확히 2명만 배정"""
        store = _store(db)
        pts = [_pt(db, f"PT{i}") for i in range(3)]
        _req(db, store.id, DayOfWeek.WED, "09:00", "18:00", count=2)
        db.commit()

        ScheduleEngine().generate(TEST_YEAR, TEST_MONTH, db)

        assert len(_get_drafts(db, work_date=OCT_7)) == 2

    def test_daily_limit_still_enforced_with_scarcity(self, db):
        """희소 슬롯 우선 도입 후에도 하루 1회 제한 유지"""
        store = _store(db)
        pt = _pt(db, "PT")
        _req(db, store.id, DayOfWeek.WED, "09:00", "13:00")
        _req(db, store.id, DayOfWeek.WED, "18:00", "23:00")
        db.commit()

        ScheduleEngine().generate(TEST_YEAR, TEST_MONTH, db)

        assert len(_get_drafts(db, work_date=OCT_7)) == 1

    def test_max_hours_still_enforced_with_scarcity(self, db):
        """희소 슬롯 우선 도입 후에도 monthly_max_hours 유지"""
        store = _store(db)
        pt = _pt(db, "PT", max_hours=10.0)
        # 이미 8h CONFIRMED
        _confirmed(db, pt.id, store.id, date(2026, 10, 1), "09:00", "17:00")
        # 새 슬롯 4h → 합계 12h > 10h
        _req(db, store.id, DayOfWeek.WED, "09:00", "13:00")
        db.commit()

        result = ScheduleEngine().generate(TEST_YEAR, TEST_MONTH, db)

        assert len(_get_drafts(db, work_date=OCT_7)) == 0
        assert any("2026-10-07" in w for w in result["warnings"])

    def test_confirmed_protected_with_scarcity(self, db):
        """희소 슬롯 우선 도입 후에도 CONFIRMED 스케줄 보호"""
        store = _store(db)
        pt = _pt(db, "PT")
        conf = _confirmed(db, pt.id, store.id, OCT_7, "09:00", "13:00")
        db.commit()

        ScheduleEngine().generate(TEST_YEAR, TEST_MONTH, db)

        still = db.query(Schedule).filter(
            Schedule.id == conf.id,
            Schedule.is_cancelled == False,
        ).first()
        assert still is not None

    def test_availability_restriction_respected_with_scarcity(self, db):
        """희소 슬롯 우선에서도 요일 불가능 설정 준수"""
        store = _store(db)
        pt = _pt(db, "PT")
        _unavailable(db, pt.id, DayOfWeek.WED, day_off=True)
        _req(db, store.id, DayOfWeek.WED, "09:00", "13:00")
        db.commit()

        result = ScheduleEngine().generate(TEST_YEAR, TEST_MONTH, db)

        assert len(_get_drafts(db, work_date=OCT_7)) == 0
        assert any("2026-10-07" in w for w in result["warnings"])

    def test_different_dates_unaffected(self, db):
        """희소 슬롯 처리가 다른 날짜 배정에 영향 없음"""
        store = _store(db)
        pt = _pt(db, "PT")
        _req(db, store.id, DayOfWeek.WED, "09:00", "13:00")
        db.commit()

        ScheduleEngine().generate(TEST_YEAR, TEST_MONTH, db)

        # Oct 2026의 모든 수요일(7,14,21,28)에 배정되어야 함
        all_wed = db.query(Schedule).filter(
            Schedule.employee_id == pt.id,
            Schedule.is_cancelled == False,
            Schedule.status == ScheduleStatus.DRAFT,
        ).count()
        assert all_wed == 4


# ═════════════════════════════════════════════════════════════════════
# 성능 테스트
# ═════════════════════════════════════════════════════════════════════

class TestPerformance:

    def test_generation_completes_in_reasonable_time(self, db):
        """
        현실적인 규모(매장 3개, 파트타이머 10명, 하루 3슬롯)에서
        generate()가 5초 이내 완료되는지 확인.
        """
        # 매장 3개
        stores = [_store(db, f"매장{i}") for i in range(3)]
        # 파트타이머 10명
        pts = [_pt(db, f"PT{i:02d}") for i in range(10)]

        # 각 매장 × 전 요일 × 3슬롯
        for s in stores:
            for dow in DayOfWeek:
                _req(db, s.id, dow, "09:00", "14:00")
                _req(db, s.id, dow, "14:00", "19:00")
                _req(db, s.id, dow, "19:00", "23:00")
        db.commit()

        start = time.time()
        result = ScheduleEngine().generate(TEST_YEAR, TEST_MONTH, db)
        elapsed = time.time() - start

        assert elapsed < 5.0, f"생성 시간 초과: {elapsed:.2f}초"
        print(f"\n[성능] 생성 시간: {elapsed:.3f}초, 생성된 스케줄: {result['created']}개")
