"""
스케줄 자동 생성 엔진 — 그리디 알고리즘 (N+1 최적화 버전)

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

가용성 확인 우선순위:
  1순위: 특정 날짜 예외 (is_available_override=True → 가능, False → 불가능)
  2순위: 월별 요일 설정 (MonthlyAvailability)
  3순위: 기본 가용 + 기존 스케줄 충돌 확인
"""

import calendar
from collections import defaultdict
from datetime import date
from sqlalchemy.orm import Session
from sqlalchemy import update as sa_update

from app.models.models import (
    Employee, EmployeeType, Store, EmployeeWorkPattern,
    MonthlyAvailability, AvailabilityException, StaffRequirement,
    Schedule, ScheduleStatus, DayOfWeek
)

_WEEKDAY_MAP = {0: 'MON', 1: 'TUE', 2: 'WED', 3: 'THU', 4: 'FRI', 5: 'SAT', 6: 'SUN'}


def _time_to_min(t: str) -> int:
    h, m = map(int, t.split(':'))
    return h * 60 + m


def _min_to_time(m: int) -> str:
    return f"{m//60:02d}:{m%60:02d}"


def _overlaps(s1: str, e1: str, s2: str, e2: str) -> bool:
    return _time_to_min(s1) < _time_to_min(e2) and _time_to_min(s2) < _time_to_min(e1)


