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
from sqlalchemy import update as sa_update, insert as sa_insert

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


class _Slot:
    """DB 저장 전 in-memory 겹침 체크용 경량 객체"""
    __slots__ = ('start_time', 'end_time', 'is_cancelled')
    def __init__(self, start_time: str, end_time: str):
        self.start_time = start_time
        self.end_time = end_time
        self.is_cancelled = False


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

        # 파트타이머 가용성: (employee_id, day_of_week) → {'AVAILABLE': row|None, 'UNAVAILABLE': row|None}
        av_map: dict = {}
        if pt_ids:
            for a in db.query(MonthlyAvailability).filter(
                    MonthlyAvailability.employee_id.in_(pt_ids),
                    MonthlyAvailability.year == year,
                    MonthlyAvailability.month == month).all():
                key = (a.employee_id, a.day_of_week)
                if key not in av_map:
                    av_map[key] = {'AVAILABLE': None, 'UNAVAILABLE': None}
                etype = getattr(a, 'entry_type', 'UNAVAILABLE') or 'UNAVAILABLE'
                av_map[key][etype] = a

        # AVAILABLE 레코드가 하나라도 있는 직원 집합
        # → 이 직원들은 AVAILABLE 없는 요일은 불가능으로 처리
        pt_has_available: frozenset = frozenset(
            emp_id for (emp_id, _) in av_map
            if isinstance(av_map[(emp_id, _)], dict)
            and av_map[(emp_id, _)].get('AVAILABLE') is not None
        )

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
        # 파트타이머 하루 1회 근무 제한용 날짜 추적 set
        _pt_assigned_days: dict = {pt.id: set() for pt in part_timers}
        # CONFIRMED / LOCKED 스케줄의 실제 근무시간과 근무일을 동시에 반영
        # (DRAFT는 이미 위에서 is_cancelled=True 처리되어 existing_confirmed에 포함되지 않음)
        _pt_id_set = set(pt_hours.keys())
        for _s in existing_confirmed:
            if _s.employee_id in _pt_id_set:
                pt_hours[_s.employee_id] += (
                    _time_to_min(_s.end_time) - _time_to_min(_s.start_time)
                ) / 60
                _pt_assigned_days[_s.employee_id].add(_s.work_date)
        created = 0
        warnings = []
        days_in_month = calendar.monthrange(year, month)[1]

        inserted_set: set = set()
        for s in existing_confirmed:
            inserted_set.add((s.employee_id, s.store_id, s.work_date, s.start_time, s.end_time))

        # DB INSERT 대신 메모리에 누적 후 한 번에 bulk insert
        new_rows: list = []
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

                slot = _Slot(pattern.start_time, pattern.end_time)
                new_by_store_date[(store.id, work_date)].append(slot)
                new_by_emp_date[(emp.id, work_date)].append(slot)
                new_rows.append({
                    'employee_id': emp.id, 'store_id': store.id,
                    'work_date': work_date,
                    'start_time': pattern.start_time, 'end_time': pattern.end_time,
                    'break_minutes': 60, 'status': ScheduleStatus.DRAFT,
                    'is_cancelled': False, 'memo': None,
                })
                created += 1

            # ── 파트타이머 배정 (희소 슬롯 우선) ──
            # 이 날짜의 모든 (매장, 슬롯) 쌍을 수집한 뒤,
            # 배정 가능 후보자가 가장 적은 슬롯부터 처리하여 전체 충족률을 높인다.
            # 슬롯을 하나 처리할 때마다 후보자 수를 재계산하므로
            # 앞 슬롯 배정이 뒤 슬롯 희소성에 미치는 영향을 정확하게 반영한다.
            _day_slots = []
            for _st in stores:
                for _rq in reqs_map.get((_st.id, dow), []):
                    _day_slots.append((_st, _rq))

            # _pending: _day_slots의 미처리 슬롯 인덱스 목록
            _pending = list(range(len(_day_slots)))

            while _pending:
                _scored = []    # (후보자수, 원본인덱스, needed, covered, 후보자목록, store, req)
                _done_pos = []  # _pending 내 위치 — 이미 covered 된 슬롯

                for _pos, _si in enumerate(_pending):
                    _st, _rq = _day_slots[_si]

                    _asd = (
                        confirmed_by_store_date.get((_st.id, work_date), []) +
                        new_by_store_date.get((_st.id, work_date), [])
                    )
                    _cov = sum(
                        1 for _s in _asd
                        if not getattr(_s, 'is_cancelled', False)
                        and _overlaps(_s.start_time, _s.end_time, _rq.start_time, _rq.end_time)
                    )
                    _ned = _rq.required_count - _cov
                    if _ned <= 0:
                        _done_pos.append(_pos)
                        continue

                    _sh = (_time_to_min(_rq.end_time) - _time_to_min(_rq.start_time)) / 60
                    _cands = []
                    for _pt in part_timers:
                        if work_date in _pt_assigned_days[_pt.id]:
                            continue
                        if _pt.monthly_max_hours is not None:
                            if pt_hours[_pt.id] + _sh > _pt.monthly_max_hours:
                                continue
                        _eds = (
                            confirmed_by_emp_date.get((_pt.id, work_date), []) +
                            new_by_emp_date.get((_pt.id, work_date), [])
                        )
                        if self._is_available_cached(
                                _pt, work_date, dow,
                                _rq.start_time, _rq.end_time,
                                av_map, exc_map, _eds,
                                pt_has_available, _st.id):
                            _cands.append(_pt)

                    _scored.append((len(_cands), _si, _ned, _cov, _cands, _st, _rq))

                # covered 슬롯 제거 (역순 pop으로 인덱스 안정성 유지)
                for _pos in sorted(_done_pos, reverse=True):
                    _pending.pop(_pos)

                if not _scored:
                    break   # 남은 슬롯이 모두 covered

                # 1차: 후보자 수 적은 순 (희소 슬롯 우선)
                # 2차: 원본 슬롯 인덱스 (동점 시 기존 매장·시간 순서 유지)
                _scored.sort(key=lambda x: (x[0], x[1]))
                _, _si_c, _ned_c, _cov_c, _cands_c, _st_c, _rq_c = _scored[0]

                _pending.remove(_si_c)

                # 후보자 정렬: 기존 방식 유지 (누적 근무시간 적은 순 → 선호 매장 우선)
                _cands_c.sort(key=lambda _p: (
                    pt_hours[_p.id],
                    0 if _p.preferred_store_id == _st_c.id else 1,
                ))

                _sh_c = (_time_to_min(_rq_c.end_time) - _time_to_min(_rq_c.start_time)) / 60
                _asgn = 0
                for _pt in _cands_c:
                    if _asgn >= _ned_c:
                        break
                    _dk = (_pt.id, _st_c.id, work_date, _rq_c.start_time, _rq_c.end_time)
                    if _dk in inserted_set:
                        continue
                    inserted_set.add(_dk)

                    _slot = _Slot(_rq_c.start_time, _rq_c.end_time)
                    new_by_emp_date[(_pt.id, work_date)].append(_slot)
                    new_by_store_date[(_st_c.id, work_date)].append(_slot)
                    new_rows.append({
                        'employee_id': _pt.id, 'store_id': _st_c.id,
                        'work_date': work_date,
                        'start_time': _rq_c.start_time, 'end_time': _rq_c.end_time,
                        'break_minutes': 0, 'status': ScheduleStatus.DRAFT,
                        'is_cancelled': False, 'memo': None,
                    })
                    pt_hours[_pt.id] += _sh_c
                    _pt_assigned_days[_pt.id].add(work_date)
                    created += 1
                    _asgn += 1

                if _asgn < _ned_c:
                    warnings.append(
                        f"{work_date} {_st_c.name} {_rq_c.start_time}~{_rq_c.end_time}: "
                        f"필요 {_rq_c.required_count}명 중 {_cov_c + _asgn}명만 배정됨"
                    )

        # ── 3. 일괄 INSERT (DB 쓰기 1회) ────────────────────────
        if new_rows:
            db.execute(sa_insert(Schedule), new_rows)
        db.commit()
        return {'created': created, 'warnings': warnings}

    def _is_available_cached(
            self, pt: Employee, work_date: date, dow: DayOfWeek,
            start: str, end: str,
            av_map: dict, exc_map: dict,
            existing_schedules: list,
            pt_has_available: frozenset = frozenset(),
            slot_store_id: int = None) -> bool:
        """
        캐시된 데이터로 가용성 확인 (DB 조회 없음)

        판정 순서:
          1. 특정 날짜 예외 (1순위, 최우선)
          2. AVAILABLE 레코드 — 가능 요일/시간 체크
             - AVAILABLE 레코드 있음 → 시간 범위 확인 (범위 없으면 전체 가능)
             - AVAILABLE 레코드 없고 pt_has_available에 포함 → 이 요일 불가능
             - pt_has_available에 없음 → 하위 호환: 기본 가능
          3. UNAVAILABLE 레코드 — 불가능 시간 체크 (기존 로직 유지)
          4. 이미 배정된 스케줄 충돌 (항상 마지막)

        pt_has_available: AVAILABLE 레코드가 하나라도 있는 직원 ID 집합
          → 가능 요일을 명시한 직원의 경우 AVAILABLE 없는 요일은 불가능
          → 기본값 frozenset() → 기존 테스트 하위 호환 유지
        """
        req_s = _time_to_min(start)
        req_e = _time_to_min(end)

        # ── 1. 특정 날짜 예외 (최우선) ──────────────────────────────
        exc = exc_map.get((pt.id, work_date))
        if exc:
            is_override = getattr(exc, 'is_available_override', False)

            if is_override:
                # '가능' 예외: 이 날은 기본적으로 가능 (요일 설정 무시)
                if exc.unavailable_start and exc.unavailable_end:
                    avail_s = _time_to_min(exc.unavailable_start)
                    avail_e = _time_to_min(exc.unavailable_end)
                    if not (req_s >= avail_s and req_e <= avail_e):
                        return False
                # 요일 설정 건너뜀 → 스케줄 충돌만 확인
                for s in existing_schedules:
                    if getattr(s, 'is_cancelled', False):
                        continue
                    if _overlaps(start, end, s.start_time, s.end_time):
                        return False
                return True

            else:
                # '불가능' 예외
                if exc.is_day_unavailable:
                    return False
                if exc.unavailable_start:
                    # 종료 미입력 → '23:59' (마감까지)
                    exc_end = exc.unavailable_end if exc.unavailable_end else '23:59'
                    if _overlaps(start, end, exc.unavailable_start, exc_end):
                        return False
                    # 예외 레코드가 이 날짜를 명시적으로 정의 → 요일 설정 건너뜀
                    for s in existing_schedules:
                        if getattr(s, 'is_cancelled', False):
                            continue
                        if _overlaps(start, end, s.start_time, s.end_time):
                            return False
                    return True
                # 빈 예외 레코드 → 요일 기본 설정으로 fall-through

        # ── 2. 월별 요일 기본 설정 ──────────────────────────────────
        av_entry = av_map.get((pt.id, dow))  # {'AVAILABLE': row|None, 'UNAVAILABLE': row|None}

        # av_entry가 구 형식(단일 MonthlyAvailability 객체)이면 하위 호환 처리
        if av_entry is not None and not isinstance(av_entry, dict):
            av_entry = {'AVAILABLE': None, 'UNAVAILABLE': av_entry}

        av_avail = (av_entry or {}).get('AVAILABLE')
        av_unavail = (av_entry or {}).get('UNAVAILABLE')

        # 2-a. 가능 요일/시간/매장 체크
        if av_avail is not None:
            # 이 요일에 AVAILABLE 레코드 있음 → 근무 가능 요일
            # 매장 제한 체크: store_id가 지정된 경우 슬롯 매장과 일치해야 함
            av_store = getattr(av_avail, 'store_id', None)
            if av_store is not None and slot_store_id is not None and av_store != slot_store_id:
                return False

            av_start = getattr(av_avail, 'available_start', None)
            av_end = getattr(av_avail, 'available_end', None)
            if av_start:
                # 종료 미입력 → '23:59' (마감까지)
                effective_av_end = av_end if av_end else '23:59'
                avail_s = _time_to_min(av_start)
                avail_e = _time_to_min(effective_av_end)
                if not (req_s >= avail_s and req_e <= avail_e):
                    return False
            # av_start 없음(is_working_day만) → 전체 운영시간 가능
        elif pt.id in pt_has_available:
            # 이 직원은 다른 요일에 AVAILABLE 레코드가 있지만 이 요일에는 없음
            # → 가능 요일이 아님 (불가능)
            return False
        # else: AVAILABLE 레코드 자체가 없는 직원 → 하위 호환: 기본 가능

        # 2-b. 불가능 시간 체크 (UNAVAILABLE 레코드, 기존 로직 유지)
        if av_unavail is not None:
            if av_unavail.is_day_unavailable:
                return False
            if av_unavail.unavailable_start:
                # 종료 미입력 → '23:59' (마감까지)
                effective_unav_end = av_unavail.unavailable_end if av_unavail.unavailable_end else '23:59'
                if _overlaps(start, end, av_unavail.unavailable_start, effective_unav_end):
                    return False

        # ── 3. 이미 배정된 스케줄 충돌 ─────────────────────────────
        for s in existing_schedules:
            if getattr(s, 'is_cancelled', False):
                continue
            if _overlaps(start, end, s.start_time, s.end_time):
                return False

        return True


engine = ScheduleEngine()
