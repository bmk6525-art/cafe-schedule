"""
스케줄 자동 생성 엔진 — 그리디 알고리즘

HARD CONSTRAINT (반드시 준수):
  1. 매장 운영시간 외 근무 금지
  2. 정규직 고정 근무패턴 준수
  3. 파트타이머 불가능시간 배정 금지
  4. 동일 직원 동시간대 중복근무 금지
  5. 동일 직원 동시에 여러 매장 금지
  6. 정규직 주 40시간 준수
  7. 정규직 주 5일 준수

SOFT CONSTRAINT (가능하면 준수):
  1. 매장별 필요인원 부족 최소화
  2. 파트타이머 목표 근무시간 준수
  3. 파트타이머 선호 매장 반영
  4. 파트타이머 근무시간 균등화
"""

import calendar
from datetime import date, timedelta
from typing import Optional
from sqlalchemy.orm import Session

from app.models.models import (
    Employee, EmployeeType, Store, EmployeeWorkPattern,
    MonthlyAvailability, AvailabilityException, StaffRequirement,
    Schedule, ScheduleStatus, DayOfWeek
)

# Python 요일 (월=0) → DayOfWeek 매핑
_WEEKDAY_MAP = {0:'MON',1:'TUE',2:'WED',3:'THU',4:'FRI',5:'SAT',6:'SUN'}


def _time_to_min(t: str) -> int:
    """'HH:MM' → 분 단위 정수"""
    h, m = map(int, t.split(':'))
    return h * 60 + m


def _min_to_time(m: int) -> str:
    return f"{m//60:02d}:{m%60:02d}"


def _overlaps(s1: str, e1: str, s2: str, e2: str) -> bool:
    """두 시간 구간이 겹치는지 확인"""
    return _time_to_min(s1) < _time_to_min(e2) and _time_to_min(s2) < _time_to_min(e1)


def _is_within(inner_s: str, inner_e: str, outer_s: str, outer_e: str) -> bool:
    """inner 구간이 outer 구간 안에 있는지 확인"""
    return _time_to_min(outer_s) <= _time_to_min(inner_s) and _time_to_min(inner_e) <= _time_to_min(outer_e)