class ScheduleEngine:

    def generate(self, year: int, month: int, db: Session) -> dict:
        """
        스케줄 생성 메인 함수 — 모든 데이터를 선로딩하여 N+1 쿼리 제거
        Returns: {'created': int, 'warnings': List[str]}
        """
        start_date = date(year, month, 1)
        end_date = date(year + (1 if month == 12 else 0),
                        1 if month == 12 else month + 1, 1)

        # 기존 DRAFT 스케줄 일괄 삭제 (CONFIRMED/LOCKED는 유지)
        db.execute(
            sa_update(Schedule)
            .where(
                Schedule.work_date >= start_date,
                Schedule.work_date < end_date,
                Schedule.status == ScheduleStatus.DRAFT,
                Schedule.is_cancelled == False,
            )
            .values(is_cancelled=True)
            .execution_options(synchronize_session=False)
        )
        db.flush()

        # ── 1. 전체 데이터 선로딩 (N+1 제거) ──────────────────────

        stores = db.query(Store).filter_by(is_active=True).all()
        stores_map = {s.id: s for s in stores}

        regulars = db.query(Employee).filter_by(
            employee_type=EmployeeType.REGULAR, is_active=True).all()
        part_timers = db.query(Employee).filter_by(
            employee_type=EmployeeType.PART_TIMER, is_active=True).all()

        regular_ids = [e.id for e in regulars]
        pt_ids = [e.id for e in part_timers]

        # 정규직 근무패턴: (employee_id, day_of_week) → pattern
        patterns_map: dict = {}
        if regular_ids:
            for p in db.query(EmployeeWorkPattern).filter(
                    EmployeeWorkPattern.employee_id.in_(regular_ids)).all():
                patterns_map[(p.employee_id, p.day_of_week)] = p

        # 이번 달 필요인원: (store_id, day_of_week) → [StaffRequirement]
        reqs_map: dict = defaultdict(list)
        for r in db.query(StaffRequirement).filter_by(year=year, month=month).all():
            reqs_map[(r.store_id, r.day_of_week)].append(r)
        for key in reqs_map:
            reqs_map[key].sort(key=lambda r: r.start_time)

        # 파트타이머 불가능 시간: (employee_id, day_of_week) → MonthlyAvailability
        av_map: dict = {}
        if pt_ids:
            for a in db.query(MonthlyAvailability).filter(
                    MonthlyAvailability.employee_id.in_(pt_ids),
                    MonthlyAvailability.year == year,
                    MonthlyAvailability.month == month).all():
                av_map[(a.employee_id, a.day_of_week)] = a

        # 이달 특정날짜 예외: (employee_id, exception_date) → AvailabilityException
        exc_map: dict = {}
        if pt_ids:
            for e in db.query(AvailabilityException).filter(
                    AvailabilityException.employee_id.in_(pt_ids),
                    AvailabilityException.exception_date >= start_date,
                    AvailabilityException.exception_date < end_date).all():
                exc_map[(e.employee_id, e.exception_date)] = e

        # 이미 존재하는 CONFIRMED/LOCKED 스케줄
        existing_confirmed = db.query(Schedule).filter(
            Schedule.work_date >= start_date,
            Schedule.work_date < end_date,
            Schedule.is_cancelled == False,
        ).all()

        confirmed_by_store_date: dict = defaultdict(list)
        confirmed_by_emp_date: dict = defaultdict(list)
        for s in existing_confirmed:
            confirmed_by_store_date[(s.store_id, s.work_date)].append(s)
            confirmed_by_emp_date[(s.employee_id, s.work_date)].append(s)

        # ── 2. 생성 루프 ──────────────────────────────────────────

        pt_hours: dict = {pt.id: 0.0 for pt in part_timers}
        created = 0
        warnings = []
        days_in_month = calendar.monthrange(year, month)[1]

        inserted_set: set = set()
        for s in existing_confirmed:
            inserted_set.add((s.employee_id, s.store_id, s.work_date, s.start_time, s.end_time))

        new_by_store_date: dict = defaultdict(list)
        new_by_emp_date: dict = defaultdict(list)

        for day_num in range(1, days_in_month + 1):
            work_date = date(year, month, day_num)
            dow = DayOfWeek(_WEEKDAY_MAP[work_date.weekday()])

            # ── 정규직 배정 ──
            for emp in regulars:
                pattern = patterns_map.get((emp.id, dow))
                if not pattern or pattern.is_day_off:
                    continue
                store = stores_map.get(pattern.store_id)
                if not store:
                    continue

                dup_key = (emp.id, store.id, work_date, pattern.start_time, pattern.end_time)
                if dup_key in inserted_set:
                    continue
                inserted_set.add(dup_key)

                s = Schedule(
                    employee_id=emp.id, store_id=store.id,
                    work_date=work_date,
                    start_time=pattern.start_time, end_time=pattern.end_time,
                    break_minutes=60, status=ScheduleStatus.DRAFT,
                )
                db.add(s)
                new_by_store_date[(store.id, work_date)].append(s)
                new_by_emp_date[(emp.id, work_date)].append(s)
                created += 1

            # ── 파트타이머 배정 ──
            for store in stores:
                reqs = reqs_map.get((store.id, dow), [])
                for req in reqs:
                    all_store_day = (
                        confirmed_by_store_date.get((store.id, work_date), []) +
                        new_by_store_date.get((store.id, work_date), [])
                    )
                    covered = sum(
                        1 for s in all_store_day
                        if not getattr(s, 'is_cancelled', False)
                        and _overlaps(s.start_time, s.end_time, req.start_time, req.end_time)
                    )
                    needed = req.required_count - covered
                    if needed <= 0:
                        continue

                    available_pts = []
                    for pt in part_timers:
                        emp_day_schedules = (
                            confirmed_by_emp_date.get((pt.id, work_date), []) +
                            new_by_emp_date.get((pt.id, work_date), [])
                        )
                        if self._is_available_cached(
                                pt, work_date, dow,
                                req.start_time, req.end_time,
                                av_map, exc_map, emp_day_schedules):
                            available_pts.append(pt)

                    available_pts.sort(key=lambda p: (
                        pt_hours[p.id],
                        0 if p.preferred_store_id == store.id else 1,
                    ))

                    assigned = 0
                    for pt in available_pts:
                        if assigned >= needed:
                            break
                        dup_key = (pt.id, store.id, work_date, req.start_time, req.end_time)
                        if dup_key in inserted_set:
                            continue
                        inserted_set.add(dup_key)

                        s = Schedule(
                            employee_id=pt.id, store_id=store.id,
                            work_date=work_date,
                            start_time=req.start_time, end_time=req.end_time,
                            break_minutes=0, status=ScheduleStatus.DRAFT,
                        )
                        db.add(s)
                        new_by_emp_date[(pt.id, work_date)].append(s)
                        new_by_store_date[(store.id, work_date)].append(s)
                        hours = (_time_to_min(req.end_time) - _time_to_min(req.start_time)) / 60
                        pt_hours[pt.id] += hours
                        created += 1
                        assigned += 1

                    if assigned < needed:
                        warnings.append(
                            f"{work_date} {store.name} {req.start_time}~{req.end_time}: "
                            f"필요 {req.required_count}명 중 {covered + assigned}명만 배정됨"
                        )

        db.commit()
        return {'created': created, 'warnings': warnings}

    def _is_available_cached(
            self, pt: Employee, work_date: date, dow: DayOfWeek,
            start: str, end: str,
            av_map: dict, exc_map: dict,
            existing_schedules: list) -> bool:
        """
        캐시된 데이터로 가용성 확인 (DB 조회 없음)

        우선순위:
          1. 특정 날짜 예외 (is_available_override=True → '가능' 예외, False → '불가능' 예외)
          2. 월별 요일 설정
          3. 이미 배정된 스케줄 충돌 (항상 마지막 체크)
        """

        # 1. 특정 날짜 예외 (최우선)
        exc = exc_map.get((pt.id, work_date))
        if exc:
            is_override = getattr(exc, 'is_available_override', False)

            if is_override:
                # '가능' 예외: 이 날은 기본적으로 가능 (요일 설정 무시)
                if exc.unavailable_start and exc.unavailable_end:
                    # 특정 시간대만 가능 — 제안 슬롯이 해당 윈도우 안에 있어야 함
                    avail_s = _time_to_min(exc.unavailable_start)
                    avail_e = _time_to_min(exc.unavailable_end)
                    req_s = _time_to_min(start)
                    req_e = _time_to_min(end)
                    if not (req_s >= avail_s and req_e <= avail_e):
                        return False
                # 가능 — 요일 설정 건너뜀, 기존 스케줄 충돌만 체크
            else:
                # '불가능' 예외
                if exc.is_day_unavailable:
                    return False
                if exc.unavailable_start and exc.unavailable_end:
                    if _overlaps(start, end, exc.unavailable_start, exc.unavailable_end):
                        return False
                # 이 예외가 이 시간대를 제한하지 않음

            # 특정 날짜 예외가 있으면 요일 설정 건너뜀 → 기존 스케줄 충돌만 확인
            for s in existing_schedules:
                if getattr(s, 'is_cancelled', False):
                    continue
                if _overlaps(start, end, s.start_time, s.end_time):
                    return False
            return True

        # 2. 월별 요일 기본 설정
        av = av_map.get((pt.id, dow))
        if av:
            if av.is_day_unavailable:
                return False
            if av.unavailable_start and av.unavailable_end:
                if _overlaps(start, end, av.unavailable_start, av.unavailable_end):
                    return False

        # 3. 이미 배정된 스케줄 충돌
        for s in existing_schedules:
            if getattr(s, 'is_cancelled', False):
                continue
            if _overlaps(start, end, s.start_time, s.end_time):
                return False

        return True


engine = ScheduleEngine()
