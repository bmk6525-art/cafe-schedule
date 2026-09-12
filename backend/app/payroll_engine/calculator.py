"""
급여 계산 엔진 — 법률 기준은 설정값으로 분리

주휴수당 기준:
  - 1주 소정근로시간 15시간 이상 시 발생
  - 주휴수당 = (1주 근로시간 / 40) * 8 * 시급
  - 단, 5인 미만 사업장 등 실제 적용은 관리자 확인 필요
"""

from datetime import date, timedelta
from collections import defaultdict
from sqlalchemy.orm import Session

from app.models.models import Schedule, ActualWork, Employee, EmployeeType, MonthlyPayroll, WeeklyPayroll, Store
from app.core.config import settings


def _time_to_min(t: str) -> int:
    h, m = map(int, t.split(':'))
    return h * 60 + m


def _get_paid_minutes(start: str, end: str, break_min: int) -> int:
    return max(0, _time_to_min(end) - _time_to_min(start) - break_min)


def calculate_monthly_payroll(year: int, month: int, employee_id: int, db: Session) -> dict:
    """
    파트타이머 월별 급여 계산
    실제 근무시간이 있으면 실제 기준, 없으면 계획 기준으로 계산
    """
    emp = db.query(Employee).filter_by(id=employee_id).first()
    if not emp:
        return {}

    start_date = date(year, month, 1)
    end_date = date(year + (1 if month == 12 else 0), 1 if month == 12 else month + 1, 1)

    _DOW_KO = ['월', '화', '수', '목', '금', '토', '일']

    schedules = db.query(Schedule).filter(
        Schedule.employee_id == employee_id,
        Schedule.work_date >= start_date,
        Schedule.work_date < end_date,
        Schedule.is_cancelled == False,
    ).order_by(Schedule.work_date).all()

    weekly_hours: dict[int, float] = defaultdict(float)
    total_minutes = 0
    daily_details = []

    for s in schedules:
        actual = db.query(ActualWork).filter_by(schedule_id=s.id).first()
        if actual and actual.is_absent:
            continue
        if actual and actual.actual_start and actual.actual_end:
            start = actual.actual_start
            end = actual.actual_end
            paid_min = _get_paid_minutes(start, end, actual.actual_break_minutes)
        else:
            start = s.start_time
            end = s.end_time
            paid_min = _get_paid_minutes(start, end, s.break_minutes)

        hours = round(paid_min / 60, 1)
        week_num = (s.work_date.day - 1) // 7 + 1
        weekly_hours[week_num] += hours
        total_minutes += paid_min

        store = db.query(Store).filter_by(id=s.store_id).first() if s.store_id else None
        store_name = store.name if store else ''

        daily_details.append({
            'date': s.work_date.isoformat(),
            'day_of_week': _DOW_KO[s.work_date.weekday()],
            'start_time': start[:5],
            'end_time': end[:5],
            'hours': hours,
            'store_name': store_name,
            'is_actual': bool(actual and actual.actual_start),
        })

    # 주휴수당 계산
    total_holiday_pay = 0
    weekly_details = []
    threshold = settings.WEEKLY_HOLIDAY_PAY_THRESHOLD

    for week_num in sorted(weekly_hours.keys()):
        wh = weekly_hours[week_num]
        eligible = wh >= threshold
        holiday_pay = round((wh / 5) * emp.hourly_wage) if eligible else 0
        total_holiday_pay += holiday_pay
        weekly_details.append({
            'week_num': week_num,
            'total_hours': round(wh, 2),
            'is_holiday_pay_eligible': eligible,
            'holiday_pay_amount': holiday_pay,
        })

    total_hours = round(total_minutes / 60, 2)
    base_pay = round(total_hours * emp.hourly_wage)
    total_pay = base_pay + total_holiday_pay

    return {
        'employee_id': employee_id,
        'employee_name': emp.name,
        'year': year,
        'month': month,
        'hourly_wage': emp.hourly_wage,
        'total_hours': total_hours,
        'base_pay': base_pay,
        'holiday_pay': total_holiday_pay,
        'total_pay': total_pay,
        'daily_details': daily_details,
        'weekly_details': weekly_details,
    }


def calculate_all_payroll(year: int, month: int, db: Session) -> list:
    """해당 월 전체 파트타이머 급여 계산"""
    part_timers = db.query(Employee).filter_by(
        employee_type=EmployeeType.PART_TIMER, is_active=True
    ).all()
    return [calculate_monthly_payroll(year, month, pt.id, db) for pt in part_timers]