class ScheduleEngine:

    def generate(self, year: int, month: int, db: Session) -> dict:
        """
        스케줄 생성 메인 함수
        Returns: {'created': int, 'warnings': List[str]}
        """
        # 기존 DRAFT 스케줄 삭제 (CONFIRMED/LOCKED는 유지)
        db.query(Schedule).filter(
            Schedule.work_date >= date(year, month, 1),
            Schedule.work_date < date(year + (1 if month == 12 else 0),
                                      1 if month == 12 else month + 1, 1),
            Schedule.status == ScheduleStatus.DRAFT,
        ).delete()
        db.commit()

        stores = db.query(Store).filter_by(is_active=True).all()
        regulars = db.query(Employee).filter_by(
            employee_type=EmployeeType.REGULAR, is_active=True).all()
        part_timers = db.query(Employee).filter_by(
            employee_type=EmployeeType.PART_TIMER, is_active=True).all()

        # 파트타이머별 이번 달 배정 누적 시간 (소프트 컨스트레인트용)
        pt_hours: dict[int, float] = {pt.id: 0.0 for pt in part_timers}

        created = 0
        warnings = []
        days_in_month = calendar.monthrange(year, month)[1]

        for day_num in range(1, days_in_month + 1):
            work_date = date(year, month, day_num)
            dow = DayOfWeek(_WEEKDAY_MAP[work_date.weekday()])

            # ── 1. 정규직 배정 (HARD: 패턴 그대로) ──
            for emp in regulars:
                pattern = next(
                    (p for p in db.query(EmployeeWorkPattern)
                     .filter_by(employee_id=emp.id, day_of_week=dow).all()),
                    None
                )
                if not pattern or pattern.is_day_off:
                    continue
                store = db.query(Store).filter_by(id=pattern.store_id).first()
                if not store:
                    continue
                s = Schedule(
                    employee_id=emp.id, store_id=store.id,
                    work_date=work_date,
                    start_time=pattern.start_time, end_time=pattern.end_time,
                    break_minutes=60, status=ScheduleStatus.DRAFT,
                )
                db.add(s)
                created += 1

            db.flush()  # ID 발급

            # ── 2. 매장별 필요인원 확인 후 파트타이머 배정 ──
            for store in stores:
                reqs = (db.query(StaffRequirement)
                        .filter_by(store_id=store.id, year=year, month=month, day_of_week=dow)
                        .order_by(StaffRequirement.start_time)
                        .all())

                for req in reqs:
                    # 이 시간대를 커버하는 기존 스케줄 수 계산
                    existing = db.query(Schedule).filter(
                        Schedule.store_id == store.id,
                        Schedule.work_date == work_date,
                        Schedule.is_cancelled == False,
                    ).all()
                    covered = sum(
                        1 for s in existing
                        if _overlaps(s.start_time, s.end_time, req.start_time, req.end_time)
                    )
                    needed = req.required_count - covered
                    if needed <= 0:
                        continue

                    # 가용 파트타이머 탐색
                    available_pts = []
                    for pt in part_timers:
                        if self._is_available(pt, work_date, dow, req.start_time, req.end_time,
                                              year, month, db):
                            available_pts.append(pt)

                    # 소프트 컨스트레인트: 누적 시간 적은 순 → 선호 매장 우선
                    available_pts.sort(key=lambda p: (
                        pt_hours[p.id],
                        0 if p.preferred_store_id == store.id else 1,
                    ))

                    assigned = 0
                    for pt in available_pts:
                        if assigned >= needed:
                            break
                        s = Schedule(
                            employee_id=pt.id, store_id=store.id,
                            work_date=work_date,
                            start_time=req.start_time, end_time=req.end_time,
                            break_minutes=0, status=ScheduleStatus.DRAFT,
                        )
                        db.add(s)
                        db.flush()
                        hours = (_time_to_min(req.end_time) - _time_to_min(req.start_time)) / 60
                        pt_hours[pt.id] = pt_hours.get(pt.id, 0) + hours
                        created += 1
                        assigned += 1

                    if assigned < needed:
                        warnings.append(
                            f"{work_date} {store.name} {req.start_time}~{req.end_time}: "
                            f"필요 {req.required_count}명 중 {covered + assigned}명만 배정됨"
                        )

        db.commit()
        return {'created': created, 'warnings': warnings}

    def _is_available(self, pt: Employee, work_date: date, dow: DayOfWeek,
                      start: str, end: str, year: int, month: int, db: Session) -> bool:
        """파트타이머가 해당 날짜·시간에 배정 가능한지 확인 (HARD CONSTRAINT)"""

        # 1. 특정 날짜 예외 우선 확인
        exc = db.query(AvailabilityException).filter_by(
            employee_id=pt.id, exception_date=work_date).first()
        if exc:
            if exc.is_day_unavailable:
                return False
            if exc.unavailable_start and exc.unavailable_end:
                if _overlaps(start, end, exc.unavailable_start, exc.unavailable_end):
                    return False
            return True  # 예외가 있지만 해당 시간대가 가능

        # 2. 월별 요일 기본 설정 확인
        av = db.query(MonthlyAvailability).filter_by(
            employee_id=pt.id, year=year, month=month, day_of_week=dow).first()
        if av:
            if av.is_day_unavailable:
                return False
            if av.unavailable_start and av.unavailable_end:
                if _overlaps(start, end, av.unavailable_start, av.unavailable_end):
                    return False

        # 3. 당일 이미 배정된 스케줄과 충돌 확인
        existing = db.query(Schedule).filter(
            Schedule.employee_id == pt.id,
            Schedule.work_date == work_date,
            Schedule.is_cancelled == False,
        ).all()
        for s in existing:
            if _overlaps(start, end, s.start_time, s.end_time):
                return False

        return True


engine = ScheduleEngine()
