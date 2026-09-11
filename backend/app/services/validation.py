"""
스케줄 검증 서비스 — HARD CONSTRAINT 위반 감지
"""

from datetime import date
from collections import defaultdict
from sqlalchemy.orm import Session
from app.models.models import Schedule, Employee, Store, EmployeeType


def _time_to_min(t: str) -> int:
    h, m = map(int, t.split(':'))
    return h * 60 + m


def _overlaps(s1, e1, s2, e2):
    return _time_to_min(s1) < _time_to_min(e2) and _time_to_min(s2) < _time_to_min(e1)


def validate_month(year: int, month: int, db: Session) -> list[dict]:
    """
    해당 월의 모든 스케줄에서 HARD CONSTRAINT 위반을 찾아 반환
    """
    start = date(year, month, 1)
    end = date(year + (1 if month == 12 else 0), 1 if month == 12 else month + 1, 1)

    schedules = db.query(Schedule).filter(
        Schedule.work_date >= start,
        Schedule.work_date < end,
        Schedule.is_cancelled == False,
    ).all()

    employees = {e.id: e for e in db.query(Employee).all()}
    stores = {s.id: s for s in db.query(Store).all()}

    issues = []

    # 직원별 날짜별로 그룹핑
    by_emp_date = defaultdict(list)
    by_emp_week = defaultdict(list)  # (emp_id, week_num) → schedules

    for s in schedules:
        emp = employees.get(s.employee_id)
        store = stores.get(s.store_id)
        if not emp or not store:
            continue

        key = (s.employee_id, s.work_date)
        by_emp_date[key].append(s)

        week_num = (s.work_date.day - 1) // 7 + 1
        by_emp_week[(s.employee_id, week_num)].append(s)

        # 1. 매장 운영시간 외 근무 확인
        if _time_to_min(s.start_time) < _time_to_min(store.open_time):
            issues.append({
                'type': 'HARD',
                'code': 'OUTSIDE_HOURS',
                'message': f"{s.work_date} {emp.name} — {store.name} 운영 시작({store.open_time}) 전 근무",
                'schedule_id': s.id,
            })
        if _time_to_min(s.end_time) > _time_to_min(store.close_time):
            issues.append({
                'type': 'HARD',
                'code': 'OUTSIDE_HOURS',
                'message': f"{s.work_date} {emp.name} — {store.name} 운영 종료({store.close_time}) 후 근무",
                'schedule_id': s.id,
            })

    # 2. 동일 직원 당일 중복 근무 또는 다중 매장
    for (emp_id, work_date), day_schedules in by_emp_date.items():
        if len(day_schedules) < 2:
            continue
        emp = employees.get(emp_id)
        for i, s1 in enumerate(day_schedules):
            for s2 in day_schedules[i+1:]:
                if _overlaps(s1.start_time, s1.end_time, s2.start_time, s2.end_time):
                    issues.append({
                        'type': 'HARD',
                        'code': 'OVERLAP',
                        'message': f"{work_date} {emp.name} — 시간 중복 ({s1.start_time}~{s1.end_time} / {s2.start_time}~{s2.end_time})",
                        'schedule_id': s1.id,
                    })
                if s1.store_id != s2.store_id and _overlaps(
                        s1.start_time, s1.end_time, s2.start_time, s2.end_time):
                    issues.append({
                        'type': 'HARD',
                        'code': 'MULTI_STORE',
                        'message': f"{work_date} {emp.name} — 동시간 다중 매장 배정",
                        'schedule_id': s1.id,
                    })

    # 3. 정규직 주 40시간 / 주 5일 확인
    for (emp_id, week_num), week_schedules in by_emp_week.items():
        emp = employees.get(emp_id)
        if not emp or emp.employee_type != EmployeeType.REGULAR:
            continue
        work_days = len(set(s.work_date for s in week_schedules))
        total_min = sum(
            _time_to_min(s.end_time) - _time_to_min(s.start_time) - s.break_minutes
            for s in week_schedules
        )
        if work_days > 5:
            issues.append({
                'type': 'HARD', 'code': 'OVER_DAYS',
                'message': f"{emp.name} {week_num}주차 — 주 5일 초과 ({work_days}일)",
                'schedule_id': None,
            })
        if total_min > 40 * 60:
            issues.append({
                'type': 'HARD', 'code': 'OVER_HOURS',
                'message': f"{emp.name} {week_num}주차 — 주 40시간 초과 ({total_min//60}시간 {total_min%60}분)",
                'schedule_id': None,
            })

    return issues
